"""Plan and publish a bounded preview from one causal text/grid/graph snapshot."""

import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import resource
import signal
import sqlite3
import sys
import time

import numpy as np

from preview_frontier_search import FRONTIER_POLICY, render_frontiers, select_frontier
from preview_search_goal import Grid, POLICY as GOAL_POLICY, render_overlay, select_goal
from preview_search_route import plan_route
from publish_search_preview import publish
from scene_memory import canonical


GRID_POLICY = {'topic': '/map', 'max_cells': 65536,
               'encoding': 'Axis-aligned map-frame ROS int8 trinary occupancy, unchanged row order'}
POLICY = {'max_evidence_age_s': 10.,
          'revision': 'Latest received graph and occupancy must have identical source stamps',
          'start': 'Current mapped camera_link projection or explicitly supplied simulated x/y',
          'selection': 'Shortest reachable object route, then object ID; otherwise existing frontier policy'}


def grid_from_event(payload):
    width, height = payload['width'], payload['height']
    cells = np.asarray(payload['cells'])
    position = np.asarray(payload['origin_position_m'], dtype=float)
    rotation = np.asarray(payload['origin_quaternion_xyzw'], dtype=float)
    resolution = payload['resolution_m']
    if (type(width) is not int or type(height) is not int or min(width, height) <= 0
            or width*height > GRID_POLICY['max_cells'] or cells.shape != (width*height,)
            or cells.dtype.kind not in 'iu' or not np.isin(cells, [-1, 0, 100]).all()
            or payload['frame_id'] != 'map' or position.shape != (3,) or not np.isfinite(position).all()
            or position[2] != 0 or rotation.shape != (4,) or rotation.tolist() != [0, 0, 0, 1]
            or not np.isfinite(resolution) or resolution <= 0):
        raise ValueError('Unsupported or oversized metric trinary occupancy grid')
    cells = cells.astype(np.int8)
    if hashlib.sha256(cells.tobytes()).hexdigest() != payload['cells_sha256']:
        raise ValueError('Occupancy pixels disagree with their source hash')
    return Grid(cells.reshape(height, width), resolution, position[:2])


def occupancy_payload(message):
    position, rotation = message.info.origin.position, message.info.origin.orientation
    cells = np.asarray(message.data, dtype=np.int8)
    payload = {'stamp_ns': message.header.stamp.sec*10**9+message.header.stamp.nanosec,
        'frame_id': message.header.frame_id, 'width': message.info.width, 'height': message.info.height,
        'resolution_m': message.info.resolution, 'origin_position_m': [position.x, position.y, position.z],
        'origin_quaternion_xyzw': [rotation.x, rotation.y, rotation.z, rotation.w],
        'cells': cells.tolist(), 'cells_sha256': hashlib.sha256(cells.tobytes()).hexdigest()}
    grid_from_event(payload)
    return payload


