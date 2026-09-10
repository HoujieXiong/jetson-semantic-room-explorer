# Femto Mega native RGB-D capture

Run from the repository root on the Jetson, with the existing `.venv`:

```bash
.venv/bin/python scripts/femto_mega_capture_once.py --list-profiles
.venv/bin/python scripts/femto_mega_capture_once.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_femto_hardware.py --output-dir data/outputs/femto_mega_capture/stability_new
```

The hardware test requires a new output directory and exclusive access to the
camera. It runs ten separate CLI processes, one allocator/SDK warmup capture,
ten captures in one process, and real timeout/save-error recovery checks. It
saves every artifact, CLI log, timing distribution, file-descriptor/thread count,
and resident-memory measurement. It also measures glibc live allocations and
free arena space. After all cycles it releases idle allocator pages once, in
the test only, and checks live allocation growth (at most 1 MiB) and remaining
RSS growth (at most 16 MiB). Untrimmed RSS remains in the report. These are
bounded smoke-test guards, not a native memory-leak proof. SDK logs remain in
ignored `Log/`. An interrupted or failed report remains `INCOMPLETE`.

## Capture contract

The inspected device is a USB Femto Mega (PID `0x0669`), firmware `1.3.1`,
connected at 5000 Mbit/s. The installed distribution is `pyorbbecsdk2==2.1.1`,
imported as `pyorbbecsdk`; its native SDK reports `2.8.6`. The actual `cv2` import
reports `4.11.0`, despite `opencv-python-headless==4.10.0.84` also being installed;
this existing package overlap was left unchanged. The camera advertises
126 color profiles and 14 depth profiles. `profiles.json` contains the full
inventory, including formats; printed profile representations omit the format.

This utility selects the measured pair explicitly:

| Stream | Resolution | Format | Rate |
| --- | --- | --- | --- |
| Color | 1280 x 720 | MJPG, decoded to color PNG | 30 FPS |
| Depth | 640 x 576 | Y16, saved unchanged as uint16 PNG | 30 FPS |

Both profiles must exist. Unsupported profiles are an error; the utility does
not silently choose a different resolution or treat missing depth as success.
Only the selected MJPG/Y16 formats are implemented. The camera must already be
in `STANDALONE` synchronization mode. The utility enables SDK frame matching,
requires complete color/depth framesets, and accepts device timestamp differences
of at most 5000 microseconds. This is an application bound, not a guarantee that
color and depth exposure intervals are identical. Frame indexes differ between
sensors; compare device timestamps, not indexes or host arrival times.

The first 15 synchronized pairs are discarded for sensor stabilization, following
the installed SDK's `examples/advanced/03_save_image_to_disk.py`. All waits,
including warmup, count against `--max-attempts` (default 60); each wait is bounded
by `--timeout-ms` (default 1000). Rejected-frame counts are saved. These settings
bound frame acquisition, not a native SDK call that itself hangs; the hardware
test also applies a 90-second timeout to each CLI process.

Each successful capture creates a unique UTC directory containing:

- `color.png`: 1280 x 720 color image; OpenCV's in-memory BGR is encoded correctly
  into PNG. The source MJPG is already lossy.
- `depth_raw.png`: 640 x 576 original uint16 SDK counts, without metric rounding,
  clipping, resizing, alignment, or additional host filtering. Camera-internal
  processing is not bypassed.
- `depth_vis.png`: a display-only color map normalized by the valid-depth 95th
  percentile, with invalid pixels black. Its colors do not have fixed units.
- `metadata.json`: device/SDK versions, selected and delivered profiles, per-image
  intrinsics/distortion, device and system timestamps in microseconds, sync mode
  and skew, metric scale, depth statistics, and depth-to-color extrinsics.

The pipeline is stopped before writing. All PNGs are read back and compared
exactly with the arrays being saved. `metadata.json` is written last; a directory
without a complete, parseable metadata file is an incomplete capture. Any stop,
format, calibration, timeout, or save failure terminates with an error.

## Depth and geometry

`depth_raw.png` stores **counts**, not an assumed millimeter encoding:

```text
valid = raw_count != 0
z_m = raw_count * metadata.depth_encoding.scale_mm_per_count / 1000
```

