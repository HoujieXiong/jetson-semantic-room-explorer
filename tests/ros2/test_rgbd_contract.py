"""Run with system ROS Python: python3 -m unittest discover -s tests/ros2 -v."""

import importlib.util
from pathlib import Path
import unittest

import numpy as np
from rclpy.serialization import serialize_message
from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage

spec = importlib.util.spec_from_file_location('contract', Path(__file__).parents[1] / 'check_femto_rosbag.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class TimestampTests(unittest.TestCase):
    def test_skew_and_recording_boundary(self):
        report = contract.paired_timestamps(
            [10_000_000, 43_000_000, 76_000_000, 109_000_000],
            [43_250_000, 76_250_000, 109_250_000])
        self.assertEqual(report['pairs'], 3)
        self.assertEqual(report['absolute_skew_us']['max'], 250)
        self.assertEqual(report['unmatched_color_interior'], 0)

    def test_missing_depth_interior_is_reported(self):
        report = contract.paired_timestamps(
            [10_000_000, 43_000_000, 76_000_000], [10_200_000, 76_200_000])
        self.assertEqual(report['pairs'], 2)
        self.assertEqual(report['unmatched_color_interior'], 1)

    def test_pairing_does_not_reuse_depth(self):
        report = contract.paired_timestamps(
            [10_000_000, 43_000_000, 44_000_000, 76_000_000],
            [10_000_000, 43_500_000, 76_000_000])
        self.assertEqual(report['pairs'], 3)
        self.assertEqual(report['unmatched_color_interior'], 1)

    def test_disjoint_intervals_fail(self):
        with self.assertRaisesRegex(ValueError, 'share a time interval'):
            contract.paired_timestamps([10, 20], [40, 50])


class DepthContractTests(unittest.TestCase):
    def setUp(self):
        self.check = contract.ContractCheck()
        self.message = Image()
        self.message.header.frame_id = contract.OPTICAL_FRAME
        self.message.header.stamp.sec = 1
        self.message.width, self.message.height = 1280, 720
        self.message.encoding, self.message.step = '16UC1', 2560
        self.message.data = np.full((720, 1280), 2350, dtype='<u2').tobytes()

    def add(self):
        self.check.add('/camera/depth/image_raw', serialize_message(self.message), 1)

    def test_millimeters_and_invalid_zero(self):
        pixels = np.full((720, 1280), 2350, dtype='<u2')
        pixels[:100] = 0
        self.message.data = pixels.tobytes()
        self.add()
        self.assertEqual(self.check.depth_centers, [2.35])
        self.assertAlmostEqual(self.check.depth_coverage[0], 620 / 720)

    def test_duplicate_timestamp_fails(self):
        self.add()
        with self.assertRaisesRegex(ValueError, 'Non-increasing'):
            self.add()

    def test_source_resolution_is_not_registered_color_grid(self):
        self.message.width, self.message.height = 640, 576
        with self.assertRaisesRegex(ValueError, 'pixel grid'):
            self.add()

    def test_depth_optical_frame_is_not_color_optical_frame(self):
        self.message.header.frame_id = 'camera_depth_optical_frame'
        with self.assertRaisesRegex(ValueError, 'optical frame'):
            self.add()

    def test_empty_wall_roi_fails(self):
        pixels = np.full((720, 1280), 2350, dtype='<u2')
        pixels[350:370, 630:650] = 0
        self.message.data = pixels.tobytes()
        with self.assertRaisesRegex(ValueError, 'no valid depth'):
            self.add()

    def test_room_walk_retains_empty_center_without_fabricating_distance(self):
        self.check = contract.ContractCheck('room-walk')
        pixels = np.full((720, 1280), 1500, dtype='<u2')
        pixels[350:370, 630:650] = 0
        self.message.data = pixels.tobytes()
        self.add()
        self.assertEqual(self.check.depth_centers, [])
        self.assertEqual(self.check.depth_empty_centers, 1)
        self.assertAlmostEqual(self.check.depth_coverage[0], 1 - 400 / (720 * 1280))


class CompleteContractTests(unittest.TestCase):
    def test_non_unit_tf_is_rejected(self):
        transform = TransformStamped()
        transform.header.frame_id = 'camera_link'
        transform.child_frame_id = contract.OPTICAL_FRAME
        transform.transform.rotation.w = 0.999275748
        with self.assertRaisesRegex(ValueError, 'not normalized'):
            contract.ContractCheck().add('/tf_static', serialize_message(TFMessage(transforms=[transform])), 1)

    def sample(self, depth_mm=2350, depth_fx=1000.0, color_count=10, scene='fixed-wall'):
        check = contract.ContractCheck(scene)
        transform = TransformStamped()
        transform.header.frame_id = 'camera_link'
        transform.child_frame_id = contract.OPTICAL_FRAME
        transform.transform.rotation.w = 1.0
        check.add('/tf_static', serialize_message(TFMessage(transforms=[transform])), 1)
        for stream in ('color', 'depth'):
            image = Image()
            image.width, image.height = 1280, 720
            image.header.frame_id = contract.OPTICAL_FRAME
            image.encoding = 'rgb8' if stream == 'color' else '16UC1'
            image.step = 3840 if stream == 'color' else 2560
            image.data = (np.zeros((720, 1280, 3), dtype=np.uint8) if stream == 'color'
                          else np.full((720, 1280), depth_mm, dtype='<u2')).tobytes()
            info = CameraInfo()
            info.width, info.height = 1280, 720
            info.distortion_model = 'rational_polynomial'
            info.d = [0.0] * 8
            info.k = [depth_fx if stream == 'depth' else 1000.0, 0.0, 640.0,
                      0.0, 1000.0, 360.0, 0.0, 0.0, 1.0]
            for index in range(color_count if stream == 'color' else 10):
                image.header.stamp.sec = 1
                image.header.stamp.nanosec = index * 33_333_333 + (250_000 if stream == 'depth' else 0)
                info.header = image.header
                check.add(f'/camera/{stream}/image_raw', serialize_message(image), 1 + index * 33_333_333)
                check.add(f'/camera/{stream}/camera_info', serialize_message(info), 1 + index * 33_333_333)
        return check

    def test_complete_contract_resolves_static_tf_at_image_times(self):
        report = self.sample().finish()
        self.assertEqual(report['status'], 'PASSED')
        self.assertEqual(report['synchronization']['pairs'], 10)

    def test_meter_counts_cannot_masquerade_as_millimeters(self):
        with self.assertRaisesRegex(ValueError, 'Millimeter depth interpretation'):
            self.sample(depth_mm=2).finish()

    def test_same_grid_with_different_calibration_fails(self):
        with self.assertRaisesRegex(ValueError, 'CameraInfo disagree'):
            self.sample(depth_fx=900.0).finish()

    def test_stream_stall_is_not_excused_as_a_recording_boundary(self):
        with self.assertRaisesRegex(ValueError, 'Too many unmatched RGB-D'):
            self.sample(color_count=20).finish()

    def test_room_walk_accepts_distance_outside_original_wall_range(self):
        report = self.sample(depth_mm=4500, scene='room-walk').finish()
        self.assertEqual(report['depth_center_m']['median'], 4.5)
        self.assertFalse(report['fixed_wall_unit_check'])
        with self.assertRaisesRegex(ValueError, 'Millimeter depth interpretation'):
            self.sample(depth_mm=4500).finish()

    def test_room_walk_rejects_recording_with_no_valid_depth(self):
        with self.assertRaisesRegex(ValueError, 'no valid depth'):
            self.sample(depth_mm=0, scene='room-walk').finish()

    def test_room_walk_still_rejects_calibration_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'CameraInfo disagree'):
            self.sample(depth_fx=900.0, scene='room-walk').finish()


if __name__ == '__main__':
    unittest.main()
