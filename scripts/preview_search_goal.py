"""Preview object observation goals against a frozen occupancy export, without motion."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt
import yaml

from extract_mapped_rgbd import file_hash
from scene_memory import query


POLICY = {'min_standoff_m': 0.75, 'preferred_standoff_m': 1.0, 'max_standoff_m': 1.25,
          'clearance_m': 0.25,
          'ranking': 'Closest to preferred stand-off, then greatest clearance, then grid y/x',
          'assumption': 'Planar circular clearance for offline inspection; not a measured robot footprint'}


@dataclass
class Grid:
    cells: np.ndarray  # -1 unknown, 0 free, 100 occupied; row zero is map-grid bottom.
    resolution_m: float
    origin_xy_m: np.ndarray

    def cell_xy(self, point):
        point = np.asarray(point, dtype=float)
        if point.shape != (2,) or not np.isfinite(point).all():
            raise ValueError('Expected finite map x/y coordinates')
        return tuple(np.floor((point-self.origin_xy_m)/self.resolution_m).astype(int))

    def contains(self, cell):
        x, y = cell
        return 0 <= x < self.cells.shape[1] and 0 <= y < self.cells.shape[0]

    def center_xy(self, cell):
        return self.origin_xy_m+(np.asarray(cell)+0.5)*self.resolution_m

    def clearance(self):
        # Padded non-free cells include the outside of the map. Subtract half a
        # cell diagonal to bound distance to blocked cell areas, not just centers.
        free = np.pad(self.cells == 0, 1, constant_values=False)
        centers = distance_transform_edt(free)[1:-1, 1:-1]*self.resolution_m
        return np.maximum(0, centers-self.resolution_m/np.sqrt(2))


def decode_grid(image, metadata):
    origin = np.asarray(metadata['origin'], dtype=float)
    resolution = float(metadata['resolution'])
    free, occupied = float(metadata['free_thresh']), float(metadata['occupied_thresh'])
    if (image is None or image.ndim != 2 or image.dtype != np.uint8 or not image.size
            or origin.shape != (3,) or not np.isfinite(origin).all()
            or not np.isfinite(resolution) or resolution <= 0 or not 0 <= free < occupied <= 1):
        raise ValueError('Invalid grayscale occupancy image or metric map metadata')
    if origin[2] != 0 or metadata['negate'] not in (0, 1) or metadata.get('mode', 'trinary') != 'trinary':
        raise ValueError('Only axis-aligned trinary occupancy exports are supported')
    pixels = image.astype(float)
    probability = (pixels if metadata['negate'] else 255-pixels)/255
    cells = np.full(image.shape, -1, dtype=np.int8)
    cells[probability < free] = 0
    cells[probability > occupied] = 100
    # PGM row zero is the top; ROS grid origin is the lower-left cell corner.
    return Grid(np.flipud(cells).copy(), resolution, origin[:2])


def load_grid(mapping, context):
    if context['map_frame'] != 'map' or context['point_unit'] != 'meter':
        raise ValueError('Expected memory in metric map coordinates')
    database = json.loads((mapping/'database_check.json').read_text())
    exported = json.loads((mapping/'export_run.json').read_text())
    if (database['status'] != 'VERIFIED' or exported['status'] != 'EXPORTED'
            or exported['exit_code'] != 0 or not exported['database_unchanged']):
        raise ValueError('Use the verified frozen mapping/export evidence')
    database_hash = file_hash(mapping/'map.db')
    if database_hash != database['database_sha256'] or database_hash != context['database_sha256']:
        raise ValueError('Memory and occupancy export have incompatible map identity')
    hashes = {}
    for name in ('room.yaml', 'room.pgm', 'room_camera_poses.txt'):
        matching = [f for f in exported['files'] if f['name'] == name]
        actual = file_hash(mapping/'export'/name)
        if len(matching) != 1 or actual != matching[0]['sha256']:
            raise ValueError(f'Frozen export changed: {name}')
        hashes[name] = actual
    if hashes['room_camera_poses.txt'] != context['camera_poses_sha256']:
        raise ValueError('Memory and occupancy export have incompatible pose identity')
    metadata = yaml.safe_load((mapping/'export/room.yaml').read_text())
    if metadata['image'] != 'room.pgm':
        raise ValueError('Expected the hash-verified room.pgm export')
    grid = decode_grid(cv2.imread(str(mapping/'export/room.pgm'), cv2.IMREAD_UNCHANGED), metadata)
    provenance = {'mapping_run': str(mapping), 'database_sha256': database_hash, 'export_sha256': hashes,
                  'export_manifest_sha256': file_hash(mapping/'export_run.json'), 'metadata': metadata,
                  'width_cells': grid.cells.shape[1], 'height_cells': grid.cells.shape[0],
                  'cell_counts': {name: int(np.count_nonzero(grid.cells == value))
                                  for name, value in [('unknown', -1), ('free', 0), ('occupied', 100)]},
                  'cell_coordinates': 'x right, y up; origin at lower-left cell corner; goals use cell centers'}
    return grid, provenance


def select_goal(grid, target, clearance):
    target = np.asarray(target, dtype=float)
    if target.shape != (3,) or not np.isfinite(target).all():
        raise ValueError('Expected a finite map-frame object surface point')
    cell = grid.cell_xy(target[:2])
    result = {'status': 'NO_GOAL', 'target_cell_xy': [int(v) for v in cell], 'goal': None}
    if not grid.contains(cell):
        return {**result, 'reason': 'target_outside_grid'}, np.zeros_like(grid.cells, dtype=bool)
    result['target_cell_state'] = int(grid.cells[cell[1], cell[0]])
    ys, xs = np.indices(grid.cells.shape)
    centers = grid.center_xy(np.stack((xs, ys), axis=-1))
    distances = np.linalg.norm(centers-target[:2], axis=-1)
    band = (distances >= POLICY['min_standoff_m']) & (distances <= POLICY['max_standoff_m'])
    free = band & (grid.cells == 0)
    eligible = free & (clearance >= POLICY['clearance_m'])
    result['cell_checks'] = {'in_standoff_band': int(band.sum()), 'free_in_band': int(free.sum()),
                            'unknown_in_band': int(np.count_nonzero(band & (grid.cells == -1))),
                            'occupied_in_band': int(np.count_nonzero(band & (grid.cells == 100))),
                            'passing_clearance': int(eligible.sum())}
    if not free.any():
        return {**result, 'reason': 'no_free_cells_in_standoff_band'}, eligible
    if not eligible.any():
        return {**result, 'reason': 'insufficient_map_clearance'}, eligible
    rows, cols = np.nonzero(eligible)
    order = np.lexsort((cols, rows, -clearance[eligible],
                       np.abs(distances[eligible]-POLICY['preferred_standoff_m'])))
    x, y = int(cols[order[0]]), int(rows[order[0]])
    point = grid.center_xy([x, y])
    delta = target[:2]-point
    goal = {'map_xy_m': point.tolist(), 'yaw_rad': float(np.arctan2(delta[1], delta[0])),
            'cell_xy': [x, y], 'cell_state': int(grid.cells[y, x]),
            'standoff_m': float(distances[y, x]), 'clearance_lower_bound_m': float(clearance[y, x])}
    return {**result, 'status': 'PREVIEW_CANDIDATE', 'goal': goal}, eligible


def draw_occupancy(ax, grid):
    """Draw the shared metric occupancy backdrop and return its legend entries."""
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    colors = ['#cbd0d6', '#fafafa', '#39424e']
    display = np.where(grid.cells == -1, 0, np.where(grid.cells == 0, 1, 2))
    lower = grid.origin_xy_m
    upper = lower+np.array(grid.cells.shape[::-1])*grid.resolution_m
    ax.imshow(display, origin='lower', cmap=ListedColormap(colors), vmin=0, vmax=2,
              extent=[lower[0], upper[0], lower[1], upper[1]], interpolation='nearest')
    ax.set_xlabel('map x (m)')
    ax.set_ylabel('map y (m)')
    ax.set_aspect('equal')
    return [Patch(facecolor=color, label=name) for color, name in zip(colors, ['Unknown', 'Free', 'Occupied'])]


def render_overlay(grid, label, obj, decision, eligible, path, route=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    figure, axes = plt.subplots(1, 2 if obj else 1, figsize=(12, 5.6) if obj else (8, 5.6))
    try:
        for index, ax in enumerate(np.atleast_1d(axes)):
            legend = draw_occupancy(ax, grid)
            if obj:
                target = np.array(obj['map_point_m'][:2])
                rows, cols = np.nonzero(eligible)
                candidates = grid.center_xy(np.column_stack((cols, rows)))
                ax.scatter(candidates[:, 0], candidates[:, 1], s=5, c='#2f83cc', label='Passing cells')
                ax.scatter(*target, marker='D', s=65, c='#d97706', edgecolors='white', zorder=5, label='Remembered surface point')
                for radius in (POLICY['min_standoff_m'], POLICY['max_standoff_m']):
                    ax.add_patch(Circle(target, radius, fill=False, color='#d97706', linestyle='--', linewidth=1))
                if decision['goal']:
                    goal = np.array(decision['goal']['map_xy_m'])
                    ax.scatter(*goal, marker='x', s=80, color='#b91c1c', linewidths=2, zorder=6, label='Preview goal')
                    ax.add_patch(Circle(goal, POLICY['clearance_m'], fill=False, color='#16a34a', linewidth=1.5))
                    ax.annotate('', target, goal, arrowprops={'arrowstyle': '->', 'color': '#b91c1c', 'lw': 1.2})
                if index == 1:
                    radius = POLICY['max_standoff_m']+0.3
                    ax.set_xlim(target[0]-radius, target[0]+radius)
                    ax.set_ylim(target[1]-radius, target[1]+radius)
            if route is not None:
                start = np.array(route['start']['map_xy_m'])
                ax.scatter(*start, marker='*', s=130, color='#0891b2', edgecolors='black',
                           zorder=7, label='Explicit start ('+route['start']['kind'].replace('_', ' ')+')')
                points = np.array(route['path_map_xy_m'])
                if len(points):
                    ax.plot(points[:, 0], points[:, 1], color='#9333ea', linewidth=2,
                            zorder=6, label='Checked four-direction route')
                if index == 1:
                    ax.set_xlim(min(ax.get_xlim()[0], start[0]-.2), max(ax.get_xlim()[1], start[0]+.2))
                    ax.set_ylim(min(ax.get_ylim()[0], start[1]-.2), max(ax.get_ylim()[1], start[1]+.2))
            ax.set_title('Occupancy grid' if index == 0 else 'Target detail')
        title = f'{label}: no object candidate' if obj is None else f'Object {obj["object_id"]}: {obj["label"]} | '+(
            'cell-only goal preview' if decision['goal'] else 'No goal: '+decision['reason'].replace('_', ' '))
        if route is None:
            subtitle = 'Offline map checks; route, visibility and physical clearance unverified'
        else:
            title = f'{label}'+(f' / object {obj["object_id"]}' if obj else '')+' | '+route['status']
            if route.get('reason'):
                title += ': '+route['reason'].replace('_', ' ')
            subtitle = 'Offline route check; physical traversal and target visibility unverified'
        figure.suptitle(title+'\n'+subtitle, fontsize=12)
        handles, _ = np.atleast_1d(axes)[-1].get_legend_handles_labels()
        figure.legend(handles=legend+handles, loc='lower center', ncol=3, fontsize=9)
        figure.tight_layout(rect=(0, 0.18 if route is not None else 0.12, 1, 0.9))
        figure.savefig(path, dpi=150)
    finally:
        plt.close(figure)


def query_candidates(memory, label, object_ids=None):
    if object_ids is None:
        return query(memory, 'find', label)
    if (any(type(i) is not int or i <= 0 for i in object_ids) or len(set(object_ids)) != len(object_ids)):
        raise ValueError('Expected unique positive object IDs')
    result = query(memory)
    objects = {obj['object_id']: obj for obj in result['objects']}
    if any(i not in objects for i in object_ids):
        raise ValueError('Selected object ID is absent from this memory')
    result['objects'] = [objects[i] for i in object_ids]
    result['status'] = 'FOUND' if object_ids else 'NO_SELECTED_OBJECTS'
    return result


def preview(memory, mapping, label, output, object_ids=None):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'status': 'INCOMPLETE', 'dry_run': True, 'query_label': label, 'policy': POLICY,
              'map_frame': 'map', 'coordinate_unit': 'meter', 'results': [],
              'limitation': 'Cell-only planar preview; no route, visibility, current localization, robot footprint or physical traversability verification. No motion commands.'}
    try:
        memory_hash = file_hash(memory)
        result = query_candidates(memory, label, object_ids)
        if object_ids is not None:
            report['selected_object_ids'] = object_ids
        report.update(memory_path=str(memory), memory_sha256=memory_hash,
                      memory_context=result['context'], query_status=result['status'],
                      object_candidates=result['objects'])
        grid, provenance = load_grid(mapping, result['context'])
        report['occupancy'] = provenance
        clearance = grid.clearance()
        report['cells_passing_clearance'] = int(np.count_nonzero((grid.cells == 0) & (clearance >= POLICY['clearance_m'])))
        for obj in result['objects']:
            begin = time.monotonic()
            decision, eligible = select_goal(grid, obj['map_point_m'], clearance)
            decision.update(object_id=obj['object_id'], selection_ms=(time.monotonic()-begin)*1000,
                            overlay=f'object_{obj["object_id"]}.png')
            render_overlay(grid, label, obj, decision, eligible, output/decision['overlay'])
            report['results'].append(decision)
        if not result['objects']:
            report['reason'] = 'target_not_in_memory' if object_ids is None else 'no_selected_objects'
            report['overview'] = 'overview.png'
            render_overlay(grid, label, None, None, None, output/'overview.png')
        if file_hash(memory) != memory_hash:
            raise ValueError('Memory changed during preview; retry against one fixed snapshot')
        report['status'] = 'PREVIEW_READY' if any(row['goal'] for row in report['results']) else 'NO_GOAL'
        report['runtime'] = {'numpy': np.__version__, 'opencv': cv2.__version__, 'pyyaml': yaml.__version__}
    except ValueError as error:
        report['error'] = str(error)
        raise
    finally:
        report['duration_ms'] = (time.monotonic()-started)*1000
        (output/'preview.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--memory', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = preview(args.memory.resolve(), args.mapping.resolve(), args.label, args.output.resolve())
    print(json.dumps({'status': report['status'], 'results': report['results'],
                      'duration_ms': report['duration_ms']}, indent=2, allow_nan=False))
