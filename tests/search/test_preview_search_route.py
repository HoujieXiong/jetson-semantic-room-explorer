"""Known shortest paths, segment geometry, refusal cases and explicit start provenance."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from preview_search_goal import Grid
from preview_search_route import make_start, plan_route, segment_clearance


def empty_grid(size=5):
    return Grid(np.zeros((size, size), dtype=np.int8), 1, np.array([0., 0.]))


class RouteGeometryTests(unittest.TestCase):
    def test_open_grid_shortest_cardinal_path_and_metric_length(self):
        grid = empty_grid()
        result = plan_route(grid, [.5, .5], [4.5, 4.5], grid.clearance())
        self.assertEqual(result['status'], 'ROUTE_READY')
        self.assertEqual(result['path_cell_xy'][0], [0, 0])
        self.assertEqual(result['path_cell_xy'][-1], [4, 4])
        self.assertEqual(len(result['path_cell_xy']), 9)
        self.assertEqual(result['length_m'], 8)
        self.assertEqual(result['min_segment_clearance_m'], .5)
        self.assertLessEqual(result['expanded_cells'], 25)
        self.assertGreaterEqual(result['planning_ms'], 0)
        steps = np.diff(result['path_cell_xy'], axis=0)
        np.testing.assert_array_equal(np.abs(steps).sum(axis=1), np.ones(8))

    def test_wall_requires_known_eight_meter_detour_through_gap(self):
        grid = empty_grid()
        grid.cells[:4, 2] = 100
        result = plan_route(grid, [1.5, 1.5], [3.5, 1.5], grid.clearance())
        self.assertEqual(result['status'], 'ROUTE_READY')
        self.assertEqual(result['length_m'], 8)
        self.assertIn([2, 4], result['path_cell_xy'])
        self.assertTrue(all(grid.cells[y, x] == 0 for x, y in result['path_cell_xy']))

    def test_occupied_and_unknown_barriers_are_disconnected(self):
        for state in [100, -1]:
            grid = empty_grid()
            grid.cells[:, 2] = state
            result = plan_route(grid, [1.5, 1.5], [3.5, 1.5], grid.clearance())
            self.assertEqual(result['status'], 'NO_ROUTE')
            self.assertEqual(result['reason'], 'disconnected_under_route_policy')
            self.assertEqual(result['expanded_cells'], 10)
            self.assertEqual(result['path_map_xy_m'], [])
            self.assertIsNone(result['length_m'])
            self.assertGreaterEqual(result['planning_ms'], 0)

    def test_diagonal_corner_does_not_connect_free_cells(self):
        grid = empty_grid(2)
        grid.cells[0, 1] = grid.cells[1, 0] = 100
        result = plan_route(grid, [.5, .5], [1.5, 1.5], grid.clearance())
        self.assertEqual(result['status'], 'NO_ROUTE')
        self.assertEqual(result['expanded_cells'], 1)

    def test_segments_check_the_interior_not_only_endpoints(self):
        grid = empty_grid(7)
        blocked = np.array([[3.5, 3.5]])
        first, last = [1.5, 3.5], [5.5, 3.5]
        self.assertEqual(segment_clearance(grid, blocked, first, first), 1.5)
        self.assertEqual(segment_clearance(grid, blocked, last, last), 1.5)
        self.assertEqual(segment_clearance(grid, blocked, first, last), 0)
        # Both endpoints are diagonally separated from the square, but the middle is closer.
        self.assertAlmostEqual(segment_clearance(grid, blocked, [2.5, 2.5], [2.5, 2.5]), np.sqrt(.5))
        self.assertEqual(segment_clearance(grid, blocked, [2.5, 2.5], [4.5, 2.5]), .5)

    def test_boundaries_block_segment_clearance_and_diagonals_fail(self):
        grid = empty_grid()
        blocked = np.empty((0, 2))
        self.assertEqual(segment_clearance(grid, blocked, [.1, 1], [.1, 4]), .1)
        self.assertEqual(segment_clearance(grid, blocked, [-.1, 1], [.1, 1]), 0)
        with self.assertRaisesRegex(ValueError, 'axis-aligned'):
            segment_clearance(grid, blocked, [1, 1], [2, 2])

    def test_start_connector_retains_exact_input_and_checked_length(self):
        grid = empty_grid()
        result = plan_route(grid, [.61, .68], [2.5, 2.5], grid.clearance())
        self.assertEqual(result['status'], 'ROUTE_READY')
        self.assertEqual(result['path_map_xy_m'][:3], [[.61, .68], [.5, .68], [.5, .5]])
        self.assertAlmostEqual(result['length_m'], 4.29)
        self.assertGreaterEqual(result['min_segment_clearance_m'], .25)

    def test_start_near_map_edge_is_not_snapped_into_safe_cell_center(self):
        grid = empty_grid()
        result = plan_route(grid, [.1, .5], [2.5, 2.5], grid.clearance())
        self.assertEqual(result['status'], 'INVALID_START')
        self.assertEqual(result['reason'], 'insufficient_clearance')
        self.assertEqual(result['start_check']['map_xy_m'], [.1, .5])
        self.assertEqual(result['path_map_xy_m'], [])

    def test_same_start_goal_is_zero_length_with_point_clearance(self):
        grid = empty_grid()
        result = plan_route(grid, [2.5, 2.5], [2.5, 2.5], grid.clearance())
        self.assertEqual(result['status'], 'ROUTE_READY')
        self.assertEqual(result['path_map_xy_m'], [[2.5, 2.5]])
        self.assertEqual(result['length_m'], 0)
        self.assertEqual(result['min_segment_clearance_m'], 2.5)

    def test_invalid_start_and_goal_states_have_explicit_reasons(self):
        for endpoint in ['start', 'goal']:
            for state, reason in [(-1, 'unknown_cell'), (100, 'occupied_cell')]:
                grid = empty_grid()
                grid.cells[0, 0] = state
                points = ([.5, .5], [3.5, 3.5]) if endpoint == 'start' else ([3.5, 3.5], [.5, .5])
                result = plan_route(grid, *points, grid.clearance())
                self.assertEqual(result['status'], 'INVALID_'+endpoint.upper())
                self.assertEqual(result['reason'], reason)
                self.assertEqual(result['path_map_xy_m'], [])
            grid = empty_grid()
            for invalid in [[-.001, 1], [5, 1], [1, 5]]:
                points = (invalid, [3.5, 3.5]) if endpoint == 'start' else ([3.5, 3.5], invalid)
                result = plan_route(grid, *points, grid.clearance())
                self.assertEqual(result['status'], 'INVALID_'+endpoint.upper())
                self.assertEqual(result['reason'], 'outside_grid')

    def test_finite_shape_and_goal_center_contracts(self):
        grid = empty_grid()
        for bad in [[float('nan'), 1], [1, float('inf')], [1], [1, 2, 3]]:
            with self.assertRaises(ValueError):
                plan_route(grid, bad, [2.5, 2.5], grid.clearance())
        with self.assertRaisesRegex(ValueError, 'cell center'):
            plan_route(grid, [.5, .5], [2.6, 2.5], grid.clearance())

    def test_same_inputs_produce_identical_decisions(self):
        grid = empty_grid()
        first = plan_route(grid, [.5, .5], [4.5, 4.5], grid.clearance())
        second = plan_route(grid, [.5, .5], [4.5, 4.5], grid.clearance())
        self.assertEqual({k: v for k, v in first.items() if k != 'planning_ms'},
                         {k: v for k, v in second.items() if k != 'planning_ms'})


class StartProvenanceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.mapping = Path(folder.name)
        (self.mapping/'export').mkdir()
        (self.mapping/'export/room_camera_poses.txt').write_text('123.000000 1.25 2.75 3.5 0 0 0 1 7\n')
        self.node = {'node_id': 7, 'map_id': 0, 'source_stamp_ns': 123000000001}
        (self.mapping/'database_check.json').write_text(json.dumps({'nodes': [self.node]}))

    def test_camera_start_preserves_original_pose_and_nanosecond_source(self):
        start = make_start(self.mapping, empty_grid(), 7, None)
        self.assertEqual(start['kind'], 'recorded_camera_projection')
        self.assertEqual(start['map_xy_m'], [1.25, 2.75])
        self.assertEqual(start['camera_position_m'], [1.25, 2.75, 3.5])
        self.assertEqual(start['source_stamp_ns'], 123000000001)
        self.assertEqual(len(start['camera_poses_sha256']), 64)

    def test_simulated_point_is_explicit_and_never_snapped(self):
        start = make_start(self.mapping, empty_grid(), None, [1.123, 2.345])
        self.assertEqual(start['kind'], 'simulated_grid_fixture')
        self.assertEqual(start['map_xy_m'], [1.123, 2.345])
        self.assertNotIn('source_stamp_ns', start)

    def test_ambiguous_missing_unknown_or_nonfinite_start_fails(self):
        for node, xy in [(None, None), (7, [1, 2]), (999, None), (None, [float('nan'), 2])]:
            with self.assertRaises(ValueError):
                make_start(self.mapping, empty_grid(), node, xy)

    def test_source_timestamp_or_map_disagreement_fails(self):
        for change in [{'source_stamp_ns': 124000000000}, {'map_id': 1}]:
            (self.mapping/'database_check.json').write_text(json.dumps({'nodes': [{**self.node, **change}]}))
            with self.assertRaisesRegex(ValueError, 'map/source timestamp'):
                make_start(self.mapping, empty_grid(), 7, None)


if __name__ == '__main__':
    unittest.main()
