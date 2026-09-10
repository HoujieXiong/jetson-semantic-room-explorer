"""Run explicitly on the Jetson: ten CLI executions and ten in-process cycles."""

import argparse
import ctypes
import gc
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.femto_mega_capture_once import capture_once


# Jetson uses glibc. Separate live allocations from idle allocator arenas.
class MallInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_size_t) for name in (
        "arena", "ordblks", "smblks", "hblks", "hblkhd", "usmblks",
        "fsmblks", "uordblks", "fordblks", "keepcost",
    )]


LIBC = ctypes.CDLL("libc.so.6")
LIBC.mallinfo2.restype = MallInfo
LIBC.malloc_trim.argtypes = [ctypes.c_size_t]
LIBC.malloc_trim.restype = ctypes.c_int


def resources() -> dict:
    gc.collect()
    status = Path("/proc/self/status").read_text().splitlines()
    values = {line.split(":")[0]: line.split(":")[1].strip() for line in status}
    handles = []
    for path in Path("/proc/self/fd").iterdir():
        try:
            handles.append(os.readlink(path))
        except FileNotFoundError:
            continue  # The directory iterator's own fd may already be closed.
    heap = LIBC.mallinfo2()
    return {
        "fd_count": len(handles), "threads": int(values["Threads"]),
        "rss_kib": int(values["VmRSS"].split()[0]),
        "camera_handles": [h for h in handles if h.startswith(("/dev/video", "/dev/bus/usb", "/dev/hidraw"))],
        "allocated_bytes": heap.uordblks + heap.hblkhd,
        "free_arena_bytes": heap.fordblks,
    }


def verify_artifact(path: Path, expect_aligned: bool = False) -> dict:
    metadata = json.loads((path / "metadata.json").read_text())
    color = cv2.imread(str(path / "color.png"), cv2.IMREAD_UNCHANGED)
    raw = cv2.imread(str(path / "depth_raw.png"), cv2.IMREAD_UNCHANGED)
    vis = cv2.imread(str(path / "depth_vis.png"), cv2.IMREAD_UNCHANGED)
    assert color is not None and color.shape == (720, 1280, 3) and color.dtype == np.uint8
    assert raw is not None and raw.shape == (576, 640) and raw.dtype == np.uint16
    assert vis is not None and vis.shape == (576, 640, 3)
    assert np.all(vis[raw == 0] == 0)
    for name, image in (("color", color), ("depth", raw)):
        stream = metadata[name]
        assert stream["intrinsic"]["width"] == image.shape[1]
        assert stream["intrinsic"]["height"] == image.shape[0]
        assert stream["profile"] == metadata["selected_profiles"][name]
    delta = metadata["color"]["device_timestamp_us"] - metadata["depth"]["device_timestamp_us"]
    assert abs(delta) <= metadata["synchronization"]["max_accepted_skew_us"]
    assert delta == metadata["synchronization"]["color_minus_depth_us"]
    scale = metadata["depth_encoding"]["scale_mm_per_count"]
    assert scale > 0 and np.isfinite(scale)
    valid = raw[raw != 0]
    assert valid.size > 0
    stats = metadata["depth_statistics"]
    assert stats["raw_min_nonzero"] == int(valid.min())
    assert stats["raw_max"] == int(valid.max())
    assert stats["valid_ratio"] == valid.size / raw.size
    assert stats["median_m"] == float(np.median(valid) * scale / 1000)
    result = {"path": str(path), "skew_us": delta, "scale_mm": scale, **stats}
    if expect_aligned:
        aligned = cv2.imread(str(path / "depth_aligned.png"), cv2.IMREAD_UNCHANGED)
        overlay = cv2.imread(str(path / "alignment_overlay.png"), cv2.IMREAD_UNCHANGED)
        assert aligned is not None and aligned.shape == (720, 1280) and aligned.dtype == np.uint16
        assert overlay is not None and overlay.shape == color.shape
        assert np.array_equal(overlay[aligned == 0], color[aligned == 0])
        info = metadata["aligned_depth"]
        for key in ("intrinsic", "distortion"):
            assert info[key] == metadata["color"][key], key
        for key in ("device_timestamp_us", "system_timestamp_us", "frame_index"):
            assert info[key] == metadata["depth"][key], key
        assert info["optical_frame"] == "color_optical"
        assert info["profile"] == {"width": 1280, "height": 720, "fps": 30, "format": "Y16"}
        assert info["registration"]["settings"] == {"TargetDistortion": 1, "GapFillCopy": 0, "MatchTargetRes": 1}
        unit = info["encoding"]["scale_mm_per_count"]
        valid_aligned = aligned[aligned != 0]
        assert unit > 0 and np.isfinite(unit) and valid_aligned.size > 0
        assert info["depth_statistics"]["valid_ratio"] == valid_aligned.size / aligned.size
        assert info["depth_statistics"]["median_m"] == float(np.median(valid_aligned) * unit / 1000)
        result["aligned_depth"] = {
            "scale_mm": unit, "processing_ms": info["registration"]["processing_ms"],
            **info["depth_statistics"],
        }
    else:
        assert "aligned_depth" not in metadata
        assert not (path / "depth_aligned.png").exists()
    return result


