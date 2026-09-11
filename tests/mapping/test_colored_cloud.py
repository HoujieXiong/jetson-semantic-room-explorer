"""Known RGB-D geometry, frame association and color preservation cases."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from extract_mapped_rgbd import selected_stamp
from rebuild_colored_cloud import project_frame


class ColoredCloudTests(unittest.TestCase):
    def setUp(self):
        self.rgb = np.zeros((3, 3, 3), dtype=np.uint8)
        self.depth = np.zeros((3, 3), dtype=np.uint16)
        self.k = [2, 0, 1, 0, 2, 1, 0, 0, 1]

    def project(self, position=(0, 0, 0), quaternion=(0, 0, 0, 1), stride=1):
        return project_frame(self.rgb, self.depth, self.k, position, quaternion, stride)

    def test_millimeters_optical_axes_and_rgb_channels(self):
        self.depth[2, 2] = 2000
        self.rgb[2, 2] = [255, 0, 64]
        cloud = self.project()
        np.testing.assert_allclose(np.asarray(cloud.points), [[1, 1, 2]])
        np.testing.assert_allclose(np.asarray(cloud.colors), [[1, 0, 64/255]])

    def test_map_from_camera_rotation_and_translation(self):
        self.depth[1, 2] = 2000
        cloud = self.project((3, 4, 5), (0, 0, np.sqrt(0.5), np.sqrt(0.5)))
        np.testing.assert_allclose(np.asarray(cloud.points), [[3, 5, 7]])

    def test_stride_preserves_original_pixel_coordinates(self):
        self.depth[2, 2] = 2000
        np.testing.assert_allclose(np.asarray(self.project(stride=2).points), [[1, 1, 2]])

    def test_zero_and_out_of_range_depth_are_excluded(self):
        self.depth[0, 0], self.depth[1, 1] = 6000, 1000
        np.testing.assert_allclose(np.asarray(self.project().points), [[0, 0, 1]])

    def test_empty_depth_is_an_explicit_failure(self):
        with self.assertRaisesRegex(ValueError, 'no valid depth'):
            self.project()

    def test_null_and_nonfinite_pose_are_rejected(self):
        for position, quaternion in (((0, 0, 0), (0, 0, 0, 0)), ((np.nan, 0, 0), (0, 0, 0, 1))):
            with self.assertRaisesRegex(ValueError, 'finite translation'):
                self.project(position, quaternion)

    def test_float_depth_cannot_be_treated_as_millimeters(self):
        self.depth = self.depth.astype(float)
        with self.assertRaisesRegex(ValueError, 'uint16 millimeter'):
            self.project()

    def test_different_rgb_depth_grids_are_rejected(self):
        self.rgb = self.rgb[:2]
        with self.assertRaisesRegex(ValueError, 'same-grid'):
            self.project()

    def test_source_association_is_bounded_and_unambiguous(self):
        source = 1789080202178160000
        self.assertEqual(selected_stamp(source-1_186_000, [source]), source)
        self.assertIsNone(selected_stamp(source+5_000_001, [source]))
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            selected_stamp(source, [source-1_000_000, source+1_000_000])
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            selected_stamp(source, [source, source+1_000_000])


if __name__ == '__main__':
    unittest.main()
