"""Persist causal observations/graph revisions and query one consistent online snapshot."""

import argparse
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import queue
import sqlite3
import threading
import time

import numpy as np

from observe_rgbd_objects import DEPTH_POLICY, INFERENCE
from rgbd_geometry import map_from_camera, match_source_stamp
from scene_memory import SCHEMA, canonical, query_contents, rebuild_objects, require_hash
from online_semantic_memory import rank_snapshot, validate_semantic
from online_search_preview import GRID_POLICY, grid_from_event


POLICY = {'queue_capacity': 16, 'max_events': 20000, 'max_payload_bytes': 524288,
          'max_graph_nodes': 600, 'sqlite_timeout_s': .5,
          'geometry': 'Reproject original camera points with the latest received graph and fixed camera extrinsic',
          'selection': 'Mapped keyframes still present in that graph, with an originally accepted source-time pose',
          'identity': 'Provisional object IDs belong only to the named event-prefix/graph snapshot'}
# Live recording/query startup exposed consecutive 5.79 s and 2.91 s fsync stalls.
# Drain existing bursts in bounded FULL transactions; never wait to fill a batch.
LIVE_POLICY = {**POLICY, 'queue_capacity': 512, 'commit_batch_capacity': 16}
TABLES = {'metadata', 'events'}


def rigid(matrix):
    value = np.asarray(matrix, dtype=float)
    if (value.shape != (4, 4) or not np.isfinite(value).all()
            or not np.allclose(value[3], [0, 0, 0, 1], atol=1e-8, rtol=0)
            or not np.allclose(value[:3, :3].T@value[:3, :3], np.eye(3), atol=2e-6, rtol=0)
            or not np.isclose(np.linalg.det(value[:3, :3]), 1, atol=2e-6, rtol=0)):
        raise ValueError('Expected a finite rigid transform')
    return value


def positive_int(value):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError('Expected a positive integer timestamp or node ID')


def validate_event(kind, payload, elapsed):
    if not np.isfinite(elapsed) or elapsed < 0:
        raise ValueError('Invalid event availability time')
    canonical(payload)
    if kind == 'occupancy':
        positive_int(payload['stamp_ns'])
        grid_from_event(payload)
    elif kind == 'semantic':
        positive_int(payload['node_id'])
    elif kind == 'mapping':
        positive_int(payload['node_id'])
        positive_int(payload['stamp_ns'])
    elif kind == 'graph':
        positive_int(payload['stamp_ns'])
        poses = payload['poses']
        if len(poses) > POLICY['max_graph_nodes'] or len({p['node_id'] for p in poses}) != len(poses):
            raise ValueError('Duplicate or excessive graph nodes')
        for pose in poses:
            positive_int(pose['node_id'])
            map_from_camera(pose['position_m'], pose['quaternion_xyzw'])
        if payload['extrinsic']['status'] == 'ACCEPTED':
            rigid(payload['extrinsic']['camera_link_from_optical'])
        elif payload['extrinsic']['status'] != 'REJECTED' or not payload['extrinsic']['reason']:
            raise ValueError('Invalid graph camera extrinsic evidence')
    elif kind == 'observation':
        stamp = payload['source_stamp_ns']
        for key in ('source_stamp_ns', 'rgb_stamp_ns', 'depth_stamp_ns'):
            positive_int(payload[key])
        if (stamp != max(payload['rgb_stamp_ns'], payload['depth_stamp_ns'])
                or payload['rgb_depth_skew_ns'] != payload['rgb_stamp_ns']-payload['depth_stamp_ns']
                or abs(payload['rgb_depth_skew_ns']) > 5_000_000):
            raise ValueError('Invalid original RGB-D source timestamps')
        for key in ('rgb_pixels_sha256', 'depth_pixels_sha256'):
            require_hash(payload[key])
        if payload['status'] == 'DROPPED':
            if not payload['reason']:
                raise ValueError('Dropped observation needs a reason')
            return
        if payload['status'] != 'PROCESSED':
            raise ValueError('Only finalized observations can enter memory')
        pose = payload['pose']
        times = [payload[key] for key in ('arrived_elapsed_s', 'dispatched_elapsed_s',
                 'prediction_completed_elapsed_s')] + [pose['checked_elapsed_s'], payload['completed_elapsed_s'], elapsed]
        if min(times) < 0 or any(a > b for a, b in zip(times, times[1:])):
            raise ValueError('Observation predates its evidence availability')
        accepted = pose['status'] == 'ACCEPTED'
        if accepted:
            transform = rigid(pose['map_from_camera'])
            odom = pose['odom_evidence']
            if (pose['source_stamp_ns'] != stamp or odom['stamp_ns'] != stamp or odom['lost']
                    or odom['received_elapsed_s'] > pose['checked_elapsed_s']):
                raise ValueError('Accepted pose lacks causal source odometry')
        elif pose['status'] != 'REJECTED' or not pose['reason'] or 'map_from_camera' in pose:
            raise ValueError('Invalid refused pose evidence')
        indices = set()
        for detection in payload['detections']:
            index = detection['detection_index']
            box = np.asarray(detection['box_xyxy'], dtype=float)
            if (type(index) is not int or index < 0 or index in indices or box.shape != (4,)
                    or np.any(box[2:] <= box[:2]) or not detection['label'].strip()
                    or not 0 <= detection['detection_confidence'] <= 1):
                raise ValueError('Invalid detection identity, label, box or confidence')
            indices.add(index)
            depth = detection['depth']
            if depth['status'] == 'ACCEPTED':
                camera = np.asarray(depth['camera_point_m'])
                if camera.shape != (3,) or camera[2] != depth['depth_m'] or not 0 < camera[2] < DEPTH_POLICY['max_depth_m']:
                    raise ValueError('Invalid metric camera point')
                if accepted:
                    if not np.allclose((transform@np.r_[camera, 1])[:3], detection['map_point_m'], atol=1e-6, rtol=0):
                        raise ValueError('Original online point disagrees with its source pose')
                elif 'map_point_m' in detection:
                    raise ValueError('Refused pose cannot supply a map point')
            elif (depth['status'] != 'REJECTED' or not depth['reason']
                  or 'camera_point_m' in depth or 'map_point_m' in detection):
                raise ValueError('Invalid depth rejection')
    else:
        raise ValueError('Unknown online-memory event kind')


