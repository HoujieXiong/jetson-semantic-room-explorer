"""Known frontier boundaries, cardinal viewing rays and reachable exploration goals."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from preview_search_goal import Grid, POLICY
from preview_frontier_search import frontier_candidates, frontier_inventory, select_frontier


def scene():
    grid = Grid(np.zeros((24, 24), dtype=np.int8), .1, np.array([0., 0.]))
    grid.cells[16:] = -1
    return grid


class FrontierTests(unittest.TestCase):
    def test_known_free_unknown_boundary_is_one_ordered_group(self):
        grid = scene()
        labels, groups = frontier_inventory(grid)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0], {'frontier_id': 1, 'cell_xy': [[x, 15] for x in range(24)]})
        self.assertEqual(int(np.count_nonzero(labels)), 24)
        self.assertFalse(labels[16:].any())

    def test_outside_is_not_an_unknown_neighbor(self):
        grid = scene()
        grid.cells[:] = 0
        labels, groups = frontier_inventory(grid)
        self.assertFalse(labels.any())
        self.assertEqual(groups, [])

    def test_occupied_cells_cannot_be_frontiers(self):
        grid = scene()
        grid.cells[15] = 100
        labels, groups = frontier_inventory(grid)
        self.assertFalse(labels.any())
        self.assertEqual(groups, [])

    def test_diagonal_unknowns_and_diagonal_groups_do_not_join(self):
        grid = Grid(np.zeros((3, 3), dtype=np.int8), .1, np.array([0., 0.]))
        grid.cells[0, 0] = grid.cells[2, 2] = -1
        labels, groups = frontier_inventory(grid)
        self.assertEqual(labels[1, 1], 0)
        self.assertEqual(len(groups), 4)
        self.assertEqual([row['cell_xy'] for row in groups], [[[1, 0]], [[0, 1]], [[2, 1]], [[1, 2]]])

    def test_goal_stays_behind_frontier_with_explicit_free_ray(self):
        grid = scene()
        result = select_frontier(grid, [1.25, 1.25], grid.clearance())
        self.assertEqual(result['status'], 'EXPLORATION_READY')
        goal = result['goal']
        self.assertEqual(goal['cell_xy'], [12, 12])
        self.assertEqual(goal['frontier_cell_xy'], [12, 15])
        self.assertEqual(goal['unknown_cell_xy'], [12, 16])
        self.assertEqual(goal['free_ray_cell_xy'], [[12, y] for y in range(12, 16)])
        self.assertAlmostEqual(goal['frontier_standoff_m'], .3)
        self.assertAlmostEqual(goal['yaw_rad'], np.pi/2)
        self.assertEqual(result['route']['length_m'], 0)
        self.assertEqual(result['route_attempts'], 1)

    def test_cardinal_rays_stop_at_first_unknown(self):
        grid = scene()
        grid.cells[11, 12] = -1
        labels, _ = frontier_inventory(grid)
        rows = frontier_candidates(grid, grid.clearance(), labels)
        # A valid observation ray must end before the first unknown, not cross it to the farther boundary.
        selected = [row for row in rows if row['cell_xy'] == [12, 6] and row['yaw_rad'] == np.pi/2]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['frontier_cell_xy'], [12, 10])
        self.assertEqual(selected[0]['unknown_cell_xy'], [12, 11])

    def test_occupied_row_occludes_far_frontier(self):
        grid = scene()
        grid.cells[10] = 100
        labels, _ = frontier_inventory(grid)
        rows = frontier_candidates(grid, grid.clearance(), labels)
        self.assertFalse(any(row['cell_xy'] == [12, 6] and row['yaw_rad'] == np.pi/2 for row in rows))

    def test_standoff_range_is_bounded(self):
        grid = scene()
        labels, _ = frontier_inventory(grid)
        rows = frontier_candidates(grid, grid.clearance(), labels)
        self.assertTrue(any(row['cell_xy'] == [12, 8] for row in rows))  # 0.7 m behind frontier.
        self.assertFalse(any(row['cell_xy'] == [12, 7] for row in rows))  # 0.8 m is outside the band.
        self.assertTrue(all(.30 <= row['frontier_standoff_m'] <= .75 for row in rows))

    def test_goals_obey_original_clearance_without_relabeling_frontiers(self):
        grid = scene()
        clearance = grid.clearance()
        labels, _ = frontier_inventory(grid)
        rows = frontier_candidates(grid, clearance, labels)
        self.assertTrue(rows)
        for row in rows:
            x, y = row['cell_xy']
            self.assertEqual(grid.cells[y, x], 0)
            self.assertGreaterEqual(clearance[y, x], POLICY['clearance_m'])
            self.assertEqual(labels[y, x], 0)
        self.assertFalse(np.any((labels > 0) & (clearance >= POLICY['clearance_m'])))

    def test_valid_start_without_frontiers_is_explicit_no_frontier(self):
        grid = scene()
        grid.cells[:] = 0
        result = select_frontier(grid, [1.25, 1.25], grid.clearance())
        self.assertEqual(result['status'], 'NO_FRONTIER')
        self.assertEqual(result['reason'], 'no_free_unknown_boundary')
        self.assertIsNone(result['goal'])
        self.assertIsNone(result['route'])

    def test_tiny_frontier_has_no_clear_observation_goal(self):
        grid = Grid(np.full((40, 40), 100, dtype=np.int8), .1, np.array([0., 0.]))
        grid.cells[2:18, 2:18] = 0
        grid.cells[2:8, 28:34] = -1
        grid.cells[3:6, 29:32] = 0
        result = select_frontier(grid, [.95, .95], grid.clearance())
        self.assertGreater(result['frontier_cell_count'], 0)
        self.assertEqual(result['status'], 'NO_FRONTIER')
        self.assertEqual(result['reason'], 'no_cardinal_viewpoint_with_clearance_and_standoff')
        self.assertEqual(result['route_attempts'], 0)

    def test_frontier_in_disconnected_chamber_has_no_route(self):
        grid = Grid(np.full((32, 32), 100, dtype=np.int8), .1, np.array([0., 0.]))
        grid.cells[1:15, 1:9] = 0
        grid.cells[1:19, 16:30] = 0
        grid.cells[19:24, 16:30] = -1
        result = select_frontier(grid, [.45, .75], grid.clearance())
        self.assertEqual(result['status'], 'NO_ROUTE')
        self.assertEqual(result['reason'], 'no_reachable_frontier_viewpoint')
        self.assertGreater(result['route_attempts'], 0)
        self.assertEqual(result['route_attempts'], result['candidate_count'])
        self.assertTrue(all(row['reason'] == 'disconnected_under_route_policy' for row in result['route_rejections']))
        self.assertIsNone(result['goal'])

    def test_unknown_occupied_outside_and_low_clearance_starts_are_refused(self):
        grid = scene()
        grid.cells[5, 5] = 100
        for point, reason in [([1.25, 1.85], 'unknown_cell'), ([.55, .55], 'occupied_cell'),
                              ([-.1, 1], 'outside_grid'), ([.1, 1], 'insufficient_clearance')]:
            with self.subTest(point=point):
                result = select_frontier(grid, point, grid.clearance())
                self.assertEqual(result['status'], 'INVALID_START')
                self.assertEqual(result['reason'], reason)
                self.assertEqual(result['start_validation']['start_check']['map_xy_m'], point)
                self.assertIsNone(result['goal'])
                self.assertEqual(result['route_attempts'], 0)

    def test_equal_goal_displacement_uses_stable_frontier_order(self):
        grid = scene()
        grid.cells[:, 0] = -1
        result = select_frontier(grid, [.85, .85], grid.clearance())
        self.assertEqual(result['status'], 'EXPLORATION_READY')
        self.assertEqual(result['goal']['cell_xy'], [8, 8])
        self.assertEqual(result['goal']['frontier_cell_xy'], [1, 8])
        self.assertAlmostEqual(result['goal']['yaw_rad'], np.pi)

    def test_repeated_selection_preserves_decisions_and_does_not_modify_grid(self):
        grid = scene()
        before = grid.cells.copy()
        results = [select_frontier(grid, [1.25, 1.25], grid.clearance()) for _ in range(2)]
        for result in results:
            result.pop('selection_ms')
            result['start_validation'].pop('planning_ms')
            result['route'].pop('planning_ms')
        self.assertEqual(*results)
        np.testing.assert_array_equal(grid.cells, before)

    def test_nonfinite_start_fails_without_fabricated_proposal(self):
        grid = scene()
        with self.assertRaises(ValueError):
            select_frontier(grid, [float('nan'), 1], grid.clearance())


if __name__ == '__main__':
    unittest.main()
