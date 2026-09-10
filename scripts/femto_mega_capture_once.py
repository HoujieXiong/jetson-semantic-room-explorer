#!/usr/bin/env python3
"""Save one synchronized, unaligned Femto Mega RGB-D pair and its calibration."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path

import cv2
import numpy as np
import pyorbbecsdk as ob


# Application acceptance bound, stricter than half a 30 FPS frame period.
MAX_PAIR_SKEW_US = 5000
# Matches the installed SDK save-image example's sensor stabilization period.
WARMUP_PAIRS = 15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/outputs/femto_mega_capture"))
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--max-attempts", type=int, default=60)
    parser.add_argument("--list-profiles", action="store_true", help="Save device/profile inventory without streaming.")
    args = parser.parse_args()
    if args.timeout_ms <= 0 or args.max_attempts <= 0:
        parser.error("--timeout-ms and --max-attempts must be positive")
    return args


def profile_metadata(profile: ob.VideoStreamProfile) -> dict:
    return {
        "width": profile.get_width(), "height": profile.get_height(),
        "fps": profile.get_fps(), "format": profile.get_format().name,
    }


def device_metadata(device: ob.Device) -> dict:
    info = device.get_device_info()
    if info.get_pid() != 0x0669:
        raise RuntimeError(f"Expected Femto Mega (PID 0x0669), got {info.get_name()}")
    return {
        "name": info.get_name(), "serial_number": info.get_serial_number(),
        "firmware": info.get_firmware_version(), "connection": info.get_connection_type(),
        "sdk_version": ob.get_version(), "python_sdk_version": version("pyorbbecsdk2"),
    }


def list_profiles(output_dir: Path) -> Path:
    pipeline = ob.Pipeline()
    inventory = {"device": device_metadata(pipeline.get_device()), "profiles": {}}
    for label, sensor in (("color", ob.OBSensorType.COLOR_SENSOR), ("depth", ob.OBSensorType.DEPTH_SENSOR)):
        profiles = pipeline.get_stream_profile_list(sensor)
        inventory["profiles"][label] = [
            profile_metadata(profiles.get_stream_profile_by_index(i).as_video_stream_profile())
            for i in range(profiles.get_count())
        ]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "profiles.json"
    path.write_text(json.dumps(inventory, indent=2, allow_nan=False) + "\n")
    return path


def color_frame_to_bgr(frame: ob.ColorFrame) -> np.ndarray:
    # This utility deliberately selects MJPG; payload size cannot identify a format.
    if frame.get_format() != ob.OBFormat.MJPG:
        raise ValueError(f"color format: expected MJPG, got {frame.get_format()}")
    data = np.frombuffer(frame.get_data(), dtype=np.uint8)
    if data.size == 0:
        raise ValueError("color format: empty MJPG payload")
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None or image.shape != (frame.get_height(), frame.get_width(), 3):
        raise ValueError("color format: invalid MJPG or decoded dimensions disagree with frame")
    return image


def depth_frame_to_uint16(frame: ob.DepthFrame) -> np.ndarray:
    if frame.get_format() != ob.OBFormat.Y16:
        raise ValueError(f"depth format: expected Y16, got {frame.get_format()}")
    if frame.get_data_size() != frame.get_width() * frame.get_height() * 2:
        raise ValueError("depth format: Y16 payload size disagrees with frame dimensions")
    # Preserve SDK counts losslessly; conversion to millimeters is metadata-driven.
    return np.frombuffer(frame.get_data(), dtype="<u2").reshape(
        frame.get_height(), frame.get_width()
    ).copy()


def depth_statistics(raw: np.ndarray, scale_mm: float) -> dict:
    if not np.isfinite(scale_mm) or scale_mm <= 0:
        raise ValueError(f"depth scale must be finite and positive, got {scale_mm}")
    valid = raw[raw != 0]
    if valid.size == 0:
        raise ValueError("depth contains no valid samples (all zero)")
    h, w = raw.shape
    roi = raw[max(0, h // 2 - 10):h // 2 + 10, max(0, w // 2 - 10):w // 2 + 10]
    center = roi[roi != 0]
    return {
        "valid_ratio": valid.size / raw.size,
        "raw_min_nonzero": int(valid.min()), "raw_max": int(valid.max()),
        "min_m": float(valid.min() * scale_mm / 1000),
        "median_m": float(np.median(valid) * scale_mm / 1000),
        "p95_m": float(np.percentile(valid, 95) * scale_mm / 1000),
        "max_m": float(valid.max() * scale_mm / 1000),
        "center_roi_xywh": [max(0, w // 2 - 10), max(0, h // 2 - 10), roi.shape[1], roi.shape[0]],
        "center_valid_ratio": center.size / roi.size,
        "center_median_m": float(np.median(center) * scale_mm / 1000) if center.size else None,
    }


def frame_metadata(frame: ob.VideoFrame) -> dict:
    profile = frame.get_stream_profile().as_video_stream_profile()
    intr = profile.get_intrinsic()
    dist = profile.get_distortion()
    intrinsic = {key: getattr(intr, key) for key in ("width", "height", "fx", "fy", "cx", "cy")}
    if (intr.width, intr.height) != (frame.get_width(), frame.get_height()):
        raise ValueError("calibration dimensions disagree with delivered frame")
    if intr.fx <= 0 or intr.fy <= 0 or not all(np.isfinite(v) for v in intrinsic.values()):
        raise ValueError("calibration has invalid focal lengths or non-finite values")
    return {
        "profile": profile_metadata(profile), "intrinsic": intrinsic,
        "distortion": {key: getattr(dist, key) for key in ("k1", "k2", "k3", "k4", "k5", "k6", "p1", "p2")},
        "frame_index": frame.get_index(),
        "device_timestamp_us": frame.get_timestamp_us(),
        "system_timestamp_us": frame.get_system_timestamp_us(),
    }


def wait_for_pair(pipeline: ob.Pipeline, timeout_ms: int, max_attempts: int) -> tuple:
    rejected = {"timeout": 0, "incomplete": 0, "timestamp": 0}
    warmed = 0
    for attempt in range(1, max_attempts + 1):
        frames = pipeline.wait_for_frames(timeout_ms)
        if frames is None:
            rejected["timeout"] += 1
            continue
        color, depth = frames.get_color_frame(), frames.get_depth_frame()
        if color is None or depth is None:
            rejected["incomplete"] += 1
            continue
        ct, dt = color.get_timestamp_us(), depth.get_timestamp_us()
        if min(ct, dt) <= 0 or abs(ct - dt) > MAX_PAIR_SKEW_US:
            rejected["timestamp"] += 1
            continue
        if warmed < WARMUP_PAIRS:
            warmed += 1
            continue
        return color, depth, {"attempts": attempt, "warmup_pairs_discarded": warmed, "rejected": rejected}
    raise TimeoutError(
        f"No synchronized RGB-D pair after {max_attempts} waits of {timeout_ms} ms: "
        f"{rejected}, warmup={warmed}/{WARMUP_PAIRS}"
    )


def write_png(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise OSError(f"PNG save failed: {path}")
    saved = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if saved is None or saved.dtype != image.dtype or not np.array_equal(saved, image):
        raise OSError(f"PNG read-back verification failed: {path}")


def save_depth_visualization(raw: np.ndarray, path: Path) -> None:
    valid = raw[raw != 0]
    maximum = np.percentile(valid, 95)
    gray = (np.clip(raw.astype(np.float32) / maximum, 0, 1) * 255).astype(np.uint8)
    vis = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
    vis[raw == 0] = 0
    write_png(path, vis)


def capture_once(output_dir: Path, timeout_ms: int = 1000, max_attempts: int = 60) -> Path:
    if timeout_ms <= 0 or max_attempts <= 0:
        raise ValueError("timeout_ms and max_attempts must be positive")
    pipeline = ob.Pipeline()
    device = pipeline.get_device()
    metadata = {"device": device_metadata(device)}
    sync = device.get_multi_device_sync_config()
    if sync.mode != ob.OBMultiDeviceSyncMode.STANDALONE:
        raise RuntimeError(f"Expected STANDALONE camera sync mode, got {sync.mode}")
    config = ob.Config()
    selected = {}
    for label, sensor, width, height, fmt in (
        ("color", ob.OBSensorType.COLOR_SENSOR, 1280, 720, ob.OBFormat.MJPG),
        ("depth", ob.OBSensorType.DEPTH_SENSOR, 640, 576, ob.OBFormat.Y16),
    ):
        try:
            profile = pipeline.get_stream_profile_list(sensor).get_video_stream_profile(width, height, fmt, 30)
        except ob.OBError as exc:
            raise RuntimeError(f"Unsupported {label} stream {width}x{height} {fmt.name}@30; run --list-profiles") from exc
        config.enable_stream(profile)
        selected[label] = profile_metadata(profile)
    config.set_align_mode(ob.OBAlignMode.DISABLE)
    config.set_frame_aggregate_output_mode(ob.OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)
    pipeline.enable_frame_sync()
    try:
        pipeline.start(config)
        color, depth, waits = wait_for_pair(pipeline, timeout_ms, max_attempts)
        bgr = color_frame_to_bgr(color)
        raw = depth_frame_to_uint16(depth)
        scale_mm = float(depth.get_depth_scale())
        metadata.update({
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "alignment": "disabled; each image uses its own optical camera frame",
            "optical_axes": "x right, y down, z forward",
            "color": frame_metadata(color), "depth": frame_metadata(depth),
            "selected_profiles": selected,
            "synchronization": {
                "device_mode": sync.mode.name,
                "color_delay_us": sync.color_delay_us, "depth_delay_us": sync.depth_delay_us,
                "sdk_frame_sync": True, "aggregate_mode": "FULL_FRAME_REQUIRE",
                "color_minus_depth_us": color.get_timestamp_us() - depth.get_timestamp_us(),
                "max_accepted_skew_us": MAX_PAIR_SKEW_US,
                **waits,
            },
            "depth_encoding": {
                "dtype": "uint16", "stored_unit": "raw SDK count", "invalid_value": 0,
                "scale_mm_per_count": scale_mm, "meters_per_count": scale_mm / 1000,
                "conversion": "z_m = raw_count * scale_mm_per_count / 1000; zero is invalid",
            },
            "depth_statistics": depth_statistics(raw, scale_mm),
        })
        for label in ("color", "depth"):
            if metadata[label]["profile"] != selected[label]:
                raise ValueError(f"Delivered {label} profile disagrees with selected profile")
        ext = depth.get_stream_profile().get_extrinsic_to(color.get_stream_profile())
        metadata["depth_to_color"] = {
            "rotation_row_major": np.asarray(ext.rot).reshape(3, 3).tolist(),
            "translation_mm": np.asarray(ext.transform).tolist(),
            "equation": "P_color_mm = R @ P_depth_mm + translation_mm",
        }
    finally:
        # Also attempt cleanup if start partially enabled a stream before failing.
        pipeline.stop()
    # Saving runs only after a successful stop; metadata is the completion marker.
    destination = output_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    destination.mkdir(parents=True, exist_ok=False)
    write_png(destination / "color.png", bgr)
    write_png(destination / "depth_raw.png", raw)
    save_depth_visualization(raw, destination / "depth_vis.png")
    (destination / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    return destination


def main() -> None:
    args = parse_args()
    try:
        if args.list_profiles:
            path = list_profiles(args.output_dir)
            print(f"Saved profile inventory: {path}", flush=True)
        else:
            path = capture_once(args.output_dir, args.timeout_ms, args.max_attempts)
            metadata = json.loads((path / "metadata.json").read_text())
            stats = metadata["depth_statistics"]
            print(
                f"Saved RGB-D pair: {path}\n"
                f"Depth valid: {stats['valid_ratio']:.2%}; center median (m): {stats['center_median_m']}; "
                f"color-depth skew (us): {metadata['synchronization']['color_minus_depth_us']}",
                flush=True,
            )
    except ob.OBError as exc:
        raise RuntimeError(f"Orbbec USB/device/stream operation failed: {exc}") from exc


if __name__ == "__main__":
    main()