The tested SDK reports `1.0` mm/count. Zero is invalid, not zero-distance.
Fractional scales and values exceeding 65535 mm are handled in floating-point
statistics; the raw PNG is never converted through uint16 millimeters. A center
20 x 20 depth ROI has its valid ratio and median recorded. A fully invalid center
is represented by JSON `null` rather than a fabricated distance.

Each image retains its own optical camera frame (x right, y down, z forward).
Depth and color are synchronized in time but **not registered pixel-for-pixel**.
Use the depth intrinsics for depth pixels and the color intrinsics for color
pixels; do not resize depth to color and assume correspondence. The saved
extrinsic maps depth-camera points to color-camera points, with translation in
millimeters and a row-major rotation matrix. Intrinsics are in pixels; all eight
SDK distortion coefficients are exported. Account for distortion before applying
pinhole back-projection; use the SDK's calibrated transformations for this camera.

The installed SDK calibration example documents extrinsic translation in mm;
its depth visualization example documents `get_depth_scale()` in mm/count.
Offline tests independently check known metric values, fractional scales,
invalid samples, raw buffer ownership, codec round trips, and rejection paths.
A physical distance check complements the SDK unit contract. The range check
below passed against a user-supplied 2-3 m reference; it does not measure absolute
distance accuracy.

## Physical distance check

Fix the camera facing a flat, matte surface near the center of the **depth**
image. Measure and record camera-front-to-surface distance with a ruler or tape,
keep the surface approximately perpendicular to the optical axis, and capture
again. Record the reference distance, measurement uncertainty, center ROI valid
ratio, depth median, and signed error in meters. The front housing is only an
approximation to the optical origin; this checks units rather than precise
factory calibration. A center ROI with no valid depth cannot pass this check.
A reported distance interval can support a coarse unit check; keep that interval
as supplied and leave signed error unset until a point reference is available.

## Measured on 2026-09-10

Initial status: capture/artifact/lifecycle checks `VERIFIED`; M2 was `IMPLEMENTED`
while the physical check was blocked. The later range check below completes
M2's native capture/unit acceptance; the initial measurements remain as history.

Evidence root: `data/outputs/femto_mega_capture/verification_20260910/` (ignored).
The final runner exited 0 and wrote `final/summary.json` with status `PASSED`.
That status covers the automated checks, not the missing physical measurement.
Conditions: Jetson Orin Nano, 25 W mode, L4T R36.5.0, Python 3.10.12,
NumPy 1.26.4, OpenCV 4.11.0; no project inference or SLAM workload launched.

| Check | Measured result |
| --- | --- |
| Offline tests | 14 passed (`offline_tests.log`) |
| Separate open/capture/close executions | 10/10, all exit 0 |
| Same-process open/capture/close cycles | 10/10 after one warmup capture |
| RGB/depth absolute device timestamp skew, 20 captures | 72–670 us |
| Raw depth scale | 1.0 mm/count in all 20 captures |
| Valid-depth coverage, 20 captures | 0.2764–0.2930%; center ROI 0% valid |
| Nonzero raw counts across 20 captures | 46–12465; physical accuracy unverified |
| File descriptors / threads after each close | 4 / 12, equal to warmed baseline |
| Retained video/USB/HID handles | None |
| Untrimmed RSS, baseline / peak over ten cycles | 81072 / 131744 KiB |
| Live glibc allocation growth over ten cycles | 54640 bytes |
| RSS after error recovery and one idle-page trim | 87648 KiB |
| Separate CLI duration, mean / median / P95 | 4.538 / 4.534 / 4.564 s |
| Same-process duration, mean / median / P95 | 4.186 / 4.184 / 4.197 s |
| Real failure recovery | 1 ms timeout and invalid output path raised errors; subsequent capture passed |

These durations include open, 15-pair warmup, capture, close and PNG verification;
they are not streaming FPS. The RSS rise is retained allocator memory: the
test records it and trims idle pages only after the measured cycles. The
production utility does not trim. This short run found no retained camera
handles or accumulating threads; it does not certify long-duration SDK behavior.