def registration_edge_metrics(color: np.ndarray, depth: np.ndarray, scale_mm: float, roi: tuple[int, int, int, int]) -> dict:
    """Diagnostic distances to RGB edges, not a calibration-accuracy estimate."""
    if color.shape[:2] != depth.shape or scale_mm <= 0 or not np.isfinite(scale_mm):
        raise ValueError("Edge comparison requires matching grids and a positive metric scale")
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > depth.shape[1] or y + h > depth.shape[0]:
        raise ValueError("Edge ROI lies outside the image")
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    rgb_edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 120)
    if not np.any(rgb_edges):
        raise ValueError("No RGB edges available for comparison")
    distance = cv2.distanceTransform((rgb_edges == 0).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    valid = depth != 0
    metric = depth.astype(np.float32) * scale_mm
    jumps = np.zeros(depth.shape, bool)
    holes = np.zeros(depth.shape, bool)
    jumps[:, :-1] |= valid[:, :-1] & valid[:, 1:] & (np.abs(np.diff(metric, axis=1)) >= 50)
    jumps[:-1, :] |= valid[:-1, :] & valid[1:, :] & (np.abs(np.diff(metric, axis=0)) >= 50)
    holes[:, :-1] |= valid[:, :-1] != valid[:, 1:]
    holes[:-1, :] |= valid[:-1, :] != valid[1:, :]
    result = {"roi_xywh": list(roi), "depth_jump_mm": 50, "rgb_canny_thresholds": [60, 120]}
    for name, mask in (("depth_jumps", jumps), ("validity_boundaries", holes)):
        values = distance[y:y+h, x:x+w][mask[y:y+h, x:x+w]]
        result[name] = {
            "count": int(values.size),
            "median_px": float(np.median(values)) if values.size else None,
            "p95_px": float(np.percentile(values, 95)) if values.size else None,
            "within_3px_ratio": float(np.mean(values <= 3)) if values.size else None,
        }
    return result


def registration_projection_metrics(raw: np.ndarray, aligned: np.ndarray, metadata: dict) -> dict:
    """Independently project stable raw patches with OpenCV and saved calibration."""
    def camera_matrix(info):
        i = info["intrinsic"]
        return np.array([[i["fx"], 0, i["cx"]], [0, i["fy"], i["cy"]], [0, 0, 1]], np.float64)

    def distortion(info):
        return np.array([info["distortion"][key] for key in ("k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6")], np.float64)

    raw_scale = metadata["depth_encoding"]["scale_mm_per_count"]
    high = cv2.dilate(raw, np.ones((3, 3), np.uint8))
    low = cv2.erode(raw, np.ones((3, 3), np.uint8))
    y, x = np.mgrid[8:raw.shape[0]-8:8, 8:raw.shape[1]-8:8]
    y, x = y.ravel(), x.ravel()
    stable = (low[y, x] > 0) & ((high[y, x].astype(float) - low[y, x]) * raw_scale <= 20)
    y, x = y[stable], x[stable]
    if not x.size:
        raise ValueError("No stable raw patches available for projection check")
    pixels = np.stack((x, y), axis=1).astype(np.float64).reshape(-1, 1, 2)
    rays = cv2.undistortPointsIter(
        pixels, camera_matrix(metadata["depth"]), distortion(metadata["depth"]), None, None,
        (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 30, 1e-10),
    ).reshape(-1, 2)
    z = raw[y, x].astype(float) * raw_scale
    points = np.c_[rays, np.ones(len(rays))] * z[:, None]
    rotation = np.array(metadata["depth_to_color"]["rotation_row_major"])
    translation = np.array(metadata["depth_to_color"]["translation_mm"])
    transformed = points @ rotation.T + translation
    uv, _ = cv2.projectPoints(transformed, np.zeros(3), np.zeros(3), camera_matrix(metadata["color"]), distortion(metadata["color"]))
    u, v = np.rint(uv.reshape(-1, 2)).astype(int).T
    inside = (u >= 0) & (u < aligned.shape[1]) & (v >= 0) & (v < aligned.shape[0]) & (transformed[:, 2] > 0)
    observed = aligned[v[inside], u[inside]].astype(float) * metadata["aligned_depth"]["encoding"]["scale_mm_per_count"]
    valid = observed > 0
    if not np.any(valid):
        raise ValueError("No valid aligned samples at projected raw pixels")
    error = np.abs(observed[valid] - transformed[inside, 2][valid])
    return {
        "stable_source_samples": int(x.size), "in_bounds": int(np.count_nonzero(inside)),
        "valid_target_samples": int(np.count_nonzero(valid)),
        "color_z_error_median_mm": float(np.median(error)),
        "color_z_error_p95_mm": float(np.percentile(error, 95)),
        "color_z_error_max_mm": float(error.max()),
        "source_z_error_median_mm": float(np.median(np.abs(observed[valid] - z[inside][valid]))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--align-depth", action="store_true")
    args = parser.parse_args()
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "platform": platform.platform(), "python": sys.version,
        "opencv": cv2.__version__, "numpy": np.__version__,
        "power_mode": subprocess.check_output(["nvpmodel", "-q"], text=True).strip(),
        "workload": "headless camera capture; no project ML/SLAM workload launched",
        "status": "INCOMPLETE", "cli": [], "in_process": [],
        "align_depth": args.align_depth,
    }

    def checkpoint():
        (root / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    script = Path(__file__).resolve().parents[1] / "scripts/femto_mega_capture_once.py"
    for cycle in range(1, 11):
        output = root / f"cli_{cycle:02d}"
        start = time.perf_counter()
        command = [sys.executable, str(script), "--output-dir", str(output)]
        if args.align_depth:
            command.append("--align-depth")
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        elapsed = time.perf_counter() - start
        (root / f"cli_{cycle:02d}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, f"CLI cycle {cycle} failed; see saved log"
        artifacts = list(output.glob("*/metadata.json"))
        assert len(artifacts) == 1, f"CLI cycle {cycle} did not save exactly one pair"
        report["cli"].append({"cycle": cycle, "elapsed_s": elapsed, "exit_code": result.returncode, **verify_artifact(artifacts[0].parent, args.align_depth)})
        checkpoint()
        print(f"CLI {cycle}/10 passed ({elapsed:.2f}s)", flush=True)

    # Warm the SDK, codec and allocator before comparing resident resources.
    verify_artifact(capture_once(root / "warmup", align_depth=args.align_depth), args.align_depth)
    report["resource_baseline"] = resources()
    checkpoint()
    for cycle in range(1, 11):
        start = time.perf_counter()
        path = capture_once(root / "in_process", align_depth=args.align_depth)
        artifact = verify_artifact(path, args.align_depth)
        state = resources()
        report["in_process"].append({"cycle": cycle, "elapsed_s": time.perf_counter() - start, **artifact, "resources": state})
        checkpoint()
        assert not state["camera_handles"], f"Camera handle retained after cycle {cycle}: {state}"
        assert state["fd_count"] == report["resource_baseline"]["fd_count"], state
        assert state["threads"] == report["resource_baseline"]["threads"], state
        print(f"In-process {cycle}/10 passed: {state}", flush=True)

    # Real timeout and save failures must release the device for the next capture.
    try:
        capture_once(root / "timeout", timeout_ms=1, max_attempts=1, align_depth=args.align_depth)
    except TimeoutError as exc:
        report["timeout_failure"] = str(exc)
    else:
        raise AssertionError("Expected the 1 ms initial frame wait to time out")
    occupied = root / "output_is_a_file"
    occupied.write_text("Force a real output directory error.\n")
    try:
        capture_once(occupied, align_depth=args.align_depth)
    except NotADirectoryError as exc:
        report["save_failure"] = str(exc)
    else:
        raise AssertionError("Expected saving below an existing file to fail")
    report["recovery"] = verify_artifact(capture_once(root / "recovery", align_depth=args.align_depth), args.align_depth)
    report["resources_after_recovery"] = resources()
    checkpoint()
    state = report["resources_after_recovery"]
    assert not state["camera_handles"]
    assert state["fd_count"] == report["resource_baseline"]["fd_count"], state
    assert state["threads"] == report["resource_baseline"]["threads"], state
    values = [r["resources"]["rss_kib"] for r in report["in_process"]]
    report["rss_growth_after_warmup_kib"] = max(values) - report["resource_baseline"]["rss_kib"]
    allocated = [r["resources"]["allocated_bytes"] for r in report["in_process"]]
    report["allocated_growth_bytes"] = max(allocated) - report["resource_baseline"]["allocated_bytes"]
    # Record untrimmed RSS above. Release only idle pages once, in this test,
    # to distinguish allocator retention from live leaks; never trim in capture.
    LIBC.malloc_trim(0)
    report["resources_after_trim"] = resources()
    checkpoint()
    assert report["allocated_growth_bytes"] <= 1024 * 1024, "Live allocations grew by more than 1 MiB"
    assert report["resources_after_trim"]["rss_kib"] - report["resource_baseline"]["rss_kib"] <= 16 * 1024, "RSS remains elevated after freeing idle pages"
    for group in ("cli", "in_process"):
        times = [r["elapsed_s"] for r in report[group]]
        report[group + "_timing_s"] = {
            "mean": statistics.mean(times), "median": statistics.median(times),
            "p95": float(np.percentile(times, 95)),
        }
    report["status"] = "PASSED"
    checkpoint()
    print(f"Hardware checks passed: {root / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
