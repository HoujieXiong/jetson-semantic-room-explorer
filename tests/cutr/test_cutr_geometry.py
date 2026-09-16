"""Known gravity, calibrated resize, units and cuboid transformations for the CuTR adapter."""

import itertools
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from benchmark_cutr import assumed_gravity, benchmark, femto_sample, predictions
from cubifyanything.boxes import GeneralInstance3DBoxes
from cubifyanything.instances import Instances3D


def upright():
    result = np.eye(4)
    result[:3, :3] = [[0, 0, 1], [-1, 0, 0], [0, -1, 0]]
    return result


class GravityTests(unittest.TestCase):
    def test_level_camera_has_identity_tilt_regardless_of_world_yaw(self):
        for yaw in (0, .4, -1, 2):
            transform = upright()
            transform[:3, :3] = Rotation.from_euler('z', yaw).as_matrix()@transform[:3, :3]
            np.testing.assert_allclose(assumed_gravity(transform), np.eye(3), atol=1e-7)

    def test_tilt_preserves_assumed_down_vector_without_yaw(self):
        transform = upright()
        transform[:3, :3] = transform[:3, :3]@Rotation.from_euler('xz', [.2, -.1]).as_matrix()
        tilt = assumed_gravity(transform)
        np.testing.assert_allclose(tilt[:, 1], transform[:3, :3].T@[0, 0, -1], atol=1e-7)
        np.testing.assert_allclose(tilt.T@tilt, np.eye(3), atol=1e-7)

    def test_invalid_pose_or_non_upright_camera_is_refused(self):
        bad = upright(); bad[0, 0] = 2
        tilted = upright(); tilted[:3, :3] = tilted[:3, :3]@Rotation.from_euler('x', np.pi/2).as_matrix()
        for value in (bad, tilted, np.eye(3), np.full((4, 4), np.nan)):
            with self.assertRaises(ValueError):
                assumed_gravity(value)


class AdapterTests(unittest.TestCase):
    def test_native_units_holes_intrinsics_and_different_sizes(self):
        rgb = np.full((720, 1280, 3), [20, 80, 160], dtype=np.uint8)
        depth = np.full((720, 1280), 2000, dtype=np.uint16)
        depth[:, :640] = 0
        k = np.array([[1000., 0, 640], [0, 1000, 360], [0, 0, 1]])
        with patch('benchmark_cutr.load_frame', return_value=(rgb, depth, k, upright(), {'source_stamp_ns': 123})):
            sample, provenance = femto_sample(Path('synthetic'), 7)
        self.assertEqual(sample['wide']['image'].shape, (1, 3, 576, 1024))
        self.assertEqual(sample['wide']['depth'].shape, (1, 144, 256))
        self.assertEqual(set(sample['wide']['depth'].unique().tolist()), {0, 2})
        self.assertEqual(float((sample['wide']['depth'] > 0).float().mean()), .5)
        np.testing.assert_allclose(sample['sensor_info'].wide.image.K[0], [[800, 0, 512], [0, 800, 288], [0, 0, 1]])
        np.testing.assert_allclose(sample['sensor_info'].wide.depth.K[0], [[200, 0, 128], [0, 200, 72], [0, 0, 1]])
        self.assertEqual(sample['meta'], {'node_id': 7, 'source_stamp_ns': 123})
        self.assertIn('No measured IMU', provenance['gravity_provenance'])
        self.assertTrue(np.all(depth[:, 640:] == 2000))

    def test_other_native_resolution_is_not_silently_assumed(self):
        with patch('benchmark_cutr.load_frame', return_value=(np.zeros((10, 10, 3), dtype=np.uint8), None, None, None, {})):
            with self.assertRaisesRegex(ValueError, '1280x720'):
                femto_sample(Path('synthetic'), 1)

    def test_cpu_calibration_inverse_matches_independent_pinhole_formula(self):
        k = torch.tensor([[[800., 0, 512], [0, 800, 288], [0, 0, 1]]]).repeat(5, 1, 1)
        expected = [[1/800, 0, -512/800], [0, 1/800, -288/800], [0, 0, 1]]
        np.testing.assert_allclose(torch.linalg.inv(k).numpy(), np.array([expected]*5), atol=1e-7)


class CuboidTests(unittest.TestCase):
    def test_empty_selection_and_nonfinite_prediction(self):
        value = Instances3D((720, 1280))
        value.scores = torch.empty(0)
        value.pred_classes = torch.empty(0, dtype=torch.long)
        value.pred_boxes = torch.empty((0, 4))
        value.pred_boxes_3d = GeneralInstance3DBoxes.empty()
        self.assertEqual(predictions(value, upright()), [])
        value = Instances3D((720, 1280))
        value.scores = torch.tensor([float('nan')])
        value.pred_classes = torch.tensor([0])
        value.pred_boxes = torch.tensor([[0., 0., 10., 10.]])
        value.pred_boxes_3d = GeneralInstance3DBoxes([[0, 0, 2, 1, 1, 1]], np.eye(3)[None])
        with self.assertRaises(ValueError):
            predictions(value)

    def test_known_box_rotation_corners_and_map_center(self):
        value = Instances3D((720, 1280))
        value.scores = torch.tensor([.9, .8])
        value.pred_classes = torch.tensor([0, 0])
        value.pred_boxes = torch.tensor([[0., 0., 10., 10.], [1., 1., 5., 5.]])
        r = Rotation.from_euler('z', np.pi/2).as_matrix()
        value.pred_boxes_3d = GeneralInstance3DBoxes(np.array([[1., 2., 5., 2., 4., 6.], [2., 3., 6., 1., 2., 3.]]), np.stack([r, r]))
        transform = upright(); transform[:3, 3] = [3, 4, 5]
        rows = predictions(value, transform)
        self.assertEqual(len(rows), 2)
        np.testing.assert_allclose(rows[1]["center_map_m"], [9, 2, 2])
        self.assertEqual(np.asarray(rows[1]["corners_camera_m"]).shape, (8, 3))
        row = rows[0]
        self.assertEqual(row['dimensions_local_xyz_m'], [2, 4, 6])
        np.testing.assert_allclose(row['center_map_m'], [8, 3, 3])
        expected = np.array(list(itertools.product([-1, 1], [-2, 2], [-3, 3])))@r.T+[1, 2, 5]
        actual = np.asarray(row['corners_camera_m'])
        self.assertTrue(all(np.linalg.norm(actual-p, axis=1).min() < 1e-6 for p in expected))
        np.testing.assert_allclose(row['corners_map_m'], actual@transform[:3, :3].T+transform[:3, 3], atol=1e-6)


class BoundaryTests(unittest.TestCase):
    def test_invalid_work_limit_or_source_is_refused_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'run'
            for kwargs in ({}, {'sample_tar': Path('sample'), 'frames': Path('frames')},
                           {'sample_tar': Path('sample'), 'repeats': 11},
                           {'frames': Path('frames'), 'nodes': [1, 1]}):
                with self.assertRaises(ValueError):
                    benchmark(Path('model'), output, **kwargs)
                self.assertFalse(output.exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            evidence = output/'benchmark.json'
            evidence.write_text('existing evidence')
            with self.assertRaises(FileExistsError):
                benchmark(Path('model'), output, sample_tar=Path('sample'))
            self.assertEqual(evidence.read_text(), 'existing evidence')


if __name__ == '__main__':
    unittest.main()