`profiles.json` records all advertised formats. `final/cli_01/` through
`final/cli_10/` and `final/in_process/` contain the complete artifacts;
`final.log` and `sdk.log` preserve test/SDK output. `depth_diagnostic/summary.json`
records ten samples from a 150-pair observation: coverage remained 0.2827–0.2951%
and the center remained invalid. Warmup did not fix this scene's depth coverage.
Camera properties were read without changing settings; the supported exposure
readback was 125 (SDK integer units), depth mirror/flip were false, and reported
IR/laser temperatures were 25.0/26.6 degrees C. The cause remains undetermined.

Earlier diagnostic artifacts are retained: `probe.log` initially observed about
21% valid coverage; `stability/` was interrupted before the warmup revision;
`stability_warm.log` failed the original RSS-only guard. The follow-up
`memory_diagnostic/summary.json` distinguished idle arena pages from live
allocations before the final test was revised. None of these earlier runs is
substituted for the final evidence.

### Physical range check after repositioning

Status: M2 native capture and coarse metric units `VERIFIED`. The user reported
a fixed, unobstructed camera and a front-panel-to-wall distance of 200-300 cm.
This is an interval, not a precise 250 cm reference. No signed accuracy error
was calculated and no capture-code or device-setting changes were made.

Three independent captures at 18:19 UTC passed the existing artifact checker
and independent PNG/ROI decoding. The depth ROI was `[310, 278, 20, 20]`:

| Capture | Center median count | Center median | Valid image pixels | Valid center pixels | Absolute RGB/depth skew |
| --- | --- | --- | --- | --- | --- |
| 1 | 2333 | 2.333 m | 74.8714% | 400/400 | 316 us |
| 2 | 2332 | 2.332 m | 74.9156% | 400/400 | 267 us |
| 3 | 2332 | 2.332 m | 74.9064% | 400/400 | 410 us |

All three centers lie within the independent 2-3 m reference using the reported
1.0 mm/count scale. Combined with the earlier ten-run lifecycle and metadata
checks, this meets M2's simple physical unit check. The 1 mm spread between
medians describes these three observations, not absolute accuracy. A narrower
tape-measure reference is needed for an accuracy experiment.

Evidence root: `data/outputs/femto_mega_capture/physical_check_20260910T181935Z/`.
`physical_reference.json` preserves the user's interval and reference surface;
`summary.json` records the three measurements and assessment. Each `capture_01/`
through `capture_03/` holds the complete raw artifacts, with matching CLI logs
beside them. The earlier lifecycle evidence remains applicable because the
capture code is unchanged.

Depth coverage recovered after repositioning. Placement or scene conditions are
a plausible explanation for the earlier dropout, but its exact cause was not
isolated. Depth and color still use separate optical frames; the next task is
SDK depth-to-color registration with preserved raw artifacts and checked edges.

## Troubleshooting

- **SDK import:** use `.venv/bin/python`; the package distribution name differs
  from its import name. No dependency reinstall was needed for this milestone.
- **USB/device open:** inspect `lsusb -t`, `/sys/bus/usb/devices`, permissions on
  `/dev/video*` and `/dev/bus/usb/*`, and `Log/OrbbecSDK.log.txt`. Another viewer or
  driver may already own the camera. Preserve the original SDK error.
- **Sandbox initialization:** the tool sandbox can fail with `getifaddrs:
  Operation not permitted` or `libusb: -99` despite a visible camera. Hardware
  verification here used authorized execution outside that sandbox; this is not
  evidence that the camera or SDK is absent.
- **Profile negotiation:** use `--list-profiles`; RGB and depth resolutions are
  independent. The Python profile list includes SDK-converted color formats.
- **Timeout:** check both streams, STANDALONE mode, USB bandwidth, and the logged
  counts of missing/unsynchronized frames. Warmup needs at least 16 accepted
  pairs. Increasing retries cannot fix an unsupported profile.
- **Low valid-depth ratio:** inspect raw statistics and the scene, including
  occlusion, near objects, surfaces, and illumination. Record the ratio; a
  successful file write does not establish useful depth coverage.
- **Save error:** inspect free space and the output path. Partial output has no
  completed metadata file. Fix the path and run again; failures are not converted
  into success messages.
