# Femto Mega RGB-D capture and registration

Run from the repository root on the Jetson, with the existing `.venv`:

```bash
.venv/bin/python scripts/femto_mega_capture_once.py --list-profiles
.venv/bin/python scripts/femto_mega_capture_once.py
.venv/bin/python scripts/femto_mega_capture_once.py --align-depth
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
The raw depth and color are synchronized in time but **not registered pixel-for-pixel**.
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

## Optional depth-to-color registration

`--align-depth` preserves the raw artifacts above and adds:

- `depth_aligned.png`: 1280 x 720 uint16 SDK-registered counts, on the original
  color image's distorted pixel grid. Zero remains invalid.
- `alignment_overlay.png`: 65% original color plus 35% TURBO depth visualization,
  normalized by valid-depth P95. Invalid depth leaves the original color visible;
  the overlay is a diagnostic, not a metric image or a filled depth map.
- `metadata.aligned_depth`: actual delivered profile, intrinsics, distortion,
  scale, source depth timestamps/index, optical frame, depth statistics, filter
  settings and processing duration. The top-level `alignment` still describes
  the preserved raw pair.

The installed SDK example `beginner/03_color_and_depth_aligned.py` uses
`AlignFilter`. Local profile queries advertise the selected raw pair for both
software and hardware D2C, but only **software AlignFilter** was executed here.
It processes the retained synchronized frameset after the pipeline stops. This
keeps the single-capture lifecycle and original buffers intact.

The filter's default `TargetDistortion=0` produces zero target distortion and
would not match the saved original color image. The utility explicitly sets and
reads back `TargetDistortion=1`, `MatchTargetRes=1`, and `GapFillCopy=0`. It checks
that aligned calibration equals color calibration, timestamps/index equal source
depth, and raw depth and decoded color remain unchanged. Unsupported settings,
empty filter output, calibration mismatch and save failures raise errors. No
host resizing or hole filling is applied.

Raw depth measures axial Z in `depth_optical`; aligned depth measures axial Z in
`color_optical`. Both use x right, y down, z forward. The aligned scale must be
read from `metadata.aligned_depth.encoding`, even though both measured scales
here are 1.0 mm/count. SDK registration transforms 3D geometry: counts can change
when the optical frame changes. The two images' center ROIs are different rays,
so their median difference is not a registration-error measurement. Color pixels
still require the saved distortion model for accurate back-projection.

Run the affected lifecycle checks with:

```bash
.venv/bin/python tests/check_femto_hardware.py --align-depth --output-dir data/outputs/femto_mega_capture/alignment_stability_new
```

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
isolated. At this checkpoint depth and color still used separate optical frames;
the subsequent registration verification is recorded below.

### SDK registration verification

Status: optional SDK depth-to-color registration `VERIFIED` on the same Jetson,
SDK and native stream profiles, without dependency or device-setting changes.
Evidence root: `data/outputs/femto_mega_capture/alignment_verification_20260910/`.
`stability/summary.json` reports `PASSED`; captures ran at 18:30–18:32 UTC in 25 W
mode with no project ML/SLAM workload launched.

| Check | Measured result |
| --- | --- |
| Offline tests | 21 passed, including known projection/edge cases and explicit filter failures |
| Separate CLI / same-process cycles | 10/10 and 10/10, plus warmup and timeout/save-error recovery |
| Saved image sizes | Color and aligned depth 1280 x 720; original depth 640 x 576 |
| Raw / aligned scale | Both 1.0 mm/count in all 20 captures |
| Absolute RGB/depth timestamp skew | 200–413 us; aligned timestamps/index exactly preserved |
| Raw / aligned valid coverage | 69.40–69.59% / 60.85–61.08% |
| Raw / aligned center medians | 2.353–2.355 m / 2.347–2.349 m; all center ROIs 400/400 valid |
| Cold filter process time, mean / median / P95 | 139.46 / 141.88 / 143.38 ms |
| CLI total time, mean / median / P95 | 4.553 / 4.543 / 4.620 s |
| Same-process total time, mean / median / P95 | 4.264 / 4.262 / 4.283 s |
| Descriptors / threads after close | 4 / 12, matching warmed baseline; no camera handles |
| Untrimmed RSS, baseline / peak | 85112 / 157764 KiB |
| Live allocation growth over ten cycles | 70256 bytes |
| RSS after recovery and test-only idle-page trim | 96800 KiB (11688 KiB above baseline) |

These are single captures with a newly constructed filter, not a sustained
30 FPS alignment benchmark. The allocator retained idle pages; unchanged bounded
resource guards passed, without proving long-duration absence of SDK leaks.
Coverage is scene-dependent; the lower percentages than the earlier physical
check are recorded rather than treated as a universal camera characteristic.
Different optical fields of view and occlusions also prevent direct equality
between raw and aligned coverage.

After adding explicit raw/target optical-frame and axial-Z metadata labels, one
raw-only and one aligned capture passed artifact/contract checks again; see
`final_contract.json`, its log, and `final_raw_only/` / `final_aligned/`. Those
serialization-only additions do not change the earlier lifecycle path.

#### Geometry and visible boundaries

The first three CLI artifacts were checked offline and their overlays inspected.
`geometry.json` records every count, ROI and statistic; `analyze.py` alongside it
reproduces the report from the repository root. Test helpers in
`tests/check_femto_hardware.py` also work on new saved frames:

```python
import json, sys
from pathlib import Path
import cv2
sys.path.insert(0, "tests")
from check_femto_hardware import registration_edge_metrics, registration_projection_metrics
path = Path("data/outputs/femto_mega_capture/<timestamp>")
metadata = json.loads((path / "metadata.json").read_text())
color = cv2.imread(str(path / "color.png"))
raw = cv2.imread(str(path / "depth_raw.png"), cv2.IMREAD_UNCHANGED)
aligned = cv2.imread(str(path / "depth_aligned.png"), cv2.IMREAD_UNCHANGED)
print(registration_projection_metrics(raw, aligned, metadata))
# Choose an actual object boundary ROI [x, y, width, height] for the current scene.
print(registration_edge_metrics(color, aligned,
    metadata["aligned_depth"]["encoding"]["scale_mm_per_count"], (835, 335, 160, 35)))