def plan_snapshot(query, phrase, simulated_xy=None, *, now_ns=None):
    now_ns = time.monotonic_ns() if now_ns is None else now_ns
    evidence, snapshot = query['planning_evidence'], query['snapshot']
    semantic = query['semantic']
    result = {'search_status': 'REFUSED', 'branch': None, 'selection': None, 'start': None,
        'query_label': phrase, 'snapshot': snapshot, 'dry_run': True, 'motion_executed': False,
        'map_frame': 'map', 'coordinate_unit': 'meter', 'outcomes': [],
        'policy': POLICY, 'goal_policy': GOAL_POLICY, 'frontier_policy': FRONTIER_POLICY,
        'semantic_selection': {k: semantic[k] for k in ('status', 'selected_object_ids', 'selection_policy')},
        'decision_monotonic_ns': now_ns,
        'limitation': 'Recorded-data snapshot preview. Camera projections and simulated starts are not robot localization. No physical traversal, identity or real-time acceptance.'}

    def refuse(reason):
        return {**result, 'reason': reason}

    visual_ids = semantic.get('unlocalized', {}).get('selected_observation_ids', [])
    if visual_ids:
        result['unlocalized_selection'] = {'selected_observation_ids': visual_ids,
            'planning_status': 'REFUSED', 'reason': 'unlocalized_visual_evidence'}
    review = semantic.get('identity_review')
    if review is not None:
        result['identity_review'] = review
        if review['session_id'] != snapshot['session_id'] or review['query_text'] != phrase:
            return refuse('identity_feedback_scope_mismatch')
    graph, occupancy, mapping = (evidence[k] for k in ('graph', 'occupancy', 'mapping'))
    if evidence['session_id'] != snapshot['session_id'] or evidence['grid_policy'] != GRID_POLICY:
        return refuse('incompatible_snapshot_or_grid_policy')
    if graph is None:
        return refuse('missing_graph')
    if occupancy is None:
        return refuse('missing_occupancy')
    if (graph['event_seq'] != snapshot['graph_seq'] or
            hashlib.sha256(canonical(graph['payload']).encode()).hexdigest() != snapshot['graph_sha256']):
        return refuse('graph_identity_mismatch')
    records = [graph, occupancy]+([mapping] if mapping else [])
    if any(not 0 < row['event_seq'] <= snapshot['event_seq'] or
           not 0 <= row['available_elapsed_s'] <= snapshot['available_elapsed_s'] for row in records):
        return refuse('evidence_outside_query_prefix')
    stamp = graph['payload']['stamp_ns']
    if occupancy['payload']['stamp_ns'] != stamp:
        return refuse('grid_graph_stamp_mismatch')
    if mapping is None or mapping['payload']['stamp_ns'] != stamp:
        return refuse('missing_current_mapping')
    # Both the source-time lag and wall-time age matter on a slow/pauseable replay.
    source_age = ((evidence['latest_source_stamp_ns']-stamp)/1e9
                  if evidence['latest_source_stamp_ns'] is not None else 0.)
    available_ns = [evidence['origin_monotonic_ns']+int(row['available_elapsed_s']*1e9) for row in records]
    age = (now_ns-min(available_ns))/1e9
    result['evidence_age_s'] = age
    if (max(available_ns) > query['read_started_monotonic_ns'] or now_ns < query['read_started_monotonic_ns']
            or age < 0 or age > POLICY['max_evidence_age_s'] or source_age > POLICY['max_evidence_age_s']):
        return refuse('stale_or_future_map_evidence')
    if review is not None and set(review['blocked_object_ids']) & set(semantic['selected_object_ids']):
        return refuse('selected_identity_rejected')
    grid = grid_from_event(occupancy['payload'])
    result['occupancy'] = {k: v for k, v in occupancy.items() if k != 'payload'}
    result['occupancy'].update({k: v for k, v in occupancy['payload'].items() if k != 'cells'})
    result['valid_until_monotonic_ns'] = min(available_ns)+int(POLICY['max_evidence_age_s']*1e9)
    node = mapping['payload']['node_id']
    poses = [pose for pose in graph['payload']['poses'] if pose['node_id'] == node]
    if len(poses) != 1:
        return refuse('current_start_node_missing_from_graph')
    if simulated_xy is None:
        start = {'kind': 'recorded_camera_link_projection', 'map_xy_m': poses[0]['position_m'][:2],
                 'node_id': node, 'source_stamp_ns': stamp, 'mapping_event_seq': mapping['event_seq'],
                 'provenance': 'Current graph camera_link x/y projection; not a robot-base pose'}
    else:
        grid.cell_xy(simulated_xy)
        start = {'kind': 'simulated_grid_fixture', 'map_xy_m': list(simulated_xy),
                 'provenance': 'Explicit test coordinates in this snapshot, not measured localization'}
    result['start'] = start
    ids = semantic['selected_object_ids']
    objects = [obj for obj in query['objects'] if obj['object_id'] in ids]
    if {obj['object_id'] for obj in objects} != set(ids):
        return refuse('semantic_object_missing_from_snapshot')
    if not ids and visual_ids:
        return refuse('unlocalized_visual_evidence')
    clearance = grid.clearance()
    chosen = []
    for obj in objects:
        goal, _ = select_goal(grid, obj['map_point_m'], clearance)
        route = (plan_route(grid, start['map_xy_m'], goal['goal']['map_xy_m'], clearance)
                 if goal['goal'] else {'status': 'NO_GOAL', 'reason': goal['reason'], 'path_map_xy_m': []})
        row = {'object_id': obj['object_id'], 'goal': goal['goal'], 'goal_checks': goal, 'route': route}
        result['outcomes'].append(row)
        if route['status'] == 'ROUTE_READY':
            chosen.append(row)
    if any(row['goal'] for row in result['outcomes']):
        result.update(branch='object_route', search_status='ROUTE_READY' if chosen else 'NO_ROUTE')
        if chosen:
            row = min(chosen, key=lambda r: (r['route']['length_m'], r['object_id']))
            result['selection'] = {k: row[k] for k in ('object_id', 'goal', 'route')}
    else:
        exploration = select_frontier(grid, start['map_xy_m'], clearance)
        result.update(branch='frontier', search_status=exploration['status'], exploration=exploration)
        if exploration['status'] == 'EXPLORATION_READY':
            result['selection'] = {'object_id': None, 'goal': exploration['goal'], 'route': exploration['route']}
    return result


