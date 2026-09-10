# Jetson Semantic Room Explorer: Codex Project Playbook

Last updated: 2026-09-10

This file is the canonical execution plan, living handoff, and operating contract
for Codex sessions working in this repository. It is intentionally kept at the
repository root so Codex CLI can discover it automatically.

## 1. How To Use This File

From the Jetson:

```bash
cd ~/projects/jetson-semantic-room-explorer
git pull --ff-only
codex
```

Suggested first message in a new Codex session:

```text
Read AGENTS.md and README.md, inspect git status and the latest commits, then
continue only the Current Next Task. Explain the purpose of the step in Chinese
before changing code. Preserve existing work, verify the result on this Jetson,
update the Progress Ledger, and leave one clear next action before stopping.
```

### 1.1 Reusable High-Quality Task Prompt

Replace `[TASK]` and `[ACCEPTANCE RESULT]`, then send this when starting a new
implementation step:

```text
Work on [TASK] in this repository. The required observable result is
[ACCEPTANCE RESULT].

Before editing, read AGENTS.md, inspect git status and relevant existing code,
and explain in Chinese: the current behavior, the smallest coherent change, the
files you expect to touch, and how you will verify it. Search for existing
helpers and established patterns before adding anything.

Implementation constraints:
- Make the smallest change that fully satisfies the acceptance result.
- Reuse existing code and dependencies when they fit.
- Do not add speculative abstractions, placeholder modules, compatibility layers,
  duplicate configuration, or future-facing options without a current caller.
- Do not add a dependency unless the standard library and current dependencies
  are insufficient; explain the cost before adding one.
- Do not hide failures with broad exception handling, silent fallback, fabricated
  defaults, or fake success output. Preserve units, timestamps, coordinate frames,
  and resource cleanup explicitly.
- Do not refactor unrelated files or rewrite working code for style alone.
- Add focused tests for behavior and failure cases. Do not write tests that only
  duplicate the implementation or mock away the behavior being verified.
- Do not claim hardware behavior that was not run on the Jetson.

After implementation, run the narrowest relevant tests, then any affected smoke
or integration test. Review the complete diff for duplicated logic, dead code,
unused imports, unnecessary comments, accidental generated files, weak error
handling, and documentation that overstates reality. Simplify before stopping.

Report: what changed, why this design is sufficient, exact verification performed,
remaining limitations, what I should learn from this step, and one next action.
Update the Progress Ledger only when evidence supports a status change.
```

The prompt intentionally asks for an observable result. A vague request such as
"build the camera system" encourages unnecessary scaffolding. A stronger request
is "save one synchronized RGB-D frame plus intrinsics and prove depth units with
ten clean open/capture/close runs."

The human-facing conversation may be in Chinese. Public documentation, code,
identifiers, commit messages, and logs committed to this repository should be in
clear English unless there is a specific reason to do otherwise.

## 2. Project Mission

Build an edge robotics system that enters an unfamiliar indoor environment with
no prebuilt map, creates a geometric map, observes objects, converts observations
into persistent 3D scene memory, and supports object queries and later autonomous
object search.

Core loop:

```text
Explore -> Observe -> Localize -> Fuse -> Remember -> Query -> Navigate
```

Target project description:

```text
Persistent open-vocabulary 3D scene mapping and object search on a Jetson Orin
Nano using a Femto Mega RGB-D camera, RTAB-Map, learned object perception, and
resource-aware edge inference.
```

The project is not:

- A YOLO-only demonstration.
- A Cubify Anything demo with no system integration.
- A sim-to-real project unless simulation is explicitly added as a test backend.
- A claim that autonomous navigation is complete before a mobile base is tested.
- A requirement to reconstruct a photorealistic dense scene before object search
  can work.

## 3. Codex Operating Contract

### 3.1 Start Every Session By Recovering State

Run these read-only checks before making changes:

```bash
pwd
git status --short --branch
git log --oneline --decorate -8
git diff --stat
```

Then read:

1. `AGENTS.md`, especially Current State, Current Next Task, and Progress Ledger.
2. `README.md` for the public project story.
3. Files directly related to the next task.
4. The latest relevant test output or benchmark artifact.

Never assume the previous session finished cleanly. If the worktree is dirty,
inspect and preserve the changes. Do not reset, checkout, overwrite, or delete
work merely because Codex did not create it.

### 3.2 Use Evidence-Based Status

Use only these status labels:

- `VERIFIED`: executed on the stated hardware and supported by saved output.
- `IMPLEMENTED`: code exists, but hardware or integration verification remains.
- `PLANNED`: no implementation claim.
- `BLOCKED`: an external dependency currently prevents progress, with evidence.

Do not turn planned architecture into resume claims. Do not mark a milestone
complete because code was generated. Completion requires the acceptance check to
pass and the evidence location to be recorded.

### 3.3 Teach While Building

For each meaningful step, explain to the user in Chinese:

1. What subsystem is being changed.
2. Why it exists in the full robot pipeline.
3. What input and output contract it owns.
4. How the result will be verified.
5. What failure would mean.

Keep explanations focused. Let the user run or inspect the central command when
that helps learning, while Codex handles repetitive edits and diagnostics. End a
milestone with a short "what we learned" summary tied to actual results.

### 3.4 Engineering Standards

- Inspect existing code and APIs before designing replacements.
- Prefer a thin vertical slice over several disconnected modules.
- Keep hardware adapters, perception, mapping, memory, and planning decoupled.
- Use typed data structures and structured serialization, not ad hoc strings.
- Use camera timestamps consistently and request TF at the observation timestamp.
- Keep ROS callbacks bounded; inference must not block sensor ingestion forever.
- Always clean up camera pipelines, files, and ROS resources on exceptions.
- Add unit tests for math and data association; use rosbag replay for integration.
- Make headless operation the default. Visualization is an optional consumer.
- Record latency distributions, not one favorable frame.
- Never commit secrets, credentials, private network details, large model weights,
  raw rosbags, generated engines, or large generated outputs.
- Treat model, dataset, and code licenses as part of the design.

### 3.5 Minimal-Change Gate

Every new file, class, helper, configuration key, dependency, process, or ROS node
must answer both questions:

1. Which current acceptance condition requires it?
2. Why is the existing code or a smaller local change insufficient?

If neither answer is concrete, do not add it.

Additional rules:

- Add an abstraction when it removes current meaningful duplication, isolates a
  real hardware/external boundary, or has at least two current callers.
- Do not introduce interfaces for imagined future backends. A measured second
  backend is a valid reason; a possible future backend is not.
- Keep one source of truth for each setting. ROS parameters, YAML, CLI defaults,
  environment variables, and constants must not silently disagree.
