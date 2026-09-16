"""Known metric points, invalid depth and observation timestamp failure cases."""

import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from observe_rgbd_objects import INFERENCE, depth_observation, inference_config, source_association
from rgbd_geometry import map_from_camera


class ObjectObservationTests(unittest.TestCase):
    def setUp(self):
        self.depth = np.full((20, 20), 2000, dtype=np.uint16)
        self.k = [100, 0, 10, 0, 100, 10, 0, 0, 1]
        self.box = [0, 0, 20, 20]

    def observe(self):
        return depth_observation(self.depth, self.k, self.box)

    def test_explicit_detector_sizes_preserve_default_and_reject_unsupported_values(self):
        self.assertEqual(inference_config(), INFERENCE)
        large = inference_config(1280)
        self.assertEqual(large, {'imgsz': 1280, 'confidence_threshold': .25, 'device': 'cuda:0'})
        large['confidence_threshold'] = .1
        self.assertEqual(INFERENCE, {'imgsz': 640, 'confidence_threshold': .25, 'device': 'cuda:0'})
        for size in (0, 641, 1920, True, 1280., '1280', None):
            with self.assertRaises(ValueError):
                inference_config(size)

    def test_center_pixel_has_metric_optical_depth(self):
        result = self.observe()
        self.assertEqual(result['status'], 'ACCEPTED')
        self.assertEqual(result['roi_xyxy_exclusive'], [5, 5, 15, 15])
        self.assertEqual(result['pixel_uv'], [10, 10])
        self.assertEqual(result['camera_point_m'], [0, 0, 2])
        self.assertEqual(result['valid_pixels'], 100)

    def test_off_axis_point_and_map_rotation_translation(self):
        self.k = [10, 0, 5, 0, 20, 10, 0, 0, 1]
        result = self.observe()
        np.testing.assert_allclose(result['camera_point_m'], [1, 0, 2])
        transform = map_from_camera([3, 4, 5], [0, 0, np.sqrt(0.5), np.sqrt(0.5)])
        np.testing.assert_allclose(transform@[*result['camera_point_m'], 1], [3, 5, 7, 1])

    def test_mad_rejects_far_depth_when_majority_is_constant(self):
        self.depth[5, 5:15] = 4500
        result = self.observe()
        self.assertEqual(result['rejected_outlier_pixels'], 10)
        self.assertEqual(result['inlier_pixels'], 90)
        self.assertEqual(result['depth_m'], 2)

    def test_selected_point_uses_an_actual_valid_source_pixel(self):
        self.depth[10, 10] = 0
        result = self.observe()
        u, v = result['pixel_uv']
        self.assertNotEqual([u, v], [10, 10])
        self.assertEqual(result['depth_m']*1000, self.depth[v, u])

    def test_empty_depth_is_rejected_with_evidence(self):
        self.depth[:] = 0
        result = self.observe()
        self.assertEqual(result['reason'], 'insufficient_valid_depth')
        self.assertEqual(result['invalid_zero_pixels'], 100)
        self.assertNotIn('camera_point_m', result)

    def test_sparse_valid_depth_is_rejected(self):
        self.depth[:] = 0
        self.depth[5:7, 5:15] = 2000
        result = self.observe()
        self.assertEqual(result['valid_pixels'], 20)
        self.assertEqual(result['reason'], 'insufficient_valid_depth')

    def test_range_limit_is_exclusive(self):
        self.depth[:] = 5000
        result = self.observe()
        self.assertEqual(result['out_of_range_pixels'], 100)
        self.assertEqual(result['status'], 'REJECTED')

    def test_mixed_foreground_background_spread_is_rejected(self):
        self.depth[10:15, 5:15] = 3000
        self.assertEqual(self.observe()['reason'], 'depth_spread_too_large')

    def test_off_image_box_has_no_fabricated_point(self):
        self.box = [30, 30, 40, 40]
        self.assertEqual(self.observe()['reason'], 'empty_inner_roi')

    def test_float_meter_depth_cannot_be_read_as_raw_millimeters(self):
        self.depth = self.depth.astype(float)/1000
        with self.assertRaisesRegex(ValueError, 'uint16 millimeter'):
            self.observe()

    def test_invalid_intrinsics_and_box_are_not_silent_rejections(self):
        self.k[0] = 0
        with self.assertRaisesRegex(ValueError, 'intrinsics'):
            self.observe()
        self.k[0] = 100
        self.box[0] = float('nan')
        with self.assertRaisesRegex(ValueError, 'detection box'):
            self.observe()

    def test_source_association_rejects_stale_info_and_wrong_map_stamp(self):
        source = 1789080208207783000
        row = {'source_stamp_ns': source, 'messages': {}}
        for stream, stamp in [('color', source), ('depth', source-1_186_000)]:
            for kind in ('image_raw', 'camera_info'):
                row['messages'][f'/camera/{stream}/{kind}'] = {'stamp_ns': stamp}
        self.assertEqual(source_association(row)['rgb_depth_skew_ns'], 1_186_000)
        bad = copy.deepcopy(row)
        bad['messages']['/camera/color/camera_info']['stamp_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'CameraInfo'):
            source_association(bad)
        bad = copy.deepcopy(row)
        bad['source_stamp_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'mapped source timestamp'):
            source_association(bad)
        for kind in ('image_raw', 'camera_info'):
            row['messages'][f'/camera/depth/{kind}']['stamp_ns'] -= 5_000_000
        with self.assertRaisesRegex(ValueError, 'mapped source timestamp'):
            source_association(row)


if __name__ == '__main__':
    unittest.main()