class OnlineMemoryWriter:
    """One bounded queue and SQLite-owning thread; overflow/failure aborts the trial."""
    def __init__(self, database, context):
        if context['inference'] != INFERENCE or context['depth_policy'] != DEPTH_POLICY:
            raise ValueError('Online memory requires the measured perception policy')
        sources = [key for key in ('reference_sha256', 'live_config_sha256') if key in context]
        if len(sources) != 1:
            raise ValueError('Require exactly one replay reference or live camera configuration hash')
        require_hash(context[sources[0]])
        require_hash(context['model_sha256'])
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.database.touch(exist_ok=False)
        policy = LIVE_POLICY if 'live_config_sha256' in context else POLICY
        self.context = {**context, 'kind': 'causal_rgbd_journal', 'schema_version': 1, 'policy': policy}
        self.queue = queue.Queue(maxsize=policy['queue_capacity'])
        self.error = None
        self.closed = False
        self.ready = threading.Event()
        self.stats = {'events_committed': 0, 'queue_peak': 0, 'write_ms': [], 'committed_batch_sizes': []}
        self.thread = threading.Thread(target=self._run, name='online_memory_writer')
        self.thread.start()
        if not self.ready.wait(5):
            raise TimeoutError('Online memory initialization exceeded five seconds')
        self.check()

    def check(self):
        if self.error is not None:
            raise RuntimeError('Online memory writer failed') from self.error

    def submit(self, kind, payload, elapsed):
        self.check()
        if self.closed:
            raise RuntimeError('Online memory writer is closed')
        serialized = canonical(payload)
        if len(serialized.encode()) > POLICY['max_payload_bytes']:
            raise ValueError('Online memory event exceeds bounded payload size')
        try:
            self.queue.put_nowait((kind, serialized, elapsed))
        except queue.Full as error:
            raise RuntimeError('Online memory queue full; no silent event loss') from error
        self.stats['queue_peak'] = max(self.stats['queue_peak'], self.queue.qsize())

    def _run(self):
        try:
            with closing(sqlite3.connect(self.database, timeout=POLICY['sqlite_timeout_s'])) as connection:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.execute('PRAGMA synchronous=FULL')
                with connection:
                    connection.execute('CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), context_json TEXT NOT NULL)')
                    connection.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY, available_elapsed_s REAL NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL)')
                    connection.execute('CREATE UNIQUE INDEX original_source ON events(json_extract(payload_json, "$.source_stamp_ns")) WHERE kind="observation"')
                    connection.execute('CREATE UNIQUE INDEX mapping_node ON events(json_extract(payload_json, "$.node_id")) WHERE kind="mapping"')
                    connection.execute('CREATE UNIQUE INDEX semantic_node ON events(json_extract(payload_json, "$.node_id")) WHERE kind="semantic"')
                    connection.execute('PRAGMA user_version=1')
                    connection.execute('INSERT INTO metadata VALUES (1, ?)', (canonical(self.context),))
                self.ready.set()
                previous = -1.
                extrinsic = None
                while True:
                    try:
                        item = self.queue.get(timeout=.1)
                    except queue.Empty:
                        if self.closed:
                            break
                        continue
                    batch = [item]
                    while len(batch) < self.context['policy'].get('commit_batch_capacity', 1):
                        try:
                            batch.append(self.queue.get_nowait())
                        except queue.Empty:
                            break
                    begin = time.monotonic()
                    with connection:
                        for offset, (kind, serialized, elapsed) in enumerate(batch, 1):
                            payload = json.loads(serialized)
                            validate_event(kind, payload, elapsed)
                            if kind == 'semantic':
                                validate_semantic(connection, self.context, payload, elapsed)
                            if kind == 'occupancy' and self.context.get('grid_policy') != GRID_POLICY:
                                raise ValueError('Occupancy events require the declared grid policy')
                            seq = self.stats['events_committed']+offset
                            if elapsed < previous or seq > POLICY['max_events']:
                                raise ValueError('Regressing availability time or online event limit exceeded')
                            if kind == 'graph' and payload['extrinsic']['status'] == 'ACCEPTED':
                                current = payload['extrinsic']['camera_link_from_optical']
                                if extrinsic is not None and not np.allclose(current, extrinsic, atol=1e-8, rtol=0):
                                    raise ValueError('Camera extrinsic changed; start a new memory session')
                                extrinsic = current
                            connection.execute('INSERT INTO events VALUES (?, ?, ?, ?)',
                                               (seq, elapsed, kind, serialized))
                            previous = elapsed
                    self.stats['events_committed'] += len(batch)
                    self.stats['committed_batch_sizes'].append(len(batch))
                    self.stats['write_ms'].append((time.monotonic()-begin)*1000)
                connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception as error:
            # Propagate thread failures to the caller; no success result or fallback.
            self.error = error
        finally:
            self.ready.set()

    def close(self):
        if not self.closed:
            self.closed = True
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise TimeoutError('Online memory writer did not close within five seconds')
        self.check()