- Prefer explicit unsupported-operation errors over a fallback that produces
  plausible but incorrect output.
- Avoid wrappers that only rename another API without enforcing a useful contract.
- Avoid large manager/controller classes that own camera, inference, mapping,
  persistence, and UI behavior simultaneously.
- Avoid comments that restate the code. Document units, coordinate frames,
  ownership, invariants, and non-obvious hardware behavior instead.
- Do not preserve obsolete code "just in case." Remove it after replacement is
  verified, or mark a short, explicit migration period with a real consumer.
- Do not create empty package trees, unused configuration files, or TODO-only
  modules to make the repository look complete.

### 3.6 Common AI Coding Failure Modes

| Failure mode | What it looks like | Required correction |
| --- | --- | --- |
| Scope drift | Camera task also rewrites logging, packaging, and README style | Revert unrelated scope and keep the acceptance result central |
| Scaffold explosion | Many empty packages and interfaces before one frame works | Build one tested vertical slice first |
| Premature abstraction | Factory/registry/plugin layer with one implementation | Use the concrete implementation until a second measured backend exists |
| Duplicate logic | New helper repeats an existing parser, transform, or config | Search first and consolidate around one owner |
| Dependency creep | Adds a package for a small standard-library operation | Remove it or justify a capability the project actually needs |
| Silent fallback | Wrong camera format quietly becomes a blank/default image | Fail with actionable context and preserve evidence |
| Broad exception handling | `except Exception` converts real errors into success/empty data | Catch expected exceptions narrowly; re-raise unexpected failures |
| Happy-path-only code | Works once but leaks the camera or fails on missing depth | Test cleanup, timeout, empty, invalid, and repeated-run behavior |
| Fake robustness | Retries forever or ignores stale TF/data | Bound queues/retries and expose drop/failure metrics |
| Unit/frame confusion | Millimeters treated as meters or optical axes as `base_link` | Encode units/frames in contracts and test known examples |
| Benchmark theater | Reports one warm frame or model-only latency as system FPS | Record conditions and distributions with synchronized timing |
| Test mirroring | Test reproduces the same formula and always agrees | Use independent known cases, boundaries, and failure behavior |
| Documentation drift | README says integrated while code is unrun | Use evidence-based status and update docs after verification |
| Compatibility clutter | Aliases and legacy paths with no known consumer | Remove them until a real compatibility requirement exists |

### 3.7 Pre-Final Self-Review

Before reporting a coding task complete, Codex must inspect the entire diff and
answer internally:

1. Does every changed file directly support the requested result?
2. Is there a smaller implementation with the same correctness and clarity?
3. Did I duplicate an existing helper, setting, schema, or error path?
4. Did I add code for a future possibility instead of a current requirement?
5. Are failures explicit, bounded, and diagnosable?
6. Are time, units, frames, array shapes, and ownership unambiguous?
7. Do tests cover externally visible behavior and at least one realistic failure?
8. Did I leave dead code, unused imports, debug output, TODO placeholders, or
   generated artifacts?
9. Do documentation and status claims match what was actually executed?
10. Can the next session understand and reproduce the result from the repository?

Useful final checks include:

```bash
git diff --check
git diff --stat
git diff
python -m compileall scripts
```

Run project-specific tests and linters when they exist. `compileall` is only a
syntax smoke test and must not be presented as behavioral verification.

### 3.8 Change And Commit Discipline

- Keep `main` runnable and use focused branches such as `feat/femto-capture`.
- Make small commits around verified behavior.
- Before committing, run the most relevant tests and inspect `git diff`.
- Update this file when a milestone changes state or a durable decision is made.
- Update `README.md` only with public, verified progress.
- Do not force-push or rewrite shared history.
- Push a verified checkpoint before risky dependency or system changes.

## 4. Current Verified State

The following was verified from captured Jetson command output in earlier project
sessions. Re-run the environment smoke test after a major system update.

### 4.1 Hardware And OS

```text
Device: NVIDIA Jetson Orin Nano, 8 GB
Power mode observed: 25 W
JetPack: 6.2.2
Ubuntu: 22.04.5 LTS
L4T: R36.5.0
Kernel: 5.15.185-tegra
Development mode: headless over SSH
Camera target: Orbbec Femto Mega RGB-D
```

### 4.2 NVIDIA And ROS Stack

```text
CUDA 12.6 runtime: VERIFIED
cuDNN 9.3 runtime libraries: VERIFIED
TensorRT 10.3 runtime libraries: VERIFIED
VPI 3.2 packages: VERIFIED
NVIDIA multimedia/GStreamer stack: VERIFIED
NVIDIA container runtime and Docker: VERIFIED
ROS 2 Humble environment: VERIFIED
```

Known caveats:

- `nvcc` was not on `PATH`; PyTorch CUDA runtime operation was still verified.
- TensorRT Python bindings were not verified in the project virtual environment.
- VPI Python imports were not verified in the project virtual environment.
- The current dependency snapshot is useful evidence, but it is not yet a clean,
  portable installation manifest.

### 4.3 Python And ML Stack

```text
Python 3.10.12
PyTorch 2.8.0
TorchVision 0.23.0
torch.cuda.is_available(): True
CUDA device reported by PyTorch: Orin
NumPy 1.26.4
OpenCV headless 4.10.0
Ultralytics 8.4.112
```

### 4.4 YOLO Baseline

Status: `VERIFIED`

Existing repository artifacts:

```text
scripts/yolo_image_smoke_test.py
scripts/benchmark_yolo_pytorch.py
data/sample_images/test.jpg
runs/detect/data/outputs/yolo_smoke_test/test.jpg
```

Measured baseline:

```text
Model: YOLOv8n PyTorch
Input size: 640
Warmup: 10 runs
Measured runs: 50
Mean model inference: 30.76 ms
Median model inference: 32.93 ms
P95 model inference: 33.09 ms
Mean end-to-end call: 59.79 ms
Estimated throughput from mean total time: 16.72 FPS
```

This is a static-image repeated-input baseline. It is not yet a live-camera or
concurrent SLAM benchmark.

### 4.5 Camera And Mapping State

```text
pyorbbecsdk2 2.1.1 import / native SDK 2.8.6 on this Jetson: VERIFIED
Femto Mega synchronized frame-pair capture and intrinsics export: VERIFIED
SDK depth-to-color registration: VERIFIED (single frames; edge limitations recorded)
Physical depth-unit range check: VERIFIED (user reference 2-3 m; center 2.332-2.333 m)
Absolute distance accuracy: PLANNED (precise reference not yet measured)
ROS 2 camera topics: NOT VERIFIED
Rosbag recording/replay: NOT VERIFIED
RTAB-Map RGB-D SLAM: NOT VERIFIED
```

