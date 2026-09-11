"""Validate offline grid routes from an explicit camera projection or simulated start."""

import argparse
from collections import deque
import json
from pathlib import Path
import time

import numpy as np

from extract_mapped_rgbd import file_hash
from preview_search_goal import POLICY, load_grid, render_overlay, select_goal
from scene_memory import query


CARDINAL_DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def segment_clearance(grid, blocked_centers, first, last):
    """Exact planar distance from an axis-aligned segment to blocked cell squares."""
    first, last = np.asarray(first, dtype=float), np.asarray(last, dtype=float)
    if np.count_nonzero(first != last) > 1:
        raise ValueError('Route segments must be axis-aligned; diagonal moves are unsupported')
    lower, upper = np.minimum(first, last), np.maximum(first, last)
    map_upper = grid.origin_xy_m+np.array(grid.cells.shape[::-1])*grid.resolution_m
    boundary = float(min(np.min(lower-grid.origin_xy_m), np.min(map_upper-upper)))
    if not len(blocked_centers):
        return max(0, boundary)
    half = grid.resolution_m/2
    gaps = np.maximum(np.maximum(blocked_centers-half-upper, lower-blocked_centers-half), 0)
    return max(0, min(boundary, float(np.linalg.norm(gaps, axis=1).min())))


def plan_route(grid, start_xy, goal_xy, clearance):
    started = time.monotonic()
    result = {'status': 'NO_ROUTE', 'path_cell_xy': [], 'path_map_xy_m': [],
              'length_m': None, 'min_segment_clearance_m': None, 'expanded_cells': 0,
              'movement': 'Four cardinal neighbors; equal edge cost; no diagonal moves or smoothing',
              'start_connector': 'Explicit start to its cell center: x first, then y; every segment checked'}
    rows, cols = np.nonzero(grid.cells != 0)
    blocked = grid.center_xy(np.column_stack((cols, rows)))
    allowed = (grid.cells == 0) & (clearance >= POLICY['clearance_m'])
    try:
        endpoints = []
        for name, point in [('start', start_xy), ('goal', goal_xy)]:
            point = np.asarray(point, dtype=float)
            cell = grid.cell_xy(point)  # Reject malformed/nonfinite coordinates, without coercing to a cell.
            check = {'map_xy_m': point.tolist(), 'cell_xy': [int(v) for v in cell]}
            result[name+'_check'] = check
            reason = None
            if not grid.contains(cell):
                reason = 'outside_grid'
            else:
                x, y = cell
                check.update(cell_state=int(grid.cells[y, x]),
                             cell_center_clearance_lower_bound_m=float(clearance[y, x]),
                             point_clearance_m=segment_clearance(grid, blocked, point, point))
                if grid.cells[y, x] != 0:
                    reason = 'unknown_cell' if grid.cells[y, x] == -1 else 'occupied_cell'
                elif not allowed[y, x] or check['point_clearance_m'] < POLICY['clearance_m']:
                    reason = 'insufficient_clearance'
            if reason:
                result.update(status='INVALID_'+name.upper(), reason=reason)
                return result
            endpoints.append((point, cell))
        (start, start_cell), (goal, goal_cell) = endpoints
        center = grid.center_xy(start_cell)
        if not np.allclose(goal, grid.center_xy(goal_cell), rtol=0, atol=1e-12):
            raise ValueError('Expected the preceding preview goal at its exact cell center')
        connector = [start]
        for point in (np.array([center[0], start[1]]), center):
            if not np.array_equal(connector[-1], point):
                connector.append(point)
        connector_clearances = [segment_clearance(grid, blocked, a, b) for a, b in zip(connector, connector[1:])]
        if connector_clearances and min(connector_clearances) < POLICY['clearance_m']:
            result.update(status='INVALID_START', reason='start_connector_insufficient_clearance')
            return result
        frontier = deque([start_cell])
        parents = {start_cell: None}
        edge_clearances = {}
        while frontier:
            cell = frontier.popleft()
            result['expanded_cells'] += 1
            if cell == goal_cell:
                path = []
                while cell is not None:
                    path.append(cell)
                    cell = parents[cell]
                path.reverse()
                metric = connector+[grid.center_xy(cell) for cell in path[1:]]
                distances = connector_clearances+[edge_clearances[cell] for cell in path[1:]]
                result.update(status='ROUTE_READY', path_cell_xy=[[int(v) for v in cell] for cell in path],
                              path_map_xy_m=[point.tolist() for point in metric],
                              length_m=float(sum(np.linalg.norm(b-a) for a, b in zip(metric, metric[1:]))),
                              min_segment_clearance_m=min(distances) if distances else result['start_check']['point_clearance_m'])
                return result
            x, y = cell
            for dx, dy in CARDINAL_DIRECTIONS:
                neighbor = (x+dx, y+dy)
                if not grid.contains(neighbor) or neighbor in parents or not allowed[neighbor[1], neighbor[0]]:
                    continue
                distance = segment_clearance(grid, blocked, grid.center_xy(cell), grid.center_xy(neighbor))
                if distance >= POLICY['clearance_m']:
                    parents[neighbor] = cell
                    edge_clearances[neighbor] = distance
                    frontier.append(neighbor)
        result['reason'] = 'disconnected_under_route_policy'
        return result
    finally:
        result['planning_ms'] = (time.monotonic()-started)*1000


