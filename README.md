# Jetson Semantic Room Explorer

Autonomous semantic room exploration and object memory on Jetson Orin Nano.

> The living architecture, milestone plan, Codex CLI workflow, verification
> criteria, and recovery protocol are maintained in [AGENTS.md](AGENTS.md).

The first **offline pipeline MVP is verified** on the Jetson: one command takes
saved RGB-D frames and final map poses through GPU detection, persistent object
memory and search decisions. See the [runnable demo and measured timeline](docs/rgbd-search-demo.md).
Planning starts are explicitly simulated. SLAM and GPU perception now also pass
a bounded concurrent rosbag trial at 0.25x. Its own final map and observations
now feed a separate persistent memory and matching search preview; see the
[measured finalization](docs/finalize-concurrent-memory.md). Sustained real-time
throughput and physical navigation remain unverified.

A new forward/backward recording also passes the full pipeline: 899 RGB-D pairs,
898 tracked odometry outputs with zero reported tracking losses at 0.25x replay,
and a separate map/memory/search result. Distance was estimated, so physical
scale accuracy remains unverified. See the
[capture results and playable video command](docs/straight-line-capture.md).

ROS 2 goal/path preview publication is also verified against independent
subscribers, including explicit refusal and timeout cases. See the
[ROS preview commands](docs/ros-search-preview.md).

Persistent image-text retrieval is now verified on 63 source observations and 17
provisional objects. A text phrase can drive candidate selection, map checks and
ROS previews; retrieval quality remains limited (including failed bottle queries).
See [semantic memory, query results and the browser review](docs/semantic-memory.md).

CuTR RGB-D now runs on official samples and existing Femto frames. Warm inference
is about 1.8 seconds; a concurrent SLAM trial stopped CuTR at the declared low-memory
guard before its first result. It remains an offline research comparison. See
[CuTR measurements, images and limitations](docs/cutr-feasibility.md).

Causal observation memory and label queries now also pass during a bounded
899-pair replay. SQLite retains 1,019 observation/map events, and queries use only
their committed prefix and one received graph revision. A refrigerator is found
before playback ends; reopening preserves 14 provisional active-graph objects.
See [online memory, query timeline and measured limits](docs/online-scene-memory.md).
MobileCLIP text queries now also pass during playback: 59 keyframes produce 226
source-verified crops/vectors; refrigerator synonyms select the visible fridge,
while unknown and bottle queries remain below the fixed threshold. CLI queries
take 14–16 seconds including model startup. See
[online text retrieval and its limitations](docs/online-semantic-memory.md).
Text queries now also drive ROS decisions from matching online graph/grid
snapshots. One recorded-data frontier goal/path is independently received; its
simulated start nearly coincides with the goal, so this does not validate room
travel. Unknown starts, insufficient clearance and stale maps correctly refuse
goals. See [causal search previews and measured limits](docs/online-search-preview.md).
Sustained real-time throughput and physical navigation remain unverified.

A bounded **live camera measurement is now verified**: 947 recorded RGB-D pairs,
221 tracked odometry outputs and 1,162 persistent events, with one independently
received ROS refusal. Real input exposes transport loss, heavy frame dropping and
stationary map-node merging that leaves the query without eligible object support.
This does not establish useful live object search. See the
[live measurements, retained failures and source evidence](docs/live-rgbd-search.md).

## Goal

Build a robot-facing system that can explore an indoor environment, estimate camera pose with RGB-D SLAM, detect objects with an edge-optimized YOLO pipeline, localize objects in 3D, and maintain persistent object memory.

The system should eventually support queries such as:

```text
Where is the bottle?
What objects have been seen in this room?
Where did I last see my backpack?
```

## Core Idea

This project is not just a YOLO demo. The goal is to connect perception, mapping, and memory:

```text
Femto Mega RGB-D camera
-> RTAB-Map RGB-D SLAM and timestamped camera pose
-> YOLO-plus-depth baseline or CuTR keyframe 3D cuboids
-> map-frame temporal fusion
-> persistent open-vocabulary scene memory
-> query, goal proposal, and later autonomous exploration
```

The key transformation is:

```text
map_T_object = map_T_camera * camera_T_object
```

RTAB-Map provides the camera pose in the map frame. The stable baseline uses
YOLO and depth for camera-frame object positions. The advanced path evaluates
Cubify Transformer (CuTR) for class-agnostic 3D cuboids on selected keyframes,
with semantic labels or text embeddings supplied separately. Together, the
system stores fused object observations in persistent room-level memory.

## Hardware

Target hardware:

- Jetson Orin Nano
- Orbbec Femto Mega RGB-D camera; native synchronized capture and coarse depth-unit check verified
- Optional mobile robot base
- Optional DisplayPort dummy plug for headless remote desktop

Current development mode:

- Jetson Orin Nano
- JetPack 6.2.2
- Ubuntu 22.04.5 LTS
- Jetson Linux / L4T R36.5.0
- SSH / headless workflow
- Image/video-file inference baseline; native RGB-D capture now available
- YOLOv8n image inference running on Jetson GPU
- ROS2 Humble environment available

## Software Stack

Planned stack:

- Ubuntu 22.04
- JetPack 6.2.2
- ROS2 Humble
- RTAB-Map RGB-D SLAM
- YOLO object detection
- Cubify Transformer RGB-D 3D detection, experimental
- MobileCLIP-S0 text-aligned embeddings, minimum saved-data integration verified
- ONNX
- TensorRT FP16
- OpenCV
- Python
- C++ where performance-critical
- RViz visualization

Current verified Jetson base stack:

- Ubuntu 22.04.5 LTS rootfs
- Jetson Linux / L4T R36.5.0
- CUDA 12.6 runtime present
- cuDNN 9.3 runtime libraries present
- TensorRT 10.3 runtime libraries present
- VPI 3.2 packages present
- NVIDIA multimedia / GStreamer stack present
- NVIDIA container runtime / toolkit present
- Docker present
- ROS2 Humble environment sourced successfully

Current verified ML environment:

- Python 3.10.12
- PyTorch 2.8.0
- TorchVision 0.23.0
- CUDA available on Orin GPU
- NumPy 1.26.4
- OpenCV 4.10.0 headless
- Ultralytics 8.4.112

Known environment notes:

- `nvcc` is not currently on `PATH`; CUDA runtime is present and PyTorch CUDA inference works.
- TensorRT runtime libraries are present, but Python `tensorrt` binding still needs to be added before the TensorRT phase.
- VPI system packages are present; VPI Python is not visible inside the current project virtual environment.
- The project uses `opencv-python-headless` in the virtual environment for SSH/headless development.

## Important Paths

Jetson project paths:

```text
Project root:
~/projects/jetson-semantic-room-explorer

Python virtual environment:
~/projects/jetson-semantic-room-explorer/.venv

Sample images:
~/projects/jetson-semantic-room-explorer/data/sample_images

Sample videos:
~/projects/jetson-semantic-room-explorer/data/sample_videos

Project outputs:
~/projects/jetson-semantic-room-explorer/data/outputs

Ultralytics default runs:
~/projects/jetson-semantic-room-explorer/runs

YOLO smoke test output:
~/projects/jetson-semantic-room-explorer/runs/detect/data/outputs/yolo_smoke_test

Models:
~/projects/jetson-semantic-room-explorer/models

Benchmarks:
~/projects/jetson-semantic-room-explorer/benchmarks

Environment snapshot:
~/projects/jetson-semantic-room-explorer/docs/jetson_env_snapshot.txt

Jetson stack check:
~/jetson_stack_check.txt
```

System paths:

```text
ROS2 Humble setup:
/opt/ros/humble/setup.bash

CUDA symlink:
/usr/local/cuda

CUDA 12.6 root:
/usr/local/cuda-12.6

NVIDIA multimedia packages:
/usr/lib/aarch64-linux-gnu/nvidia

NVIDIA container runtime config:
/etc/nvidia-container-runtime/config.toml

Docker daemon config:
/etc/docker/daemon.json
```

## Project Phases

### Phase 1: Jetson Bring-Up

Status: mostly complete

Goals:

- Set up Jetson Orin Nano
- Confirm JetPack, CUDA, TensorRT, Python, and disk/memory state
- Create reproducible project structure
- Configure Git and GitHub
- Establish headless SSH workflow

Deliverables:

- Environment snapshot
- Project repository
- Basic Python/OpenCV validation
- Jetson-compatible PyTorch / TorchVision with CUDA validation
- ROS2 Humble environment validation

### Phase 2: YOLO Perception Baseline

Status: image inference and repeated-image benchmark verified

Goals:

- Run YOLO on still images
- Run YOLO on video files
- Save annotated outputs without GUI
- Measure baseline PyTorch latency and FPS

Deliverables:

- Image inference script
- Video inference script
- Annotated output images/videos
- Baseline benchmark table

Current milestone:

```text
YOLOv8n PyTorch inference runs on Jetson Orin Nano GPU.
Test input: data/sample_images/test.jpg
Detected classes: person, cars, trains, traffic light
Model inference latency: 34.0 ms
Preprocess latency: 44.0 ms
Postprocess latency: 35.8 ms
Input tensor shape: (1, 3, 448, 640)
Output directory: runs/detect/data/outputs/yolo_smoke_test
```

PyTorch baseline benchmark:

```text
Model: YOLOv8n
Backend: PyTorch
Device: Jetson Orin Nano GPU
Input: data/sample_images/test.jpg
Image size: 640
Confidence threshold: 0.25
Warmup runs: 10
Benchmark runs: 50
Detections per run: 7

Mean inference latency: 30.76 ms
Median inference latency: 32.93 ms
P95 inference latency: 33.09 ms

Mean total wall time: 59.79 ms
Median total wall time: 62.51 ms
P95 total wall time: 63.59 ms

Estimated FPS from mean total wall time: 16.72 FPS
CSV: benchmarks/yolo_pytorch_baseline.csv
```

Benchmark table:

| Model   | Backend | Device   | Image Size | Mean Inference | Mean Total | FPS   | Notes               |
| ------- | ------- | -------- | ---------- | -------------- | ---------- | ----- | ------------------- |
| YOLOv8n | PyTorch | Orin GPU | 640        | 30.76 ms       | 59.79 ms   | 16.72 | image-file baseline |

### Phase 3: Femto Mega RGB-D Bring-Up

Native capture is verified on the Jetson as of 2026-09-10:

| Check | Measured result |
| --- | --- |
| Synchronized streams | 1280x720 MJPG color + 640x576 Y16 depth, 30 FPS |
| Saved contract | Raw images, intrinsics, distortion, extrinsics, timestamps, depth scale and profiles |
| Lifecycle | 10 independent runs + 10 same-process cycles; failure recovery passed |
| Physical unit check | Center depth 2.332-2.333 m within the user-reported 2-3 m wall range |
| Depth coverage after repositioning | About 74.9% overall; 400/400 valid center pixels |
| Offline checks | 14 tests passed |

Capture a new pair from the repository root:

```bash
.venv/bin/python scripts/femto_mega_capture_once.py
```

SDK depth-to-color registration is also verified. Add `--align-depth` to save
1280x720 registered depth and an overlay alongside the original raw pair.
Aligned calibration matches the original color image, with explicit optical
frames, depth units and preserved source timestamps. Twenty capture cycles
passed (10 separate CLI processes and 10 in one process); all 21 offline tests
passed. Aligned center depth was 2.347–2.349 m with 60.85–61.08% whole-image
coverage in this scene. Object-edge diagnostics retain and quantify invalid
regions, including up to 18 px P95 distance to RGB edges near the basket.

