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


def verify_artifact(path: Path) -> dict:
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
    return {"path": str(path), "skew_us": delta, "scale_mm": scale, **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "platform": platform.platform(), "python": sys.version,
        "opencv": cv2.__version__, "numpy": np.__version__,
        "power_mode": subprocess.check_output(["nvpmodel", "-q"], text=True).strip(),
        "workload": "headless camera capture; no project ML/SLAM workload launched",
        "status": "INCOMPLETE", "cli": [], "in_process": [],
    }

    def checkpoint():
        (root / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    script = Path(__file__).resolve().parents[1] / "scripts/femto_mega_capture_once.py"
    for cycle in range(1, 11):
        output = root / f"cli_{cycle:02d}"
        start = time.perf_counter()
        command = [sys.executable, str(script), "--output-dir", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        elapsed = time.perf_counter() - start
        (root / f"cli_{cycle:02d}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, f"CLI cycle {cycle} failed; see saved log"
        artifacts = list(output.glob("*/metadata.json"))
        assert len(artifacts) == 1, f"CLI cycle {cycle} did not save exactly one pair"
        report["cli"].append({"cycle": cycle, "elapsed_s": elapsed, "exit_code": result.returncode, **verify_artifact(artifacts[0].parent)})
        checkpoint()
        print(f"CLI {cycle}/10 passed ({elapsed:.2f}s)", flush=True)

    # Warm the SDK, codec and allocator before comparing resident resources.
    verify_artifact(capture_once(root / "warmup"))
    report["resource_baseline"] = resources()
    checkpoint()
    for cycle in range(1, 11):
        start = time.perf_counter()
        path = capture_once(root / "in_process")
        artifact = verify_artifact(path)
        state = resources()
        report["in_process"].append({"cycle": cycle, "elapsed_s": time.perf_counter() - start, **artifact, "resources": state})
        checkpoint()
        assert not state["camera_handles"], f"Camera handle retained after cycle {cycle}: {state}"
        assert state["fd_count"] == report["resource_baseline"]["fd_count"], state
        assert state["threads"] == report["resource_baseline"]["threads"], state
        print(f"In-process {cycle}/10 passed: {state}", flush=True)

    # Real timeout and save failures must release the device for the next capture.
    try:
        capture_once(root / "timeout", timeout_ms=1, max_attempts=1)
    except TimeoutError as exc:
        report["timeout_failure"] = str(exc)
    else:
        raise AssertionError("Expected the 1 ms initial frame wait to time out")
    occupied = root / "output_is_a_file"
    occupied.write_text("Force a real output directory error.\n")
    try:
        capture_once(occupied)
    except NotADirectoryError as exc:
        report["save_failure"] = str(exc)
    else:
        raise AssertionError("Expected saving below an existing file to fail")
    report["recovery"] = verify_artifact(capture_once(root / "recovery"))
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
