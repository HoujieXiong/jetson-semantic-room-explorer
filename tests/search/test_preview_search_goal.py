"""Known map cells, conservative clearance and frozen-export failure cases."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from extract_mapped_rgbd import file_hash
from preview_search_goal import Grid, decode_grid, load_grid, select_goal


def metadata():
    return {'image': 'room.pgm', 'resolution': 0.5, 'origin': [-1, -2, 0],
            'negate': 0, 'occupied_thresh': 0.5, 'free_thresh': 0.196}


class GridGoalTests(unittest.TestCase):
    def test_pgm_top_row_becomes_upper_map_row(self):
        image = np.array([[254, 0], [205, 254]], dtype=np.uint8)
        grid = decode_grid(image, metadata())
        np.testing.assert_array_equal(grid.cells, [[-1, 0], [0, 100]])
        self.assertEqual(grid.cell_xy([-0.75, -1.75]), (0, 0))
        self.assertEqual(grid.cells[0, 0], -1)
        np.testing.assert_array_equal(grid.center_xy([1, 1]), [-0.25, -1.25])

    def test_grid_corners_centers_and_exclusive_upper_bounds(self):
        grid = Grid(np.zeros((2, 3), dtype=np.int8), 0.5, np.array([-1, -2]))
        for cell in [(0, 0), (2, 0), (0, 1), (2, 1)]:
            self.assertEqual(grid.cell_xy(grid.center_xy(cell)), cell)
            self.assertTrue(grid.contains(cell))
        self.assertEqual(grid.cell_xy([-1, -2]), (0, 0))
        for point in [(-1.0001, -2), (-1, -2.0001), (0.5, -1.5), (-0.5, -1)]:
            self.assertFalse(grid.contains(grid.cell_xy(point)))

    def test_negated_map_and_strict_threshold_equality(self):
        settings = metadata()
        settings['negate'] = 1
        np.testing.assert_array_equal(decode_grid(np.array([[0, 255]], dtype=np.uint8), settings).cells, [[0, 100]])
        settings = metadata()
        settings.update(free_thresh=50/255, occupied_thresh=100/255)
        grid = decode_grid(np.array([[206, 205, 155, 154]], dtype=np.uint8), settings)
        np.testing.assert_array_equal(grid.cells, [[0, -1, -1, 100]])

    def test_unsupported_rotation_mode_and_negation_fail(self):
        for change in [{'origin': [0, 0, 0.1]}, {'mode': 'scale'}, {'negate': 2}]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'axis-aligned trinary'):
                decode_grid(np.zeros((2, 2), dtype=np.uint8), {**metadata(), **change})

    def test_bad_images_resolution_origin_and_thresholds_fail(self):
        for image in [None, np.zeros((0, 0), dtype=np.uint8), np.zeros((2, 2), dtype=np.uint16), np.zeros((2, 2, 3), dtype=np.uint8)]:
            with self.subTest(image_type=type(image)), self.assertRaises(ValueError):
                decode_grid(image, metadata())
        for change in [{'resolution': 0}, {'resolution': float('nan')}, {'origin': [0, 0]},
                       {'origin': [0, float('inf'), 0]}, {'free_thresh': .6}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_grid(np.zeros((2, 2), dtype=np.uint8), {**metadata(), **change})

    def test_clearance_includes_map_outside_and_cell_areas(self):
        grid = Grid(np.zeros((7, 7), dtype=np.int8), .1, np.array([0, 0]))
        clearance = grid.clearance()
        self.assertAlmostEqual(clearance[0, 0], .1-.1/np.sqrt(2))
        self.assertAlmostEqual(clearance[3, 3], .4-.1/np.sqrt(2))
        self.assertLess(clearance[0, 3], .25)

    def test_unknown_obstacle_and_diagonal_corner_are_not_clear(self):
        for value in [-1, 100]:
            grid = Grid(np.zeros((15, 15), dtype=np.int8), .1, np.array([0, 0]))
            grid.cells[5, 5] = value
            clearance = grid.clearance()
            self.assertEqual(clearance[5, 5], 0)
            # Center distance sqrt(.2^2+.2^2) exceeds .25, but blocked cell area is closer.
            self.assertLess(clearance[7, 7], .25)
            self.assertAlmostEqual(clearance[7, 7], .15*np.sqrt(2))

    def test_unique_clear_cell_has_metric_goal_and_faces_target(self):
        cells = np.full((60, 60), 100, dtype=np.int8)
        cells[29:36, 39:46] = 0
        grid = Grid(cells, .1, np.array([-3, -3]))
        result, eligible = select_goal(grid, [.25, .25, -1], grid.clearance())
        self.assertEqual(result['status'], 'PREVIEW_CANDIDATE')
        self.assertEqual(int(eligible.sum()), 1)
        self.assertEqual(result['goal']['cell_xy'], [42, 32])
        np.testing.assert_allclose(result['goal']['map_xy_m'], [1.25, .25])
        self.assertAlmostEqual(result['goal']['standoff_m'], 1)
        self.assertGreaterEqual(result['goal']['clearance_lower_bound_m'], .25)
        self.assertAlmostEqual(abs(result['goal']['yaw_rad']), np.pi)
        self.assertEqual(result['target_cell_state'], 100)  # Surface cell need not be free.

    def test_equal_distance_clearance_tie_uses_grid_y_then_x(self):
        cells = np.full((42, 42), 100, dtype=np.int8)
        cells[19:22, 15:18] = 0
        cells[19:22, 23:26] = 0
        grid = Grid(cells, .25, np.array([-5.125, -5.125]))
        result, eligible = select_goal(grid, [0, 0, 2], grid.clearance())
        self.assertEqual(int(eligible.sum()), 2)
        self.assertEqual(result['goal']['cell_xy'], [16, 20])
        self.assertEqual(result['goal']['map_xy_m'], [-1, 0])
        self.assertEqual(result['goal']['yaw_rad'], 0)

    def test_no_free_band_has_no_fabricated_goal(self):
        grid = Grid(np.full((60, 60), -1, dtype=np.int8), .1, np.array([-3, -3]))
        result, eligible = select_goal(grid, [0, 0, 1], grid.clearance())
        self.assertEqual(result['reason'], 'no_free_cells_in_standoff_band')
        self.assertIsNone(result['goal'])
        self.assertFalse(eligible.any())
        self.assertGreater(result['cell_checks']['unknown_in_band'], 0)

    def test_free_cell_without_clearance_is_explicit_no_goal(self):
        cells = np.full((60, 60), 100, dtype=np.int8)
        cells[30, 40] = 0
        grid = Grid(cells, .1, np.array([-3, -3]))
        result, eligible = select_goal(grid, [0, 0, 1], grid.clearance())
        self.assertEqual(result['cell_checks']['free_in_band'], 1)
        self.assertEqual(result['reason'], 'insufficient_map_clearance')
        self.assertIsNone(result['goal'])
        self.assertFalse(eligible.any())

    def test_outside_or_invalid_target_is_not_clamped(self):
        grid = Grid(np.zeros((2, 2), dtype=np.int8), 1, np.array([0, 0]))
        result, _ = select_goal(grid, [-.1, .5, 1], grid.clearance())
        self.assertEqual(result['target_cell_xy'], [-1, 0])
        self.assertEqual(result['reason'], 'target_outside_grid')
        self.assertIsNone(result['goal'])
        for target in [[0, 0], [0, float('nan'), 1], [0, 0, float('inf')]]:
            with self.assertRaises(ValueError):
                select_goal(grid, target, grid.clearance())


class ExportIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mapping = Path(self.temp.name)
        export = self.mapping/'export'
        export.mkdir()
        (self.mapping/'map.db').write_bytes(b'Synthetic frozen database identity')
        (export/'room_camera_poses.txt').write_text('Synthetic frozen pose identity\n')
        (export/'room.yaml').write_text(yaml.safe_dump(metadata()))
        self.assertTrue(cv2.imwrite(str(export/'room.pgm'), np.array([[254, 0], [205, 254]], dtype=np.uint8)))
        self.context = {'map_frame': 'map', 'point_unit': 'meter', 'database_sha256': file_hash(self.mapping/'map.db'),
                        'camera_poses_sha256': file_hash(export/'room_camera_poses.txt')}
        (self.mapping/'database_check.json').write_text(json.dumps({'status': 'VERIFIED', 'database_sha256': self.context['database_sha256']}))
        self.manifest = {'status': 'EXPORTED', 'exit_code': 0, 'database_unchanged': True,
                         'files': [{'name': p.name, 'sha256': file_hash(p)} for p in sorted(export.iterdir())]}
        (self.mapping/'export_run.json').write_text(json.dumps(self.manifest))

    def test_verified_artifacts_decode_with_retained_hashes(self):
        grid, evidence = load_grid(self.mapping, self.context)
        self.assertEqual(evidence['cell_counts'], {'unknown': 1, 'free': 2, 'occupied': 1})
        self.assertEqual(evidence['export_sha256']['room_camera_poses.txt'], self.context['camera_poses_sha256'])
        np.testing.assert_array_equal(grid.cells, [[-1, 0], [0, 100]])

    def test_incompatible_memory_map_pose_and_units_fail(self):
        for key, value in [('database_sha256', 'f'*64), ('camera_poses_sha256', 'f'*64), ('point_unit', 'millimeter')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_grid(self.mapping, {**self.context, key: value})

    def test_changed_pgm_yaml_pose_or_database_is_rejected(self):
        for relative in ['export/room.pgm', 'export/room.yaml', 'export/room_camera_poses.txt', 'map.db']:
            path = self.mapping/relative
            original = path.read_bytes()
            try:
                path.write_bytes(original+b'changed')
                with self.subTest(path=relative), self.assertRaises(ValueError):
                    load_grid(self.mapping, self.context)
            finally:
                path.write_bytes(original)

    def test_incomplete_or_ambiguous_export_manifest_is_rejected(self):
        for change in [{'status': 'INCOMPLETE'}, {'exit_code': 1}, {'database_unchanged': False},
                       {'files': self.manifest['files']+[copy.deepcopy(self.manifest['files'][0])]}]:
            (self.mapping/'export_run.json').write_text(json.dumps({**self.manifest, **change}))
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                load_grid(self.mapping, self.context)


if __name__ == '__main__':
    unittest.main()