Absolute distance accuracy and sustained 30 FPS recording remain unverified.
See [native capture commands and evidence](docs/camera-femto-mega.md).

M3's stationary ROS camera/rosbag step is verified on the Jetson. Driver/SDK 2.9.3
builds in an isolated workspace with OpenCV 4.8 and two small upstream fixes.
System packages and the native capture implementation remain unchanged.

- Final source profiles: 1280x720 RGB and 640x576 depth at 15 FPS; published RGB
  and hardware-registered depth share the undistorted 1280x720 grid and CameraInfo.
- A 59.39-second bag contains 887 synchronized pairs and matching CameraInfo,
  with no source-index gaps or unmatched frames inside the recording.
- Center depth: 2.359–2.363 m; maximum device/global timestamp skew:
  0.955/4.197 ms. Optical frames, static TF, encodings and millimeter units pass.
- With the driver stopped, 1x replay reproduced exact per-topic message counts
  and serialized contents, with an advancing simulated clock.
- Fourteen ROS contract tests and 21 native tests pass; native hardware capture
  still passes after recording. Room images and bags remain ignored and local.

The earlier 30 FPS recording had a 2.18 s reception stall; the selected 15 FPS
recording passed. Two subsequent moving recordings (93.88/94.49 seconds,
1402/1411 RGB-D pairs) also pass the sensor contract and exact simulated-time
replay, with unchanged calibration and no source-index gaps inside either bag.
The moving-scene checker reports empty center depth without applying the old
wall-distance constraint; 18 ROS tests and the original stationary regression pass.

Controlled room-loop capture quality remains unverified: the second recording
contains blur/tilt and end handling despite a reported return to the start.
Transient receipt intervals reached about 402 ms for images and 693 ms for color
CameraInfo across these runs, without missing recorded source frames. Preserve
these limitations before proceeding to mapping. Long-duration stability and
SLAM remain unverified. See [ROS commands and measured evidence](docs/camera-ros2.md).

Goals:

- Capture synchronized color and metric depth headlessly
- Record stream profiles, camera intrinsics, distortion, and depth scale
- Validate depth units and RGB-depth alignment
- Publish a stable ROS2 camera contract and record a replayable rosbag

Deliverables:

- Camera diagnostic and capture scripts
- RGB, raw depth, depth visualization, and metadata output
- ROS2 topic/rate/TF validation
- Short RGB-D rosbag for deterministic downstream development

### Phase 4: RTAB-Map RGB-D SLAM

Offline odometry now runs on the existing second room recording using isolated
RTAB-Map 0.23.7 Humble binaries. Both complete replays passed output timestamp/TF
checks and exited normally, but sustained tracking failed:

| Trial | Results / input pairs | Tracked / lost results | Longest loss |
| --- | --- | --- | --- |
| 1x, default latest-frame policy | 466 / 1411 | 100 / 366 | 75.37 s |
| 0.25x, offline input policy | 1410 / 1411 | 420 / 990 | 60.77 s |

Slow replay processed almost every input but still lost tracking from about
21.1 to 81.9 seconds. Twelve odometry checker tests pass. Continuous tracking,
pose accuracy and room mapping remain unverified; no new recording is required
to investigate the first failure. Both playback rate and input policy changed,
so these runs do not isolate the effect of rate alone.

A subsequent controlled 0.25x replay changed only `Odom/GuessMotion` to `false`:
1138 tracked / 272 lost results, with 1410 / 1411 inputs processed. The longest
loss fell from 60.77 to 10.45 s, but both settings failed at the same 21.104 s
turn; the 18–25 s window had 61 lost results with prediction and 68 without.
Recovery improved in this one comparison, while processing became slower and
pose accuracy remains unknown. The checked-in default is retained.
See [odometry setup and evidence](docs/rtabmap-odometry.md).

