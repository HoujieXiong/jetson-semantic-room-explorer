"""Use actual search fixtures and ROS message serialization at the publication boundary."""

import json
import math
import unittest

from test_run_offline_search import SearchFixture
from publish_search_preview import messages, run, select_preview
from run_offline_search import run_search


class PreviewSelectionTests(SearchFixture):
    def select(self, label='chair', **start):
        if not start:
            start = {'simulated_xy': [1.05, 1.55]}
        search = run_search(self.memory, self.mapping, label, self.output, **start)
        return select_preview(search, self.output)

    def test_multiple_candidates_select_shortest_then_id_keep_all(self):
        decision = self.select()
        ready = [row for row in decision['outcomes'] if row['status'] == 'ROUTE_READY']
        self.assertEqual(len(ready), 2)
        self.assertEqual(decision['selection']['object_id'],
                         min(ready, key=lambda row: (row['length_m'], row['object_id']))['object_id'])
        self.assertTrue(decision['dry_run'])
        self.assertFalse(decision['motion_executed'])

    def test_frontier_retains_view_direction_and_does_not_invent_object(self):
        decision = self.select('backpack')
        self.assertEqual(decision['search_status'], 'EXPLORATION_READY')
        self.assertIsNone(decision['selection']['object_id'])
        self.assertIn('frontier_id', decision['selection']['goal'])

    def test_invalid_camera_start_has_no_pose_or_path(self):
        for label in ('chair', 'backpack'):
            self.output = self.root/label
            decision = self.select(label, node_id=1)
            self.assertIsNone(decision['selection'])
            self.assertEqual(decision['start']['map_xy_m'], [.15, 3.55])

    def test_changed_stage_fails_before_any_publication(self):
        search = run_search(self.memory, self.mapping, 'chair', self.output, simulated_xy=[1.05, 1.55])
        (self.output/'route/route.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'stage changed'):
            select_preview(search, self.output)

    def test_waits_are_finite_bounded_and_rejected_before_output(self):
        for duration, timeout in [(0, 1), (61, 1), (1, float('nan')), (1, 0), (1, 61)]:
            with self.assertRaises(ValueError):
                run(self.memory, self.mapping, 'chair', self.output, simulated_xy=[1, 1],
                    duration_s=duration, subscriber_timeout_s=timeout)
        self.assertFalse(self.output.exists())


class RosMessageTests(unittest.TestCase):
    def test_serialized_metric_path_goal_yaw_and_publication_timestamp(self):
        from builtin_interfaces.msg import Time
        from rclpy.serialization import deserialize_message, serialize_message
        decision = {'selection': {'goal': {'map_xy_m': [2., 3.], 'yaw_rad': math.pi},
                                  'route': {'path_map_xy_m': [[2., 2.], [2., 3.]]}}}
        result = messages(decision, Time(sec=10, nanosec=123))
        for key, value in result.items():
            result[key] = deserialize_message(serialize_message(value), type(value))
        self.assertEqual(json.loads(result['decision'].data)['publication_stamp_ns'], 10_000_000_123)
        goal, path = result['goal'], result['path']
        self.assertEqual(goal.header.frame_id, 'map')
        self.assertEqual(goal.header, path.header)
        self.assertEqual((goal.pose.position.x, goal.pose.position.y, goal.pose.position.z), (2, 3, 0))
        self.assertAlmostEqual(goal.pose.orientation.z, 1)
        self.assertAlmostEqual(goal.pose.orientation.w, 0)
        self.assertEqual(path.poses[-1], goal)
        self.assertAlmostEqual(path.poses[0].pose.orientation.z, math.sqrt(.5))
        self.assertTrue(all(p.header == goal.header for p in path.poses))

    def test_zero_length_frontier_keeps_goal_orientation(self):
        from builtin_interfaces.msg import Time
        result = messages({'selection': {'goal': {'map_xy_m': [1., 2.], 'yaw_rad': -math.pi/2},
                                         'route': {'path_map_xy_m': [[1., 2.]]}}}, Time(sec=1))
        self.assertEqual(result['path'].poses, [result['goal']])
        self.assertAlmostEqual(result['goal'].pose.orientation.z, -math.sqrt(.5))

    def test_refusal_publishes_decision_only(self):
        from builtin_interfaces.msg import Time
        self.assertEqual(set(messages({'selection': None}, Time(sec=1))), {'decision'})


if __name__ == '__main__':
    unittest.main()
