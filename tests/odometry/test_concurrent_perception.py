"""Real ROS synchronization/TF with a controlled inference future at the GPU boundary."""

from concurrent.futures import Future
import copy
from pathlib import Path
import sys
import unittest

import numpy as np
from rclpy.serialization import serialize_message
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_concurrent_perception import ConcurrentCheck
import test_rtabmap_mapping as mapping_tests


class ControlledExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, function, *args):
        future = Future()
        self.calls.append((args, future))
        return future


class ConcurrentPerceptionTests(unittest.TestCase):
    def setUp(self):
        self.executor = ControlledExecutor()
        self.check = ConcurrentCheck(None, self.executor)
        self.now = 0.0
        self.check.elapsed = lambda: self.now
        fixture = mapping_tests.MappingContractTests()
        fixture.setUp()
        self.check.tf = fixture.check.tf
        self.check.dynamic_tf = fixture.check.dynamic_tf
        self.stamp = 2_002_000_000
        self.check.odom_by_stamp[self.stamp] = {**fixture.check.info[0], 'received_elapsed_s': 0.0}
        self.calibration = {'width': 1280, 'height': 720, 'distortion_model': 'plumb_bob',
                            'k': [1000., 0., 640., 0., 1000., 360., 0., 0., 1.],
                            'd': [0.]*5, 'r': np.eye(3).flatten().tolist(),
                            'p': [1000., 0., 640., 0., 0., 1000., 360., 0., 0., 0., 1., 0.]}
        for stream in ('color', 'depth'):
            self.check.sensor.calibration[f'/camera/{stream}/camera_info'] = copy.deepcopy(self.calibration)

    def messages(self, offset=0):
        messages = []
        for kind, delta in ((Image, 2_000_000), (Image, 0), (CameraInfo, 2_000_000), (CameraInfo, 0)):
            m = kind()
            m.header.frame_id = 'camera_color_optical_frame'
            m.header.stamp.sec = 2
            m.header.stamp.nanosec = delta+offset
            m.width, m.height = 1280, 720
            if kind is CameraInfo:
                for key in ('distortion_model', 'd', 'k', 'r', 'p'):
                    setattr(m, key, self.calibration[key])
            else:
                m.encoding, m.step = ('rgb8', 3840) if delta else ('16UC1', 2560)
                m.data = (np.ones((720, 1280, 3), np.uint8) if delta else np.full((720, 1280), 2000, '<u2')).tobytes()
            messages.append(m)
        return messages

    def offer(self, offset=0):
        self.check.pair(*self.messages(offset))

    def finish_prediction(self):
        self.executor.calls[-1][1].set_result({'detections': []})
        self.check.pump()

    def test_online_pose_is_exact_and_frozen_at_result_finalization(self):
        self.offer()
        self.check.pump()
        row = self.check.rows[0]
        self.assertNotIn('pose', row)
        self.now = .1
        self.finish_prediction()
        np.testing.assert_allclose(row['pose']['position_m'], [3., 1.2, 0.], atol=1e-12)
        self.assertEqual(row['pose']['source_stamp_ns'], self.stamp)
        original = copy.deepcopy(row['pose'])
        self.check.tf.clear()
        self.check.pump()
        self.assertEqual(row['status'], 'PROCESSED')
        self.assertEqual(row['pose'], original)
        self.assertAlmostEqual(row['arrival_to_result_ms'], 100.)

    def test_one_worker_one_pending_and_explicit_overflow(self):
        self.offer()
        self.check.pump()
        self.offer(60_000_000)
        self.offer(120_000_000)
        self.check.pump()
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual([r['status'] for r in self.check.rows], ['PROCESSING', 'QUEUED', 'DROPPED'])
        self.assertEqual(self.check.rows[2]['reason'], 'pending_queue_full')

    def test_lost_tracking_never_uses_available_tf(self):
        self.check.odom_by_stamp[self.stamp]['lost'] = True
        self.offer()
        self.check.pump()
        self.finish_prediction()
        self.assertEqual(self.check.rows[0]['pose']['reason'], 'tracking_lost')
        self.assertIsNone(self.executor.calls[0][0][-1])
        self.assertNotIn('map_from_camera', self.check.rows[0]['pose'])

    def test_missing_odometry_waits_then_rejects_without_latest_pose(self):
        self.check.odom_by_stamp.clear()
        self.offer()
        self.check.pump()
        self.finish_prediction()
        self.assertEqual(self.check.rows[0]['status'], 'AWAITING_POSE')
        self.now = 2.001
        self.check.pump()
        self.assertEqual(self.check.rows[0]['pose']['reason'], 'missing_source_odometry')
        self.assertIsNone(self.executor.calls[0][0][-1])

    def test_tf_can_arrive_within_bounded_wait(self):
        original = self.check.tf
        self.check.tf = Buffer()
        self.offer()
        self.check.pump()
        self.finish_prediction()
        self.assertEqual(self.check.rows[0]['status'], 'AWAITING_POSE')
        self.now = .5
        self.check.tf = original
        self.check.pump()
        self.assertEqual(self.check.rows[0]['pose']['status'], 'ACCEPTED')

    def test_missing_tf_is_explicit_after_deadline(self):
        self.check.tf.clear()
        self.offer()
        self.check.pump()
        self.finish_prediction()
        self.now = 2.001
        self.check.pump()
        self.assertEqual(self.check.rows[0]['pose']['reason'], 'missing_source_map_tf')
        self.assertIsNone(self.executor.calls[0][0][-1])

    def test_waiting_for_pose_does_not_block_next_gpu_job(self):
        self.check.tf.clear()
        self.offer()
        self.check.pump()
        self.finish_prediction()
        self.offer(60_000_000)
        self.check.pump()
        self.assertEqual(len(self.executor.calls), 2)
        self.assertEqual([r['status'] for r in self.check.rows], ['AWAITING_POSE', 'PROCESSING'])

    def test_pose_result_queue_is_bounded_and_times_out(self):
        self.check.odom_by_stamp.clear()
        for index in range(8):
            self.offer(index*60_000_000)
            self.check.pump()
            self.finish_prediction()
        self.offer(8*60_000_000)
        self.check.pump()
        self.assertEqual(len(self.executor.calls), 8)
        self.assertEqual(len(self.check.awaiting_pose), 8)
        self.offer(9*60_000_000)
        self.assertEqual(self.check.rows[-1]['status'], 'DROPPED')
        self.now = 2.001
        self.check.pump()
        self.assertEqual(len(self.check.awaiting_pose), 0)
        self.assertEqual(len(self.executor.calls), 9)
        self.assertTrue(all(row['pose']['reason'] == 'missing_source_odometry' for row in self.check.rows[:8]))

    def test_worker_failure_is_retained_and_reraised(self):
        self.offer()
        self.check.pump()
        self.executor.calls[0][1].set_exception(RuntimeError('Injected CUDA failure'))
        with self.assertRaisesRegex(RuntimeError, 'CUDA failure'):
            self.check.pump()
        self.assertEqual(self.check.rows[0]['status'], 'FAILED')
        self.assertEqual(self.check.evidence()['counts']['FAILED'], 1)

    def test_unfinished_work_cannot_pass_measurement(self):
        self.offer()
        with self.assertRaisesRegex(RuntimeError, 'Pending perception work'):
            self.check.finish({})

    def test_real_synchronizer_accepts_reordered_arrival_without_inference(self):
        messages = self.messages()
        topics = list(self.check.filters)
        for index in (3, 1, 2, 0):
            self.check.ingest(topics[index], serialize_message(messages[index]))
        self.assertEqual(len(self.check.rows), 1)
        self.assertEqual(self.check.rows[0]['source_stamp_ns'], self.stamp)
        self.assertEqual(self.executor.calls, [])

    def test_mismatched_image_info_and_calibration_fail(self):
        messages = self.messages()
        messages[2].header.stamp.nanosec += 1
        with self.assertRaisesRegex(ValueError, 'exact CameraInfo'):
            self.check.pair(*messages)
        self.check.sensor.calibration['/camera/depth/camera_info']['k'][0] += 1
        with self.assertRaisesRegex(ValueError, 'calibration differs'):
            self.offer()

    def test_nonrectified_calibration_and_duplicate_pairs_fail(self):
        self.offer()
        with self.assertRaisesRegex(ValueError, 'timestamps must increase'):
            self.offer()
        for value in self.check.sensor.calibration.values():
            value['d'][0] = .1
        with self.assertRaisesRegex(ValueError, 'rectified pinhole'):
            self.offer(60_000_000)


if __name__ == '__main__':
    unittest.main()
