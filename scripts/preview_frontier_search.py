"""Preview a geometric exploration fallback when saved memory has no object goal."""

import argparse
import json
from pathlib import Path
import time

import numpy as np
from scipy.ndimage import label as label_components

from extract_mapped_rgbd import file_hash
from preview_search_goal import POLICY, draw_occupancy
from preview_search_route import CARDINAL_DIRECTIONS, load_goal_preview, make_start, plan_route


FRONTIER_POLICY = {
    'min_standoff_m': 0.30, 'max_standoff_m': 0.75,
    'boundary': 'Free cells with an in-map cardinal unknown neighbor; four-connected groups',
    'view': 'Four cardinal zero-width planar rays; all cells through the frontier free, next cell unknown',
    'ranking': 'Smallest straight-line start displacement, then frontier ID, goal y/x and frontier y/x; first reachable candidate',
    'assumption': 'Planar visibility only; no measured camera FOV, height, information gain or physical visibility',
}


def frontier_inventory(grid):
    height, width = grid.cells.shape
    unknown = np.pad(grid.cells == -1, 1, constant_values=False)
    adjacent = np.zeros_like(grid.cells, dtype=bool)
    structure = np.zeros((3, 3), dtype=int)
    structure[1, 1] = 1
    for dx, dy in CARDINAL_DIRECTIONS:
        adjacent |= unknown[1+dy:1+dy+height, 1+dx:1+dx+width]
        structure[1+dy, 1+dx] = 1
    labels, count = label_components((grid.cells == 0) & adjacent, structure=structure)
    groups = []
    for group_id in range(1, count+1):
        rows, cols = np.nonzero(labels == group_id)
        groups.append({'frontier_id': group_id, 'cell_xy': np.column_stack((cols, rows)).tolist()})
    return labels, groups


def frontier_candidates(grid, clearance, labels):
    candidates = []
    rows, cols = np.nonzero((grid.cells == 0) & (clearance >= POLICY['clearance_m']))
    max_steps = int(np.floor(FRONTIER_POLICY['max_standoff_m']/grid.resolution_m))+1
    for y, x in zip(rows, cols):
        for dx, dy in CARDINAL_DIRECTIONS:
            ray = [[int(x), int(y)]]
            for step in range(1, max_steps+1):
                cell = (int(x+dx*step), int(y+dy*step))
                if not grid.contains(cell) or grid.cells[cell[1], cell[0]] == 100:
                    break
                if grid.cells[cell[1], cell[0]] == -1:
                    distance = (step-1)*grid.resolution_m
                    if FRONTIER_POLICY['min_standoff_m'] <= distance <= FRONTIER_POLICY['max_standoff_m']:
                        frontier = ray[-1]
                        candidates.append({'cell_xy': [int(x), int(y)], 'map_xy_m': grid.center_xy([x, y]).tolist(),
                                           'clearance_lower_bound_m': float(clearance[y, x]),
                                           'frontier_id': int(labels[frontier[1], frontier[0]]),
                                           'frontier_cell_xy': frontier, 'unknown_cell_xy': list(cell),
                                           'frontier_standoff_m': distance, 'yaw_rad': float(np.arctan2(dy, dx)),
                                           'free_ray_cell_xy': ray})
                    break
                ray.append(list(cell))
    return candidates


def select_frontier(grid, start_xy, clearance):
    started = time.monotonic()
    labels, groups = frontier_inventory(grid)
    result = {'status': 'NO_FRONTIER', 'goal': None, 'route': None, 'frontiers': groups,
              'frontier_cell_count': int(np.count_nonzero(labels)), 'candidate_count': 0,
              'candidate_goal_cells': 0, 'route_attempts': 0, 'route_rejections': []}
    try:
        start_cell = grid.cell_xy(start_xy)
        check = plan_route(grid, start_xy, grid.center_xy(start_cell), clearance)
        result['start_validation'] = check
        if check['status'] != 'ROUTE_READY':
            result.update(status='INVALID_START', reason=check['reason'])
            return result
        if not groups:
            result['reason'] = 'no_free_unknown_boundary'
            return result
        candidates = frontier_candidates(grid, clearance, labels)
        result['candidate_count'] = len(candidates)
        result['candidate_goal_cells'] = len({tuple(row['cell_xy']) for row in candidates})
        for candidate in candidates:
            candidate['start_displacement_m'] = float(np.linalg.norm(np.array(candidate['map_xy_m'])-start_xy))
        candidates.sort(key=lambda row: (row['start_displacement_m'], row['frontier_id'],
                                         row['cell_xy'][1], row['cell_xy'][0],
                                         row['frontier_cell_xy'][1], row['frontier_cell_xy'][0]))
        if not candidates:
            result['reason'] = 'no_cardinal_viewpoint_with_clearance_and_standoff'
            return result
        for candidate in candidates:
            route = plan_route(grid, start_xy, candidate['map_xy_m'], clearance)
            result['route_attempts'] += 1
            if route['status'] == 'ROUTE_READY':
                result.update(status='EXPLORATION_READY', goal=candidate, route=route)
                return result
            result['route_rejections'].append({'cell_xy': candidate['cell_xy'], 'frontier_id': candidate['frontier_id'],
                                                'status': route['status'], 'reason': route['reason']})
        result.update(status='NO_ROUTE', reason='no_reachable_frontier_viewpoint')
        return result
    finally:
        result['selection_ms'] = (time.monotonic()-started)*1000