def load_goal_preview(path, memory, mapping):
    source = json.loads(path.read_text())
    if (source['status'] not in ('PREVIEW_READY', 'NO_GOAL') or source['dry_run'] is not True
            or source['map_frame'] != 'map' or source['coordinate_unit'] != 'meter' or source['policy'] != POLICY):
        raise ValueError('Expected a completed metric preview with the current goal policy')
    if file_hash(memory) != source['memory_sha256']:
        raise ValueError('Memory changed since the goal preview')
    remembered = query(memory, 'find', source['query_label'])
    if (remembered['context'] != source['memory_context'] or remembered['objects'] != source['object_candidates']
            or remembered['status'] != source['query_status']):
        raise ValueError('Goal preview differs from the original memory evidence')
    grid, provenance = load_grid(mapping, remembered['context'])
    if provenance != source['occupancy']:
        raise ValueError('Goal preview differs from the frozen occupancy evidence')
    clearance = grid.clearance()
    if len(source['results']) != len(remembered['objects']):
        raise ValueError('Goal preview dropped or added object candidates')
    for obj, row in zip(remembered['objects'], source['results']):
        expected, _ = select_goal(grid, obj['map_point_m'], clearance)
        if row['object_id'] != obj['object_id'] or any(row.get(key) != value for key, value in expected.items()):
            raise ValueError('Saved goal decision does not reproduce the current map checks')
    status = 'PREVIEW_READY' if any(row['goal'] for row in source['results']) else 'NO_GOAL'
    if source['status'] != status or (not remembered['objects'] and source.get('reason') != 'target_not_in_memory'):
        raise ValueError('Inconsistent saved no-goal outcome')
    return source, grid, clearance