`scripts/femto_mega_capture_once.py` captures 1280x720 MJPG color and 640x576
Y16 depth at 30 FPS using SDK synchronization and exports raw counts, calibration,
timestamps, and scale. PNG round trips, failure recovery and ten-run lifecycle
checks pass. After repositioning, three captures have about 74.9% valid depth
and fully valid center ROIs at 2.332-2.333 m, consistent with the user-reported
2-3 m wall distance. M2 native capture and coarse unit acceptance are verified;
absolute accuracy remains unmeasured. Optional `--align-depth` additionally saves
1280x720 depth on the original color grid, with the actual calibration, scale,
source depth timestamps and color optical frame. Twenty aligned capture cycles
and 21 offline tests pass. Center aligned depth is 2.347–2.349 m; boundary checks
record occlusion gaps and mismatches. See the M2 and registration ledger entries
and `docs/camera-femto-mega.md` for evidence and limitations.

## 5. Current Next Task

Milestone: **M3 ROS 2 camera contract and stationary rosbag smoke test**.

Native capture, coarse metric units and SDK registration have passed. Preserve
those scripts and artifacts while establishing a replayable ROS sensor contract.
The camera is fixed; room-walk recording and SLAM are separate later checks.

Required sequence:

1. Recover git state and inspect local ROS 2 Humble, Orbbec wrapper/source, its
   SDK requirements, existing launch patterns and available profile settings.
   If a needed component cannot be found locally, ask the user before downloading
   or installing it, as requested. Do not replace the working native SDK casually.
2. Use a compatible maintained ROS driver to publish 1280x720 color, registered
   depth and matching CameraInfo. Verify actual support; native depth resolution
   remains independent. Avoid a new camera node when the existing driver suffices.
3. Measure encodings, depth units, calibration/distortion, timestamp domains/skew,
   monotonicity, frame IDs, TF, QoS and delivered rates over a bounded interval.
4. Record about 60 seconds of the stationary scene, including required camera
   topics and transforms; keep the bag ignored and local.
5. Stop the camera driver and replay with simulated time. Verify matching frame
   counts, timestamps, metadata and TF availability without reopening hardware.
6. Save exact launch/record/replay commands and measured results. Run affected
   checks and update the ledger; do not start SLAM, perception or robot motion.

Acceptance evidence:

```text
Driver/version and launch configuration
Live topic, timestamp, CameraInfo and TF measurements
Ignored short rosbag, rosbag metadata and driver-stopped replay report
```

Commit small launch/configuration and verification code as needed, plus compact
measured results. Raw room images and rosbags should remain ignored.

Acceptance conditions:

- Color/aligned depth/CameraInfo agree on pixel grid and calibration; units,
  invalid depth, timestamp domain and optical frames are documented and checked.
- No unexplained timestamp regression, frame-ID mismatch or missing required TF;
  topic rates, synchronization skew and dropped/unmatched frames are measured.
- The bag replays the recorded sensor contract with the driver stopped.
- Native capture remains usable; no room-walk, SLAM or sustained mapping claim
  follows from this stationary smoke test alone.

Learning checkpoint:

```text
Explain Image/CameraInfo, QoS, optical TF, hardware versus ROS timestamps, and
why rosbag replay with a consistent clock enables repeatable downstream tests.
```

## 6. Target System Architecture

```text
Orbbec Femto Mega
  |-- color + depth + camera_info + timestamps
  |
  +--> RTAB-Map RGB-D SLAM
  |      |-- map -> odom -> camera TF
  |      |-- occupancy map / geometric map
  |      `-- loop closures
  |
  +--> Perception scheduler
         |-- Baseline: YOLO + robust depth localization
         `-- Advanced keyframes: CuTR RGB-D 3D cuboids
                       |
                       +--> semantic label / language embedding
                       |
                       `--> timestamped camera-frame observation
                                      |
                              TF into map frame
                                      |
                         temporal data association and fusion
                                      |
                       persistent SQLite scene memory
                                      |
                         query / visualization / goal proposal
                                      |
                           frontier exploration + Nav2
```

### 6.1 Stable Baseline

The first complete vertical slice uses:

```text
YOLO 2D detection
-> robust depth ROI statistics
-> camera-frame 3D point
-> RTAB-Map pose at the same timestamp
-> map-frame observation
-> repeated-observation fusion
-> queryable object memory
```

This baseline is intentionally simple. It proves timing, coordinate transforms,
memory, and query behavior before introducing a heavier model.

### 6.2 Advanced CuTR Path

Cubify Transformer is an experimental perception backend, not a replacement for
SLAM, temporal fusion, scene memory, exploration, or navigation.

Expected CuTR outputs:

```text
objectness score
2D bounding box
camera-frame 3D center
3D dimensions
gravity-aligned yaw
decoder object feature
```

The released model is class-agnostic. It finds object cuboids but does not
reliably name them. Semantic labels must come from a separate closed-vocabulary
detector or a text-aligned vision model.

Recommended hybrid:

```text
CuTR 2D/3D object proposal
-> crop or region feature
-> MobileCLIP/SigLIP/other measured edge-compatible encoder
-> text-aligned semantic embedding
-> persistent 3D object record
```

References:

- https://github.com/apple/ml-cubifyanything
- https://arxiv.org/abs/2412.04458

CuTR integration is allowed to run on selected keyframes. Scene memory does not
need a heavy detector at camera frame rate.

### 6.3 Coordinate And Time Contract

Use ROS REP-103 conventions and make every transform explicit.

```text
map_T_object = map_T_camera(timestamp) * camera_T_object
```

Rules:

- Every observation carries the source image timestamp and camera frame ID.
- Look up TF at that timestamp, not simply the latest available transform.
- Do not mix optical-frame axes with `base_link` axes without a named transform.
- Preserve raw observations so fusion bugs can be replayed.
- Store geometry quality or covariance when available.
- A missing transform causes a bounded retry/drop with a metric, not silent use of
  an unrelated pose.

### 6.4 Persistent Object Record

Initial logical schema:

```text
object_id
canonical_label
label_candidates
semantic_embedding_reference
map_position_xyz
map_orientation
dimensions_xyz
position_uncertainty
observation_count
first_seen_timestamp
last_seen_timestamp
last_observation_pose
source_backend
status
```

Use SQLite for durable structured state. Keep large embeddings or image crops in
versioned artifact storage and store references in the database when appropriate.
Start with explainable geometric association, then measure before adding a learned
tracker.

## 7. Module Boundaries

The eventual ROS 2 workspace should keep these responsibilities separate:

```text
semantic_explorer_camera
  Camera adapter, calibration, timestamps, and recording.