def run(database, model, phrase, output, simulated_xy=None, ros_preview=False, *, merge_duplicates=False,
        encoder=None, identity_feedback=None):
    from online_semantic_memory import query_text
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'motion_executed': False}
    started = time.monotonic()
    try:
        query = query_text(database, model, phrase, output/'query', planning=True,
                           merge_duplicates=merge_duplicates, encoder=encoder, identity_feedback=identity_feedback)
        decision = plan_snapshot(query, phrase, simulated_xy)
        report['decision'] = decision
        if ros_preview:
            report['publication'] = {'status': 'INCOMPLETE'}
            publish(decision, 1, 5, report['publication'])
        # Render after publication so plotting/import latency cannot age a goal.
        if decision['branch'] in ('frontier', 'object_route'):
            grid = grid_from_event(query['planning_evidence']['occupancy']['payload'])
            if decision['branch'] == 'frontier':
                render_frontiers(grid, {**decision, 'status': decision['search_status']}, output/'preview.png')
            else:
                row = next((r for r in decision['outcomes'] if decision['selection'] and
                            r['object_id'] == decision['selection']['object_id']), decision['outcomes'][0])
                obj = next(o for o in query['objects'] if o['object_id'] == row['object_id'])
                _, eligible = select_goal(grid, obj['map_point_m'], grid.clearance())
                render_overlay(grid, phrase, obj, row['goal_checks'], eligible, output/'preview.png',
                               route={**row['route'], 'start': decision['start']})
        report['status'] = 'ONLINE_SEARCH_COMPLETE'
    except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'search.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


SESSION_LIMITS = {'requests': 32, 'request_bytes': 4096, 'initialization_s': 60,
                  'idle_s': 60, 'response_s': 45}


