"""Run using the isolated RTAB-Map environment."""
from pathlib import Path
import copy
import sys
import unittest

from rclpy.serialization import deserialize_message, serialize_message
from sensor_msgs.msg import CameraInfo, Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_rtabmap_odometry import OdomCheck, check_pose, lost_intervals
from check_femto_rosbag import comparison_key, message_content_bytes


class MessageIdentityTests(unittest.TestCase):
    def test_padding_is_not_message_content(self):
        message = CameraInfo()
        payload = serialize_message(message)
        self.assertEqual(message_content_bytes(message), message_content_bytes(
            deserialize_message(payload + b'\x00\x00\x00', CameraInfo)))

    def test_all_calibration_fields_and_timestamps_count(self):
        original = CameraInfo()
        variants = []
        for field, value in [('binning_x', 2), ('distortion_model', 'plumb_bob')]:
            changed = copy.deepcopy(original)
            setattr(changed, field, value)
            variants.append(changed)
        changed = copy.deepcopy(original)
        changed.k[0] = 500.
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed.roi.x_offset = 1
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed.header.stamp.nanosec = 1
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed.header.frame_id = 'other'
        variants.append(changed)
        for changed in variants:
            self.assertNotEqual(message_content_bytes(original), message_content_bytes(changed))

    def test_image_pixels_and_layout_count(self):
        original = Image(height=1, width=1, encoding='rgb8', step=3, data=[1, 2, 3])
        for field, value in [('data', [1, 2, 4]), ('encoding', 'bgr8'), ('step', 4),
                             ('width', 2), ('height', 2), ('is_bigendian', 1)]:
            changed = copy.deepcopy(original)
            setattr(changed, field, value)
            self.assertNotEqual(message_content_bytes(original), message_content_bytes(changed))

    def test_default_identity_stays_serialized_and_unknown_mode_fails(self):
        self.assertEqual(comparison_key({}), 'serialized_sha256')
        with self.assertRaisesRegex(ValueError, 'Unknown replay'):
            comparison_key({'wire_comparison': 'unchecked'})


class OdometryEvidenceTests(unittest.TestCase):
    def test_lost_span_includes_time_until_recovery(self):
        rows = [{'stamp_ns': index*1_000_000_000, 'lost': lost}
                for index, lost in enumerate([False, True, True, False])]
        self.assertEqual(lost_intervals(rows, 4_000_000_000),
                         [{'start_ns': 1_000_000_000, 'end_ns': 3_000_000_000, 'duration_s': 2.0}])

    def test_unrecovered_span_ends_at_input_end(self):
        rows = [{'stamp_ns': 1_000_000_000, 'lost': True}]
        self.assertEqual(lost_intervals(rows, 5_000_000_000)[0]['duration_s'], 4.0)

    def test_success_does_not_create_loss(self):
        self.assertEqual(lost_intervals([{'stamp_ns': 1, 'lost': False}], 2), [])

    def test_null_pose_is_allowed_only_when_lost(self):
        row = {'position_m': [0, 0, 0], 'quaternion_xyzw': [0, 0, 0, 0], 'covariance_diagonal': [9999]*6}
        check_pose(row, True)
        with self.assertRaisesRegex(ValueError, 'not normalized'):
            check_pose(row, False)

    def test_valid_pose_is_not_a_null_lost_pose(self):
        row = {'position_m': [1, 2, 3], 'quaternion_xyzw': [0, 0, 0, 1], 'covariance_diagonal': [0.01]*6}
        check_pose(row, False)
        with self.assertRaisesRegex(ValueError, 'null quaternion'):
            check_pose(row, True)

    def test_nonfinite_pose_is_rejected_even_when_lost(self):
        row = {'position_m': [float('nan'), 0, 0], 'quaternion_xyzw': [0]*4, 'covariance_diagonal': [9999]*6}
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            check_pose(row, True)