semantic_explorer_perception
  YOLO baseline, depth localization, CuTR backend, and semantic embeddings.

semantic_explorer_mapping
  RTAB-Map launch/config integration and transform validation.

semantic_explorer_memory
  Data association, fusion, SQLite persistence, and object lifecycle.

semantic_explorer_query
  Text/class queries, result ranking, visualization, and target pose proposal.

semantic_explorer_bringup
  Launch files, configuration profiles, diagnostics, and lifecycle coordination.

semantic_explorer_exploration
  Frontier selection and Nav2 integration when a mobile base is available.
```

Python is appropriate for orchestration, experimentation, data fusion, and query
logic. Use existing C++ ROS drivers and RTAB-Map packages. Move a Python component
to C++ only after profiling shows that it is a real bottleneck.

## 8. Execution Roadmap

### M0: Jetson Foundation

Status: `VERIFIED`

Delivered:

- JetPack 6.2.2 and Ubuntu 22.04.
- SSH/headless workflow.
- CUDA-enabled PyTorch.
- ROS 2 Humble environment.
- GitHub repository and environment snapshot.

### M1: Reproducible Repository And ML Baseline

Status: `IMPLEMENTED`, cleanup remains

Delivered:

- YOLO image smoke-test script.
- PyTorch benchmark script.
- Annotated sample output.
- Measured baseline on Orin GPU.

Remaining:

- Separate a human-maintained runtime dependency manifest from `pip freeze`.
- Avoid local wheel URLs in portable install instructions.
- Resolve the presence of both GUI and headless OpenCV packages.
- Add lightweight unit tests and a standard benchmark metadata header.

Learning goal: distinguish an environment snapshot from a reproducible install.

### M2: Femto Mega Native Capture

Status: `VERIFIED` for native capture, lifecycle checks and coarse metric units.
Absolute distance accuracy is not measured. Optional SDK registration is also
`VERIFIED`; see its separate ledger entry for coverage and edge limitations.

Deliverables:

- Device/profile diagnostic script.
- Headless synchronized RGB-D capture script.
- Intrinsics and depth-scale metadata.
- Ten-run stability evidence.
- Troubleshooting notes for USB permissions and stream negotiation.

### M3: ROS 2 Camera Contract And Rosbag

Status: `PLANNED`

Steps:

1. Evaluate the maintained Orbbec ROS 2 wrapper against the native SDK version.
2. Publish color, aligned depth, and `camera_info` with consistent timestamps.
3. Verify topic rates, encodings, QoS, and TF frame names.
4. Record a short privacy-safe rosbag walking through one room.
5. Replay it without camera hardware and reproduce the topic graph.

Acceptance:

- No unexplained timestamp regression or frame-ID mismatch.
- A recorded bag can drive downstream development deterministically.

Learning goal: ROS topics, QoS, synchronization, calibration, TF, and rosbag.

### M4: RTAB-Map RGB-D SLAM

Status: `PLANNED`

Steps:

1. Run RTAB-Map on recorded data first.
2. Validate odometry and TF before enabling full mapping.
3. Tune depth limits and synchronization using measured camera behavior.
4. Run a room loop and verify a plausible loop closure.
5. Save database, occupancy map, trajectory, and launch configuration.

Acceptance:

- The TF tree is connected and temporally valid.
- Mapping survives the full bag without repeated reset or fatal frame drops.
- A loop trajectory produces a visibly consistent room map.

Learning goal: odometry versus mapping, pose graphs, loop closure, and TF.

### M5: YOLO Plus Depth 3D Baseline

Status: `PLANNED`

Steps:

1. Subscribe to synchronized RGB, depth, and intrinsics.
2. Run YOLO at a configurable capped rate.
3. Reject invalid and outlier depth within an inner detection ROI.
4. Back-project the robust depth estimate into the optical camera frame.
5. Publish structured timestamped observations.
6. Test the projection math with synthetic and measured cases.

Acceptance:

- Unit tests cover projection, invalid depth, and coordinate conventions.
- Repeated views of a static object produce characterized position jitter.

Learning goal: projective geometry and uncertainty from 2D detection plus depth.

### M6: Persistent Map-Frame Scene Memory

Status: `PLANNED`

Steps:

1. Transform observations into `map` at their timestamps.
2. Implement gated nearest-neighbor association using label and geometry.
3. Fuse repeated observations with confidence/uncertainty-aware updates.
4. Persist objects and source observations in SQLite.
5. Add `list`, `find`, and `last_seen` queries.
6. Visualize object IDs and positions in RViz or a headless export.

Acceptance:

- Replay produces deterministic database contents.
- Static objects do not multiply without a documented association failure.
- The database can be closed, reopened, and queried after ROS stops.

Learning goal: data association, state estimation, persistence, and observability.

### M7: Cubify Anything Feasibility Gate

Status: `PLANNED`

Do this only after M2 provides trustworthy RGB-D frames. Start outside the main
runtime dependency environment if necessary.

Steps:

1. Record model license and dependency constraints.
2. Run the official sample with the released RGB-D checkpoint.
3. Build a Femto Mega input adapter with calibrated intrinsics and gravity input.
4. Measure model load time, peak memory, warm latency, P50/P95, and output count.
5. Inspect 3D cuboid quality on multiple real indoor objects and viewpoints.
6. Run concurrently with the recorded RTAB-Map workload.
7. Compare against the YOLO-plus-depth baseline.

Decision gate:

```text
Unstable or out of memory with SLAM -> keep as offline research comparison.
Stable near 1 Hz -> use as a keyframe geometry backend.
Stable at several Hz with headroom -> consider as the primary 3D proposal backend.
Poor Femto domain transfer -> retain architecture but do not claim deployment.
```

Do not describe CuTR as open-vocabulary semantics. It is class-agnostic geometry.

Learning goal: paper-to-system integration, domain shift, benchmarking, and edge
resource tradeoffs.

### M8: Open-Vocabulary Semantic Layer

Status: `PLANNED`

Steps:

1. Establish YOLO labels as the closed-vocabulary baseline.
2. Benchmark a lightweight text-aligned vision encoder on object crops.
3. Store normalized semantic embeddings per observation.
4. Fuse embeddings over repeated views without erasing ambiguity.
5. Rank scene objects against arbitrary text queries.
6. Evaluate known, synonym, attribute, and unknown-object queries.

Acceptance:

- Query evaluation uses a documented set, not selected demo successes only.
- Geometry and semantic confidence remain separate fields.

Learning goal: closed versus open vocabulary, embeddings, similarity, and
multi-view semantic fusion.

### M9: Object Search Interface

Status: `PLANNED`

Steps:

1. Query known memory before initiating exploration.
2. Return object candidates with confidence, last-seen time, and map location.
3. Convert an object cuboid into a collision-checked stand-off goal candidate.
4. Support dry-run goal publication before any robot motion.
5. Continue search when the target is absent or confidence is insufficient.

Learning goal: grounding semantic results into actionable robot goals.

### M10: Exploration And Navigation

Status: `PLANNED`, mobile base dependent for physical validation

Steps:

1. Use occupancy-grid frontiers as the geometric baseline.
2. Score candidate frontiers by travel cost, expected new coverage, and visibility.
3. Add semantic priors only after the geometric baseline is measured.
4. Integrate with Nav2 through goals, feedback, cancellation, and recovery.
5. Stop or replan when the target is confidently observed.

Without a mobile base, validate frontier selection and goal generation through
rosbag replay and dry-run visualization. Do not claim physical autonomy.

Learning goal: active perception, coverage, planning, and behavior recovery.

### M11: Edge Optimization And Final Evaluation

Status: `PLANNED`

Optimization comes after a working vertical slice.

Steps:

1. Measure concurrent camera, SLAM, perception, and memory workloads.
2. Record `tegrastats`, power mode, thermals, memory, dropped frames, and latency.
3. Optimize the measured bottleneck: rate caps, keyframes, FP16, ONNX, TensorRT,
   zero-copy paths, or process placement as justified by evidence.
4. Re-run accuracy/stability tests after every optimization.
5. Produce a reproducible demo, architecture document, results table, and video.

Learning goal: system-level optimization rather than isolated model speed.

## 9. Verification Strategy

### Unit Tests

- Pixel/depth back-projection.
- Coordinate transform composition.
- Invalid depth and outlier rejection.
- Data association gates and update equations.
- SQLite schema migration and persistence.
- Query ranking and deterministic tie handling.

### Offline Integration Tests

- Run camera consumers from a rosbag.
- Run SLAM and perception separately, then concurrently.
- Rebuild scene memory from the same bag and compare deterministic summaries.
- Inject missing depth, delayed TF, empty detections, and duplicate observations.

### Hardware Tests

- Repeated camera open/close.
- Sustained capture and topic-rate monitoring.
- Room-loop SLAM.
- Static-object multi-view localization.
- Concurrent latency/memory/thermal measurement.

### Benchmark Rules

- Record hardware, power mode, software versions, input shape, backend, precision,
  warmup count, run count, and whether workloads were concurrent.
- Report mean, median, and P95 latency.
- Separate preprocessing, inference, postprocessing, and end-to-end timing.
- Synchronize CUDA when measuring host wall-clock duration.
- Keep raw CSV or JSON results outside Git only when large; commit compact summaries.
- Never compare numbers collected under undocumented power or thermal conditions.

## 10. Recovery Protocol

### After An Interrupted Codex Session

```bash
cd ~/projects/jetson-semantic-room-explorer
git status --short --branch
git diff --stat
git diff
git log --oneline --decorate -8
```

Then:

1. Identify the last `VERIFIED` ledger entry.
2. Inspect uncommitted files without deleting them.
3. Re-run the smallest relevant test.
4. Continue from the first unmet acceptance condition.
5. Commit and push a clean checkpoint before risky changes.

### After A Dependency Failure

1. Save the exact command and complete error.
2. Record Python, architecture, JetPack/L4T, CUDA, and package source.
3. Determine whether the failure is system package, Python ABI, CUDA ABI, ROS
   overlay, or application code.
4. Prefer a targeted repair. Do not reinstall JetPack or recreate the whole
   environment without evidence that the lower layer is broken.
5. Re-run the previously passing smoke test to detect regressions.

### After A Hardware Or Camera Failure

1. Separate USB/device enumeration from SDK import and stream negotiation.
2. Preserve kernel and SDK error output.
3. Verify power, cable, port, permissions, firmware, and selected profile.
4. Fall back to recorded data so software work can continue.
5. Keep the milestone `BLOCKED` or `IMPLEMENTED`, never `VERIFIED`.

### After A ROS Failure

Inspect in this order:

```text
process/node exists
-> expected topics exist
-> message rate and encoding are correct
-> timestamps advance
-> frame IDs are correct
-> TF exists at message time
-> synchronization queues are bounded
-> downstream algorithm parameters
```

## 11. Risk Register

| Risk | Evidence To Collect | Mitigation |
| --- | --- | --- |
| CuTR exceeds 8 GB or is too slow | Peak memory and concurrent latency | Keyframes, smaller model, offline comparison, retain baseline |
| CuTR transfers poorly from ARKit depth to Femto | Real-object cuboid review and stability | Calibrated preprocessing, baseline comparison, no unsupported claim |
| RGB and depth are misregistered | Edge overlays and physical depth checks | Use calibrated SDK alignment and preserve raw streams |
| SLAM loses frames under inference load | Topic rate, queue drops, trajectory discontinuity | Rate cap, separate worker/process, keyframe scheduling |
| Python/ROS/CUDA dependencies conflict | Reproducible environment smoke tests | Separate system ROS from model environments and document bridges |
| Object memory creates duplicates | Replay association metrics | Geometry/label gates, uncertainty, explicit lifecycle |
| No mobile base is available | Dry-run and replay evidence | Complete mapping/memory first; keep physical autonomy as separate claim |
| Research model license limits use | License record per model | Keep research use explicit and avoid commercial deployment claims |

## 12. Durable Architecture Decisions

### ADR-001: RTAB-Map Is The Baseline SLAM

Reason: it is RGB-D and ROS 2 friendly, provides loop closure and mapping, and
fits the need for map-frame persistent memory. ORB-SLAM3 remains a comparison or
fallback, not a parallel implementation priority.

### ADR-002: YOLO Remains The Baseline

Reason: it is already measured on the target hardware and provides a stable,
understandable reference for later 3D and open-vocabulary methods.

### ADR-003: CuTR Is An Experimental Keyframe Backend

Reason: it can improve per-frame 3D geometry from a point estimate to a full
cuboid, but Jetson feasibility and Femto domain transfer are unverified.

### ADR-004: Geometry And Semantics Are Separate Signals

Reason: objectness, 3D geometry, class labels, and text similarity have different
failure modes and must not be collapsed into one confidence value.

### ADR-005: Build The Vertical Slice Before TensorRT Optimization

Reason: optimizing YOLO alone does not prove that camera, SLAM, TF, memory, and
query behavior work together. Profile the integrated system first.

### ADR-006: The Core Is Robot-Base Agnostic

Reason: mapping, perception, memory, and goal proposal can be developed with a
handheld camera and rosbag. Physical autonomous navigation requires a real base
and must be reported separately.

### ADR-007: Persistent Memory Uses SQLite First

Reason: it is durable, queryable, easy to inspect, and sufficient before a more
complex database is justified.

## 13. Target Repository Layout

```text
jetson-semantic-room-explorer/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  requirements/
    runtime.txt
    development.txt
    jetson-notes.md
  configs/
    camera/
    mapping/
    perception/
    memory/
  docs/
    architecture.md
    setup-jetson.md
    camera-femto-mega.md
    experiments.md
    troubleshooting.md
    jetson_env_snapshot.txt
  scripts/
    check_environment.py
    capture_femto_rgbd.py
    yolo_image_smoke_test.py
    benchmark_yolo_pytorch.py
  ros2_ws/src/
    semantic_explorer_interfaces/
    semantic_explorer_camera/
    semantic_explorer_perception/
    semantic_explorer_mapping/
    semantic_explorer_memory/
    semantic_explorer_query/
    semantic_explorer_bringup/
  tests/
    unit/
    integration/
  data/
    sample_images/
    outputs/
  benchmarks/
  models/
