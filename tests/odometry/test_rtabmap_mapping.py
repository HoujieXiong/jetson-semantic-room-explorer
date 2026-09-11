"""Mapping acceptance checks using timestamped ROS messages and real TF math."""
from pathlib import Path
import math
import sys
import unittest

from geometry_msgs.msg import Pose, TransformStamped
from rclpy.serialization import serialize_message
from rtabmap_msgs.msg import Info, MapGraph
from sensor_msgs.msg import CameraInfo
from tf2_msgs.msg import TFMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_rtabmap_mapping import MappingCheck, match_source_stamp


class MappingContractTests(unittest.TestCase):
    def setUp(self):
        self.check = MappingCheck()
        self.reference = {'topics': {}}
        for stream, ns in (('color', 2_000_000), ('depth', 0)):
            message = CameraInfo()
            message.header.stamp.sec = 2
            message.header.stamp.nanosec = ns
            self.check.camera_info(stream, serialize_message(message))
            self.reference['topics'][f'/camera/{stream}/camera_info'] = {
                'count': 1, 'serialized_sha256': self.check.camera_hashes[stream].hexdigest()}
        self.check.info = [{'stamp_ns': 2_002_000_000, 'lost': False,
                            'processing_s': 0.1, 'inliers': 30}]
        self.check.poses = [{'stamp_ns': 2_002_000_000, 'position_m': [1, 0, 0],
                             'quaternion_xyzw': [0, 0, 0, 1], 'covariance_diagonal': [0.01]*6}]
        self.check.clock_stamps = [2_000_000_000, 2_002_000_000]
        self.add_tf('odom', 'camera_link', 1.0)
        self.add_tf('camera_link', 'camera_color_optical_frame', 0.2, static=True)
        self.add_tf('map', 'odom', 3.0, yaw=math.pi/2)
        info = Info()
        info.header.frame_id = 'map'
        info.header.stamp.sec = 2
        info.header.stamp.nanosec = 2_000_000
        info.ref_id = 1
        self.check.mapping_stats(info)
        graph = MapGraph()
        graph.header = info.header
        graph.map_to_odom.rotation.w = 1.0
        graph.poses_id = [1]
        pose = Pose()
        pose.orientation.w = 1.0
        graph.poses = [pose]
        self.check.map_graph(graph)

    def add_tf(self, parent, child, x, yaw=0.0, static=False, ns=2_000_000):
        transform = TransformStamped()
        transform.header.frame_id = parent
        transform.child_frame_id = child
        transform.header.stamp.sec = 2
        transform.header.stamp.nanosec = ns
        transform.transform.translation.x = x
        transform.transform.rotation.z = math.sin(yaw/2)
        transform.transform.rotation.w = math.cos(yaw/2)
        self.check.transforms(TFMessage(transforms=[transform]), static)

    def test_map_optical_pose_composes_rotation_and_translation(self):
        result = self.check.finish(self.reference)
        observation = result['mapping']['validated_map_observations'][0]
        self.assertAlmostEqual(observation['position_m'][0], 3.0)
        self.assertAlmostEqual(observation['position_m'][1], 1.2)
        self.assertAlmostEqual(observation['position_m'][2], 0.0)
        self.assertEqual(result['mapping']['reported_loop_closures'], 0)

    def test_mapped_lost_pose_is_rejected(self):
        self.check.info[0]['lost'] = True
        self.check.poses[0]['quaternion_xyzw'] = [0]*4
        with self.assertRaisesRegex(ValueError, 'no tracked source pose'):
            self.check.finish(self.reference)

    def test_map_observation_must_keep_source_stamp(self):
        self.check.mapping_info[0]['stamp_ns'] += 1_000_000
        with self.assertRaisesRegex(ValueError, 'no tracked source pose'):
            self.check.finish(self.reference)

    def test_epoch_float_roundtrip_keeps_the_original_source_stamp(self):
        source = 1789080202178160000
        self.assertEqual(match_source_stamp(1789080202178160191, [source]), source)

    def test_precision_allowance_does_not_accept_microsecond_offset(self):
        source = 1789080202178160000
        with self.assertRaisesRegex(ValueError, 'timestamp precision'):
            match_source_stamp(source+1000, [source])

    def test_map_tf_at_other_time_is_not_a_valid_observation(self):
        self.check.tf.clear()
        self.add_tf('odom', 'camera_link', 1.0)
        self.add_tf('camera_link', 'camera_color_optical_frame', 0.2, static=True)
        self.add_tf('map', 'odom', 3.0, ns=3_000_000)
        with self.assertRaisesRegex(ValueError, 'timestamped map-to-camera TF'):
            self.check.finish(self.reference)

    def test_empty_map_does_not_pass_on_odometry_alone(self):
        self.check.graphs = []
        with self.assertRaisesRegex(ValueError, 'No nonempty mapping graph'):
            self.check.finish(self.reference)

    def test_unexpected_tf_publisher_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected dynamic TF'):
            self.add_tf('world', 'odom', 0.0)

    def test_null_map_transform_is_rejected(self):
        transform = TransformStamped()
        transform.header.frame_id = 'map'
        transform.child_frame_id = 'odom'
        transform.transform.rotation.w = 0.0
        with self.assertRaisesRegex(ValueError, 'not normalized'):
            self.check.transforms(TFMessage(transforms=[transform]), False)

    def test_incomplete_report_retains_mapping_evidence(self):
        evidence = self.check.incomplete_evidence()
        self.assertEqual(evidence['mapping_info'][0]['node_id'], 1)
        self.assertEqual(len(evidence['map_graphs']), 1)


if __name__ == '__main__':
    unittest.main()