class OdometryContractTests(unittest.TestCase):
    def setUp(self):
        self.check = OdomCheck()
        self.reference = {'topics': {}}
        for stream, ns in (('color', 2_000_000), ('depth', 0)):
            message = CameraInfo()
            message.header.stamp.sec = 2
            message.header.stamp.nanosec = ns
            self.check.camera_info(stream, serialize_message(message))
            self.reference['topics'][f'/camera/{stream}/camera_info'] = {
                'count': 1, 'serialized_sha256': self.check.camera_hashes[stream].hexdigest()}
        self.check.info = [{'stamp_ns': 2_002_000_000, 'lost': True,
                            'processing_s': 0.1, 'inliers': 0}]
        self.check.poses = [{'stamp_ns': 2_002_000_000, 'position_m': [0]*3,
                             'quaternion_xyzw': [0]*4, 'covariance_diagonal': [9999]*6}]
        self.check.clock_stamps = [2_000_000_000, 2_002_000_000]

    def test_complete_tracking_loss_remains_explicit(self):
        result = self.check.finish(self.reference)
        self.assertEqual(result['status'], 'MEASURED')
        self.assertEqual(result['tracked_frames'], 0)
        self.assertEqual(result['lost_fraction_of_processed'], 1)
        self.assertIsNone(result['last_tracked_offset_s'])

    def test_output_must_use_later_input_stamp(self):
        self.check.info[0]['stamp_ns'] = 2_000_000_000
        self.check.poses[0]['stamp_ns'] = 2_000_000_000
        with self.assertRaisesRegex(ValueError, 'source image stamp'):
            self.check.finish(self.reference)

    def test_altered_replay_is_rejected(self):
        self.check.camera_hashes['color'].update(b'altered')
        with self.assertRaisesRegex(ValueError, 'differs from the verified bag'):
            self.check.finish(self.reference)

    def test_explicit_content_identity_accepts_padding_but_rejects_fields(self):
        self.reference['wire_comparison'] = 'message_content_sha256'
        for stream in ('color', 'depth'):
            self.reference['topics'][f'/camera/{stream}/camera_info']['message_content_sha256'] = (
                self.check.camera_content_hashes[stream].hexdigest())
        self.check.camera_hashes['color'].update(b'padding')
        self.assertEqual(self.check.finish(self.reference)['status'], 'MEASURED')
        self.check.camera_content_hashes['color'].update(b'changed field')
        with self.assertRaisesRegex(ValueError, 'differs from the verified bag'):
            self.check.finish(self.reference)

    def test_clock_must_advance(self):
        self.check.clock_stamps = [2_000_000_000]*2
        with self.assertRaisesRegex(ValueError, 'advancing simulated clock'):
            self.check.finish(self.reference)

    def test_live_source_needs_no_bag_or_simulated_clock(self):
        self.check.clock_stamps = []
        result = self.check.finish(None)
        self.assertIsNone(result['reference_pairs'])
        self.assertEqual(result['received_pairs'], 1)
        with self.assertRaisesRegex(ValueError, 'advancing simulated clock'):
            self.check.finish(self.reference)

    def test_live_source_rejects_simulated_clock_and_missing_camera(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected simulated clock'):
            self.check.finish(None)
        self.check.clock_stamps = []
        self.check.camera_stamps['color'] = []
        with self.assertRaisesRegex(ValueError, 'CameraInfo timestamps'):
            self.check.finish(None)

    def test_live_source_still_requires_source_stamp_and_tf(self):
        self.check.clock_stamps = []
        self.check.info[0]['stamp_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'No source-matched'):
            self.check.finish(None)
        self.check.info[0]['stamp_ns'] -= 1
        self.check.info[0]['lost'] = False
        self.check.poses[0]['quaternion_xyzw'] = [0, 0, 0, 1]
        with self.assertRaisesRegex(ValueError, 'Missing TF'):
            self.check.finish(None)

    def test_live_unmatched_pose_is_counted_and_never_validated_as_tracked(self):
        self.check.clock_stamps = []
        extra = copy.deepcopy(self.check.poses[0])
        extra['stamp_ns'] += 66_000_000
        self.check.poses.append(extra)
        result = self.check.finish(None)
        self.assertFalse(result['contract_checks_passed'])
        self.assertEqual(result['unmatched_odometry_stamps']['pose_without_info'], [extra['stamp_ns']])
        self.assertEqual(result['processed_frames'], 1)
        self.assertEqual(len(result['trajectory']), 1)
        self.assertEqual(result['received_odometry_messages'], 2)
        with self.assertRaisesRegex(ValueError, 'unmatched'):
            self.check.finish(self.reference)

    def test_missing_output_is_rejected(self):
        self.check.poses = []
        with self.assertRaisesRegex(ValueError, 'unmatched'):
            self.check.finish(self.reference)

    def test_tracked_pose_requires_timestamped_tf(self):
        self.check.info[0]['lost'] = False
        self.check.poses[0]['quaternion_xyzw'] = [0, 0, 0, 1]
        with self.assertRaisesRegex(ValueError, 'Missing TF'):
            self.check.finish(self.reference)


if __name__ == '__main__':
    unittest.main()