```

The projection check independently undistorts raw rays with OpenCV, transforms
metric 3D points using saved depth-to-color extrinsics, then projects onto the
distorted color grid. It samples every eighth row/column, excluding an eight-pixel
border and requiring a valid 3 x 3 source patch with at most 20 mm depth spread.
Across three frames, 2685–2692 target samples per frame were valid. Absolute
color-frame Z residual medians were 0.936–0.950 mm, P95 3.870–3.976 mm, and maxima
20.52–41.64 mm. Incorrectly retaining source-frame Z instead gave median residuals
47–48 mm. This checks consistency with the device calibration, not independent
distance accuracy; occlusions and rasterization can still produce outliers.

Five ROIs were selected on the initial overlay before analyzing these three
captures. Distances below are to the nearest RGB Canny edge (thresholds 60/120
after a 3 x 3 blur). Valid-to-valid depth jumps of at least 50 mm are separated
from valid/invalid mask boundaries. Each range spans the three frame statistics.

| Boundary, ROI xywh | Depth-jump count; median / P95 distance (px) | Invalid-mask boundary P95 (px) |
| --- | --- | --- |
| Upper drawer bottom, 835 335 160 35 | 12–16; 1 / 1–2 | 3–4 |
| Middle drawer bottom, 835 465 160 35 | 18–25; 1–2 / 3.61–4.02 | 3.61–4 |
| Shelf right, 977 270 45 220 | 0–3; 2 / 2 when present | 5 |
| Basket right, 430 535 50 80 | 0; no valid depth-jump samples | 15.77–18 |
| Air conditioner left, 1118 365 45 120 | 0–5; 4 / 4–4.10 when present | 6.08–8.10 |

The drawer boundaries agree closely in this diagnostic. Basket and air-conditioner
regions show wider missing-depth gaps; mesh/near-chair regions also retain many
invalid pixels. The few valid jump samples at the air conditioner are about
four pixels from RGB edges. Texture edges, occlusions and missing returns bias
nearest-edge distances, so these values do not certify calibration accuracy or
uniform pixel correspondence across the image. Holes remain invalid.

The earlier `alignment_probe_20260910T182532Z/probe.json` records advertised D2C
profiles and the default-filter distortion mismatch; `alignment_initial/` holds
the first successful explicitly configured capture. These diagnostic artifacts
and the final images remain ignored. The verified contract is ready for M3 ROS 2
camera topics and a replayable rosbag; that integration has not been started.

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