def make_start(mapping, grid, node_id, simulated_xy):
    if (node_id is None) == (simulated_xy is None):
        raise ValueError('Provide exactly one recorded camera node or simulated start')
    if simulated_xy is not None:
        grid.cell_xy(simulated_xy)  # Validate the explicit metric point without snapping it.
        return {'kind': 'simulated_grid_fixture', 'map_xy_m': list(simulated_xy),
                'provenance': 'Explicit CLI test coordinates; not measured localization'}
    path = mapping/'export/room_camera_poses.txt'
    poses = np.loadtxt(path, ndmin=2)
    if poses.shape[1] != 9 or not np.isfinite(poses).all():
        raise ValueError('Expected finite timestamp/translation/quaternion/node-ID camera poses')
    selected = poses[poses[:, 8] == node_id]
    database = json.loads((mapping/'database_check.json').read_text())
    nodes = [row for row in database['nodes'] if row['node_id'] == node_id]
    if len(selected) != 1 or len(nodes) != 1:
        raise ValueError('Expected one verified camera pose and source timestamp for the selected node')
    pose = selected[0]
    if nodes[0]['map_id'] != 0 or abs(pose[0]-nodes[0]['source_stamp_ns']/1e9) > 1e-6:
        raise ValueError('Camera pose does not match the original map/source timestamp')
    return {'kind': 'recorded_camera_projection', 'map_xy_m': pose[1:3].tolist(), 'node_id': node_id,
            'source_stamp_ns': nodes[0]['source_stamp_ns'], 'camera_position_m': pose[1:4].tolist(),
            'camera_quaternion_xyzw': pose[4:8].tolist(), 'export_stamp_s': float(pose[0]),
            'camera_poses_sha256': file_hash(path),
            'provenance': 'Frozen optimized camera translation projected to map x/y; not a robot-base pose or current localization'}


def preview_route(preview_path, memory, mapping, output, node_id=None, simulated_xy=None):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'dry_run': True, 'results': [],
              'limitation': 'Offline planar route under an assumed circular clearance; physical footprint, traversability, target visibility and current localization unverified. No motion commands.'}
    try:
        source_hash = file_hash(preview_path)
        source, grid, clearance = load_goal_preview(preview_path, memory, mapping)
        start = make_start(mapping, grid, node_id, simulated_xy)
        report.update(source_preview_path=str(preview_path), source_preview_sha256=source_hash,
                      source_preview=source, start=start, map_frame='map', coordinate_unit='meter',
                      clearance_m=POLICY['clearance_m'])
        for obj, decision in zip(source['object_candidates'], source['results']):
            if decision['goal'] is None:
                route = {'status': 'NO_GOAL', 'reason': decision['reason'], 'path_map_xy_m': []}
            else:
                route = plan_route(grid, start['map_xy_m'], decision['goal']['map_xy_m'], clearance)
            route.update(object_id=obj['object_id'], start=start, overlay=f'object_{obj["object_id"]}.png')
            _, eligible = select_goal(grid, obj['map_point_m'], clearance)
            render_overlay(grid, source['query_label'], obj, decision, eligible, output/route['overlay'], route=route)
            report['results'].append(route)
        if not source['object_candidates']:
            report.update(reason=source['reason'], overview='overview.png')
            render_overlay(grid, source['query_label'], None, None, None, output/'overview.png',
                           route={'status': 'NO_GOAL', 'start': start, 'path_map_xy_m': []})
        if file_hash(preview_path) != source_hash or file_hash(memory) != source['memory_sha256']:
            raise ValueError('Preview or memory changed during route validation')
        report['status'] = ('NO_GOAL' if source['status'] == 'NO_GOAL' else
                            'ROUTE_READY' if any(row['status'] == 'ROUTE_READY' for row in report['results']) else 'NO_ROUTE')
    except ValueError as error:
        report['error'] = str(error)
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'route.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preview', 'memory', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    start = parser.add_mutually_exclusive_group(required=True)
    start.add_argument('--start-node', type=int, help='Recorded camera node projected to map x/y; not a robot pose')
    start.add_argument('--simulated-start-xy', type=float, nargs=2, metavar=('X_M', 'Y_M'),
                       help='Explicit simulated planning fixture in map meters; not measured localization')
    args = parser.parse_args()
    report = preview_route(args.preview.resolve(), args.memory.resolve(), args.mapping.resolve(), args.output.resolve(),
                           args.start_node, args.simulated_start_xy)
    print(json.dumps({'status': report['status'], 'results': report['results'],
                      'duration_ms': report['duration_ms']}, indent=2, allow_nan=False))