```

Create directories only when the corresponding implementation begins. Avoid an
empty architecture made of placeholders.

## 14. Definition Of Done

### Level 1: Perception And Mapping Demo

- Femto Mega RGB-D is reproducibly captured and replayable.
- RTAB-Map builds a room map and provides timestamp-correct poses.
- YOLO-plus-depth observations appear in the map frame.

### Level 2: Persistent Scene Memory Demo

- Repeated observations merge into durable objects.
- The database survives restart and supports useful object queries.
- A room scan can be replayed to reproduce the semantic map.
- CuTR is either integrated under a measured gate or documented as a failed
  experiment with useful results.

### Level 3: Object Search Demo

- A text or class query retrieves remembered objects.
- Unknown targets trigger further frontier search rather than a false success.
- A valid stand-off goal is produced and checked against the occupancy map.
- Physical navigation is demonstrated only when a mobile base and safety layer
  are available; otherwise the result is a clearly labeled dry run.

### Final Quality Bar

- Fresh setup and replay instructions are tested.
- Architecture and message contracts match the code.
- Results are reproducible and raw measurement conditions are documented.
- Known failures and limitations are explicit.
- A demo shows the complete data flow, not disconnected screenshots.
- Resume bullets describe only verified behavior.

## 15. Progress Ledger

Update this section at the end of every verified milestone. Add entries; do not
rewrite history merely to make progress look cleaner.

### 2026-07-27: Jetson Environment Baseline

Status: `VERIFIED`

Evidence:

- `docs/jetson_env_snapshot.txt`
- Captured CUDA-enabled PyTorch test output from the Jetson.

Result:

- JetPack 6.2.2, CUDA stack, ROS 2 Humble, and headless development established.

### 2026-07-29: YOLO Image Inference

Status: `VERIFIED`

Evidence:

- `scripts/yolo_image_smoke_test.py`
- `runs/detect/data/outputs/yolo_smoke_test/test.jpg`

Result:

- YOLOv8n inference executed on the Orin CUDA device and saved headlessly.

### 2026-07-29: YOLO PyTorch Benchmark

Status: `VERIFIED`

Evidence:

- `scripts/benchmark_yolo_pytorch.py`
- Captured 10-warmup, 50-run console output.

Result:

- Mean inference 30.76 ms; mean end-to-end call 59.79 ms; estimated 16.72 FPS.

### 2026-09-10: Architecture Revision

Status: `PLANNED`

Decision:

- Preserve YOLO-plus-depth as the vertical-slice baseline.
- Evaluate CuTR as a class-agnostic RGB-D 3D cuboid backend on keyframes.
- Add text-aligned semantics separately and fuse observations into persistent
  scene memory.
- Move TensorRT optimization after the first integrated pipeline is measurable.

Next action:

- Complete M2, Femto Mega reproducible RGB-D capture.

### 2026-09-10: M2 Native Capture And Lifecycle Checks

Status: `IMPLEMENTED`; automated capture checks are `VERIFIED`, physical-distance
validation is `BLOCKED`. M2 acceptance and the current task remain open.

Changed:

- Reused `scripts/femto_mega_capture_once.py` for profile enumeration and explicit
  1280x720 MJPG color + 640x576 Y16 depth at 30 FPS, STANDALONE/SDK synchronization,
  complete framesets, a 5000 us skew bound, and 15-pair sensor warmup.
- Preserved uint16 raw counts, exported separate calibration, timestamps, scale,
  profiles and depth-to-color extrinsics; added checked PNG writes/readbacks,
  bounded acquisition, explicit invalid depth and cleanup on failure.
- Added offline tests and a Jetson lifecycle/resource check under `tests/`, plus
  `docs/camera-femto-mega.md`; updated README with the measured partial status.
- No dependencies or device settings changed; work is on `feat/femto-capture`.

Verified:

```bash
.venv/bin/python scripts/femto_mega_capture_once.py --list-profiles --output-dir data/outputs/femto_mega_capture/verification_20260910
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_femto_hardware.py --output-dir data/outputs/femto_mega_capture/verification_20260910/final
.venv/bin/python -m compileall -q scripts tests
git diff --check
```

- Femto Mega firmware 1.3.1, USB 5000 Mbit/s, pyorbbecsdk2 2.1.1 / native SDK
  2.8.6; 126 color profiles and 14 depth profiles enumerated locally.
- 14 offline tests passed. Final hardware runner exited 0: ten separate CLI
  executions and ten same-process cycles passed, with PNG dimensions/content,
  calibration dimensions, raw depth and timestamps checked.
- Across those 20 captures: absolute device timestamp skew 72–670 us;
  depth scale 1.0 mm/count; valid ratio 0.2764–0.2930%; center ROI 0% valid.
  Raw nonzero range 46–12465 is recorded, not accepted as physical ground truth.
- After each close: 4 file descriptors, 12 threads, zero camera handles.
  Untrimmed RSS grew from 81072 to a peak 131744 KiB, but live glibc allocations
  grew only 54640 bytes. One test-only idle-page trim after error recovery left
  RSS at 87648 KiB. Short-run resource checks passed; long-run behavior is unproven.
- Actual 1 ms frame timeout and output-path failure raised errors, followed by
  successful capture and unchanged descriptor/thread counts.
- CLI mean/median/P95 4.538/4.534/4.564 s; same-process cycle durations
  4.186/4.184/4.197 s. Conditions: Orin Nano, 25 W, L4T R36.5.0, Python 3.10.12,
  NumPy 1.26.4, actual OpenCV import 4.11.0; no project ML/SLAM workload launched.

Evidence:

- `data/outputs/femto_mega_capture/verification_20260910/final/summary.json`
- Complete RGB/depth/visualization/metadata under that directory's `cli_01/`
  through `cli_10/`, `in_process/`, and `recovery/`.
- Same evidence root: `profiles.json`, `offline_tests.log`, `final.log`, `sdk.log`,
  `depth_diagnostic/summary.json`, and `memory_diagnostic/summary.json`.
- Compact results, reproduction commands and troubleshooting:
  `docs/camera-femto-mega.md`. Large artifacts remain ignored.

Problems and decisions:

- Physical distance/reference is not available locally; user was asked before
  implementation. A 150-pair follow-up still had only 0.2827–0.2951% valid depth
  and an invalid center. Cause is undetermined; do not claim metric accuracy.
- Retain the initial probe (~21% valid depth) and the failed RSS-only test as
  diagnostic history. The final resource check distinguishes live allocations
  from allocator retention; production capture does not force allocator cleanup.
- The sandbox blocks SDK initialization (`getifaddrs: Operation not permitted`);
  authorized hardware runs outside it succeeded. No SDK reinstall was needed.
- Existing overlapping OpenCV distributions remain; actual import is 4.11.0.
- Temporal synchronization is verified; spatial registration and independent
  calibration accuracy are not. Do not advance to ROS/SLAM or replace `prompt.md`.

Next action:

- Complete one fixed-plane physical-distance check with an unobstructed camera
  and user-supplied tape-measure reference, recording valid center depth and error.

### 2026-09-10: M2 Physical Range Check And Acceptance

Status: `VERIFIED` for native synchronized RGB-D capture and coarse metric units.
Absolute distance accuracy and RGB/depth spatial registration remain unmeasured.

Changed:

- No capture-code or camera-setting changes. The user fixed the camera, reported
  its front was unobstructed, and supplied a front-panel-to-wall distance interval
  of 200–300 cm. Recorded the interval as supplied, without inventing a point
  distance or signed error.
- Updated current status, README and capture documentation with the new evidence;
  advanced `prompt.md` to registration only after recording this acceptance.

Verified:

- Three new independent executions of
  `.venv/bin/python scripts/femto_mega_capture_once.py --output-dir <evidence-root>/capture_0N`
  exited 0 and saved complete 1280x720 color / 640x576 raw-depth artifacts.
- Independent PNG decoding and the existing hardware artifact checker passed.
  The central depth ROI `[310, 278, 20, 20]` had 400/400 valid samples each time.
- Center medians: 2333, 2332, 2332 raw counts. SDK scale: 1.0 mm/count, giving
  2.333, 2.332, 2.332 m, all within the user's independently supplied 2–3 m range.
  This supports the required simple unit check, not centimeter-level accuracy.
- Whole-image valid ratios: 74.8714%, 74.9156%, 74.9064%; absolute color/depth
  timestamp differences: 316, 267, 410 us. The three medians span 1 mm; this is
  short-run repeatability, not accuracy against a measured point distance.
- Reused the earlier final lifecycle evidence: ten CLI runs, ten same-process
  cycles, failure recovery and resource checks passed; 14 offline tests passed.
  Capture code is unchanged, so these checks were not unnecessarily rerun.

Evidence:

- Root: `data/outputs/femto_mega_capture/physical_check_20260910T181935Z/`.
- `physical_reference.json`, `summary.json`, and `capture_01.log` through
  `capture_03.log`; complete PNGs and metadata in `capture_01/` through `capture_03/`.
- Prior lifecycle evidence:
  `data/outputs/femto_mega_capture/verification_20260910/final/summary.json`.

Decisions and limitations:

- M2's native capture acceptance is met by the existing lifecycle/metadata tests
  plus this coarse physical range check. A narrower reference is optional for a
  later accuracy experiment, not a new prerequisite for the unit check.
- Coverage recovered after the user repositioned the camera. This is consistent
  with a placement/scene issue; the exact cause of the earlier dropout was not
  isolated. Preserve the earlier failed/low-coverage evidence as history.
- Raw depth is still unaligned. The next task is calibrated depth-to-color
  registration before using color pixels for 3D localization or ROS integration.

Next action:

- Verify SDK depth-to-color registration on this working setup, preserving the
  raw pair and checking transformed depth units, intrinsics and object edges.

### 2026-09-10: SDK Depth-to-Color Registration Acceptance

Status: `VERIFIED` for optional single-frame SDK registration and affected
capture/lifecycle checks. Absolute calibration accuracy, sustained throughput
and ROS integration remain unverified.

Changed:

- Updated README's measured M2 progress first, as requested, then extended the
  existing capture utility with `--align-depth`. Raw images remain unchanged;
  optional aligned depth and an overlay use the original color pixel grid.
- Used installed SDK `AlignFilter` with explicit `TargetDistortion=1`,
  `MatchTargetRes=1`, `GapFillCopy=0`. Default target distortion was zero and did
  not match the saved color. Hardware D2C profiles are advertised but hardware
  alignment was not executed; software registration satisfies this task.
- Exported actual aligned calibration, scale, source timestamps/index and
  `color_optical` axial Z. Added explicit raw optical-frame/Z labels. Checked
  source buffers, output calibration and filter settings; failures remain errors.
- Extended the existing tests with saved-artifact checks, independent projection
  and boundary diagnostics. No dependencies, device settings or ROS nodes added.
  Branch: `feat/femto-alignment`, based on verified M2 commit `b42334a`.

Verified:

```bash
.venv/bin/python scripts/femto_mega_capture_once.py --align-depth --output-dir data/outputs/femto_mega_capture/alignment_initial
.venv/bin/python tests/check_femto_hardware.py --align-depth --output-dir data/outputs/femto_mega_capture/alignment_verification_20260910/stability
.venv/bin/python data/outputs/femto_mega_capture/alignment_verification_20260910/analyze.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q scripts tests
```

- 21 offline tests passed, including synthetic shifted edges, target-frame Z with
  fractional raw scale, invalid pixels and missing/misconfigured SDK output.
- Final hardware runner: ten separate CLI and ten same-process cycles passed,
  plus warmup, actual timeout/save failure and successful recovery. Color/aligned
  images 1280x720, raw depth 640x576; both scales 1.0 mm/count. Aligned calibration
  exactly matched color; source depth timestamps/index and raw buffers survived.
- Across 20 pairs: absolute time skew 200–413 us; raw coverage 69.40–69.59%,
  aligned coverage 60.85–61.08%. All center ROIs were 400/400 valid. Raw medians
  2.353–2.355 m; aligned medians 2.347–2.349 m, within the user's 2–3 m reference.
  The raw/aligned centers are different rays, not an accuracy comparison.
- Cold filter mean/median/P95: 139.46/141.88/143.38 ms. Whole CLI cycle:
  4.553/4.543/4.620 s; same-process cycle: 4.264/4.262/4.283 s. Orin Nano, 25 W,
  existing SDK 2.8.6, Python 3.10.12, OpenCV 4.11.0; no ML/SLAM workload launched.
- After close: 4 descriptors, 12 threads, no camera handles. Untrimmed RSS
  baseline/peak 85112/157764 KiB; live allocations grew 70256 bytes. One test-only
  idle-page trim after recovery left 96800 KiB RSS. Existing guards passed.
- After final metadata-label additions, one raw-only and one aligned capture
  passed again, including explicit frame/quantity fields (`final_contract.json`).
- Three saved overlays inspected at five predefined ROIs. Drawer depth-jump
  median distances to RGB edges: 1–2 px, P95 up to 4.02 px. Sparse air-conditioner
  jumps were about 4 px away; basket valid/invalid boundary P95 reached 18 px.
  Invalid pixels and occlusion gaps remain visible and unfilled.
- Independent OpenCV projection: 2685–2692 valid target samples per frame;
  color-Z residual median 0.936–0.950 mm, P95 3.870–3.976 mm, max 20.52–41.64 mm.
  Retaining source-frame Z incorrectly gives 47–48 mm median residual. This is
  device-calibration consistency, not external distance accuracy.
- Complete diff reviewed; `git diff --check` and script/test compilation passed.
  Generated evidence and SDK logs were confirmed ignored.

Evidence:

- Root: `data/outputs/femto_mega_capture/alignment_verification_20260910/`.
- `stability/summary.json` (`PASSED`), all raw/aligned PNGs and metadata, CLI logs,
  `stability.log`, `geometry.json`, reproducible `analyze.py`, `offline_tests.log`,
  and `final_contract.json` / log / captures. Generated artifacts remain ignored.
- Local SDK/profile/default-distortion probe:
  `data/outputs/femto_mega_capture/alignment_probe_20260910T182532Z/probe.json`.
- Reproduction commands, all five boundary ROIs, metrics and caveats are in
  `docs/camera-femto-mega.md`; README reflects the measured state.

Limitations and decisions:

- Registration acceptance is met; it does not establish universal pixel accuracy.
  Missing returns, occlusions and texture edges affect boundary diagnostics.
- New filter instances include cold setup; no 30 FPS streaming claim is made.
  Short-run allocator/resource checks do not prove long-duration leak freedom.
- Preserve prior M2 low-coverage evidence. No precise distance reference or causal
  explanation for scene-dependent depth dropout was invented.
- ROS/SLAM was not started in this bounded task. Advance the current-task prompt
  only after this acceptance entry is recorded.

Next action:

- Verify the M3 ROS 2 camera contract and a short stationary rosbag replay using
  an inspected compatible Orbbec driver; room-walk mapping remains a later check.

### 2026-09-10: M3 Driver Source And Initial Build

Status: source checkout and message-package build `VERIFIED`; camera-driver build
`BLOCKED` by missing dependencies. M3 camera topics and rosbag acceptance remain
`PLANNED`.

Changed:

- With explicit user approval, cloned official Orbbec ROS 2 `v2-main` source into
  `/home/jeffx/projects/femto_ros2_ws/src/OrbbecSDK_ROS2` at commit
  `8e7cad2bfa2c4a6ac4e779be99c64e72166043af`. Checkout is unmodified.
- Driver and bundled ARM64 SDK are 2.9.3; native Python SDK 2.8.6 remains separate.
  Inspected source licenses, build requirements and Femto Mega launch defaults.
- Added `docs/camera-ros2.md` and README build status on `feat/ros2-camera`.
  No system packages or native capture code changed.

Verified:

- System ROS imports and sqlite3 bag reader/writer registration passed. Local
  search found no preinstalled Orbbec ROS driver; camera USB enumeration is 5000
  Mbit/s. No camera streaming was started in this build step.
- Ran the documented Release colcon build with two compiler jobs and upstream
  lint disabled. `orbbec_camera_msgs` completed in 1 min 37 s; Python message
  imports and a ROS serialization round trip passed.
- Camera CMake exited 1 at missing `backward_ros`. The first colcon process did
  not terminate after that error and was interrupted. Retrying with
  `--event-handlers console_direct+ desktop_notification-` exited 1 in 2.79 s,
  reporting the same missing dependency cleanly.
- CMake/header inspection and APT simulation identified six missing packages:
  `ros-humble-backward-ros`, `ros-humble-camera-info-manager`,
  `ros-humble-camera-calibration-parsers`, `ros-humble-image-publisher`,
  `ros-humble-diagnostic-updater`, `nlohmann-json3-dev`. Simulation: six new,
  zero upgraded, zero removed. No installation has been performed.

Evidence:

- `data/outputs/femto_ros2/bringup_20260910/`: `local_environment.json`,
  `source_and_build.json`, `build_initial.log`, `build_headless.log`,
  `dependency_plan.txt`; build details and exact commands in `docs/camera-ros2.md`.
- Upstream source and generated build/install/log files remain in the isolated
  workspace, outside the project repository.

Decision and next action:

- An explicit approval question for these six packages is pending, following
  the user's request to ask when components are missing locally. Once approved,
  install the reviewed dependencies and resume the pinned driver build. Do not
  ask again if the user has already approved them in the continued conversation.
- Preserve the Current Next Task and `prompt.md`; M3 acceptance is not complete.

## 16. End-Of-Session Handoff Template

Before ending a substantial Codex session, append or update the latest ledger
entry using this structure:

```text
Date:
Milestone:
Status: VERIFIED | IMPLEMENTED | PLANNED | BLOCKED

Changed:
- Files and behavior changed.

Verified:
- Exact commands/tests run.
- Important result values.

Evidence:
- Paths to logs, images, bags, benchmark summaries, or commits.

Problems:
- Exact failure and current diagnosis.

Decisions:
- Durable choices and why they were made.

Next action:
- One concrete task that can be resumed without reconstructing the conversation.
```

The repository, tests, and this ledger must be sufficient to resume the project
after chat history is unavailable.