def render_frontiers(grid, report, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    exploration = report['exploration']
    goal = exploration['goal'] if exploration else None
    figure, axes = plt.subplots(1, 2 if goal else 1, figsize=(12, 5.8) if goal else (9, 5.8))
    try:
        for index, ax in enumerate(np.atleast_1d(axes)):
            legend = draw_occupancy(ax, grid)
            start = report['start']
            ax.scatter(*start['map_xy_m'], marker='*', s=140, color='#0891b2', edgecolors='black',
                       zorder=8, label='Start ('+start['kind'].replace('_', ' ')+')')
            if exploration and exploration['frontiers']:
                cells = np.array([cell for group in exploration['frontiers'] for cell in group['cell_xy']])
                points = grid.center_xy(cells)
                ax.scatter(points[:, 0], points[:, 1], marker='s', s=12, color='#eab308', label='Free/unknown frontiers')
            if goal:
                point = np.array(goal['map_xy_m'])
                boundary = grid.center_xy(goal['frontier_cell_xy'])
                unknown = grid.center_xy(goal['unknown_cell_xy'])
                route = np.array(exploration['route']['path_map_xy_m'])
                ax.plot(route[:, 0], route[:, 1], color='#9333ea', linewidth=2, label='Checked route', zorder=6)
                ax.scatter(*point, marker='x', s=110, color='#b91c1c', linewidths=2, label='Observation goal', zorder=9)
                ax.scatter(*boundary, marker='D', s=60, color='#d97706', edgecolors='white', label='Selected frontier', zorder=7)
                ax.scatter(*unknown, marker='s', s=75, facecolors='none', edgecolors='#d97706', linewidths=2, label='Unknown neighbor', zorder=7)
                ax.annotate('', unknown, point, arrowprops={'arrowstyle': '->', 'color': '#d97706', 'linestyle': '--'})
                if index == 1:
                    focus = np.array([point, boundary, unknown, start['map_xy_m']])
                    ax.set_xlim(focus[:, 0].min()-.6, focus[:, 0].max()+.6)
                    ax.set_ylim(focus[:, 1].min()-.6, focus[:, 1].max()+.6)
            ax.set_title('Full occupancy export' if index == 0 else 'Exploration detail')
        reason = exploration.get('reason', '') if exploration else report['reason']
        title = report['query_label']+' | '+report['status']+(': '+reason.replace('_', ' ') if reason else '')
        figure.suptitle(title+'\nGeometric preview only; no observation, new coverage or physical navigation verified', fontsize=11)
        handles, _ = np.atleast_1d(axes)[-1].get_legend_handles_labels()
        figure.legend(handles=legend+handles, loc='lower center', ncol=3, fontsize=8)
        figure.tight_layout(rect=(0, .20, 1, .9))
        figure.savefig(path, dpi=150)
    finally:
        plt.close(figure)


def preview_frontiers(preview_path, memory, mapping, output, node_id=None, simulated_xy=None):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'dry_run': True, 'exploration': None,
              'observation_executed': False, 'new_coverage_measured': False,
              'policy': FRONTIER_POLICY, 'clearance_m': POLICY['clearance_m'],
              'limitation': 'Geometric exploration proposal, not an object location or detection. Camera visibility, information gain, physical traversal and current localization unverified.'}
    try:
        source_hash = file_hash(preview_path)
        source, grid, clearance = load_goal_preview(preview_path, memory, mapping)
        start = make_start(mapping, grid, node_id, simulated_xy)
        report.update(source_preview_path=str(preview_path), source_preview_sha256=source_hash, source_preview=source,
                      query_label=source['query_label'], start=start, map_frame='map', coordinate_unit='meter')
        if source['status'] == 'PREVIEW_READY':
            status = 'NOT_NEEDED'
            report['reason'] = 'object_goal_available'
        else:
            report['fallback_trigger'] = {'reason': source.get('reason', 'no_object_goal'),
                                          'object_rejections': [{'object_id': row['object_id'], 'reason': row['reason']}
                                                                for row in source['results']]}
            exploration = select_frontier(grid, start['map_xy_m'], clearance)
            status = exploration['status']
            report['exploration'] = exploration
        render_frontiers(grid, {**report, 'status': status}, output/'frontier.png')
        if file_hash(preview_path) != source_hash or file_hash(memory) != source['memory_sha256']:
            raise ValueError('Preview or memory changed during frontier selection')
        report['status'] = status
    except ValueError as error:
        report.update(status='INCOMPLETE', error=str(error))
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'frontier.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preview', 'memory', 'mapping', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    start = parser.add_mutually_exclusive_group(required=True)
    start.add_argument('--start-node', type=int)
    start.add_argument('--simulated-start-xy', type=float, nargs=2, metavar=('X_M', 'Y_M'))
    args = parser.parse_args()
    report = preview_frontiers(args.preview.resolve(), args.memory.resolve(), args.mapping.resolve(), args.output.resolve(),
                               args.start_node, args.simulated_start_xy)
    print(json.dumps({'status': report['status'], 'fallback_trigger': report.get('fallback_trigger'),
                      'exploration': report['exploration'], 'duration_ms': report['duration_ms']}, indent=2, allow_nan=False))