def query_online(database, command='list', label=None, *, text_vector=None, encoder_identity=None, planning=False):
    """Read one committed event prefix, then derive associations in a private SQLite snapshot."""
    started = time.monotonic_ns()
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro', uri=True,
                                timeout=POLICY['sqlite_timeout_s'])) as connection:
        connection.execute('BEGIN')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != TABLES or connection.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('Expected an online observation journal, not frozen scene memory')
        context = json.loads(connection.execute('SELECT context_json FROM metadata WHERE id=1').fetchone()[0])
        # Preserve the actual failed live trials as readable evidence.
        supported = (POLICY, {**POLICY, 'queue_capacity': 128},
                     {**LIVE_POLICY, 'queue_capacity': 128}, LIVE_POLICY) if 'live_config_sha256' in context else (POLICY,)
        if context['kind'] != 'causal_rgbd_journal' or context['policy'] not in supported:
            raise ValueError('Unsupported online memory context/policy')
        events = connection.execute('SELECT seq, available_elapsed_s, kind, payload_json FROM events ORDER BY seq').fetchall()
    if len(events) > POLICY['max_events']:
        raise ValueError('Online memory event limit exceeded')
    sources, mappings, graph, semantic = {}, {}, None, []
    occupancy = None
    for seq, elapsed, kind, serialized in events:
        payload = json.loads(serialized)
        if kind == 'observation':
            sources[payload['source_stamp_ns']] = (seq, payload)
        elif kind == 'mapping':
            mappings[payload['node_id']] = (seq, payload)
        elif kind == 'graph':
            graph = (seq, payload)
        elif kind == 'semantic':
            semantic.append((seq, payload))
        elif kind == 'occupancy':
            occupancy = (seq, elapsed, payload)
    snapshot = {'session_id': context['session_id'], 'event_seq': events[-1][0] if events else 0,
                'available_elapsed_s': events[-1][1] if events else None,
                'graph_seq': graph[0] if graph else None,
                'graph_sha256': hashlib.sha256(canonical(graph[1]).encode()).hexdigest() if graph else None}
    excluded, included = [], []
    with closing(sqlite3.connect(':memory:')) as derived:
        derived.row_factory = sqlite3.Row
        for statement in SCHEMA:
            derived.execute(statement)
        derived.execute('INSERT INTO metadata VALUES (1, ?)', (canonical({**context, 'snapshot': snapshot}),))
        poses = {pose['node_id']: pose for pose in graph[1]['poses']} if graph else {}
        stamps = sorted(sources)
        for node in sorted(set(poses) | set(mappings)):
            reason = None
            source_seq = source = None
            if node not in poses:
                reason = 'not_in_current_graph'
            elif node not in mappings:
                reason = 'mapping_source_not_received'
            else:
                try:
                    stamp = match_source_stamp(mappings[node][1]['stamp_ns'], stamps)
                except ValueError:
                    reason = 'source_observation_not_finalized'
                else:
                    source_seq, source = sources[stamp]
                    if source['status'] == 'DROPPED':
                        reason = 'observation_dropped: '+source['reason']
                    elif source['pose']['status'] != 'ACCEPTED':
                        reason = 'source_pose_rejected: '+source['pose']['reason']
                    elif graph[1]['extrinsic']['status'] != 'ACCEPTED':
                        reason = 'graph_extrinsic_unavailable'
            if reason:
                excluded.append({'node_id': node, 'reason': reason, 'observation_seq': source_seq})
                continue
            pose = poses[node]
            transform = map_from_camera(pose['position_m'], pose['quaternion_xyzw'])@rigid(graph[1]['extrinsic']['camera_link_from_optical'])
            frame = {**copy.deepcopy(source), 'node_id': node, 'observation_seq': source_seq,
                     'mapping_seq': mappings[node][0], 'map_from_camera': transform.tolist()}
            for detection in frame['detections']:
                if detection['depth']['status'] == 'ACCEPTED':
                    detection['original_online_map_point_m'] = detection['map_point_m']
                    detection['map_point_m'] = (transform@np.r_[detection['depth']['camera_point_m'], 1])[:3].tolist()
            derived.execute('INSERT INTO frames VALUES (?, ?, ?)', (node, frame['source_stamp_ns'], canonical(frame)))
            included.append({'node_id': node, 'source_stamp_ns': frame['source_stamp_ns'],
                             'observation_seq': source_seq, 'mapping_seq': mappings[node][0]})
        rebuild_objects(derived)
        result = query_contents(derived, command, label)
        if text_vector is not None:
            if command != 'list' or label is not None:
                raise ValueError('Text retrieval requires the complete geometric snapshot')
            result['semantic'] = rank_snapshot(derived, context, semantic, result, text_vector, encoder_identity)
    if graph is None:
        result['status'] = 'NO_GRAPH'
    result.update(snapshot=snapshot, included_frames=included, excluded_nodes=excluded,
                  observation_events=len(sources), read_started_monotonic_ns=started,
                  query_ms=(time.monotonic_ns()-started)/1e6,
                  limitation='Causal active-graph keyframe snapshot; absent/excluded records do not prove object absence. IDs may change between snapshots. No physical accuracy or navigation acceptance.')
    if planning:
        def evidence(seq, payload):
            return {'event_seq': seq, 'available_elapsed_s': events[seq-1][1], 'payload': payload}
        current = [evidence(seq, payload) for seq, payload in mappings.values()
                   if graph and payload['stamp_ns'] == graph[1]['stamp_ns']]
        result['planning_evidence'] = {'session_id': context['session_id'],
            'origin_monotonic_ns': context['origin_monotonic_ns'], 'grid_policy': context.get('grid_policy'),
            'latest_source_stamp_ns': max(sources) if sources else None,
            'graph': evidence(*graph) if graph else None,
            'occupancy': evidence(occupancy[0], occupancy[2]) if occupancy else None,
            'mapping': current[0] if len(current) == 1 else None}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--command', choices=('list', 'find', 'last_seen'), default='list')
    parser.add_argument('--label')
    args = parser.parse_args()
    if args.command != 'list' and not (args.label and args.label.strip()):
        parser.error('find/last_seen requires a nonempty --label')
    print(json.dumps(query_online(args.db, args.command, args.label), indent=2, allow_nan=False))