def run_session(database, model, output, max_requests, *, request_stream=None, merge_duplicates=False,
                identity_feedback=None):
    """Bounded main-thread JSON-lines caller; owns one encoder and never publishes ROS commands."""
    from online_semantic_memory import load_text_encoder
    if type(max_requests) is not int or not 1 <= max_requests <= SESSION_LIMITS['requests']:
        raise ValueError('Session request limit must be between 1 and 32')
    output.mkdir(parents=True, exist_ok=False)
    request_stream = sys.stdin.buffer if request_stream is None else request_stream
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'requests': [], 'limits': dict(SESSION_LIMITS),
              'max_requests': max_requests, 'motion_executed': False, 'ros_publication': False}
    encoder = None

    def timeout(signum, frame):
        raise TimeoutError('Bounded query session exceeded its current stage deadline')

    previous = signal.signal(signal.SIGALRM, timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL, SESSION_LIMITS['initialization_s'])
        with redirect_stdout(sys.stderr):
            encoder = load_text_encoder(database, model)
        report.update(encoder=encoder.identity, load_ms=encoder.load_ms,
                      initialization_ms=(time.monotonic()-started)*1000)
        print(json.dumps({'status': 'READY', 'initialization_ms': report['initialization_ms'],
                          'load_ms': encoder.load_ms}), flush=True)
        for index in range(1, max_requests+1):
            signal.setitimer(signal.ITIMER_REAL, SESSION_LIMITS['idle_s'])
            line = request_stream.readline(SESSION_LIMITS['request_bytes']+1)
            if not line:
                report['stop_reason'] = 'input_closed'
                break
            if len(line) > SESSION_LIMITS['request_bytes'] or not line.endswith(b'\n'):
                raise ValueError('Request must be a newline-terminated JSON object of at most 4096 bytes')
            request = json.loads(line)
            if not isinstance(request, dict) or set(request) != {'text'}:
                raise ValueError('Request must contain exactly one text field')
            signal.setitimer(signal.ITIMER_REAL, SESSION_LIMITS['response_s'])
            name = f'request_{index:03d}'
            before = time.monotonic_ns()
            with redirect_stdout(sys.stderr):
                result = run(database, model, request['text'], output/name,
                             merge_duplicates=merge_duplicates, encoder=encoder, identity_feedback=identity_feedback)
            entry = {'text': request['text'], 'output': name,
                     'before_monotonic_ns': before, 'after_monotonic_ns': time.monotonic_ns(),
                     'status': result['status'], 'search_status': result['decision']['search_status'],
                     'snapshot': result['decision']['snapshot']}
            report['requests'].append(entry)
            print(json.dumps(entry, allow_nan=False), flush=True)
        else:
            report['stop_reason'] = 'request_limit'
        report['status'] = 'SESSION_COMPLETE'
    except (ValueError, OSError, KeyError, RuntimeError, sqlite3.Error, KeyboardInterrupt) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        report['duration_ms'] = (time.monotonic()-started)*1000
        report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if encoder is not None:
            report['peak_cuda_allocated_bytes'] = encoder.torch.cuda.max_memory_allocated()
            report['peak_cuda_reserved_bytes'] = encoder.torch.cuda.max_memory_reserved()
        (output/'session.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'model', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--text')
    mode.add_argument('--session-requests', type=int, help='Read up to 32 JSON-lines text requests from stdin with one loaded encoder')
    parser.add_argument('--simulated-start-xy', type=float, nargs=2, metavar=('X_M', 'Y_M'))
    parser.add_argument('--publish-preview', action='store_true')
    parser.add_argument('--merge-duplicate-tracks', action='store_true', help='Require repeated shared-frame RGB-D evidence before merging tracks')
    parser.add_argument('--identity-feedback', type=Path, help='Exact-phrase/session/source-crop operator feedback JSON; rejected supports veto selected localized targets')
    args = parser.parse_args()
    feedback = json.loads(args.identity_feedback.read_text()) if args.identity_feedback is not None else None
    if args.identity_feedback is not None and not isinstance(feedback, dict):
        parser.error('Identity feedback must be a JSON object')
    if args.session_requests is not None:
        if args.publish_preview or args.simulated_start_xy is not None:
            parser.error('Session mode uses recorded starts and does not publish ROS previews')
        run_session(args.db.resolve(), args.model.resolve(), args.output.resolve(), args.session_requests,
                    merge_duplicates=args.merge_duplicate_tracks, identity_feedback=feedback)
        sys.exit(0)
    report = run(args.db.resolve(), args.model.resolve(), args.text, args.output.resolve(),
                 args.simulated_start_xy, args.publish_preview, merge_duplicates=args.merge_duplicate_tracks,
                 identity_feedback=feedback)
    print(json.dumps({'status': report['status'], 'decision': report['decision']['search_status']}))