Minimum mapping integration is now verified on this same bag: a 41.8 MB database
reopens with 48 graph nodes; exports contain 45733 points, 48 camera poses and a
222 × 138 occupancy grid at 5 cm/cell. Fifty-six mapped observations pass the
source-time map-to-camera TF check; the initial observation is excluded for
unavailable map TF. Tracking gaps remain, and the six reported loop closures
have not been independently confirmed. A late CLI metadata-query failure is
preserved separately and was resolved through direct service checks on reopening.
See [mapping setup, artifacts and limits](docs/rtabmap-mapping.md).

An additional color reconstruction fuses 48 original RGB-D frames using these
fixed poses into 447905 points at 2 cm voxel size, with a full colored PLY and
an offline rotatable HTML viewer (180000 points displayed). All selected depth
pixels match the stored node images, nine geometry/failure tests pass, and
Chromium mouse rotation/zoom were verified. This makes the partial map easier
to inspect; tracking gaps and overlapping surfaces remain. See the
[colored point-cloud follow-up](docs/rtabmap-mapping.md#dense-colored-point-cloud-follow-up-2026-09-10).
On the Jetson display, double-click **Room point cloud.ply** on the desktop.
It opens directly in the installed Open3D viewer; the user confirmed the native
view looks acceptable. The dedicated Chromium/software-WebGL viewer remains
available through its documented command for the HTML artifact.

The current priority is to connect the pipeline before further component tuning.
YOLO plus depth observations now connect original color frames to the saved map
poses and persistent memory (Phases 5–6 below); minimum offline search-goal
previews are also verified (Phase 8). The odometry bundle/database image and
geometric cloud are grayscale in the original RTAB-Map export; the original RGB
recording remains available for perception and the new colored reconstruction.

Goals:

- Run RTAB-Map first on recorded RGB-D data
- Validate odometry, timestamps, and the TF tree
- Build a room map and verify loop closure
- Save the database, map, trajectory, and launch configuration

Deliverables:

- RTAB-Map launch/config files
- Map and camera trajectory
- TF and loop-closure validation evidence

### Phase 5: YOLO Plus Depth 3D Baseline

Status: `VERIFIED` for minimum offline camera/map observation integration.

YOLOv8n ran on the Jetson GPU using three original mapped 1280x720 RGB-D frames.
Of 18 detections, 15 passed depth filtering and produced source-associated
camera/map points in meters; three were explicitly rejected for missing or broad
depth. All 21 geometry/association tests pass, including the existing point-cloud
regressions. Independent Open3D projection agrees with all accepted points within
2.251e-7 m per coordinate; this verifies computation, not physical accuracy.

The saved annotated images reveal overlapping chair boxes and likely class
errors. These are 15 observations, not 15 distinct objects, and each point samples
a visible surface within a detection box. Reliable instance association, position
accuracy and live performance remain unverified. Measured processing times were
8226.27/77.59/65.37 ms for the three frames, including first-call initialization
and excluding PNG writing. No steady-state FPS is claimed. See
[the observation contract, command and evidence](docs/rgbd-object-observations.md).

Goals:

- Use synchronized aligned RGB, depth, and camera intrinsics
- Estimate robust object depth from detection regions
- Back-project detections into camera-frame 3D positions
- Transform timestamped observations into the map frame
- Publish or log structured 3D object observations

Core math:

```text
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
Z = depth
```

Depth strategy:

```text
bbox ROI
-> filter invalid depth
-> median depth
-> 3D object position
```

Deliverables:

- 3D localization script/node
- Object coordinate logs
- Error/stability analysis

### Phase 6: Persistent Semantic Object Memory

Status: `VERIFIED` for minimum offline SQLite memory and reopened queries.

The three M5 frames now persist as 18 source observations: 13 representatives
support nine provisional objects, two overlapping detections add no extra support,
and three depth rejections remain unlocalized. Repeated imports leave the database
byte-identical. Importing the same frames in reversed, separate batches produces
the same logical database. All 17 memory tests and 21 existing mapping/observation
tests pass, including transaction rollback and source-conflict cases.

Fresh-process `list`, `find` and `last_seen` queries work after the importer exits.
The refrigerator candidate retains three supporting frames and mean map point
`[4.675447, 0.911362, -0.794313]` m. Labels and positions remain provisional:
the original likely mislabels are retained, and this does not establish nine
distinct real objects. Association uses explicit label/distance gates and one
representative per object per frame; position means and detector confidence
remain separate. See [commands, schema and measured evidence](docs/scene-memory.md).

Goals:

- Merge repeated map-frame observations across time
- Preserve geometry and semantic confidence separately
- Store durable object state in SQLite
- Support object queries after the runtime restarts

Deliverables:

- Object association and fusion tests
- Persistent scene database
- Query command/service
- Semantic map visualization

Object memory fields:

```text
object_id
canonical_label and label candidates
geometry and semantic confidence
map-frame pose and dimensions
observation count
first-seen and last-seen timestamps
source observations and backend
```

### Phase 7: CuTR And Open-Vocabulary Upgrade

Goals:

- Benchmark Cubify Transformer on calibrated Femto Mega RGB-D frames
- Compare its full 3D cuboids against the YOLO-plus-depth baseline
- Run CuTR on keyframes if Jetson memory and latency permit
- Attach separately measured text-aligned semantics to object proposals
- Fuse multi-view geometry and semantic embeddings in persistent memory

Deliverables:

- CuTR Jetson/Femto feasibility report
- Baseline-versus-CuTR benchmark
- Keyframe perception backend or documented negative result
- Open-vocabulary query evaluation

### Phase 8: Exploration, Navigation, And Edge Optimization

Status: `VERIFIED` for minimum offline object goals, routes and frontier fallback,
including a single-command search demo.

The saved memory now connects to the frozen occupancy map through a read-only
query and hash-verified map/pose identity. With a fixed 0.75–1.25 m stand-off
band and assumed 0.25 m planar clearance, both provisional chair candidates
produce a goal at map x/y `[1.15, 0.63366]` m, about 1 m from their recorded
surface points. They retain separate IDs and evidence. The conservative map
clearance is 0.256192 m; an independent cell-area check gives 0.257391 m.

The refrigerator has no free cell in its stand-off band; the sink has 140 free
cells but none pass clearance; `backpack` is absent from memory. Each produces
an explicit no-goal result. Six CLI runs verified these outcomes, identical
repeated chair decisions and rejection of incompatible pose identity. All
16 search tests and 17 memory regressions pass; input artifacts remain unchanged.
JSON results and ordinary PNG overlays need no WebGL. See
[commands, previews and evidence](docs/search-goal-preview.md).

Offline route validation is now verified with explicit start provenance. All
48 recorded camera positions project into unknown cells, so camera node 1 is
refused as a start. An explicitly simulated start `[1.65, 0.08366]` m reaches
both chair goals through 22 grid cells over 1.05 m. Whole-segment map clearance
is 0.257391 m; an independent continuous lower bound is 0.256141 m. All 32
goal/route tests pass, eight route CLI cases match their expected outcomes,
and an original goal-preview regression is unchanged. See
[route commands, images and evidence](docs/search-route-preview.md).

The offline frontier fallback is also verified. The frozen map has 102
free/unknown boundary cells in 70 groups; the fixed clearance and cardinal-view
policy produces 123 viewing candidates at 115 goal cells. Missing `backpack`
and unavailable refrigerator/sink goals retain their reasons while producing
the same geometric observation proposal from the same simulated start. One
fixture proposes looking toward unknown space in place; a second requires a
5 cm checked route. An available chair goal suppresses fallback, and the recorded
camera start remains invalid. All 48 goal/route/frontier tests and nine frontier
CLI cases match expected outcomes; original goal/route regressions are unchanged.
See [frontier commands, images and evidence](docs/frontier-search-preview.md).

`scripts/run_offline_search.py` now joins these stages in one command and saves
`search.json` with the branch, reason, candidate outcomes, start provenance and
links to existing JSON/PNG evidence. All 63 search tests and 12 fresh CLI checks
pass, including repeated queries, source-identity failure and output protection.
Chair routes and frontier proposals match the preceding independent stages;
all input hashes remain unchanged. See the
[single-command demo and measured results](docs/offline-search-demo.md).

Chronological observation feedback is now verified with
`scripts/replay_observation_search.py`. Frozen prefixes for nodes 7/14/32 show
`bottle` changing from a depth-rejected, unlocalized detection to two remembered
candidates with 0.75/0.60 m routes. Later observations leave the earlier snapshots
intact. All 78 search tests, 17 memory tests and 14 CLI checks pass; the final
logical memory matches the original M6 result. See the
[replay command, timeline and evidence](docs/observation-search-replay.md).

These are offline grid checks. Physical footprint, floor/map accuracy, sensor
visibility, current localization and traversability remain unverified. No new
coverage or live observation was measured.

The complete saved RGB-D-to-search command is now verified with actual Jetson
GPU perception: 18 detections, 15 accepted depth observations and three rejections
feed the same memory/search timeline. All 130 focused tests and 11 fresh CLI
acceptance cases pass; repeated detections and decisions match, and all 66 PNGs
decode. This completes the first offline pipeline MVP. See the
[command, artifacts and limitations](docs/rgbd-search-demo.md). Nav2 and edge
optimization remain planned.

Concurrent SLAM and GPU perception are now verified at 0.25x rosbag replay.
All 1411 source pairs are received unchanged; overlapping inference with online
pose waiting reduces queue drops from 793 to nine. The final run processes 1402
frames, with 1109 accepted poses and 293 explicit pose refusals. All 56 focused
tests pass, independent pixel/TF checks pass, and every owned process closes.
See [the measured comparison and commands](docs/concurrent-rgbd-perception.md).
Real-time throughput and reliable room-loop tracking remain unverified. Causal
label queries on the newer line recording are now verified as described in
[online scene memory](docs/online-scene-memory.md).

The concurrent run's own frozen map now feeds memory and search without rerunning
inference: 62 of 64 exported nodes retain 252 detections, with 189 accepted depths
and 63 explicit rejections. Two nodes are excluded with source reasons. The new
memory has 46 provisional records; duplicate import leaves it byte-identical.
Bottle/chair searches produce routes from an explicit simulated start, backpack
uses the frontier fallback, and the recorded camera start is refused as unknown.
All 29 memory/finalization tests pass. Original online poses/points are preserved
beside final optimized coordinates. See the
[commands, results and evidence](docs/finalize-concurrent-memory.md).

A new forward/backward capture has now completed with an estimated 1 m distance.
It produces 898 tracked outputs with zero reported losses at 0.25x replay, plus
19 finalized nodes, 90 detections and 17 provisional memory records. A saved-graph
membership check was corrected for an online endpoint absent from the final
optimized map; old map memberships remain unchanged. Physical scale and drift
acceptance still need measured positions and fixed endpoint holds. See the
[new capture, validation and limitations](docs/straight-line-capture.md).

Goals:

- Use occupancy-grid frontiers to guide unknown-room exploration
- Query memory before initiating a new search
- Produce a collision-checked stand-off goal for a selected object
- Integrate Nav2 when a mobile base is available
- Profile the complete concurrent system before applying TensorRT/FP16 work
- Support manual, semi-autonomous, or robot-base exploration modes

Mobility backends:

- Handheld RGB-D scan
- Recorded RGB-D sequence
- Mobile robot base, optional
- Simulated robot, optional

Deliverables:

- Frontier and goal-proposal prototype
- Concurrent Jetson latency, memory, power, and thermal results
- Evidence-driven ONNX/TensorRT optimization where useful
- Semantic room exploration demo
- Final demo video

## Performance Priorities

The project prioritizes robotics system usefulness over single-frame ML metrics.

Priority order:

1. System stability and real-time operation
2. Timestamp, camera pose, and map-frame consistency
3. Stable multi-view object geometry and data association
4. Useful semantic retrieval accuracy
5. Model throughput, memory, power, and thermal headroom

Design principle:

```text
A slightly smaller detector running reliably in real time is more useful than a heavier detector that causes SLAM drops, high latency, or memory pressure.
```

## Initial Repository Structure

```text
jetson-semantic-room-explorer/
  README.md
  docs/
  scripts/
  src/
  data/
    sample_images/
    sample_videos/
    outputs/
  models/
  benchmarks/
```

## Current Status

- [X] Project scope defined
- [X] JetPack 6.2.2 installed
- [X] SSH access available
- [X] Headless workflow selected
- [X] GitHub repository initialized
- [X] Environment snapshot saved
- [X] Python/OpenCV baseline verified
- [X] Jetson-compatible PyTorch CUDA verified
- [X] YOLO image inference running
- [X] ROS2 Humble environment sourced
- [X] YOLO inference script added
- [X] YOLO PyTorch benchmark script added
- [X] YOLO baseline measured: 30.76 ms inference, 59.79 ms total mean
- [X] YOLO baseline benchmark table added
- [X] Femto Mega M2 native capture acceptance (including coarse physical unit check)
- [X] SDK depth-to-color registration verified with preserved raw pair and edge diagnostics
- [X] Stationary RGB-D ROS2 topics and rosbag replay verified
- [X] Moving RGB-D sensor contract and exact rosbag replay verified
- [ ] Controlled room-loop capture quality verified
- [X] RTAB-Map offline odometry trial measured, including sustained tracking failure
- [X] Controlled motion-prediction comparison measured; turn failure remains
- [ ] TensorRT Python binding added
- [ ] TensorRT benchmark complete
- [X] RTAB-Map minimum mapping integration: database reopening, geometry export and TF
- [ ] Continuous tracking and room-map quality acceptance
- [X] Minimum offline semantic object memory and reopened queries verified
- [X] Minimum offline object-search goal previews and explicit no-goal outcomes verified
- [X] Offline route validation with an explicit simulated start and camera-start refusal
- [X] Minimum offline frontier-search fallback with explicit simulated starts
- [X] Single-command offline search demo with preserved decisions and stage evidence
- [X] Chronological observation-feedback replay with preserved memory snapshots
- [X] Single-command saved RGB-D-to-search demo: first offline pipeline MVP
- [X] Bounded concurrent SLAM/perception and resources at 0.25x rosbag replay
- [X] Concurrent observations finalized into their own frozen memory and search
- [X] New forward/backward capture through the full pipeline; zero reported tracking losses at 0.25x
- [X] Causal persistent observations and label queries during bounded RGB-D replay
- [X] Causal MobileCLIP text retrieval during bounded RGB-D replay
- [X] Causal search decisions and bounded ROS previews from a changing recorded map
- [ ] Live-camera search validation and meaningful physical routes
- [ ] Real-time SLAM/perception and continuous live operation
- [ ] Physical navigation acceptance
- [X] CuTR Jetson/Femto feasibility measured; retained as an offline research comparison
- [X] Minimum saved-data MobileCLIP text retrieval and ROS search previews

## Resume-Oriented Summary

Planned final description:

```text
Built a Jetson Orin Nano-based persistent 3D scene mapping system that fuses
RTAB-Map RGB-D poses with resource-aware object perception and multi-view
semantic memory to support language-grounded object queries and search in
previously unseen indoor environments.
```

## Notes

This project is designed to be robot-base agnostic. The core contribution is semantic perception and memory. A mobile robot base can consume the resulting target/object poses later, but the system can also be developed and validated with handheld RGB-D scans, recorded sequences, or headless Jetson inference.
