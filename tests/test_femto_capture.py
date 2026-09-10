"""Offline checks of capture data and rejection behavior; no camera is opened."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pyorbbecsdk as ob

from scripts import femto_mega_capture_once as capture
from check_femto_hardware import registration_edge_metrics, registration_projection_metrics


def frame(data: bytes, width: int, height: int, fmt: ob.OBFormat) -> SimpleNamespace:
    return SimpleNamespace(
        get_data=lambda: data, get_data_size=lambda: len(data),
        get_width=lambda: width, get_height=lambda: height, get_format=lambda: fmt,
    )


def frameset(color_us: int, depth_us: int | None) -> SimpleNamespace:
    return SimpleNamespace(
        get_color_frame=lambda: SimpleNamespace(get_timestamp_us=lambda: color_us),
        get_depth_frame=lambda: SimpleNamespace(get_timestamp_us=lambda: depth_us) if depth_us is not None else None,
    )


class CaptureDataTests(unittest.TestCase):
    def test_mjpg_color_channels_and_dimensions(self):
        red_bgr = np.full((24, 32, 3), (0, 0, 255), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", red_bgr)
        self.assertTrue(ok)
        decoded = capture.color_frame_to_bgr(frame(encoded.tobytes(), 32, 24, ob.OBFormat.MJPG))
        self.assertEqual(decoded.shape, (24, 32, 3))
        self.assertGreater(decoded[12, 16, 2], 250)
        self.assertLess(decoded[12, 16, 0], 5)

    def test_color_rejects_wrong_format_bad_jpeg_and_wrong_dimensions(self):
        for data, fmt in ((b"bad jpeg", ob.OBFormat.MJPG), (b"", ob.OBFormat.MJPG), (bytes(12), ob.OBFormat.RGB)):
            with self.subTest(fmt=fmt, data=data), self.assertRaises(ValueError):
                capture.color_frame_to_bgr(frame(data, 2, 2, fmt))
        _, jpg = cv2.imencode(".jpg", np.zeros((4, 4, 3), np.uint8))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            capture.color_frame_to_bgr(frame(jpg.tobytes(), 8, 4, ob.OBFormat.MJPG))

    def test_raw_depth_is_lossless_and_owned(self):
        payload = bytearray(np.array([[0, 1, 1000, 65535]], dtype="<u2").tobytes())
        raw = capture.depth_frame_to_uint16(frame(payload, 4, 1, ob.OBFormat.Y16))
        payload[:] = bytes(len(payload))
        np.testing.assert_array_equal(raw, [[0, 1, 1000, 65535]])
        self.assertEqual(raw.dtype, np.uint16)

    def test_depth_rejects_wrong_format_and_size(self):
        for payload, fmt in ((bytes(6), ob.OBFormat.Y16), (bytes(8), ob.OBFormat.MJPG)):
            with self.subTest(fmt=fmt), self.assertRaises(ValueError):
                capture.depth_frame_to_uint16(frame(payload, 2, 2, fmt))

    def test_metric_scale_fractional_and_no_uint16_overflow(self):
        raw = np.array([[0, 10000, 20000, 60000]], dtype=np.uint16)
        small = capture.depth_statistics(raw, 0.1)
        self.assertEqual(small["valid_ratio"], 0.75)
        self.assertEqual(small["min_m"], 1.0)
        self.assertEqual(small["median_m"], 2.0)
        self.assertEqual(small["max_m"], 6.0)
        self.assertEqual(capture.depth_statistics(raw, 2.0)["max_m"], 120.0)

    def test_invalid_depth_and_scale_fail(self):
        with self.assertRaisesRegex(ValueError, "no valid"):
            capture.depth_statistics(np.zeros((32, 32), np.uint16), 1)
        for scale in (0, -1, float("nan"), float("inf")):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                capture.depth_statistics(np.ones((32, 32), np.uint16), scale)

    def test_invalid_center_is_null_not_zero_distance(self):
        raw = np.zeros((64, 64), np.uint16)
        raw[0, 0] = 1000
        stats = capture.depth_statistics(raw, 1)
        self.assertIsNone(stats["center_median_m"])
        self.assertEqual(stats["center_valid_ratio"], 0)

    def test_png_roundtrip_preserves_full_depth_range(self):
        raw = np.array([[0, 1, 1000, 65535]], np.uint16)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "depth_raw.png"
            capture.write_png(path, raw)
            np.testing.assert_array_equal(cv2.imread(str(path), cv2.IMREAD_UNCHANGED), raw)

    def test_save_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(OSError, "save failed"):
                capture.write_png(Path(folder) / "missing" / "depth.png", np.ones((2, 2), np.uint16))

    def test_readback_mismatch_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(capture.cv2, "imread", return_value=np.zeros((2, 2), np.uint16)):
                with self.assertRaisesRegex(OSError, "read-back"):
                    capture.write_png(Path(folder) / "depth.png", np.ones((2, 2), np.uint16))

    def test_visualization_marks_invalid_black(self):
        raw = np.array([[0, 1000], [2000, 3000]], np.uint16)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "depth_vis.png"
            capture.save_depth_visualization(raw, path)
            vis = cv2.imread(str(path))
            self.assertTrue(np.all(vis[0, 0] == 0))
            self.assertTrue(np.any(vis[1, 1] != 0))

    def test_overlay_keeps_invalid_pixels_as_original_color(self):
        raw = np.array([[0, 1000], [2000, 0]], np.uint16)
        color = np.full((2, 2, 3), (40, 100, 180), np.uint8)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "overlay.png"
            capture.save_depth_visualization(raw, path, color)
            overlay = cv2.imread(str(path))
            np.testing.assert_array_equal(overlay[raw == 0], color[raw == 0])
            self.assertTrue(np.any(overlay[raw != 0] != color[raw != 0]))

    def test_overlay_rejects_different_pixel_grids(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "pixel grid"):
                capture.save_depth_visualization(
                    np.ones((2, 2), np.uint16), Path(folder) / "overlay.png", np.zeros((4, 4, 3), np.uint8)
                )

    def test_missing_sdk_alignment_result_is_an_error(self):
        sdk_filter = Mock()
        sdk_filter.get_config_value.side_effect = {"TargetDistortion": 1, "GapFillCopy": 0, "MatchTargetRes": 1}.__getitem__
        sdk_filter.process.return_value = None
        with patch.object(capture.ob, "AlignFilter", return_value=sdk_filter):
            with self.assertRaisesRegex(RuntimeError, "no frameset"):
                capture.align_depth_to_color(Mock(), np.ones((2, 2), np.uint16), np.zeros((4, 4, 3), np.uint8), {})

    def test_sdk_alignment_configuration_cannot_silently_fail(self):
        sdk_filter = Mock()
        sdk_filter.get_config_value.return_value = 0
        with patch.object(capture.ob, "AlignFilter", return_value=sdk_filter):
            with self.assertRaisesRegex(RuntimeError, "TargetDistortion"):
                capture.align_depth_to_color(Mock(), np.ones((2, 2), np.uint16), np.zeros((4, 4, 3), np.uint8), {})
        sdk_filter.process.assert_not_called()

    def test_edge_diagnostic_detects_known_spatial_shift(self):
        color = np.zeros((80, 80, 3), np.uint8)
        color[20:60, 20:60] = 255
        depth = np.full((80, 80), 2000, np.uint16)
        depth[20:60, 20:60] = 1000
        good = registration_edge_metrics(color, depth, 1, (0, 0, 80, 80))
        shifted = np.full((80, 80), 2000, np.uint16)
        shifted[20:60, 28:68] = 1000
        bad = registration_edge_metrics(color, shifted, 1, (0, 0, 80, 80))
        self.assertLessEqual(good["depth_jumps"]["p95_px"], 1)
        self.assertGreaterEqual(bad["depth_jumps"]["p95_px"], 7)

    def test_edge_diagnostic_separates_missing_depth_from_metric_jump(self):
        color = np.zeros((80, 80, 3), np.uint8)
        color[20:60, 20:60] = 255
        depth = np.full((80, 80), 2000, np.uint16)
        depth[20:60, 20:60] = 0
        stats = registration_edge_metrics(color, depth, 1, (0, 0, 80, 80))
        self.assertEqual(stats["depth_jumps"]["count"], 0)
        self.assertGreater(stats["validity_boundaries"]["count"], 0)

    def test_projection_uses_target_axial_depth_in_metric_units(self):
        calibration = {
            "intrinsic": {"fx": 100, "fy": 100, "cx": 48, "cy": 40},
            "distortion": dict.fromkeys(("k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6"), 0),
        }
        metadata = {
            "color": calibration, "depth": calibration,
            "depth_encoding": {"scale_mm_per_count": 0.5},
            "aligned_depth": {"encoding": {"scale_mm_per_count": 1.0}},
            "depth_to_color": {"rotation_row_major": np.eye(3).tolist(), "translation_mm": [0, 0, 100]},
        }
        raw = np.full((80, 96), 4000, np.uint16)  # 2 m in depth coordinates.
        correct = registration_projection_metrics(raw, np.full((80, 96), 2100, np.uint16), metadata)
        wrong = registration_projection_metrics(raw, np.full((80, 96), 2000, np.uint16), metadata)
        self.assertEqual(correct["color_z_error_p95_mm"], 0)
        self.assertEqual(wrong["color_z_error_median_mm"], 100)

    @patch.object(capture, "WARMUP_PAIRS", 0)
    def test_wait_rejects_missing_and_unsynchronized_frames(self):
        pipeline = Mock()
        accepted = frameset(100000, 100500)
        pipeline.wait_for_frames.side_effect = [None, frameset(100000, None), frameset(100000, 133333), accepted]
        pair, stats = capture.wait_for_pair(pipeline, 20, 4)
        color, depth = pair.get_color_frame(), pair.get_depth_frame()
        self.assertEqual(color.get_timestamp_us(), 100000)
        self.assertEqual(depth.get_timestamp_us(), 100500)
        self.assertEqual(stats, {"attempts": 4, "warmup_pairs_discarded": 0,
                                 "rejected": {"timeout": 1, "incomplete": 1, "timestamp": 1}})

    @patch.object(capture, "WARMUP_PAIRS", 0)
    def test_wait_is_bounded_and_checks_skew_boundary(self):
        for color, depth in ((0, 0), (10000, 15001)):
            pipeline = Mock()
            pipeline.wait_for_frames.return_value = frameset(color, depth)
            with self.assertRaisesRegex(TimeoutError, "after 3 waits"):
                capture.wait_for_pair(pipeline, 1, 3)
            self.assertEqual(pipeline.wait_for_frames.call_count, 3)
        pipeline.wait_for_frames.return_value = frameset(10000, 15000)
        capture.wait_for_pair(pipeline, 1, 1)

    def test_startup_pairs_are_discarded(self):
        pipeline = Mock()
        pipeline.wait_for_frames.side_effect = [frameset(10000, 10000)] * 15 + [frameset(20000, 20001)]
        pair, stats = capture.wait_for_pair(pipeline, 1, 16)
        color, depth = pair.get_color_frame(), pair.get_depth_frame()
        self.assertEqual(color.get_timestamp_us(), 20000)
        self.assertEqual(depth.get_timestamp_us(), 20001)
        self.assertEqual(stats["warmup_pairs_discarded"], 15)


if __name__ == "__main__":
    unittest.main()
