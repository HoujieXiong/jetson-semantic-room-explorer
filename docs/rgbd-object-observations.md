# First RGB-D Object Observations

Status: `VERIFIED` for minimum offline integration on the Jetson Orin Nano,
2026-09-10. Three existing mapped RGB-D frames produced 18 YOLO detections,
15 depth-accepted camera/map observations and three explicit depth rejections.
These are observations, not 15 distinct or confirmed objects.

## Input And Output Contract

`scripts/observe_rgbd_objects.py` consumes the verified NPZ frames and manifest
from the [colored point-cloud extraction](rtabmap-mapping.md#dense-colored-point-cloud-follow-up-2026-09-10).
They preserve original RGB8 color, registered uint16 millimeter depth, invalid
zeros and rectified CameraInfo on the same 1280x720 grid. Native sensor resolutions
differ; these images have already undergone the measured camera registration.
No image resizing is used for depth lookup. Ultralytics rescales its detection
boxes to the original image grid; its NumPy input receives explicit RGB-to-BGR
conversion. YOLO uses the existing local `yolov8n.pt`, `imgsz=640`, confidence
threshold 0.25 and CUDA device 0. Missing weights fail before library loading;
online checks and automatic dependency installation are disabled.

Each selected node must match its source RGB/depth and CameraInfo timestamps,
the frozen camera-pose export, and a validated source-time map observation.
The database, pose export and NPZ hashes are checked before inference. RGB/depth
skew is bounded at 5 ms; each stream's CameraInfo stamp must match its image.
Node IDs join the poses to the original integer nanosecond timestamps. Rounded
pose-text timestamps are not used as exact source identifiers. Node 1 is rejected
because its historical source-time map TF was unavailable.

Projection uses **frozen final optimized optical-camera poses** from `mapping_02`.
It does not substitute historical online TF or estimate a new trajectory.
Output records the map database and camera-pose hashes, source message hashes,
intrinsics, transform, original timestamps, model hash and runtime versions.
The intrinsics and pose checks are shared with the existing point-cloud script
through `scripts/rgbd_geometry.py`.

For each detection, the depth policy is:

1. Use the central 50% of the clipped box width and height.
2. Keep raw depths greater than zero and less than 5000 mm. Require at least
   20 pixels and 25% valid coverage of the inner ROI.
3. Reject values outside median +/- `max(0.02 m, 3 * 1.4826 * MAD)`.
   Require at least 20 remaining pixels and a P90-P10 spread at most 0.5 m.
4. Select an actual remaining pixel closest to the median depth, breaking ties
   by distance to the box center. Back-project using that pixel's own raw depth
   divided by 1000. Optical axes are x right, y down, z forward.
5. Apply `map_from_camera` to this camera point. Both point arrays are in meters.

`observations.json` retains every detection with its confidence, box, ROI,
valid/inlier counts and rejection reason or camera/map coordinates. Rejections
have no invented 3D point. The representative point samples a visible surface
inside a detection box; it is not an object center or a segmentation result.
Detector confidence is not geometric confidence. Thresholds are baseline
heuristics and have not been calibrated for accuracy.

PNG annotations show the outer detection box, inner depth ROI and selected
pixel cross. Green indicates that depth filtering passed; red indicates rejection.
It does not certify the class label. An inference/IO failure exits nonzero and
leaves an `INCOMPLETE` report once an output directory exists. A completed run
with no accepted points records `NO_VALID_OBSERVATIONS` and exits 2. Existing
output directories are refused to preserve previous evidence.

## Reproduce On This Jetson

Use a fresh shell with the existing native virtual environment, without the
isolated ROS/OpenCV overlay. The camera and ROS replay are not needed.

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/mapping -v

OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/observe_rgbd_objects.py \
  --frames data/outputs/rtabmap_slam/colored_cloud_20260910/frames/frames.json \
  --model "$PWD/yolov8n.pt" --nodes 7 14 32 \
  --output data/outputs/object_observations/NEW_RUN
```

Choose a new output directory. GPU device access is required: the initial Codex
sandbox probe failed with `NvRmMemInitNvmap`, while the authorized device-access
probe and inference both passed. There was no CPU fallback, package installation
or model download. The measured runtime was PyTorch 2.8.0, Ultralytics 8.4.112,
OpenCV 4.11.0 and device `Orin`; the earlier baseline used OpenCV 4.10.0.

## Measured Evidence

Local evidence root: `data/outputs/object_observations/m5_20260910/`.

| Node | Detections | Accepted | Rejected | RGB/depth skew |
| --- | ---: | ---: | ---: | ---: |
| 7 | 7 | 5 | 2 | 2.972 ms |
| 14 | 6 | 5 | 1 | 3.398 ms |
| 32 | 5 | 5 | 0 | 3.216 ms |

Two detections had no valid inner-ROI depth. The remaining rejected detection
had a 0.649 m inlier P90-P10 spread. All rejection records and annotations are
retained in `trial_01/observations.json` and `trial_01/node_{7,14,32}.png`.

Example: node 7's refrigerator detection had confidence 0.9371, selected pixel
`[524, 540]`, raw depth **4607 mm**, and source stamp `1789080208207783000` ns.
Its optical-camera point was `[-0.676296, 1.253994, 4.607000]` m and map point
`[4.677179, 0.829901, -0.809701]` m. Its inner ROI was 82.65% valid, with
0.127 m inlier P90-P10 spread. Map coordinates are relative to this saved map's
origin; negative map z does not imply a negative camera depth or floor height.

Verification saved in `unit_tests.log`, `artifact_verification.json` and
`visual_inspection.json`:

- All 21 focused tests passed: 12 object-depth/time-association tests and nine
  existing point-cloud regression tests. The three affected scripts compiled.
- All 15 accepted points use actual source-depth pixels. Independent Open3D
  camera/map projection differs by at most **2.251e-7 m** per coordinate.
  This checks computation, not physical accuracy. All three PNGs read back at
  1280x720, and rejected detections contain no camera/map point.
- A real CLI attempt to use node 1 exited 1 with the explicit missing source-time
  map association error, before creating an output directory or loading YOLO.
- The bounded GPU process exited 0 in **17.826 s**, without timeout; peak child
  RSS was **1250468 KiB**. This is a single-process RSS measurement, not total
  Jetson/GPU memory accounting or a long-duration resource-leak test.
- After review consolidated inference settings into the same values recorded in
  JSON, `trial_02` exited 0 in 11.654 s, peak child RSS 1253916 KiB. Its complete
  report exactly matched `trial_01` after excluding timing fields. See
  `repeat_comparison.json` and `trial_02_process.json`. All 21 focused tests also
  passed again in `final_unit_tests.log`; no detector or depth policy changed.

Synchronized prediction wall times were **8121.49, 64.56 and 49.32 ms**. Including
depth processing and annotation drawing, they were **8226.27, 77.59 and 65.37 ms**,
excluding PNG serialization. For all three processing times, min/median/P95/max
were 65.37/77.59/7411.40/8226.27 ms. There was no explicit warmup; the first
prediction includes initialization. Three selected frames cannot establish
steady-state latency, throughput or concurrent SLAM performance. Per-stage times
and the complete process log remain in the evidence directory.

Visual inspection found overlapping chair detections in node 7 and likely class
errors: node 14's `laptop` box includes a paper-towel roll, and node 32's `oven`
box covers cabinet furniture. Depth acceptance cannot resolve these semantic
errors, background pixels inside boxes, or registration edge errors. Existing
SLAM tracking gaps, map accuracy, repeated-view jitter and live behavior remain
unverified. No model or mapping tuning was attempted in this step.

The next action is a minimal persistent SQLite scene memory using these saved
observations, with explicit association evidence and reopenable object queries.
Room images, observations, weights and verification outputs remain local and
ignored; only implementation, tests and measured documentation are committed.
