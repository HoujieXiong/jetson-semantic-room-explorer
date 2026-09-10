#!/usr/bin/env python3
"""Capture one RGB-D frame from an Orbbec Femto Mega and save it headlessly."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from pyorbbecsdk import Config, OBError, OBSensorType, Pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data/outputs/femto_mega_capture", help="Output directory.")
    parser.add_argument("--timeout-ms", type=int, default=1000, help="Frame wait timeout in milliseconds.")
    parser.add_argument("--max-attempts", type=int, default=60, help="Maximum frame wait attempts.")
    return parser.parse_args()


def try_enable_default_stream(config: Config, pipeline: Pipeline, sensor_type: OBSensorType, label: str) -> bool:
    try:
        profiles = pipeline.get_stream_profile_list(sensor_type)
        if profiles is None:
            print(f"{label}: no profile list")
            return False
        profile = profiles.get_default_video_stream_profile()
        config.enable_stream(profile)
        print(f"{label}: enabled default profile {profile}")
        return True
    except OBError as exc:
        print(f"{label}: failed to enable stream: {exc}")
        return False


def color_frame_to_bgr(frame) -> np.ndarray | None:
    width = frame.get_width()
    height = frame.get_height()
    data = np.frombuffer(frame.get_data(), dtype=np.uint8)

    # Common RGB/BGR packed color frame.
    if data.size == width * height * 3:
        image = data.reshape((height, width, 3))
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    # Common YUYV packed frame.
    if data.size == width * height * 2:
        image = data.reshape((height, width, 2))
        return cv2.cvtColor(image, cv2.COLOR_YUV2BGR_YUYV)

    # MJPEG/JPEG encoded color frame.
    decoded = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if decoded is not None:
        return decoded

    print(f"color: unsupported payload size={data.size} width={width} height={height}")
    return None


def depth_frame_to_uint16(frame) -> np.ndarray:
    width = frame.get_width()
    height = frame.get_height()
    depth = np.frombuffer(frame.get_data(), dtype=np.uint16).reshape((height, width))
    scale = float(frame.get_depth_scale())
    # Keep the saved PNG in millimeters when scale is 1.0. If the device reports a
    # different scale, convert to metric depth values while preserving uint16 PNG.
    depth_mm = (depth.astype(np.float32) * scale).astype(np.uint16)
    return depth_mm


def save_depth_visualization(depth_mm: np.ndarray, path: Path) -> None:
    valid = depth_mm[depth_mm > 0]
    if valid.size == 0:
        vis = np.zeros((*depth_mm.shape, 3), dtype=np.uint8)
    else:
        max_depth = np.percentile(valid, 95)
        normalized = np.clip(depth_mm.astype(np.float32) / max(max_depth, 1.0), 0.0, 1.0)
        gray = (normalized * 255).astype(np.uint8)
        vis = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
        vis[depth_mm == 0] = (0, 0, 0)
    cv2.imwrite(str(path), vis)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = Pipeline()
    config = Config()

    has_color = try_enable_default_stream(config, pipeline, OBSensorType.COLOR_SENSOR, "color")
    has_depth = try_enable_default_stream(config, pipeline, OBSensorType.DEPTH_SENSOR, "depth")

    if not has_color and not has_depth:
        raise RuntimeError("No color or depth stream could be enabled.")

    print("starting pipeline...")
    pipeline.start(config)

    try:
        for attempt in range(1, args.max_attempts + 1):
            frames = pipeline.wait_for_frames(args.timeout_ms)
            if frames is None:
                print(f"attempt {attempt}/{args.max_attempts}: no frames")
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_any = False

            color_frame = frames.get_color_frame() if has_color else None
            if color_frame is not None:
                color = color_frame_to_bgr(color_frame)
                if color is not None:
                    color_path = output_dir / f"color_{timestamp}.png"
                    cv2.imwrite(str(color_path), color)
                    print(f"saved color: {color_path} shape={color.shape}")
                    saved_any = True

            depth_frame = frames.get_depth_frame() if has_depth else None
            if depth_frame is not None:
                depth_mm = depth_frame_to_uint16(depth_frame)
                depth_path = output_dir / f"depth_raw_{timestamp}.png"
                depth_vis_path = output_dir / f"depth_vis_{timestamp}.png"
                cv2.imwrite(str(depth_path), depth_mm)
                save_depth_visualization(depth_mm, depth_vis_path)
                print(
                    "saved depth: "
                    f"{depth_path} shape={depth_mm.shape} "
                    f"min={int(depth_mm[depth_mm > 0].min()) if np.any(depth_mm > 0) else 0} "
                    f"max={int(depth_mm.max())}"
                )
                print(f"saved depth visualization: {depth_vis_path}")
                saved_any = True

            if saved_any:
                return

            print(f"attempt {attempt}/{args.max_attempts}: frames received but nothing saved")

        raise TimeoutError("Failed to capture a color/depth frame before max attempts.")
    finally:
        pipeline.stop()
        print("pipeline stopped")


if __name__ == "__main__":
    main()
