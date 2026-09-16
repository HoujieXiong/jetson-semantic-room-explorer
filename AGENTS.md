# Jetson Semantic Room Explorer: Codex Project Playbook

Last updated: 2026-09-15

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
ROS 2 camera topics: VERIFIED (rectified RGB-D at 15 FPS)
Rosbag recording/replay: VERIFIED (59.39 s stationary bag, exact simulated-time replay)
Moving RGB-D recording/replay: VERIFIED (93.88/94.49 s, 1402/1411 pairs)
Controlled room-loop capture quality: NOT VERIFIED (end motion/blur remains)
RTAB-Map offline odometry measurement: VERIFIED (sustained tracking loss recorded)
Motion-prediction comparison: VERIFIED (earlier recovery; same 21.104 s turn failure)
New forward/backward tracking: VERIFIED (898 tracked, zero lost at 0.25x; estimated distance)
RTAB-Map minimum mapping integration: VERIFIED (database, export, source-time TF)
Whole-room continuous tracking, geometric accuracy and navigation quality: PLANNED
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

### 4.6 RGB-D Object Observations

Status: `VERIFIED` for minimum offline camera/map observation integration.

YOLOv8n ran on the Jetson GPU with original mapped RGB-D nodes 7, 14 and 32.
Eighteen detections produced 15 depth-accepted observations and three explicit
rejections. Twenty-one focused tests pass; all accepted points agree with
independent Open3D projection within 2.251e-7 m per coordinate. This checks math,
not physical accuracy. Three annotations were inspected and reveal overlapping
chair boxes and likely class errors. The outputs represent observations, not
15 distinct objects. Surface-point accuracy, reliable instance association and live
performance remain unverified. See `docs/rgbd-object-observations.md` and the
M5 ledger entry for input identities, timestamps, timing and evidence.

### 4.7 Persistent Object Memory

Status: `VERIFIED` for minimum offline SQLite persistence and reopened queries.

The measured M5 corpus retains 18 observations: 13 representatives support nine
provisional objects, two same-frame overlapping detections add no extra support,
and three depth rejections remain unlocalized. Duplicate imports leave the
database byte-identical; reversed separate batches produce the same logical
database. Seventeen memory tests and 21 mapping/observation regressions pass.
Fresh-process `find refrigerator` returns three source-frame supports and mean
map point `[4.675447,0.911362,-0.794313]` m. Identity/accuracy and live scaling
remain unverified. See `docs/scene-memory.md`,
`data/outputs/scene_memory/m6_20260910/integration.json` and `final_check.json`.

### 4.8 Offline Object Search Goal Preview

Status: `VERIFIED` for minimum offline memory-to-goal previews and explicit
no-goal outcomes, using the frozen occupancy export and matching map/pose hashes.

The grid has 1122 free, 6379 occupied and 23135 unknown cells; 168 free cells
pass the assumed 0.25 m conservative clearance. Both provisional chair IDs
produce an observation point [1.15,0.63366] m, about 1 m from their respective
surface means. Refrigerator has no free cell in the stand-off band, sink has
insufficient clearance, and backpack is absent from memory. Six fresh CLI
processes, 16 search tests and 17 memory regressions pass the expected outcomes.
Repeated chair decisions are identical; all inputs remain unchanged. Ordinary
PNG overlays were inspected. Route, visibility, current localization, physical
footprint and traversability remain unverified. See `docs/search-goal-preview.md`
and `data/outputs/search_goal/m9_20260910/integration.json`.

### 4.9 Offline Route Validation

Status: `VERIFIED` for minimum offline routing with explicit start provenance.

All 48 recorded camera translations project into unknown grid cells; node 1
is refused as an invalid start without snapping. The explicit simulated start
[1.65,0.08366] m reaches both saved chair goals over 1.05 m / 22 grid cells.
Minimum segment clearance is approximately 0.257391 m; an independent continuous
certificate gives 0.256141 m against the assumed 0.25 m requirement. All 32
goal/route tests pass, eight route CLI cases match expected outcomes, and the
original goal-preview regression is unchanged. Inputs remain byte-identical.
Physical navigation, floor/map accuracy and current localization remain
unverified. See `docs/search-route-preview.md` and
`data/outputs/search_route/m9_20260911/integration.json`.

### 4.10 Offline Frontier Search Fallback

Status: `VERIFIED` for minimum geometric exploration proposals with explicit
simulated starts and unchanged source evidence.

The frozen map has 102 free/unknown frontier cells in 70 four-connected groups.
None is itself a clearance-valid goal. The fixed 0.30–0.75 m cardinal-view
policy produces 123 rays at 115 observation cells. Backpack/refrigerator/sink
no-goal outcomes retain their reasons while proposing the same in-place -Y view
from the original simulated start. A second simulated start exercises a 0.05 m
route to a -X view. Chair suppresses fallback; camera node 1 remains invalid.
All 48 search tests and nine frontier CLI cases match expected outcomes, with
unchanged original goal/route regressions and input hashes. No observation,
new coverage, physical visibility or navigation is verified. See
`docs/frontier-search-preview.md` and
`data/outputs/frontier_search/m10_20260911/integration.json`.

### 4.11 Single-Command Offline Search

Status: `VERIFIED` for composing the existing frozen-data search stages.

`scripts/run_offline_search.py` takes memory, map, label and an explicit start.
Available object goals lead to route checks; no-goal outcomes lead to frontier
search. It retains all candidates/refusals and writes `search.json` with the
branch, reason, source-associated outcomes and relative JSON/PNG evidence paths.
All 63 search tests and 12 native CLI cases pass. Existing goal/route/frontier
decisions and input hashes are unchanged; all 24 PNGs decode. No observations,
motion or new coverage were executed. See `docs/offline-search-demo.md` and
`data/outputs/offline_search/demo_20260911/integration.json`.

### 4.12 Chronological Observation-To-Search Replay

Status: `VERIFIED` for saved-observation feedback through immutable memory prefixes.

`scripts/replay_observation_search.py` imports original nodes 7/14/32 by source
time into separate snapshots and runs the existing search command after each
prefix. Bottle changes from `NOT_FOUND`/frontier to candidates 4/6 with
0.75/0.60 m routes, retaining one source-frame support each. All 78 search tests,
17 memory tests and 14 native CLI cases pass. Repeated/reversed inputs produce
identical decisions and corresponding snapshot bytes; the final logical SQL
dump matches the original M6 memory. Inputs and prior snapshots remain unchanged.
No causal online mapping, new observation, coverage or physical search is claimed.
See `docs/observation-search-replay.md` and
`data/outputs/observation_replay/replay_20260911/integration.json`.

### 4.13 Saved RGB-D To Search Demo

Status: `VERIFIED` for the first complete offline pipeline MVP.

`scripts/run_rgbd_search_demo.py` connects actual local GPU perception to the
existing prefix memory/search replay. Nodes 7/14/32 reproduce 18 detections,
15 accepted depth observations and three rejections; bottle changes from frontier
search to two remembered routes. Repeated results and final logical memory match
previous evidence. All 130 focused tests and 11 fresh CLI cases pass; all 66 PNGs
decode. The source pixels, units, timestamps, hashes and frozen prefixes were
checked. No dependency or existing runtime policy changed. See
`docs/rgbd-search-demo.md` and `data/outputs/rgbd_search/demo_20260911/integration.json`.
This is saved-frame inference using final poses and simulated starts; it does
not complete live integration, CuTR, open vocabulary or physical navigation.

### 4.14 Concurrent RGB-D Perception And SLAM

Status: `VERIFIED` for bounded same-stream concurrency at 0.25x replay.

`tests/check_concurrent_perception.py` reuses the mapping/sensor checkers and
shared `infer_rgbd` GPU/depth work. Inference overlaps online source-time pose
waiting, with one pending image, one worker and at most eight pose-waiting results.
Two full trials receive all 1411 original pairs. Moving pose waiting after
prediction reduces queue drops from 793 to nine; the final trial processes 1402
frames, accepts 1109 online poses and retains 293 explicit pose refusals.
Independent source-pixel/causal-TF checks pass. All 35 odometry/concurrency and
21 depth/mapping tests pass, as does the original offline GPU demo regression.
See `docs/concurrent-rgbd-perception.md` and
`data/outputs/concurrent_rgbd/trial_20260911/attempt_02/verification.json`.
Real-time throughput, tracking/geometry quality and causal online memory/search
remain unverified. No live camera capture or physical motion was executed.

### 4.15 Concurrent Observations To Frozen Memory And Search

Status: `VERIFIED` for post-run finalization against the concurrent run's own map.

The new map reopens with 76 stored nodes and exports 64 final poses, 50,537 points
and a checked occupancy grid. Original RGB-D extraction verifies all 58,982,400
depth pixels. `scripts/finalize_concurrent_observations.py` selects 62 exported
nodes by source timestamp, explicitly excludes two, and retains all 252 detections
(189 accepted depths, 63 rejections). Final poses reproject camera surface points
while preserving original online poses/points. The new SQLite memory has 46
provisional records and 185 supporting observations. Reopened queries and
matching-map searches pass: simulated bottle/chair routes, backpack frontier
fallback and recorded-camera-start refusal. Duplicate import is byte-identical;
29 focused tests pass. See `docs/finalize-concurrent-memory.md` and
`data/outputs/concurrent_rgbd/finalization_20260911/integration.json`.
No inference rerun or physical motion occurred. This is frozen post-run memory,
not causal online search; physical geometry and identity remain unverified.

### 4.16 New Forward/Backward Capture And Pipeline Replay

Status: `VERIFIED` for new source data, reported tracking continuity at 0.25x,
and its own frozen map/memory/search; physical scale and drift remain unverified.

The 60.224-second bag has 899 synchronized pairs and no source-index gaps.
Odometry produces 898 tracked outputs, zero lost outputs and one missing output.
Perception processes 893 pairs with six explicit queue drops. All owned processes
close cleanly. The operator estimated about 1 m and reported faster main movements
and additional forward/backward adjustments. Maximum estimated displacement is
1.016861 m; endpoint/hold differences are not isolated algorithm drift.
The final map has 20 saved optimized poses, excluding online-only node 60.
`extract_mapped_rgbd.py` now verifies saved database ID membership, preserving
that exclusion; 48/64-node old maps still match their native exports. The new
memory retains 90 observations from 19 nodes and 17 provisional records. Reopened
queries, simulated search and recorded-camera-start refusal pass; duplicate
import is byte-identical. All 27 mapping and 29 memory tests pass. See
`docs/straight-line-capture.md`,
`data/outputs/femto_ros2/measured_line_20260915T224455Z/`, and
`data/outputs/concurrent_rgbd/line_20260915/integration.json`.

### 4.17 ROS 2 Goal And Path Preview Publication

Status: `VERIFIED` for bounded frozen-data publication to independent subscribers.

The publisher reuses the existing search stages and publishes decision JSON,
metric map goals and checked paths on dedicated preview topics. One hundred
search tests pass. Real separate-process trials verify bottle object 8's 0.05 m
route, a zero-translation backpack frontier, recorded-camera refusal with no
pose/path, and an explicit missing-subscriber timeout. All contexts close and
source hashes remain unchanged. An initial executor/context error is preserved
and corrected. See `docs/ros-search-preview.md` and
`data/outputs/search_publication/validation_20260915/attempt_02/integration.json`.
This does not establish live localization, physical accuracy or navigation.

### 4.18 Persistent Image-Text Memory And Semantic Search

Status: `VERIFIED` for minimum saved-data MobileCLIP indexing, ranking and ROS
preview integration. Retrieval quality and live throughput remain unverified.

The isolated official S0 encoder indexes 63 accepted supports from 19 nodes into
17 existing objects, preserving per-view crops/vectors and source hashes. The
second build reproduces all per-view vector bytes. Independent source-pixel,
scalar fusion and eleven-query ranking checks pass. Final warm crop encoding has
median 37.245 ms and P95 51.758 ms. All 39 memory and 103 search tests pass, plus
five native refusal cases. Three GPU text-to-ROS cases retain geometric failures
and unknown-target fallback; independent receivers match and all contexts close.
The fixed query set includes poor bottle retrieval and unvalidated attributes;
no presence-probability or accuracy claim is made. See `docs/semantic-memory.md`,
`data/outputs/mobileclip/line_20260915/integration.json`, and its embedded-image
`queries_final/queries.html` review. Original memory/map and baseline GPU packages
are unchanged; weights/crops remain local.

## 5. Current Next Task

Milestone: **M7 CuTR feasibility, followed by remaining live pipeline integration**.

Status: `PLANNED` for measured CuTR inference/geometry acceptance. Source download
and isolated data-reader preparation are underway; no successful inference is
claimed yet. ROS preview publication and minimum saved-data M8 retrieval are
verified and recorded below.

The user explicitly requested pipeline-first work on 2026-09-15 and deferred
physical scale/return-error refinement. Do not gate software integration on new
measured-motion capture. Preserve all functional/quality limitations. The user
explicitly authorized official MobileCLIP and CuTR source, model weights and
required dependencies, plus a minimal official CuTR sample, in isolated environments.

Required sequence:

1. Finish the official CuTR RGB-D checkpoint download (the first transfer was
   interrupted; retain the failure). Check source/model licenses and exact
   versions. Reuse local GPU PyTorch and keep the camera/SLAM baseline unchanged.
2. Run a bounded headless official-sample trial, saving predictions, input shapes,
   depth units, intrinsics/gravity, initialization time, warm P50/P95 and memory.
3. If viable, adapt existing verified Femto RGB-D and compare multiple views with
   YOLO-plus-depth. Treat gravity as an explicit input; the current bags have no
   IMU stream, so any pose-derived gravity is an assumption, not a measurement.
4. Measure alongside the existing recorded SLAM workload before selecting an
   operational role. Preserve poor quality or resource failures. Do not introduce
   a second production backend before the experiment supports it.
5. Continue toward causal online memory/query decisions using existing bags.
   Reuse measured code, run focused checks, review complete diffs, update evidence
   and push verified checkpoints. Ask only for missing input/equipment/authority.

Local preparation: `~/projects/ml-cubifyanything`, `~/projects/cutr-env`, and
`data/outputs/cutr/setup_20260915/`. The official sample subset contains the first
three complete frames (42 files), copied from a 16 MiB HTTP range of the archive.
The original 2026-09-15 recording and all prior map/memory artifacts remain intact.

Learning checkpoint: CuTR proposes geometry; MobileCLIP supplies text similarity;
neither replaces source-time poses, persistent association or checked planning.

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

Status: `IMPLEMENTED`; stationary and moving sensor contracts/replay `VERIFIED`.
Controlled room-loop capture quality remains unverified.

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

Status: `VERIFIED` for minimum offline mapping integration: database reopening,
geometric export and timestamped map/optical-camera TF. Continuous tracking,
map accuracy, loop consistency and real-time performance remain `PLANNED`.

Steps:

1. Run RTAB-Map on recorded data first.
2. Use the verified odometry/TF contract to connect the mapping node.
3. Save and reopen a database; export geometry and timestamped poses/TF.
4. Advance to M5 once the minimum integration contract passes.
5. Improve tracking, depth limits and throughput, then evaluate room-loop quality.

Minimum integration acceptance:

- A nonempty database can be reopened and a geometric map exported.
- Mapped observations have a connected, timestamp-valid TF chain.
- Tracking loss and partial map coverage remain explicit for downstream users.

Later quality acceptance:

- The TF tree is connected and temporally valid.
- Mapping survives the full bag without repeated reset or fatal frame drops.
- A loop trajectory produces a visibly consistent room map.

Learning goal: odometry versus mapping, pose graphs, loop closure, and TF.

### M5: YOLO Plus Depth 3D Baseline

Status: `VERIFIED` for minimum offline integration; later quality acceptance
remains `PLANNED`. Three real mapped RGB-D frames produced 15 depth-accepted
camera/map observations and three rejections; 21 tests and independent Open3D
projection checks pass. See the M5 ledger entry and `docs/rgbd-object-observations.md`.

Steps:

1. Start with an existing mapped color RGB-D frame and its intrinsics/source stamp.
2. Run the existing YOLO baseline.
3. Reject invalid and outlier depth within an inner detection ROI.
4. Back-project the robust depth estimate into the optical camera frame.
5. Associate the mapped pose and save structured camera/map-frame observations.
6. Test the projection math and data association with known and measured cases.

Minimum integration acceptance:

- A real detection produces a source-associated camera/map-frame 3D observation.
- Tests cover projection, depth units, invalid depth and coordinate conventions.

Later quality acceptance:

- Repeated views of a static object produce characterized position jitter.
- Detection and geometric accuracy and live processing cost are measured.

Learning goal: projective geometry and uncertainty from 2D detection plus depth.

### M6: Persistent Map-Frame Scene Memory

Status: `VERIFIED` for minimum offline persistence, deterministic association and
reopened label queries. Seventeen memory tests, 21 existing regression tests and
real M5 imports pass; 18 observations form nine provisional objects with
13 supporting observations, at most one per object per frame. Reliable identity, covariance-aware fusion and
live scaling remain `PLANNED`. See the M6 ledger entry and `docs/scene-memory.md`.

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

Status: `VERIFIED` for minimum saved-data text retrieval and query-to-preview
integration with MobileCLIP-S0. The complete eleven-query set and failures are in
`docs/semantic-memory.md`. Proposal coverage, retrieval/attribute quality,
calibrated unknown rejection and live operation remain `PLANNED`.

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

Status: `VERIFIED` for minimum offline memory-to-goal and route previews,
including the single-command goal/route/frontier composition.
Fixed stand-off/clearance assumptions, map/pose identity, explicit starts,
whole-segment route checks, PNGs and no-goal/no-route outcomes pass on the saved
map. The successful route uses an explicitly simulated start; recorded camera
positions fall in unknown cells. Bounded ROS 2 preview publication is also `VERIFIED`; see
`docs/ros-search-preview.md`. Cuboid geometry, causal live decisions, continued
exploration and physical navigation remain `PLANNED`. See
`docs/search-goal-preview.md`, `docs/search-route-preview.md` and the M9 ledger.

Steps:

1. Query known memory before initiating exploration.
2. Return object candidates with confidence, last-seen time, and map location.
3. Convert an object cuboid into a collision-checked stand-off goal candidate.
4. Support dry-run goal publication before any robot motion.
5. Continue search when the target is absent or confidence is insufficient.

Learning goal: grounding semantic results into actionable robot goals.

### M10: Exploration And Navigation

Status: `VERIFIED` for minimum offline geometric frontier fallback and its
single-command search composition.
Free/unknown boundaries, restricted cardinal viewing rays, explicit start
validation and reused route checks pass on the frozen map. Starts are simulated
for successful proposals; recorded camera starts remain invalid. Active sensing,
measured coverage/information gain, semantic frontier ranking and Nav2 remain
`PLANNED`, mobile base dependent for physical validation. See
`docs/frontier-search-preview.md` and the M10 ledger entry.

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

### ADR-005: Build The Vertical Slice Before Component Optimization

Reason: optimizing YOLO or odometry alone does not prove that camera, SLAM, TF,
memory and query behavior work together. The user reaffirmed pipeline-first work
on 2026-09-10. Once a component's minimum interface contract is measured, connect
the next component; retain known limitations and profile the integrated system
before spending more time on individual quality or performance improvements.

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

### 2026-09-10: M3 Stationary ROS Contract And Replay Acceptance

Status: `VERIFIED` for the stationary ROS camera/record/replay step. M3 room-walk
recording, long-duration stability and M4 SLAM remain unverified.

Changed:

- Continued after explicit user approval and pushed the prior source-build
  checkpoint to `feat/ros2-camera`. Downloaded/extracted the six reviewed Debian
  packages under the isolated workspace because passwordless sudo was unavailable;
  no system packages or maintainer scripts were installed/run.
- Built pinned Orbbec ROS driver/SDK 2.9.3, with local Humble cv_bridge 3.2.1 from
  vision_opencv commit `9800f67cea477c44cfb64e349854bcb6a09dc9ce` against NVIDIA
  OpenCV 4.8. Initial complete build: three packages in 10 min 10 s. Runtime
  library mappings confirm only OpenCV 4.8, local cv_bridge and SDK 2.9.3.
- Preserved `patches/orbbec_ros2_rgbd_contract.patch`: six lines skip explicitly
  disabled IMU construction, which otherwise failed on missing USB/HID permission;
  one line normalizes an SDK-derived TF quaternion (initial norm 0.999275748).
  Patched builds passed; enabled IMU behavior/permissions remain unverified.
- Added `config/femto_rgbd.yaml`, `scripts/femto_ros2_env.bash`, the shared live/
  bag/replay contract checker and focused ROS tests. Reused the upstream node,
  hardware alignment, RGB undistortion, frame synchronization and timestamp CSV.
- Hardware D2C depth has zero distortion; original RGB did not. Enabled the
  existing RGB undistortion option so delivered K/D/R/P and grids match. Final
  source profiles are RGB 1280x720 MJPG and depth 640x576 Y16 at 15 FPS.
- Updated README and `docs/camera-ros2.md` with measured results and exact setup,
  launch, recording and replay commands. Native capture code remains unchanged.

Verified:

- Actual 15 FPS live check passed, followed by a 59.390958627 s SQLite/message-zstd
  bag (1.055 GB): 887 messages on each image and CameraInfo topic, plus one static
  TF message. Recorded color/depth rates were 14.9230/14.9231 Hz.
- No unmatched pairs, Image/CameraInfo mismatches, source-index gaps, timestamp
  regressions or device intervals above 1.5 nominal periods inside the bag.
  Maximum color/depth header periods were 67.571/67.354 ms. The subscriber handoff
  before recording accounts for the separate `ROS_PUBLISH dropped=15` log entries;
  the final run had no SDK drop logs.
- All recorded CameraInfo stamps exactly matched corresponding SDK-global CSV
  stamps. RGB-D device skew median/P95/max: 531/654.7/955 us; ROS-global skew:
  3628/3972.1/4197 us. Preserve this distinction for downstream synchronization.
- Both delivered images are 1280x720 in `camera_color_optical_frame`; RGB is
  `rgb8`, aligned depth `16UC1` millimeters with zero invalid. Center medians
  ranged 2.359–2.363 m within the user's 2–3 m reference; coverage 73.188–73.669%.
  Matching calibration and normalized static TF passed at observation timestamps.
- Bag receipt minus global image-header median/P95: color 205.502/213.604 ms,
  depth 209.756/217.464 ms. These include clock mapping and transport/processing;
  they are not independently calibrated exposure latency.
- Driver descriptors stayed 40, RSS 97632–99640 KiB, threads 31–34. Recorder
  descriptors stayed 20, RSS 88672–129964 KiB, threads 22. Driver/recorder exited
  0 after SIGINT without forced termination. No long-run leak claim is made.
- With no camera driver running, a complete 1x replay reproduced exact per-topic
  counts and serialized SHA-256 values, including all image bytes, headers,
  CameraInfo and TF. Only rosbag2_player publishers were observed. The checker
  received 1836 clock messages, verified active advancing simulated time and TF;
  player and checker both exited 0.
- Fourteen ROS tests and 21 existing native tests passed. After ROS recording,
  a fresh native raw/aligned capture and existing artifact checker passed:
  1 mm/count, 239 us skew, raw/aligned centers 2.380/2.364 m. This confirms the
  camera was released and the separate SDK 2.8.6 path remains usable.
- Complete diff reviewed. Final boundary-loss guards and a stalled-stream test
  passed; `stationary_15fps_final_bag.json` revalidated identical replay counts/
  hashes. Patch forward/reverse application checks, Python compilation, shell
  syntax and `git diff --check` passed. Generated room data is ignored, and no
  camera, checker, harness or build process remains running.

Evidence:

- Root: `data/outputs/femto_ros2/bringup_20260910/` (ignored).
- Current `acceptance_summary.json`; `local_dependencies.json`; build logs;
  `driver_linked_libraries.txt`; `ros_unit_tests.log`, `native_unit_tests.log`.
- `stationary_15fps_config.yaml`, live/bag/replay reports, source timestamp CSV,
  `stationary_15fps_source_timing.json`, record/replay run manifests and logs.
  The bag and its metadata are in `stationary_15fps/`.
- Saved experiment harness `run_check.py`, correlation script `analyze_timing.py`,
  local RGB/overlay inspections and `native_after_recording.json` / capture files.
  Reproduction commands and source hashes are in `docs/camera-ros2.md`.

Failures, decisions and limitations:

- Initial profile enumeration reached the required RGB/depth profiles then
  aborted on IMU access. Unpatched startup published zero frames; the bounded
  checker rejected it and closed the driver. Preserve these failures.
- Initial TF and distortion checks rejected non-unit TF and incompatible RGB/
  depth distortion. The fixes above were verified on actual messages.
- The 30 FPS bag held 1714 matched pairs over 59.294 s but had a 1.843 s maximum
  header interval and 2.182 s reception stall. Cause not fully isolated; retain
  it as diagnostic evidence. The stable 15 FPS recording is the accepted profile.
- First replay delivered sensor data but failed the clock check due to the
  checker's reliable subscription versus the player's best-effort clock. Fixed
  the subscription and repeated the complete replay successfully.
- Missing returns/occlusion holes remain. No new absolute calibration accuracy,
  moving-scene, visual-odometry, room-mapping or sustained 30 FPS claim is made.
- Stationary acceptance is now recorded; advance the Current Next Task and
  `prompt.md` to supervised room-walk recording only after this entry.

Next action:

- Prepare and capture one supervised room-walk bag after the user returns.

### 2026-09-10: Moving RGB-D Contract And Replay, Capture Quality Pending

Status: `VERIFIED` for the moving sensor contract and exact replay. The complete
supervised room-walk task remains `IMPLEMENTED`, with capture quality unresolved.

Changed:

- Added `--scene room-walk` to the existing checker, preserving the default
  fixed-wall 2–3 m check. Moving checks count empty center regions and entirely
  empty depth frames, reject recordings with no valid depth, and retain the
  millimeter conversion, calibration, timestamps, pairing and static-TF checks.
- Replay inherits its reference scene; empty/non-passing references and explicit
  scene conflicts fail before ROS starts. Added four focused ROS tests and
  updated README and `docs/camera-ros2.md`. No driver/config/dependency changes.
- User confirmed presence, portable equipment and readiness before each
  coordinated 95-second recording. Each attempt has its own preserved output.

Verified:

- Eighteen ROS tests passed (final run 12.694 s). Two CLI rejection checks passed. The
  original 887-pair stationary bag passed again with identical topic statistics
  and hashes; its wall-unit check remains enabled. New moving replays exercised
  automatic scene inheritance without an explicit `--scene` argument.
- Attempt 1: 93.883938807 s, 1402 messages on each image/CameraInfo topic, one
  static-TF message, 2.018 GB. Attempt 2: 94.487476504 s, 1411 on each camera
  topic, one static-TF message, 1.854 GB. Both retain the measured 15 FPS config.
- Attempt 2 header rates: color/depth 14.9260/14.9264 Hz; maximum header periods
  67.661/67.429 ms. Both attempts have zero unmatched RGB-D or Image/CameraInfo
  stamps, including boundaries; zero source-index gaps; and zero device intervals
  exceeding 1.5 nominal periods. All CameraInfo headers equal SDK-global CSV
  stamps; K/D/R/P and config exactly match the accepted stationary baseline.
- Attempt 1/2 maximum device skew: 0.829/0.827 ms; maximum published global skew:
  4.924/4.149 ms. Registered uint16 millimeter depth and color optical frames/TF
  pass. Unknown moving-scene distances are not a new physical accuracy check.
- Attempt 1/2 depth coverage: 53.349–77.559% / 48.812–78.962%; empty center
  frames: 5/20; entirely empty depth frames: 0/0. These gaps remain explicit.
- Complete 1x replays passed with driver absent and only rosbag2_player publishers.
  Per-topic counts and serialized hashes matched exactly, including all images,
  calibration and TF. Advancing active simulated time received 2872/2891 clock
  messages. Both players/checkers exited 0 (98.992/99.592 s harness duration).
- Both recorders/drivers exited 0 after SIGINT without forced termination. Attempt
  2 descriptors stayed at 40/20; driver/recorder RSS was 92248–99940 /
  81680–109400 KiB. This is a short sample, not a long-run leak measurement.
- Complete diff review, Python compilation and `git diff --check` passed. Final
  process inspection found no camera, recorder, checker, harness or player running.

Evidence:

- `data/outputs/femto_ros2/room_walk_20260910T223548Z/` (ignored), with
  `acceptance_summary.json`, `preparation.json`, `cli_checks.json`, stationary
  regression/preflight reports and `ros_unit_tests_final.log`. The summary explicitly leaves the current
  task incomplete while verifying the sensor/replay subset.
- `room_walk_01/` and `room_walk_02/`, matching config/CSV/live/bag/source-timing/
  transport/replay reports, exact-command run manifests and full process logs.
- `operator_context.json`, `image_review.json`, one-second RGB samples and local
  contact sheets retain user reports and observable image evidence separately.
- Existing experiment harness reused locally; analysis scripts and reproduction
  commands are documented in `docs/camera-ros2.md`. No room imagery/bag is committed.

Limitations and decisions:

- User reports attempt 1 did not complete a loop. Attempt 2 reportedly returned
  near the start and held still, but sampled images show continuing motion/blur,
  a ceiling view at about 90 s and a different final orientation at about 94 s.
  Stationary endpoints and controlled capture quality are not verified. The
  user subsequently confirmed adjusting/putting down the camera after returning.
  After the user questioned whether more recording was necessary, the assistant
  stopped preparing another take. The third take was never started. Endpoint
  handling does not invalidate the preceding moving data; an initial offline
  odometry experiment can evaluate its actual usefulness before recapture.
  No geometric return pose/loop closure was measured.
- Source continuity does not prove smooth real-time reception: maximum SDK
  callback intervals were 395.543/311.478 ms. Maximum image receipt intervals
  were 402.080/311.312 ms; color CameraInfo reached 681.903/693.036 ms. All recorded
  source frames arrived, but the transient buffering cause remains unresolved.
- Startup subscriber handoff logged 24/15 skipped publications before recording;
  no SDK drop was logged. Do not claim zero losses throughout startup.
- Keep current task and prompt unchanged in scope. No SLAM, perception or robot
  actuation was started; absolute accuracy and long-duration stability remain
  unverified. Learning: intact synchronized data and replay do not establish
  stable camera motion, useful visual odometry or a correct map.

Next action:

- Evaluate RGB-D odometry on the existing second recording when continuing to
  that scope; use measured tracking performance to decide whether recapture is
  needed. Do not automatically repeat recording for stationary endpoints alone.

### 2026-09-10: M4 Offline Odometry Trial, Sustained Tracking Failure

Status: `VERIFIED` for the offline runtime and measurement contract. Continuous
odometry and room mapping are not verified; this is a recorded negative result.

Changed:

- Continued after the user's explicit approval to try existing data and download
  the missing RTAB-Map components. Downloaded 35 packages (21,665,814 bytes), reused
  one cached archive, verified all 36 SHA-256 values and extracted locally.
  No system packages or maintainer scripts changed/ran. Core/ROS version 0.23.7.
- Added the isolated environment helper, minimal RGB-D odometry config, bounded
  result checker and focused tests. Reused the upstream odometry executable and
  existing statistics helper; no mapping node, camera activation or new capture.
- Added `docs/rtabmap-odometry.md` and README measurements. Advanced this file's
  next task under the user's newer odometry authorization, retaining unresolved
  M3 capture-quality conditions and the earlier `prompt.md` task text.

Verified:

- Runtime libraries use system Humble cv_bridge and only OpenCV 4.5d, separate
  from the camera's 4.8 overlay. Startup, OdomInfo serialization and clean close
  passed. Exact versions, hashes, library mappings and parameters are saved.
- Two full replays of the 94.487476504-second second bag, with no camera driver
  present. Both reproduce all 1411 CameraInfo messages per stream and exact
  reference hashes. Image contents were verified by the prior full M3 replay;
  this lightweight benchmark checker does not hash image payloads again.
- 1x with the default latest-frame policy: 466 results, 100 tracked and 366 lost;
  945 inputs without results. Processing median/P95/max:
  168.291/239.881/326.865 ms. Long loss: source offsets 18.559–93.931 s (75.373 s).
- 0.25x with `always_process_most_recent_frame=false`: 1410 results, 420 tracked
  and 990 lost; one final input pair without a result. Processing median/P95/max:
  183.904/239.055/349.257 ms. Long loss: 21.104–81.870 s (60.766 s), plus
  19.430–19.564 s and 89.040–94.467 s. Automatic reset stayed disabled.
- Output Odometry/OdomInfo stamps exactly match synchronized source image pairs.
  All 100/420 tracked poses match their dynamic TF and connect to the recorded
  color optical frame at that timestamp. Simulated clock checks pass, with
  2900/11373 clock messages. Null lost poses remain explicit and CSV cells empty.
- Odometry descriptors remained 19; threads 31–36. RSS ranges: 154780–277096 KiB
  and 152928–324896 KiB. Player/checker/odometry all exited 0 with no forced stop;
  complete harness times were 131.499/417.781 s. Final process inspection found
  no camera, odometry, replay, checker or harness running. No long-run leak claim.
- Twelve focused tests passed (0.068 s), plus three CLI rejection checks, Python
  compilation, shell syntax and `git diff --check`. A real ROS no-input run exited
  1 after its bounded wait and saved an `INCOMPLETE` report with zero observations.
  Complete diff reviewed; generated evidence stays ignored and local.
- User-requested viewing follow-up: exported the complete RGB recording as
  H.264 MP4 (1411 frames, 94.533 s, 26.14 MB) and an 18–25 s source-time clip at
  half speed (105 frames, 14.068 s, 2.50 MB). Captions retain source time and exact
  per-frame diagnostics from the measured 0.25x trial. All frames decode and
  presentation timestamps match within 1 us; the complete serialized RGB hash
  matches the bag reference. No dependency download or new odometry run.
- Attached-display follow-up: Totem lacked an H.264 decoder. Reused the installed
  VP8 encoder/decoder to make full/short WebM viewing copies, 1411/105 frames and
  47.40/6.53 MB. Both pass complete PyAV and system GStreamer decoding, with
  maximum timestamp quantization errors 0.500/0.498 ms. The user confirmed the
  short clip plays on the Jetson display. No decoder installation was needed.

Evidence:

- `data/outputs/rtabmap_odom/preflight_20260910T230308Z/`: approved dependency
  plan, download/extraction log and verified manifest, startup checks, library
  mappings and matching official source copies. The original blocked preflight
  plan is historical; `dependencies_prepared.json` records its successful completion.
- `data/outputs/rtabmap_odom/trials_20260910/`: both trial directories with exact
  commands/configs/parameters, scalar diagnostics, JSON/CSV trajectories and
  process/resource logs; `summary.json`, `analyze.py`, source-time PNG/PDF plot,
  `run_trial.py`, `unit_tests_final.log`, `cli_checks.json` and the checker used.
- Reproduction commands, source commit, package versions and limits are in
  `docs/rtabmap-odometry.md`. No room images, bags or trajectories are committed.
- Viewing exports, `export_video.py`, `export_report.json`, `export.log` and the
  decoded `loss_at_21_104s.png` preview are in the trials root's ignored
  `video_review/` directory. In the half-speed clip, player time 6.163 s displays
  source time 21.104 s. The frame reports 7 inliers from 130 matches; this viewing
  aid does not establish a cause or complete the controlled diagnosis task.
- `video_review/convert_webm.py`, both `.verification.json` reports and `.gst.log`
  files retain the desktop-compatible export checks. An initial conversion's
  incorrect time base was rejected; that output remains separately named
  `loss_18_to_25s_half_speed_rejected_timing.webm`. Only the corrected standard
  filenames passed verification and are linked for viewing.

Limitations and decisions:

- Initial 1x warnings explicitly recommend disabling the latest-frame policy
  for bursty offline replay. The slow diagnostic changes both rate and that
  policy; it does not isolate the effect of rate alone. Original timestamps,
  receipt bursts, calibration, depth units and images are preserved.
- Almost complete processing still produced prolonged loss well before the
  final camera handling. Insufficient inliers and later projected points outside
  the camera are observed, but a unique root cause is not established. Do not
  blame operator motion alone or claim that another full recording is necessary.
- A tracked flag is not ground-truth pose accuracy; recovery is not loop closure.
  No continuous trajectory, room map or real-time 15 FPS odometry was verified.
  Learning: sensor delivery, pose/TF consistency and usable tracking are separate
  acceptance conditions, and failed tracking must remain visible in evidence.

Next action:

- Diagnose the first sustained slow-replay loss around 21.1 s using nearby frames
  and match statistics from this same bag, then test one controlled adjustment.

### 2026-09-10: M4 Controlled Motion-Prediction Comparison

Status: `VERIFIED` for the controlled measurement. Continuous tracking, pose
accuracy and room mapping remain unverified.

Changed:

- After the user approved the fast-turn investigation, reused the existing bag,
  runtime, checker and bounded harness. Changed only `Odom/GuessMotion` to the
  string `"false"` in an ignored experimental configuration; retained the
  checked-in default. No new dependencies, camera activation or recording.
- Updated README and odometry documentation with the measured comparison and
  advanced the next diagnostic task. Earlier M3 capture-quality limits and
  `prompt.md` remain intact.

Verified:

- Ran `motion_guess_20260910/run_trial.py guess_off 0.25` with the saved
  `no_motion_guess.yaml` as its third argument, in the isolated environment.
  Compared with the saved `trials_20260910/rate_025` baseline. Runtime dumps
  differ only in `Odom/GuessMotion`; player commands and library paths match.
- Both settings processed 1410 / 1411 pairs; the final pair lacked a result.
  Prediction on: 420 tracked / 990 lost (70.21% lost). Off: 1138 / 272 (19.29%).
  The main loss starts at the same 21.104143 s source stamp, with 7 / 8 inliers
  against the required 20; recovery is at 81.870444 / 31.555048 s. The longest
  loss is 60.766301 / 10.450905 s. In the 18–25 s window, loss worsened from
  61 / 105 to 68 / 105 results. Last tracked source time was 88.973 / 87.499 s.
- Prediction-off processing median/P95/max: 229.256/268.032/332.570 ms, versus
  baseline 183.904/239.055/349.257 ms. RSS 154760–331440 KiB, descriptors 19,
  threads 31–36. All three processes exited 0 without forced termination;
  harness wall time 415.473 s. Final inspection found no experiment or camera
  process remaining. No long-run resource-leak claim.
- Both CameraInfo reference hashes and all source-stamp/clock/pose/TF checks
  passed: 1138 validated tracked pose/TF pairs and 11431 clock messages in the
  new run. Lost poses and missing outputs remain explicit in the JSON/CSV.
- Inspected 11 original 16UC1 depth frames near 18–25 s. Nonzero coverage was
  60.74–76.55%; at the shared failure it was 75.45%, with 3.092 ms RGB/depth skew
  and nonzero depth P05/median/P95 of 1.250/1.492/2.431 m. The depth frame was
  present, not entirely invalid; feature-location depth remains unmeasured.
- Across 389 common tracked stamps, estimates disagree by median 0.268 m /
  3.090 degrees without post-alignment; before 18 s, by 0.262 m / 3.029 degrees
  over 269 poses. These compare estimates and do not measure absolute accuracy.
- Saved comparison assertions pass and the source-time plot was reviewed.
  No runtime/checker code changed this session. Relative to the saved baseline,
  only earlier checker output-file/cleanup fixes differ; subscriptions and
  measurement logic match. Verification used the full-bag integration run and
  saved-result/depth analysis. Complete diff and whitespace checks pass.

Evidence:

- `data/outputs/rtabmap_odom/motion_guess_20260910/`: experiment plan, config,
  bounded harness, `guess_off/` logs/parameters/measurements, `compare.py`,
  `comparison.json`, PNG/PDF comparison plots, original depth inspection script
  and `turn_depth.json`, desktop preflight, final process check, checker snapshot
  and `verification.json`.
- Reproduction commands and all loss intervals are in
  `docs/rtabmap-odometry.md`. Images, bags, videos and trajectories remain ignored.

Limitations and decisions:

- Recovery improved in one run compared with a saved baseline; the turn still
  failed and median processing increased about 25%. Keep the existing default.
  There is no repeated-run stability result or independently verified pose.
- Turning, blur and scene texture may contribute, but neither angular speed nor
  a unique physical cause was measured. A higher tracked count does not prove a
  more accurate trajectory, and recovery does not establish loop closure.
- Learning: evaluate failure onset, recovery, processing cost and pose quality
  separately; a favorable full-bag count can hide a worse local failure.

Next action:

- Inspect feature correspondences and depth at their image locations around
  source time 21.1 s in the same bag, before another parameter change.

### 2026-09-10: Pipeline-First Direction And Mapping Dependency Preflight

Status: `VERIFIED` for local dependency inspection. Mapping integration is
`PLANNED`; its missing ROS node is `BLOCKED` pending download approval.

Changed:

- Applied the user's direction to connect the whole pipeline before refining
  components. Deferred further turn-failure diagnosis and advanced the next task
  to minimum mapping integration, followed by M5 object observations.
- Separated integration acceptance from later mapping quality acceptance in this
  file and documented the direction in README and the odometry notes. Preserved
  all negative results; no new tracking, mapping or accuracy success is claimed.

Verified:

- No `rtabmap_slam` package registration or executable exists in system Humble
  or the extracted RTAB-Map workspace. Local core tools do exist, but they do not
  provide the missing ROS node. No matching SLAM archive/source was found in the
  searched project, download and user-cache locations.
- A local `apt-get --simulate --no-install-recommends install
  ros-humble-rtabmap-slam` requires 39 packages not registered in system dpkg.
  Of these, 35 match the versions already extracted and their retained archive
  hashes pass. Four additional packages are needed: `rtabmap-slam`,
  `apriltag-msgs`, `aruco-msgs`, `aruco-opencv-msgs` (all `ros-humble-` prefixed).
- Cached metadata totals 866152 new download bytes and 7328768 declared
  extracted bytes. Exact versions, hashes and repository paths are saved;
  remote availability is not checked. No download or system installation ran.

Evidence:

- `data/outputs/rtabmap_slam/preflight_20260910/`: `dependency_plan.json`,
  `apt_simulation.log`, four package metadata records and reused archive hashes.

Decision and next action:

- Obtain the requested approval for those four missing packages, then run the
  existing bag through minimal mapping with database/export/TF verification.
  Keep the accepted camera path and `prompt.md` intact; no new recording.

### 2026-09-10: M4 Minimum Mapping Integration And Artifact Acceptance

Status: `VERIFIED` for minimum mapping integration with partial coverage.
Continuous tracking, geometric accuracy, navigation and real-time performance
remain unverified. Advance to M5 under the user's pipeline-first direction.

Changed:

- Downloaded the four approved packages (866152 bytes), checked their pinned
  hashes, paths and potential overwrites, and extracted into the existing user
  workspace. No system installation or maintainer script ran.
- Added `config/rtabmap_rgbd_mapping.yaml`, a mapping checker and eight mapping
  contract tests plus two timestamp-precision tests. Reused the odometry checker
  by sharing its subscriptions, incomplete evidence and bounded entry point.
- Mapping consumes the existing `/odom_rgbd_image` and `/odom` with exact sync.
  The odometry input still enforces 5 ms RGB/depth sync and uses the measured
  prediction-off setting; automatic reset remains disabled. No new sync node.
- Added mapping reproduction/evidence documentation and updated README/current
  task. The next step uses original color frames; the measured odometry bundle
  and database images are grayscale. `prompt.md` and original bags remain intact.

Verified:

- Node startup/interfaces and loaded system OpenCV 4.5d libraries were inspected.
  First CLI startup inspection timed out; direct discovery passed and closed cleanly.
- Second full 0.25x replay: all 1411 CameraInfo pairs/hashes reproduced, 1410
  odometry results, 858 tracked and 552 lost, one final input without a result.
  Observed source-time losses: 18.089477–49.376231 s and 88.771819–94.467266 s.
  All 858 tracked pose/TF pairs passed; 11368 clock messages were observed.
- Mapping published 57 info/graph updates and 7905 map TF messages. Fifty-six
  observations pass the map-to-optical-camera chain at the original source stamp.
  The initial observation is explicitly excluded because map TF starts later.
- Database size 41791488 bytes, 57 stored image/depth/calibration nodes, one map
  ID (0), 48 final optimized graph poses. SQLite integrity check passed. Reopening
  a copy in read-only localization returned the same 48 node IDs and 72 links;
  direct parameter queries confirmed all requested mapping settings. The copy
  was unchanged and the node exited 0.
- Upstream export using stored optimized poses produced 45733 finite points,
  48 robot and 48 optical-camera poses, 48 depth images and a 222 x 138 grid at
  0.05 m/cell. Exported robot poses match the final graph within text precision.
  The input database stayed unchanged; preview PNG/PDF was visually reviewed.
- The upstream RVL decoder/exporter preserved all 921600 pixels of one original
  1280x720 depth frame, including invalid zeros; verified units remain millimeters.
  Initial inspection assumed RGB/PNG storage and failed; that report is retained.
- Six global loop closures and 25 proximity detections were reported by the
  algorithm; these are not independently validated room-loop or accuracy results.
- Odometry processing median/P95/max: 215.34/258.28/301.75 ms. Mapping core update:
  201.17/308.10/495.53 ms. RSS ranges: odometry 151476–331076 KiB, mapping
  172840–405704 KiB; descriptors stayed 19/20, threads 31–36/31–63.
- Player/checker/odometry/mapping all exited 0 in the second run with no forced
  termination; harness time 419.274 s. Final process inspection found no remaining
  experiment or camera process. No long-duration leak or real-time claim.
- Twenty-two focused tests passed (0.096 s). A real ROS no-input measurement
  exited 1, saving `INCOMPLETE` with empty mapping evidence. Full diff and focused
  syntax/whitespace checks were reviewed before the checkpoint.

Preserved failures and limits:

- The first full run's checker rejected mapping stamps rounded through double
  seconds (maximum 218 ns difference). The corrected association allows only two
  timestamp ULPs plus 1 ns, retains both stamps/difference and rejects a 1 us
  offset in the epoch-time test. Odometry stamp equality remains exact.
- The second full measurement passed, but its harness stays `INCOMPLETE` because
  a late CLI mapping-parameter dump returned 1. Direct service queries and map
  reopening resolved the missing metadata check. The local harness now uses the
  tested service helper and saves query logs; it was not fully replayed again.
- Mapping rejects null odometry explicitly and preserves tracking gaps. Partial
  geometry and grayscale output suffice for this integration; source color is
  available for YOLO. This concurrent run is not an isolated performance comparison.
- Learning: a component's measurement, process bookkeeping, persisted artifacts
  and map quality are separate checks. Connect the next component once the
  minimum data contract passes, while keeping every failure visible.

Evidence:

- `data/outputs/rtabmap_slam/preflight_20260910/`: dependency/startup evidence,
  test logs and the real no-input failure.
- `data/outputs/rtabmap_slam/mapping_01/`: preserved first attempt and stamp diagnosis.
- `data/outputs/rtabmap_slam/mapping_02/`: all run/checker logs and implementation
  snapshots, `map.db`, `measurement.json`/CSV, `database_check.json`,
  `depth_source_check.json`, `export_run.json`, `export_check.json`, `reopen/`,
  `integration.json`, preview and final process check. Generated room data is ignored.
- Local run/export/reopen/inspection scripts are in the parent evidence directory;
  reproduction and limits are in `docs/rtabmap-mapping.md`.

Next action:

- Run YOLOv8n on an original color frame with a valid mapped node association,
  combine its detections with depth, and save the first camera/map-frame 3D object
  observation using the frozen final map pose.

### 2026-09-10: Dense Colored Point Cloud With Frozen Map Poses

Status: `VERIFIED` for color point-cloud fusion, source association and offline
interactive viewing. Geometric accuracy and continuous tracking remain unverified.

Changed:

- Followed the user's explicit choice to fuse denser color geometry with existing
  map poses. Added system-ROS frame extraction and native Open3D/Plotly fusion
  scripts, nine focused tests, and reproduction/viewing documentation.
- Reused installed Open3D 0.18.0, Plotly 6.9.0 and Chromium 152. No downloads,
  system installation, camera activation, new recording or odometry run.
- Kept all 48 final optimized optical-camera poses fixed. Generated a full PLY
  and self-contained HTML, with a desktop link named `Room point cloud.html`.

Verified:

- All four source RGB-D/CameraInfo topics reproduce 1411 messages and exact
  reference hashes. Selected image/CameraInfo stamps, registered 1280x720 grids,
  calibration, RGB8 channels and uint16 millimeter depth checks pass. Node IDs
  link frozen poses to the original aggregate source stamps; no rounded-text
  timestamp equality or historical online TF is used for projection.
- All 48 selected depth images match their database exports: 44236800 identical
  pixels, including invalid zeros. Original database and pose-export hashes pass.
- Pixel stride 2 and a 5 m depth limit yield 7191144 valid samples. Open3D
  back-projection, fixed-pose transforms and 2 cm voxel averaging yield 447905
  points; 97.72% have unequal RGB channels. No surface completion or ICP ran.
- The 12093644-byte PLY reads back with exact geometry and color differences
  bounded by half an 8-bit level. The cloud has 9.79 times the previous coarse
  export's point count. Coarse-to-new nearest distances are median 8.62 mm,
  P95 13.56 mm and maximum 30.75 mm; this is consistency, not physical accuracy.
- Extraction exited 0 in 38.69 s with maximum RSS 184748 KiB. Reconstruction,
  PLY checks and HTML generation exited 0 in 18.77 s with maximum RSS 613208 KiB;
  voxel fusion took 1.76 s. These are single offline runs, not a live benchmark.
- Nine known geometry/association/failure tests passed in 0.021 s. Tests cover
  millimeters, optical axes, RGB channel order, a known rotated/translated point,
  sampling origin, invalid/range-limited depth, invalid poses and grid mismatch.
  Final review tightened ambiguous-stamp rejection; all 192 saved selected
  image/CameraInfo associations were rechecked against the final helper.
- Chromium rendered the standalone page with 180000 sampled cloud points and
  48 camera markers. Actual mouse-drag rotation and wheel zoom changed the camera;
  no external page resource requests or severe browser errors were recorded.
  Screenshots were visually inspected. Automation used software WebGL, without
  measuring attached-display frame rate.
- Final database hash remained unchanged and no temporary browser processes
  remained. Python syntax and whitespace checks passed; full diff reviewed.

Limits and evidence:

- The denser color view still shows overlapping surfaces and holes. Existing
  trajectory errors, tracking gaps and partial coverage remain. The first node
  uses its final optimized camera pose; earlier missing online TF is not erased.
- Initial timing wrapper failed before extraction because `/usr/bin/time` was
  absent. Reused Python process timing/resource measurement successfully. A direct
  Chromium binary inspection encountered the host/Snap glibc mismatch; its
  installed Snap launcher worked. No new dependency was required for either.
- `data/outputs/rtabmap_slam/colored_cloud_20260910/` retains the original timing
  failure, successful extraction/reconstruction logs and process measurements,
  full frame/source provenance, cloud comparison, unit tests, HTML/PLY and browser
  evidence. Room data and temporary browser artifacts remain local and ignored.
- Learning: depth plus intrinsics defines each local point cloud; map poses place
  those clouds together, and RGB supplies color. Denser geometry preserves the
  errors in those poses rather than independently correcting them.

Next action:

- Use an extracted original RGB-D frame and its frozen camera pose to produce
  the first YOLO camera/map-frame 3D object observation (M5).

### 2026-09-10: Correct Desktop Point-Cloud WebGL Launch

Status: `VERIFIED` for the dedicated visible Chromium map viewer.

- The user reported unsupported WebGL after opening the previous HTML shortcut.
  Local HTML/default-browser associations are `firefox.desktop`. The previous
  successful automation used explicit Chromium software-rendering flags; it did
  not establish that the default desktop opening path worked.
- Added `scripts/view_colored_cloud.py`, using installed Snap Chromium in a
  separate `~/snap/chromium/common/room-cloud-viewer` profile. Opens only an
  existing local HTML path in an application window with ANGLE/SwiftShader.
  The software-rendering opt-in is limited to this trusted local map profile;
  no browser sandbox-disabling flag or default-browser change is used.
- Replaced the exact previous HTML symlink with a validated, trusted desktop
  application launcher named **Room point cloud**. Updated README and viewing
  instructions. No package download, point-cloud regeneration or camera activity.
- Visible desktop testing reported WebGL 2.0 and the SwiftShader renderer,
  displayed 180000 points, and passed real mouse-drag rotation and wheel zoom.
  Screenshots were inspected; no severe browser errors or external page resource
  requests were reported. The test browser/driver closed, then the actual local
  launcher opened the map for the user; the dedicated window was left running.
- Missing HTML input exits 2 explicitly. Python syntax, desktop-file validation
  and whitespace checks pass. Complete diff reviewed. The PLY hash is unchanged.
- Evidence: `data/outputs/rtabmap_slam/colored_cloud_20260910/desktop_webgl_fix/`
  contains the headed browser check, screenshots, desktop file and trust/launch
  evidence, previous shortcut target and final verification. An initial process
  check missed Chromium's space-delimited process title; corrected inspection
  confirmed its dedicated profile, local map URL and software-rendering flags.
- Learning: a browser rendering test must reproduce the user's actual launch
  path and graphics backend. A headless test alone did not verify this desktop.

Next action:

- Inspect the point cloud in the corrected desktop viewer before resuming M5.

### 2026-09-10: Native PLY Viewing And File Association

Status: `VERIFIED` for native PLY loading and the user-level file association.

- The user requested easier point-cloud viewing, then confirmed the Open3D view
  looked acceptable. Reused installed Open3D 0.18.0's `open3d draw FILE` command.
  The application selected OpenGL, reported successful PLY loading, created an
  Open3D desktop window and exited 0. No download or custom viewer code was added.
- Registered `model/ply` for `*.ply` under the user's MIME directory and associated
  it with `jetson-open3d.desktop`. Replaced the prior browser desktop launcher
  with a **Room point cloud.ply** symlink to the existing complete colored cloud.
- Desktop-file validation and GIO handler resolution pass. The PLY hash remains
  unchanged; plain-text files still use gedit and HTML still uses Firefox.
  Updated viewing documentation and reviewed the complete diff/whitespace check.
- Evidence: `data/outputs/rtabmap_slam/colored_cloud_20260910/native_ply_viewer/`
  contains the user confirmation, successful native command/exit record,
  application/MIME registration copies and `association_check.json`.
- Limits: the native window closed before a requested screenshot could be taken;
  visual acceptance comes from the user's report. Native mouse interaction and
  frame rate were not benchmarked. Map quality claims remain unchanged.
- Learning: a standard PLY file plus an existing native viewer and file association
  provides a simpler desktop workflow than a browser-dependent visualization.

Next action:

- Resume M5: produce the first YOLO object observation in camera/map coordinates.

### 2026-09-10: M5 First RGB-D Camera/Map Object Observations

Status: `VERIFIED` for minimum offline integration. Detection accuracy,
instance identity, physical position accuracy and live performance remain
unverified. Advance to M6 under the user's pipeline-first direction.

Changed:

- Added `scripts/observe_rgbd_objects.py` for local YOLO inference, bounded
  inner-ROI depth filtering, metric camera/map surface points, source/pose checks,
  explicit rejection records and PNG annotations. No dependency was added.
- Extracted existing intrinsics/pose checks into `scripts/rgbd_geometry.py`, used
  by both object observations and the existing point-cloud projection. Added
  12 focused tests and `docs/rgbd-object-observations.md`; updated README/state.

Verified on this Jetson:

- Reused original RGB8/registered uint16 depth from `colored_cloud_20260910/frames`
  and frozen final camera poses from `mapping_02`. All selected grids are
  1280x720, depth is millimeters with invalid zeros. Database, exported pose and
  NPZ hashes matched. Original source stamps/CameraInfo were checked; no pose
  association relied on rounded timestamp-text equality.
- Existing YOLOv8n weights were 6549796 bytes, SHA256
  `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`.
  Runtime reported PyTorch 2.8.0, Ultralytics 8.4.112, OpenCV 4.11.0 and GPU
  `Orin`. The initial sandbox CUDA probe failed with `NvRmMemInitNvmap`;
  authorized GPU access passed a tensor operation and actual inference. Offline
  mode was enabled, with no download, installation or CPU inference fallback.
- Nodes 7/14/32 produced respectively 7/6/5 detections and 5/5/5 accepted
  observations. RGB/depth skews were 2.972/3.398/3.216 ms. Two detections had no
  valid inner-ROI depth; one was rejected for 0.649 m inlier P90-P10 spread.
  Rejected detections contain neither camera nor map points.
- Example node 7 refrigerator: confidence 0.9371328354, pixel `[524,540]`,
  source stamp `1789080208207783000` ns, raw depth 4607 mm. Camera point
  `[-0.676296,1.253994,4.607000]` m; map point
  `[4.677179,0.829901,-0.809701]` m. Its inner ROI was 82.65% valid, with
  0.127 m inlier P90-P10 spread. This is a sampled surface point, not an object
  center or a physical reference measurement.
- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest discover
  -s tests/mapping -v`: all 21 tests passed (12 new plus nine point-cloud
  regressions). Syntax compilation of the three affected scripts passed.
- Independent Open3D 0.18.0 camera/map projection checked all 15 selected source
  pixels; maximum per-coordinate difference was 2.2506714e-7 m. All three PNGs
  read back at 1280x720. A real node-1 CLI attempt exited 1 for missing validated
  source-time map association before creating output or loading the model.
- The bounded GPU process exited 0 in 17.826 s without timeout, peak child RSS
  1250468 KiB. Prediction calls took 8121.49/64.56/49.32 ms; processing including
  geometry/drawing took 8226.27/77.59/65.37 ms, excluding PNG writing. Across the
  three processing samples min/median/P95/max were
  65.37/77.59/7411.40/8226.27 ms. First-call initialization was included and
  there was no explicit warmup. This is not a steady-state/concurrent benchmark
  or a long-duration resource-leak check.
- Inspected all three annotations. Node 7 contains overlapping chair detections;
  node 14's laptop box includes a paper-towel roll and node 32's oven box covers
  cabinet furniture, indicating likely semantic errors. Fifteen accepted
  observations do not establish 15 distinct objects. Depth gates cannot resolve
  these errors or guarantee that every chosen pixel belongs to the labeled object.
- Review consolidated inference settings so execution uses the same values
  recorded in JSON. Final `trial_02` exited 0 in 11.654 s, peak child RSS
  1253916 KiB; its complete report exactly matched `trial_01` except timing
  fields. All 21 focused tests passed again. The full seven-file diff was
  reviewed; whitespace and script compilation checks passed. Only code, tests
  and documentation are staged, with room artifacts and weights ignored.

Evidence:

- `data/outputs/object_observations/m5_20260910/`: `preflight.json`,
  `unit_tests.log`, `trial_01.log`, `trial_01_process.json`,
  `trial_01/observations.json`, `trial_01/node_{7,14,32}.png`,
  `verify_artifacts.py`, `artifact_verification.json`, `rejected_node_1.log` and
  `visual_inspection.json`. Final rerun evidence is in `trial_02/`,
  `trial_02_process.json`, `repeat_comparison.json` and `final_unit_tests.log`.
  Room data, weights and generated outputs remain local
  and ignored. No new capture, trajectory estimation or parameter sweep ran.

Learning: a detection box, actual valid depth pixel, calibration and correctly
associated map pose now produce one inspectable metric observation. Semantic
correctness, geometric validity and persistent object identity are separate.

Next action:

- Build minimal SQLite object memory from these observations, retaining source
  and association evidence and verifying idempotent import plus reopened queries.

### 2026-09-10: M6 Persistent SQLite Memory And Reopened Queries

Status: `VERIFIED` for minimum offline evidence persistence, deterministic
association and reopened label queries. Object identity/accuracy, covariance-aware
fusion, live scaling and navigation remain unverified.

Changed:

- Added `scripts/scene_memory.py`: four SQLite tables retain producer/map
  identity, original frame/detection evidence, provisional objects and every
  association decision. Reused the existing source-time helper and native
  environment; SQLite is standard-library functionality. No dependency was added.
- Added 17 focused SQLite/association tests and `docs/scene-memory.md`. Updated
  README and current state; advanced the next task to an offline M9 search-goal
  preview under the user's pipeline-first priority. M7/M8 remain planned.

Verified on this Jetson:

- Imported `object_observations/m5_20260910/trial_01/observations.json`, SHA256
  `35c7738441daeaf665e0e725508bc2f13a6846cc0ca3dbef03d90eec32d821ec`.
  Its three frames (7, 14, 32) retain all 18 detections. Thirteen representatives
  support nine provisional objects: nine new-object and four cross-frame-match
  decisions. Two same-frame overlapping detections add no support; three depth
  rejections retain null object associations. Source hashes, poses, calibration,
  timestamps, labels, confidence, boxes and depth evidence remain in the database.
- Same-frame overlap uses same label, at most 0.35 m point distance and at least
  50% intersection over the smaller box, selecting higher detector confidence
  first. Other representatives match the nearest same-label object within
  0.35 m, at most once per object per source frame. Positions are equal means
  of representatives; detector confidence remains a separate mean. No physical
  uncertainty or confirmed identity is fabricated.
- Native `memory.db` is 49152 bytes, SHA256
  `e2bf8d7db3902ded408c6a11006ab2135de654ecd11e76bee702468f6f41f3c0`.
  Integrity check returned `ok`; foreign-key check reported zero violations.
  All retained source evidence matched M5. All nine object means matched
  independently calculated source means, with at most one support per frame.
- Fresh CLI processes reopened the database for `list`, `find refrigerator`,
  `last_seen refrigerator` and `find backpack`. The last query returned
  `NOT_FOUND` with no fabricated location. Refrigerator object 1 has three
  supports and mean map point `[4.675447,0.911362,-0.794313]` m, mean detector
  confidence 0.921856, first source time `1789080208207783000` ns and last source
  time `1789080265488456000` ns. Last observation evidence points to node 32.
- Read-only queries and two duplicate imports (the original report and M5's
  second timing-variant run) left the database byte-identical. Importing nodes
  32/14/7 in separate reversed batches produced the same complete logical SQL
  dump. Canonical evidence ignores only runtime timing/first-call fields and
  annotation filenames; conflicts on an existing node/source stamp fail.
- Thirteen measured CLI processes included ten successful import/query commands
  and three expected failures: incompatible pose identity, incomplete report,
  and missing database. The first two left the database unchanged; the missing
  database query created no file. Final code passed another fresh import,
  reopened refrigerator query and duplicate import with the same logical dump.
- All 17 memory tests passed, covering label/distance gates, equal means,
  duplicate support prevention, query ties, incompatible identities, unsupported
  schemas, source-conflict rollback and an actual SQLite write-failure trigger.
  The 21 existing mapping/observation tests also passed. Script compilation and
  whitespace checks passed; no camera, ROS replay or GPU inference was needed.
- Reviewed the complete five-file diff for duplicated configuration, failure
  handling, generated data and unsupported claims. The final read-only query
  uses a single snapshot, and the schema version has one code definition.
- Runtime: Python 3.10.12, SQLite 3.37.2, aarch64. Initial import operation was
  29.850 ms; ten subsequent successful mixed import/query operations had
  min/median/P95/max 1.780/6.701/20.847/21.135 ms. All 13 CLI wall times had
  min/median/P95/max 508.219/522.186/544.231/555.822 ms, including Python/dependency
  startup. These selected three-frame functional timings are not a throughput
  or scaling benchmark.

Evidence:

- `data/outputs/scene_memory/m6_20260910/`: `memory.db`, `first_import.json`,
  `list.json`, `find.json`, `last_seen.json`, `associations.json`,
  `integration.json`, `verify_memory.py`, CLI failure logs, `split_order.db`,
  `final_check.json`, `final_check.db`, `final_unit_tests.log` and
  `mapping_regression.log`. Room evidence and SQLite outputs remain local and
  ignored; only code, tests and measured documentation belong in Git.

Limits and decisions:

- Nine provisional candidates do not establish nine distinct real objects.
  M5's likely laptop/oven errors remain recorded; chair identity is unconfirmed.
  Distance/overlap gates can still merge or split real instances incorrectly.
- Each new import rebuilds derived associations from retained evidence in source
  order. This gives deterministic results for the small offline corpus. IDs are
  stable for repeated identical evidence, but older added evidence may renumber
  them; live scaling and permanent external identifiers are not implemented.

Learning: persistent memory must preserve the distinction between raw detections,
independent source-frame support and provisional object identity. A durable query
can now retrieve the evidence and location after the processing program exits.

Next action:

- Connect remembered object candidates to an offline search-goal preview using
  the existing occupancy map, with explicit map-cell checks and no robot motion.

### 2026-09-10: M9 Offline Object Search Goal Preview

Status: `VERIFIED` for minimum offline memory-to-goal integration and explicit
no-goal outcomes. Route, visibility, localization, physical footprint and
traversability remain unverified.

Changed:

- Added `scripts/preview_search_goal.py`, reusing the existing read-only memory
  query and file-hash helper. Added 16 focused tests and
  `docs/search-goal-preview.md`; updated README and canonical current state.
  Existing native NumPy/OpenCV/SciPy/Matplotlib/PyYAML dependencies suffice.
- Retained each queried provisional object, source times/support/confidence,
  last observation, map location, memory identity and frozen map/pose hashes.
  Saved per-object decisions and PNG overlays; unknown labels have no invented
  location. Inputs are read-only and output directories cannot be overwritten.

Verified on this Jetson:

- The saved occupancy export is 222x138, 0.05 m/cell, origin
  [-4.575,-3.59134,0] (x/y/yaw). PGM top-row order was reconciled with installed
  ROS bottom-left grid-origin/cell-corner definitions. Negate zero, free
  threshold 0.196 and occupied threshold 0.5 give 1122 free (254), 6379 occupied
  (0), and 23135 unknown (205) cells. Nonzero origin yaw and unsupported image
  types/modes fail explicitly. Unknown/occupied/outside areas block clearance.
- SHA256 identities match memory and the prior frozen export evidence:
  memory `e2bf8d7db3902ded408c6a11006ab2135de654ecd11e76bee702468f6f41f3c0`;
  map DB `77ce256f9ac9a6ae443a559a4d074e7a743de8f8724fb6ceebe03aecee79fa3e`;
  camera poses `a47b2d71b6a4da402a42ec7c9b3e455767af876f172d830cee6159b9622c2c3b`;
  PGM `8e78dd53911b8137bb0e5580bdd86c1ba37572b13da9d9ed3e4ff684d878e20b`;
  YAML `7e47b94090c34765d4a9dac4ead6426e14e1f54e93edaaef8145eabf9507adc3`.
  Original memory, map, export files and evidence manifests were byte-identical
  before/after the integration runs.
- The initial fixed policy uses horizontal stand-off 0.75–1.25 m, preferred
  1.0 m, and 0.25 m clearance. It was chosen before observing goal outcomes.
  Padded distance-to-non-free-center minus half a cell diagonal conservatively
  bounds clearance to blocked cell areas; 168 cells pass globally. Rank by
  preferred stand-off error, then larger clearance, then grid y/x.
- Refrigerator object 1 has 1259 cells in its band: zero free, 373 unknown,
  886 occupied. It returns `NO_GOAL: no_free_cells_in_standoff_band` without
  altering the policy. Sink object 7 has 140 free cells in its band, none with
  sufficient clearance: `NO_GOAL: insufficient_map_clearance`. Missing
  `backpack` returns `NO_GOAL: target_not_in_memory`, with no object or goal.
- Both chair objects remain separate provisional candidates. IDs 2/3 have
  367/369 free cells in their bands and 94 clearance-passing cells each. Both
  select grid [114,84], map x/y [1.15,0.63366] m. Stand-offs are
  0.998861/0.999012 m and yaw -1.299565/-1.269940 rad. Each retains two
  supporting frames and first/last times 1789080208207783000 /
  1789080265488456000 ns. The shared goal does not resolve object identity.
- Independently indexed original PGM pixel [114,53] is free. Cell-center metric
  coordinates and facing yaw agree. An exact distance check against every
  blocked cell square and map boundary gives 0.257391 m; the script's lower
  bound is 0.256192 m. This verifies grid computation, not physical clearance.
- Six fresh CLI runs completed within the 45-second per-process limit. Five
  normal runs covered refrigerator/chair/sink/backpack and repeated chair
  selection; decisions were identical on repetition. A copied memory with a
  deliberately incompatible pose hash failed with exit 1 and `INCOMPLETE`,
  without any goal or PNG. Normal no-goal outcomes exit zero. Generated PNGs
  decoded, and both chair plus refrigerator/sink overlays were inspected.
- All 16 search tests and 17 memory regression tests pass. Coverage includes
  image direction, metric/grid boundaries, strict threshold equality, unknown
  cells, obstacle areas/corners, outside-map clearance, unique/tied selection,
  invalid targets, insufficient free space and changed/incomplete provenance.
- Reviewed the complete five-file diff for scope, coordinate/identity contracts,
  failure behavior, duplicated policy and generated data. Script/test compilation
  and staged whitespace checks passed; `final_check.json` records the reviewed
  source identities and saved verification evidence.
- Runtime: Python 3.10.12, NumPy 1.26.4, OpenCV 4.11.0, SciPy 1.15.3,
  Matplotlib 3.10.9 and PyYAML 6.0.3 on aarch64. Five successful mixed
  query/render operation times have min/median/P95/max
  1308.761/1771.175/2753.912/2762.452 ms, including hashing/PNG writing.
  Process wall times are 2123.970/2573.909/3628.249/3628.538 ms, including
  dependency startup. These are functional timings on the small frozen corpus,
  not steady-state throughput or navigation benchmarks.

Evidence:

- `data/outputs/search_goal/m9_20260910/`: `integration.json`,
  `verify_preview.py`, `verification.log`, `unit_tests.log`,
  `memory_regression.log`, `final_check.json`, per-query CLI logs and `preview.json`/PNG outputs
  in `refrigerator`, `chair`, `sink`, `backpack`, `chair_repeat`, and
  `incompatible_pose`. The deliberately changed SQLite copy is local evidence.
  Room data and generated outputs remain ignored.

Limits and learning:

- The export contains little usable free space, and saved surface means do not
  establish object centers or floor height. Tracking gaps, likely class errors,
  unresolved chair identity and map accuracy remain unchanged. No camera, ROS,
  GPU inference, Nav2 or motion was required. No dependency was downloaded.
- An object location and an observation position are different quantities.
  Memory can supply the former while the occupancy map refuses the latter.
  Passing local cell checks does not prove a route or target visibility.

Next action:

- Validate an offline grid route from an explicit, provenance-labeled start to
  an existing candidate goal, preserving invalid-start/no-route outcomes.

### 2026-09-11: M9 Offline Route Validation From Explicit Starts

Status: `VERIFIED` for minimum offline grid routes and recorded-start refusal.
Physical navigation, current localization, target visibility and floor/map
accuracy remain unverified.

Changed:

- Added `scripts/preview_search_route.py`, reusing the memory query, goal
  selection, map decoding, conservative clearance and frozen identity checks.
  The saved goal preview is revalidated against memory and the actual export
  before its decisions can be consumed by the planner.
- Added 16 route/start tests and `docs/search-route-preview.md`. Extended the
  existing renderer with an optional explicit start/path overlay, linked the
  preceding goal guide, and updated README and canonical state. No new
  dependency or model was required; existing native Python/NumPy suffices.

Verified on this Jetson:

- The unchanged 222x138 occupancy grid has 1122 free cells in 76 four-connected
  components. Its existing 0.25 m conservative clearance mask has 168 cells
  in one component. All 48 frozen camera translations project into unknown
  cells; none is a valid start under the current grid policy.
- Camera node 1 retains map x/y [-0.002109,-0.03223] m, cell [91,71], and
  original source time 1789080202178160000 ns. Its projected camera position,
  full original translation/quaternion and pose-file hash remain recorded.
  Both chair candidates return `INVALID_START: unknown_cell`, with no path
  or cost. No recorded pose is snapped into the nearby free component.
- The simulated fixture [1.65,0.08366] m was explicitly selected as the
  lowest-y, then lowest-x clearance-passing cell, [124,73]. It is labeled
  `simulated_grid_fixture` and has no fabricated observation timestamp or
  robot-localization claim. Both chair IDs 2/3 reach the saved goal
  [1.15,0.63366] m through 22 grid cells / 21 cardinal edges, length 1.05 m.
  Each search expands 163 cells. IDs, supports, object means, source times
  and the separate goal-facing yaw values remain in the source preview.
- Breadth-first search uses fixed-order four-direction neighbors and equal
  edge cost. Unknown/occupied/outside cells block clearance; there are no
  diagonal moves or smoothing. The exact start point is retained, with an
  explicit x-then-y connection to its cell center when needed. Each connection
  and grid edge checks its entire segment against blocked cell squares and
  the map boundary. Minimum segment clearance is 0.257391 m.
- Independent checks use original PGM rows, free-cell membership, endpoint
  coordinates, cardinal adjacency and metric length. Length meets the 1.05 m
  Manhattan lower bound for this pair. Point-to-square distances sampled at
  no more than 2.5 mm spacing, minus half the sampling interval using the
  distance function's Lipschitz bound, certify at least 0.256141 m continuous
  clearance. This exceeds the assumed 0.25 m but does not verify real space.
- Eight fresh route CLI processes completed within a 45-second per-command
  bound. Six normal runs cover the recorded start, simulated chair start and
  repetition, plus refrigerator/sink/backpack no-goal propagation. Repeated
  route decisions are identical apart from measured planning time. Two
  deliberately altered preview copies (goal coordinate and pose-export hash)
  fail with exit 1 / `INCOMPLETE`, producing no path or PNG.
- The initial independent verifier used a chained comparison that canceled
  its intended upper-bound floating-point tolerance. Its `INCOMPLETE` report
  and traceback are retained. Correcting only that assertion and rechecking
  the saved CLI artifacts passed; the route implementation stayed unchanged.
- All 32 search tests pass: 16 original goal regressions and 16 new route/start
  tests. They cover known shortest paths, a required detour, occupied/unknown
  barriers, diagonal corners, segment interiors, boundaries, exact-start
  connectors, zero-length paths, invalid endpoints, deterministic results and
  timestamp/map provenance disagreement. A separate original goal-preview
  CLI returns unchanged candidates/decisions after the renderer extension.
- Input memory, map database, PGM/YAML/poses, mapping check/export manifest
  and all four original goal reports remain byte-identical. Input hashes
  are recorded in `integration.json`; database and export identities remain
  those in the preceding M9 ledger. Generated PNGs decode and route/refusal
  overlays were visually inspected.
- Reviewed the complete seven-file diff for minimal scope, reused policy,
  whole-segment geometry, source contracts, explicit failures and measured
  claims. Script/test compilation and staged whitespace checks passed;
  `final_check.json` records reviewed source identities and the goal regression.
- Native runtime: Python 3.10.12, NumPy 1.26.4, OpenCV 4.11.0 on aarch64;
  existing SciPy/Matplotlib/PyYAML provide reused grid/rendering operations.
  The first two successful path searches took 307.954/307.605 ms. Across six
  successful mixed route/refusal/render commands, operation-time
  min/median/P95/max was 1236.469/2493.287/3353.786/3354.477 ms. Wall-time
  min/median/P95/max was 2022.933/3300.157/4177.882/4179.149 ms, including
  interpreter/dependency startup. These are functional measurements on the
  frozen map, not steady-state performance or live navigation acceptance.

Evidence:

- `data/outputs/search_route/m9_20260911/`: `preflight.json`,
  `integration.json`, `integration_initial.json`, `verify_routes.py`,
  `verification.log`, `verification_initial.log`, `unit_tests.log`, `final_check.json`,
  per-command logs, `camera_node_1/`, `simulated_chair/`,
  `simulated_chair_repeat/`, `refrigerator/`, `sink/`, `backpack/`,
  `changed_goal/`, `changed_identity/` and `goal_regression/` JSON/PNG outputs.
  Deliberately changed preview copies and all room evidence remain ignored.

Limits and learning:

- Actual camera starts are invalid in this occupancy export. The simulated
  path verifies the planning interface only; physical footprint, floor/map
  accuracy, current localization, visibility, turning and traversability are
  unverified. Partial tracking and provisional object identity remain unchanged.
- A remembered location, an observation goal and a route from an explicit start
  are separate outputs. Segment checks extend endpoint checks but do not turn
  a frozen map or simulated start into verified robot navigation.

Next action:

- Add an offline geometric frontier-search fallback when memory lacks the
  target or the object-goal preview cannot supply a usable observation goal.

### 2026-09-11: M10 Offline Geometric Frontier Search Fallback

Status: `VERIFIED` for minimum offline exploration proposals/refusals after
missing-target or unavailable-object-goal outcomes. No observation, new coverage,
physical visibility or navigation acceptance is claimed.

Changed:

- Added `scripts/preview_frontier_search.py`, reusing frozen goal/memory/export
  validation, explicit recorded/simulated starts and existing route checks.
  The original query candidates and no-goal reasons remain in the output;
  geometric exploration is a separate proposal, not a fabricated object location.
- Added 16 frontier tests and `docs/frontier-search-preview.md`. Extracted the
  shared occupancy backdrop and cardinal directions for their new real callers,
  without changing the previous goal or route policies. Updated the route guide,
  README and canonical current state. No dependency or model was added.

Verified on this Jetson:

- The frozen map contains 102 free cells with in-map cardinal unknown neighbors,
  forming 70 four-connected frontier groups. Independent queue/set grouping
  from the original PGM reproduces every cell, group and deterministic ID.
  Occupied/outside/diagonal-only adjacency does not create a frontier.
- None of the frontier cells passes the preceding 0.25 m clearance policy.
  The existing 168 clearance-passing free cells produce 123 cardinal viewing
  rays at 115 distinct observation cells with the initial 0.30–0.75 m distance
  to the frontier cell center. Rays remain in free cells through the frontier;
  the next cell is unknown, and any earlier unknown/occupied/outside cell stops
  the ray. This is an explicit zero-width planar visibility assumption, not a
  calibrated camera field-of-view or measured information gain.
- Candidates rank by straight-line start displacement, frontier ID, goal y/x
  and frontier y/x. The first route-valid candidate is returned, with any route
  rejections retained. Ranking does not optimize global path cost or semantic
  relevance. No object goal or clearance rule was relaxed to produce a proposal.
- The original explicit M9 simulated start [1.65,0.08366] m selects its own
  cell [124,73], viewing group 39 at frontier [124,64] and first unknown
  [124,63]. Ten free ray cells span 0.45 m to the frontier; yaw is -pi/2.
  Route length is approximately 5.13e-16 m from floating-point cell-center
  representation, effectively an in-place observation proposal. Start heading
  is unknown; no measured turn or physical movement is inferred.
- A second explicit simulated fixture [1.05,0.13366] m, cell [112,74], was
  selected as the first clearance-valid cell in y/x order with no viewing
  candidate of its own, to exercise routing. It reaches [1.05,0.18366] m,
  cell [112,75], over 0.05 m and faces -X (yaw pi) toward frontier group 49,
  cell [106,75], with unknown neighbor [105,75]. Seven free ray cells span
  0.30 m to this frontier. Both selections need one route attempt.
- Selected ray cells, first unknown neighbors, cardinal direction, metric goal
  coordinates/stand-off and route endpoints/free-cell membership match original
  PGM evidence. Exact route clearances are 0.257391/0.275000 m for the two
  fixtures. Independent point-to-square sampling at <=2.5 mm spacing, minus
  half the interval to certify unsampled positions, yields continuous lower
  bounds approximately 0.257391/0.273810 m, both above 0.25 m.
- Nine fresh frontier CLI processes completed within the 45-second per-command
  limit. Seven normal runs cover backpack, refrigerator, sink, repeated
  backpack, the second start, camera node 1 and chair. The first three preserve
  their distinct absent-target/no-free-cell/insufficient-clearance reasons while
  returning the same geometry-only proposal from the same start. Repeated
  exploration decisions are identical apart from timing.
- Camera node 1 remains `INVALID_START: unknown_cell`, with its original
  [-0.002109,-0.03223] m position and no goal. Chair returns
  `NOT_NEEDED: object_goal_available`, preserving both provisional candidates.
  Two deliberately altered source-preview copies, with a changed pose-export
  hash or reduced source clearance, fail with exit 1 / `INCOMPLETE`, producing
  no exploration goal or PNG. Normal decisions/refusals exit zero.
- All 48 search tests pass: 16 frontier tests and the preceding 32 goal/route
  regressions. Coverage includes known boundaries, diagonal/outside/occupied
  handling, first-unknown and obstacle occlusion, range/clearance limits,
  absent/tiny frontiers, disconnected viewing regions, invalid starts and
  deterministic ties. Separate original goal and route CLI regressions return
  unchanged decisions after the shared backdrop/direction edits.
- Input memory, map database, mapping check/export manifest, PGM/YAML/poses
  and all four source goal previews remain byte-identical. Runtime source hashes
  were recorded before the CLI runs. All generated PNGs decode, and both
  exploration proposal overlays were visually inspected. Room outputs stay local.
- Reviewed the complete eight-file diff. Python compilation and staged whitespace
  checks pass. `final_check.json` ties the staged source hashes to the verified
  runtime, confirms unchanged input hashes and records the ignored evidence paths.
- Runtime: Python 3.10.12, NumPy 1.26.4, OpenCV 4.11.0, SciPy 1.15.3 on
  aarch64, with existing Matplotlib/PyYAML. Seven successful mixed frontier/
  refusal/render commands have operation-time min/median/P95/max
  1264.754/1783.776/1827.173/1836.712 ms. Wall-time min/median/P95/max is
  2071.637/2574.809/2623.049/2623.705 ms. Hashing and rendering are included;
  wall time also includes dependency startup. These are functional measurements,
  not a sustained exploration or scaling benchmark.

Evidence:

- `data/outputs/frontier_search/m10_20260911/`: `integration.json`,
  `verify_frontiers.py`, `verification.log`, `unit_tests.log`, `final_check.json`, per-command logs,
  and JSON/PNG outputs in `backpack`, `refrigerator`, `sink`, `backpack_repeat`,
  `backpack_move`, `camera_node_1`, `chair`, `changed_identity`,
  `changed_policy`, `goal_regression` and `route_regression`. Altered source
  previews and all generated room evidence remain ignored.

Limits and learning:

- Actual camera starts still fall in unknown cells. Simulated starts and planar
  rays do not establish current localization, physical clearance, camera
  visibility, new observations or coverage. Tracking gaps, floor/map accuracy
  and provisional semantic identity remain unchanged.
- When object memory cannot supply a usable goal, a separate geometric proposal
  can specify where to look while preserving what is unknown. The same proposal
  for several labels is expected here; semantic exploration is not implemented.

Next action:

- Join the existing goal, route and frontier functions in one reproducible
  offline search-demo command with a single inspectable decision report.

### 2026-09-11: M9/M10 Single-Command Offline Search Demonstration

Status: `VERIFIED` for frozen-memory query, goal, route/frontier composition and
explicit refusals. Live sensor-to-motion integration remains unverified.

Changed:

- Added `scripts/run_offline_search.py`, a thin caller of the three existing
  search functions. It requires memory, map, label and one explicit start;
  object goals select the route branch and no-goal outcomes select frontiers.
  Route failure never silently switches branches. No planner, policy, dependency
  or renderer was changed.
- Added 15 composition tests and `docs/offline-search-demo.md`; updated README
  and canonical state. The top-level `search.json` preserves query candidate IDs,
  original no-goal reasons, per-candidate outcomes and start provenance. Relative
  stage report/PNG paths and completed-report hashes lead to full source evidence.
- Expected input/I/O/database errors are recorded and re-raised; incomplete
  stages remain distinguishable. Existing output directories are refused without
  overwriting them. Observation, motion and new-coverage flags remain false.

Verified on this Jetson:

- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest
  discover -s tests/search -v`: all 63 tests pass in 14.783 s, including the
  preceding 48 goal/route/frontier tests. New tests use real temporary SQLite
  memory and synthetic map files through the actual stage functions; only PNG
  rendering is stubbed. They cover branch choice, all candidate retention,
  invalid starts, disconnected object/frontier routes, absent frontiers,
  source and generated-goal corruption, image-write failure, missing memory,
  start requirements and output preservation.
- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python
  data/outputs/offline_search/demo_20260911/verify_demo.py`: 12 fresh CLI
  processes complete within the 60-second per-command limit. Nine normal
  commands cover chair, backpack, refrigerator, sink, repeated chair/backpack,
  a second simulated backpack start, and camera node 1 for both branches.
- Chair retains provisional IDs 2/3, goal [1.15,0.63366] m, and the original
  1.05 m / 22-cell route from simulated [1.65,0.08366] m. Backpack/fridge/sink
  retain absent-target/no-free-cell/insufficient-clearance reasons and propose
  the same in-place -Y view of group 39. Simulated [1.05,0.13366] m retains
  the 0.05 m route to a -X view of group 49. Full goal decisions and matching
  route/frontier decisions reproduce the preceding measured artifacts.
- Camera node 1 preserves [-0.002109,-0.03223] m and source stamp
  1789080202178160000 ns. Chair returns top-level `NO_ROUTE`, with
  `INVALID_START: unknown_cell` for each candidate; backpack returns
  `INVALID_START`. No relocation or alternate branch hides the failure.
- An isolated memory copy with incompatible pose identity exits 1 with
  `INCOMPLETE` at the goal stage and no branch/PNG. Missing start exits 2 before
  creating output. Reusing the measured chair directory exits 1 and leaves its
  successful earlier reports byte-identical; that prior report is not evidence
  of success for the rejected invocation. All nine completed decisions/refusals
  exit zero.
- Repeated chair/backpack decisions match apart from timing. All input hashes
  remain unchanged, including memory, mapping evidence and prior comparison
  artifacts. The three planning scripts match their M10 verified source hashes.
  All 24 PNGs decode; the chair route, backpack frontier and camera-chair
  refusal overlays were visually inspected. Room evidence remains local/ignored.
- Reviewed the complete five-file diff. Compilation of the new script/test and
  staged whitespace checks pass. `final_check.json` records staged hashes,
  unchanged verified runtime/input hashes, test evidence and ignored outputs.
- Python 3.10.12, NumPy 1.26.4 and OpenCV 4.11.0 on aarch64, with existing
  SciPy 1.15.3, Matplotlib 3.10.9 and PyYAML 6.0.3. Operation-time
  min/median/P95/max across nine normal commands is
  1801.753/2708.615/5378.207/5385.983 ms; process wall time is
  2573.439/3527.471/6185.650/6185.835 ms. Mixed cases include repeated source
  hashing and rendering; wall time also includes dependency startup. These are
  functional timings, not a sustained resource or live throughput benchmark.

Evidence:

- `data/outputs/offline_search/demo_20260911/`: `integration.json`,
  `verify_demo.py`, `verification.log`, `unit_tests.log`, `final_check.json`,
  per-command logs and `chair`, `backpack`, `refrigerator`, `sink`,
  `chair_repeat`, `backpack_repeat`, `backpack_move`, `camera_chair`,
  `camera_backpack` and `changed_identity` outputs. The deliberately altered
  `changed_identity_memory.db` is an ignored copy; original inputs are unchanged.

Limits and learning:

- This combines static search stages without acquiring observations or updating
  memory. Successful routes use explicit simulated starts. Recorded camera
  positions remain unsuitable in the occupancy export; physical footprint,
  map/floor accuracy, visibility and current localization remain unverified.
  Tracking gaps, likely class errors and unresolved chair identity persist.
- A complete search decision includes its evidence and refusal reasons. A
  remembered candidate, a usable goal, a route and an executed observation are
  separate conditions; composing them does not make them physical acceptance.

Next action:

- Replay the saved observations chronologically into a separate memory and use
  the new command to verify how arriving evidence changes the search decision.

### 2026-09-11: M6/M9/M10 Chronological Observation Feedback Replay

Status: `VERIFIED` for saved-evidence arrival, memory snapshots and resulting
search decisions. This is offline replay against final frozen map geometry.

Changed:

- Added `scripts/replay_observation_search.py`, reusing the original observation
  validator, map identity loader, transactional importer and search command.
  It requires the source report, frozen map, label and explicit simulated start.
  Frames sort by source time; each new prefix imports into a fresh copy of the
  closed preceding database. Earlier snapshots are never reopened for writing.
- `replay.json` links original frame times, matching-label depth accept/reject
  evidence, import counts, memory/search hashes and per-prefix search outcomes.
  Errors propagate with an incomplete replay and failing stage/node; completed
  refusals stay explicit. New-observation/motion/coverage flags remain false.
- Added 15 replay tests, reused the existing synthetic search fixture for both
  test classes, and added `docs/observation-search-replay.md`. Existing memory,
  search, planner and renderer runtime code is unchanged. No dependency was added.

Verified on this Jetson:

- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest
  discover -s tests/search -v`: 78 tests pass in 24.520 s. The analogous
  `tests/memory` command passes 17 tests in 0.312 s. New tests exercise real
  temporary SQLite and synthetic maps; only PNG rendering is stubbed. They
  cover chronological transitions, prefix isolation, final full-import
  equivalence, duplicates, rejection-only frames, explicit refusals, source
  corruption, mid-replay failure and output preservation.
- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python
  data/outputs/observation_replay/replay_20260911/verify_replay.py`: 14 fresh
  CLI processes complete within a 90-second per-command limit. These comprise
  eight replay invocations, three duplicate imports and three reopened queries.
  All four normal replays complete their three search prefixes; two source errors,
  missing start and output reuse return expected nonzero exits.
- Original M5 source SHA256 remains
  `35c7738441daeaf665e0e725508bc2f13a6846cc0ca3dbef03d90eec32d821ec`.
  Nodes 7/14/32 retain source stamps 1789080208207783000,
  1789080215242330000 and 1789080265488456000 ns. SQL inspection reproduces
  every normalized original frame/detection, not just aggregate counts.
- At node 7, bottle detection 5 retains `insufficient_valid_depth`, a null
  object association and `NOT_FOUND`. From explicit simulated [1.65,0.08366] m,
  search proposes the existing in-place -Y observation of frontier group 39.
- At node 14, two accepted bottle observations produce provisional IDs 4/6.
  Search changes to `ROUTE_READY`: goals [1.55,0.73366] and [1.70,0.63366] m,
  paths 0.75/0.60 m through 16/13 grid cells. The reused planner reports minimum
  segment clearance approximately 0.257391 m for both. No policy was relaxed.
- Node 32 contains no bottle observation. IDs 4/6 retain one supporting frame
  each, node 14 source times and the same route decisions. New unrelated evidence
  does not fabricate extra support or a new last-seen time for the bottle.
- Prefix counts are 7/13/18 detections, 3/7/9 provisional objects and 3/8/13
  supporting observations. Snapshot sizes are 32768/45056/49152 bytes. They
  contain exactly [7], [7,14] and [7,14,32], pass integrity/foreign-key checks,
  and the final complete logical SQL dump equals the original M6 database.
- Repeated and reversed-input replays produce identical decisions apart from
  timing and byte-identical corresponding snapshots. Three fresh-process
  duplicate imports into separate copies add zero frames and leave hashes
  unchanged. Fresh read-only queries reproduce `NOT_FOUND`/`FOUND`/`FOUND`.
- Explicit simulated [-0.002109,-0.03223] m is refused at every prefix:
  `INVALID_START` first, then `NO_ROUTE` with each candidate `INVALID_START:
  unknown_cell`. Although these values coincide with recorded camera node 1,
  this replay CLI records them as simulated coordinates, not measured localization.
- Altered source copies with incompatible pose identity or inconsistent source
  timestamps exit 1 before imports, leaving no database or PNG. Missing start
  exits 2 without output; reuse exits 1 with prior evidence unchanged. Normal
  replay completion includes explicit search refusals and does not mean discovery.
- All original input hashes and earlier snapshots remain unchanged. All 40
  PNGs decode; the node 7 frontier and both node 14 bottle route overlays were
  visually inspected. Generated snapshots and room evidence remain ignored.
- Reviewed the complete six-file diff. Compilation of the new script and both
  affected test files and staged whitespace checks pass. `final_check.json`
  records staged hashes, unchanged runtime/inputs, frozen prefixes and test logs.
- Runtime: Python 3.10.12, SQLite 3.37.2, NumPy 1.26.4 and OpenCV 4.11.0,
  aarch64. Four completed three-prefix replays have operation-time
  min/median/P95/max 9738.501/11035.504/11060.200/11060.587 ms and process
  wall time 10644.382/11929.296/11954.510/11954.601 ms. These mixed normal/
  refusal cases include imports, copies, source checks and rendering; wall time
  includes dependency startup. No live throughput/resource benchmark is claimed.

Evidence:

- `data/outputs/observation_replay/replay_20260911/`: `integration.json`,
  `verify_replay.py`, `verification.log`, `search_tests.log`, `memory_tests.log`,
  `final_check.json`, per-command logs and `bottle`, `bottle_repeat`,
  `bottle_reversed`, `invalid_start`, `changed_pose`, `changed_stamp` outputs.
  Reordered/altered source copies, three prefix reports and duplicate-import
  copies are local verification fixtures. Original inputs remain unchanged.

Limits and learning:

- The earliest prefix must have an accepted observation of some label under
  the unchanged memory importer contract. A rejection-only first frame fails
  explicitly; later rejection-only frames work in cumulative prefixes. This
  case is covered by tests and is not a cold-start empty-memory implementation.
- Final occupancy and optimized poses are shared by all prefixes. Replayed
  detections were not acquired at selected exploration goals. Tracking, physical
  visibility, floor/map accuracy, provisional labels/identity and current
  localization remain unverified; no observation, motion or coverage is executed.
- Arrival of accepted evidence can change an exploration decision to an object
  route. Freezing each memory prefix preserves what was actually known then;
  repeated imports and unrelated frames must not inflate target support.

Next action:

- Connect the existing RGB-D observation producer to the replay for one offline
  command from saved RGB-D frames to search decisions.

### 2026-09-11: M5/M6/M9/M10 Saved RGB-D To Search, Offline MVP Acceptance

Status: `VERIFIED` for the complete saved-frame perception-to-search pipeline.

Changed:

- Added `scripts/run_rgbd_search_demo.py`, a thin entry to the existing GPU
  observation producer and prefix replay. Explicit inputs are frames, local model,
  node selection, frozen mapping run, label and simulated start. `demo.json`
  links stage reports/hashes/images and the chronological search timeline.
- Validate source/map/model identity, preserve every depth acceptance/rejection,
  propagate failures with incomplete stage evidence, and refuse output reuse.
  No-valid perception exits 2 without replay. Complete search refusals remain
  explicit outcomes. Existing producer, memory, search and renderer code is unchanged.
- Added 14 entry-point tests and `docs/rgbd-search-demo.md`; updated README and
  this playbook with the verified offline finish line. No dependency was added.

Verified on this Jetson:

- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest
  discover -s tests/search -v`: 92 pass in 26.955 s. Analogous `tests/mapping`
  and `tests/memory` runs pass 21 in 0.030 s and 17 in 0.739 s: 130 total.
  New tests stub GPU production/rendering and run real map validation, SQLite
  imports and search. They cover source/model identity, inference/replay errors,
  no-valid observations, first-prefix rejection, source mutation and output reuse.
- GPU preflight and `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python
  data/outputs/rgbd_search/demo_20260911/verify_demo.py` ran with authorized
  native CUDA access. Eleven fresh CLI invocations completed within their
  180-second per-command bounds; six ran actual GPU inference. Five whole demos
  completed: bottle, repeated bottle, chair, backpack and an invalid simulated start.
- Original frames manifest SHA256 remains
  `3dab83691a7db746e6d85d49921c9c951b29dde4eb27428dff64e5917b5487e8`;
  local `yolov8n.pt` remains
  `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`.
  Nodes 7/14/32 retain stamps 1789080208207783000, 1789080215242330000 and
  1789080265488456000 ns. RGB/depth skew is 2.972/3.398/3.216 ms.
- Selected RGB is uint8 1280x720; registered depth is uint16 1280x720 in
  millimeters, where zero denotes invalid depth. Every accepted depth equals its actual source pixel
  divided by 1000. Independent backprojection/map transformation differs by at
  most 8.882e-16 m, an arithmetic check rather than physical position accuracy.
- All five normal fresh perception reports match original M5 detections/depth
  results apart from timing: 18 detections, 15 accepted and three rejected.
  Per-node accepted/rejected counts are 5/2, 5/1 and 5/0. Repeated bottle
  perception and timelines are identical apart from timing.
- Bottle from explicit simulated [1.65,0.08366] m changes from depth-rejected
  `NOT_FOUND`/`EXPLORATION_READY` at node 7 to `FOUND`/`ROUTE_READY` at node 14.
  Candidates 4/6 retain previous 0.75/0.60 m paths and unchanged single-frame
  supports at node 32. Goals/routes match the preceding replay exactly.
- Chair produces `FOUND`/`ROUTE_READY` at all prefixes; absent backpack produces
  `NOT_FOUND`/`EXPLORATION_READY` at all prefixes. Explicit simulated
  [-0.002109,-0.03223] m is refused: `INVALID_START`, then `NO_ROUTE` twice.
  No pose snapping, support inflation or clearance relaxation was introduced.
- Prefix databases contain exactly [7], [7,14] and [7,14,32], pass SQLite
  integrity/foreign-key checks, and retain matching memory/search/stage hashes.
  Final logical memory equals M6, including 18 observations, 13 supports,
  two overlaps and nine provisional objects. Original inputs remain unchanged.
- Synthetic all-zero-depth copies retain original RGB and produce 18 GPU
  detections, all rejected: exit 2, `NO_VALID_OBSERVATIONS`, no replay. These
  marked fixtures are not sensor captures or replacements for original data.
- Incompatible mapping identity exits 1 before perception. Corrupted node 7
  frame hash and node 1's absent validated source-time association exit 1 before
  model loading. Missing start exits 2 without output; output reuse exits 1
  without changing any earlier evidence. All failures match expected outcomes.
- All 66 PNGs decode. Visually inspected all three primary detection annotations,
  node 7 frontier and both node 14 bottle routes. Apparent laptop/oven class errors
  and overlapping chairs remain visible; no label/identity accuracy is claimed.
- Runtime: Python 3.10.12, PyTorch 2.8.0, Ultralytics 8.4.112, OpenCV 4.11.0,
  NumPy 1.26.4, SQLite 3.37.2, aarch64/Orin GPU. Five complete three-frame runs
  have operation-time min/median/P95/max 12.491/18.375/23.037/23.404 s and process
  wall time 14.868/20.722/25.503/25.896 s. These mixed normal/refusal functional
  runs include startup, inference, imports, source checks and rendering; they
  do not establish concurrent throughput, resource bounds or camera lifecycle behavior.
- Reviewed the complete five-file diff. Compilation of all scripts and the new
  test file and staged whitespace checks pass. Final checks tie the staged runtime
  to the GPU acceptance evidence and preserve all original input hashes.

Evidence:

- `data/outputs/rgbd_search/demo_20260911/`: `integration.json`, `verify_demo.py`,
  `verification.log`, GPU preflight JSON/log, search/mapping/memory test logs,
  per-command logs and run artifacts. `final_check.json` records the final
  source/input hashes, syntax/whitespace review and image checks. Room images,
  fault fixtures, weights and databases remain local and ignored.

Limits and learning:

- The first offline pipeline MVP is complete. The full project still needs
  concurrent integration, measured mapping/identity quality, the CuTR feasibility
  gate, open-vocabulary queries and later navigation/edge evaluation.
- The first replay prefix still needs an accepted observation of some label.
  Final poses/occupancy are frozen across prefixes. Actual localization, physical
  visibility and map/floor accuracy remain unresolved; all 48 recorded camera
  starts lie in unknown cells. No live capture, physical motion or new coverage
  was executed. Keep historical tracking failures and `prompt.md` unchanged.
- Accepted depth and preserved source evidence connect a detection to a search
  decision. Python currently orchestrates native/GPU work; concurrent profiling,
  not source-language proportions, should guide any C++ or TensorRT optimization.

Next action:

- Run a bounded concurrent SLAM/perception trial from the existing rosbag,
  measuring timestamp association, queues/drops and Jetson resource use.

### 2026-09-11: M4/M5 Concurrent RGB-D/SLAM And Bounded Scheduling Comparison

Status: `VERIFIED` for same-stream GPU perception and RTAB-Map at 0.25x replay.

Changed:

- Extracted `infer_rgbd` and one shared inference-settings constant from the
  existing offline producer. Detector/depth policy and offline output content
  remain unchanged. Added the concurrent measurement checker, 13 focused tests
  and `docs/concurrent-rgbd-perception.md`. No new dependency or environment was installed.
- The checker reuses the sensor and mapping checks, keeps callbacks separate
  from one GPU worker, and retains all synchronized-pair statuses and pixel hashes.
  The final scheduler allows one pending image and eight completed results awaiting
  source-time TF. Overflow drops the new pair explicitly; pose waits have a
  two-second post-prediction timeout checked by the main loop.
- Online poses are frozen at result finalization using only already received TF.
  Original odometry stamps/loss and TF receipt events remain inspectable. Missing
  poses never produce map points; missing depth never produces camera/map points.

Verified on this Jetson:

- Native `.venv` imports ROS messages/TF, PyTorch 2.8.0, Ultralytics 8.4.112 and
  OpenCV 4.11.0 together. Orin CUDA sum of arange(4) is six; ROS node lifecycle
  passes. The perception process does not import cv_bridge; RTAB-Map keeps its
  separate system OpenCV libraries. Actual library maps/ROS parameters are saved.
- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest
  discover -s tests/odometry -v` after sourcing `scripts/rtabmap_odom_env.bash`:
  35 pass in 27.394 s. The analogous `tests/mapping` run passes 21 in 0.032 s.
  New tests use real synchronization/TF and controlled inference futures to cover
  queue/result bounds, overlap, late/missing/lost poses, corrupt calibration,
  source mismatch, worker failure, immutable finalized poses and incomplete work.
- A fresh native GPU `scripts/run_rgbd_search_demo.py` invocation on original
  nodes 7/14/32 reproduces all 18 detections, 15 accepted depths, three rejections
  and the original bottle search timeline, excluding timings. Its operation time
  is 18.369 s; evidence is `offline_regression` and `offline_regression_check.json`.
- The adapted bounded local `run_trial.py attempt_01` and `attempt_02` each
  replay the full 94.487476504-second bag at 0.25x. Both receive all 1411 image/
  calibration pairs with original serialized hashes and no synchronizer omissions.
  Perception, odometry, mapping and playback all exit 0; the owned tegrastats
  process exits -2 after SIGINT. No forced termination or child PID remains.
  Total supervised wall times are 451.698 and 427.024 s, including startup,
  warmup, measurement, parameter queries, shutdown and input hashing.
- Attempt 1 waits for TF before inference: 618 processed and 793 queue drops.
  Median/P95 prediction is 79.773/98.756 ms; pre-inference waiting median is
  491.399 ms; arrival-to-result median/P95 is 600.078/822.668 ms. It has 482
  accepted and 136 rejected online poses. Exact first-trial runtime and verifier
  snapshots remain archived with the verified baseline.
- Attempt 2 overlaps inference and pose waiting: 1402 processed, nine queue
  drops (0.64%), zero inference failures or unresolved jobs. Event-interval
  reconstruction confirms peaks of one pending image, one GPU job and eight
  pose-waiting results. This reduces the measured scheduling drops without
  unbounded buffering. It does not establish a language-level speedup.
- Attempt 2 median/P95 timings: input queue 7.934/10.397 ms, prediction
  70.483/91.100 ms, prediction-plus-depth 87.247/117.748 ms, post-prediction
  pose wait 397.804/1110.800 ms, total arrival-to-result 501.363/1222.399 ms,
  callbacks 5.143/18.809 ms. Total P95 is higher than attempt 1; frame populations
  differ because more inputs are retained. Maximum pose-wait threshold overshoot
  is about 15 ms. No uniform latency improvement is claimed.
- Final perception has 5022 detections: 3832 accepted camera depth points,
  1190 explicit depth rejections and 3434 map-localized observations. Its 1109
  accepted online poses coexist with 293 refusals: 272 tracking losses, 13 source
  odometry timeouts and eight unavailable source map transforms.
- Independent `verify_trial.py attempt_02` rereads original decompressed image
  bytes and verifies every selected pixel hash/raw depth. Rebuilding TF using only
  events received by each finalization cutoff reproduces accepted poses exactly.
  Independent camera/map arithmetic differs by at most 8.882e-16 m. This checks
  source association and units rather than physical accuracy.
- Odometry processes 1410 inputs: 1138 tracked, 272 lost and one source without
  an output. Mapping stores 76 database nodes, retains 64 final graph poses and
  has 75 checked source-time map observations. SQLite integrity passes. Attempt 1
  tracked 1141 frames; no improved tracking-quality claim is made.
- Final perception/odometry/mapping RSS peaks are 1321688/335084/441476 KiB.
  Perception CPU median/P95 is 62.28/70.82% of one core, including native work
  and measurement; odometry is 92.57/103.62%. Whole-device tegrastats RAM peaks
  at 3951 MB, swap at 249 MB, GPU temperature at 53.875 C and module power at
  7451 mW. GPU load median/P95 is 43/98%. There are 381 simultaneous resource
  samples. These include startup/shutdown and do not prove long-term leak freedom.
- Original bag, weights and mapping_02 database hashes remain unchanged. Both
  runs retain actual parameters, library maps, commands and local resource logs.

Evidence:

- `data/outputs/concurrent_rgbd/trial_20260911/`: shared harness/verifier,
  `attempt_01` and `attempt_02` reports, runtime snapshots, parameters, resources,
  test logs and offline regression. Initial 43-test discovery included ten duplicate
  imported tests; the import was corrected before the final 35-test suite, which
  includes two added overlap/result-capacity cases. Earlier logs are retained.

Limits and learning:

- Slowed recorded playback is not live capture or real-time acceptance. Tracking,
  physical geometry, floor alignment, labels/identity and navigation remain
  unverified. The checker has no live memory/search integration and never revises
  old observations with later TF. Records accumulate for a bounded trial; this is
  measurement tooling, not an indefinite production service.
- The measured bottleneck was waiting for SLAM before permitting inference.
  Overlapping those stages removes most queue drops without a C++ rewrite.
  Native/GPU work, ingestion costs and pose availability must be profiled separately.

Next action:

- Finalize the new concurrent run's map and camera observations into a separate
  frozen scene memory and matching search preview, preserving both pose versions.

### 2026-09-11: M5/M6/M9 Concurrent Observations Finalized Into New Map Memory

Status: `VERIFIED` for frozen post-run observations, persistence and matching-map
search using the newly measured concurrent run, without rerunning inference.

Changed:

- Added `scripts/finalize_concurrent_observations.py` and 12 focused tests.
  The finalizer reuses mapped-frame loading, depth estimation and memory
  validation; existing inference, memory schema and search policies are unchanged.
- Exact source timestamps select exported nodes. Run/measurement verification,
  source pixels, calibration, model, map/pose identity and raw-depth results must
  agree. Every selected detection/rejection is preserved. Accepted camera points
  are reprojected with final optimized poses; original online poses, points and
  result completion times remain separately inspectable. Missing source/online
  evidence is explicitly excluded. Mismatches leave an incomplete report; existing
  outputs are refused. Added reproduction/results documentation and README status.

Verified on this Jetson:

- Existing local RTAB-Map database/export/check helpers complete successfully on
  `data/outputs/concurrent_rgbd/trial_20260911/attempt_02`. SQLite integrity passes
  with 76 stored nodes. Export has 64 optimized camera/robot poses, 50,537 grayscale
  points, 64 decoded depth images and a 223 x 140 grid at 0.05 m. Grid counts are
  1,422 free, 6,064 occupied and 23,734 unknown. Final poses match the final graph;
  the original database hash remains unchanged.
- Existing `extract_mapped_rgbd.py` retrieves all 64 original RGB-D frames. All
  58,982,400 raw depth pixels equal exported depth; original RGB is retained in
  place of database grayscale. Both are on the verified 1280x720 color grid,
  RGB uint8 and depth uint16 millimeters with zero invalid.
- First finalization completes in 29.367 s: 62 selected nodes, 252 detections,
  189 accepted depths and 63 depth rejections. Excluded node 1 has no accepted
  online source map TF; node 44's inference was queue-dropped. Later final poses
  do not erase those original exclusions. No YOLO inference is rerun.
- Independent raw-pixel projection agrees within 8.882e-16 m per coordinate.
  Accepted points shift from online to final map positions by median 0.022823 m,
  P95 0.081945 m and maximum 0.157852 m. This measures pose-version correction,
  not physical accuracy. Reversing that field replacement exactly reproduces
  every original selected detection; source poses/times are also unchanged.
- New SQLite import takes 128.575 ms and stores 62 frames/252 observations.
  There are 46 provisional records supported by 185 observations: 46 new-record
  decisions, 139 nearest matches, four same-frame overlaps without additional
  support and 63 unlocalized depth rejections. These are not 46 verified objects.
- Fresh-process bottle query returns six candidates (IDs/supports
  13/8, 38/2, 4/13, 3/5, 29/1, 14/1); chair returns four (10/16, 11/12, 30/1,
  28/1); backpack is absent from memory. Repeated finalization is identical
  except elapsed time. Duplicate import adds zero frames and leaves memory
  byte-identical. Reopened SQL integrity/foreign keys and complete stored frame
  evidence pass independent checks.
- The new grid has 186 free cells passing the assumed 0.25 m clearance.
  The explicit simulated start [1.5,0.43366000000000016] m is selected by maximum
  conservative clearance, with y/x tie ordering; clearance is 0.523662 m.
  All six bottle candidates have routes of 0.15-0.55 m and all four chair
  candidates have routes of 0.15-0.45 m. Backpack uses the geometric frontier
  branch with `EXPLORATION_READY` and a 0.05 m preview route. No movement occurs.
- All 64 recorded camera translations project into unknown grid cells. The node
  1 bottle invocation returns `NO_ROUTE`, with `INVALID_START: unknown_cell` for
  all six candidates. It is not snapped into the simulated free region. Every
  search uses the new memory/map hashes and completes with checked stage reports.
- Wrong-map finalization and existing-output reuse both exit 1 as expected;
  the wrong-map report remains `INCOMPLETE` with zero frames, and the existing
  primary report is unchanged. All 34 search PNGs decode. Map overview, bottle
  route, frontier and camera-start refusal images were visually inspected.
- `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest discover
  -s tests/memory -v`: 29 pass in 0.519 s, including 12 new cases using real depth
  validation/SQLite with a controlled frame-loader boundary. Cases exercise known
  online/final transforms, reopened means, exclusion/no-valid results, corrupted
  source evidence, policy/units, model identity, mid-run mutation and output reuse.

Evidence:

- `data/outputs/concurrent_rgbd/trial_20260911/attempt_02/`: database/export
  checks, commands/logs, final export and map preview, alongside original trial.
- `data/outputs/concurrent_rgbd/finalization_20260911/`: frames, primary/repeat
  reports, memory/import/query results, start fixture, four search cases, expected
  failures, local acceptance harness, `integration.json`, `verification.log`,
  `memory_tests.log` and `final_check.json`. Inputs and previous artifacts remain
  intact. Raw room data, databases, weights and generated outputs stay ignored.
- `docs/finalize-concurrent-memory.md`: exact commands, measured counts and limits.

Limits and learning:

- This completes the existing-data concurrent producer to frozen memory/search
  slice. It does not establish causal online memory, real-time throughput, object
  identity, physical scale/floor accuracy or navigation. Tracking failures in the
  original bag remain. Unknown camera projections alone do not diagnose the floor.
- Map optimization changes coordinates without changing the original observation.
  A consistent named pose version and preserved source evidence prevent fusion
  from silently mixing online and final geometry. Physical accuracy still needs
  a measured physical reference, which this source bag does not provide.

Next action:

- With an available operator, record a short level-camera translation between
  measured marks and back, using stationary endpoints and the existing bounded
  recorder, to evaluate tracking and scale. Await that human reference/readiness;
  no new capture has started and no whole-room loop is required.

### 2026-09-15: Forward/Backward Capture, Tracking And Saved-Graph Boundary Fix

Status: `VERIFIED` for new capture, slowed-replay tracking continuity and its own
map/memory/search. Precise physical scale and stationary drift acceptance remain
`PLANNED` because the operator supplied an estimate and additional motion.

Conditions and capture:

- Operator ready for filming; distance explicitly estimated as about 1 m, with
  forward/backward motion and unchanged intended heading. Planned phases were
  5/15/5/15/20 seconds for initial hold/outbound/far hold/return/final hold.
  Post-capture feedback reports main movements of 2-3 seconds and extra small
  forward/backward adjustments. Camera reference point/height, exact distance
  and physical endpoint error were not measured. Plan and actual feedback remain
  separate; cue timestamps do not measure chat delivery or human response.
- USB 3 Femto Mega was present and about 24 GB disk space available. No existing
  camera/SLAM process was found. Initial live preflight had nearby table/paper
  obstruction and median depth coverage 1.84%. Operator repositioned; the second
  preflight had clear room imagery and median valid depth 57.63%.
- Reused the existing local recorder and unchanged 15 FPS camera configuration,
  with a bounded preview gate, all-topic subscription check and timestamped cues.
  RGB is 1280x720; native depth is 640x576, registered to 1280x720 with uint16
  millimeter values. Driver, recorder and live checker exit 0 after capture.
- New bag duration 60.224296496 s; 899 RGB-D pairs, no unmatched interior/boundary
  pairs. Header skew median/max 4.319/4.941 ms; valid depth median 64.10%, range
  51.71-68.05%. Every recorded CameraInfo header matches the SDK global timestamp;
  both streams have zero SDK frame-index gaps and zero gaps above 1.5 periods.

Replay and motion evidence:

- Existing bounded concurrent baseline at 0.25x completes in 303.704 s total wall
  time. All 899 source pairs arrive with exact hashes. Original pixels, depth units
  and causal source-time TF pass independent verification. Perception, odometry,
  mapping and player exit 0, owned tegrastats stops on SIGINT, with no forced kill
  or remaining child PID. Brief local source inspection during playback means
  resource logs are diagnostics, not an isolated performance comparison.
- Odometry has 898 tracked outputs, zero lost outputs and one input without a
  result. Processing median/P95 is 230.786/260.066 ms. This validates reported
  tracking continuity for this recorded trajectory, not real-time performance.
- Perception processes 893 pairs, explicitly drops six and has zero inference
  failures. It accepts 887 online poses and refuses six: one unavailable source
  odometry and five unavailable source map TFs. Full detections retain 3,558
  accepted camera depth points, 896 depth rejections and 3,540 map points.
- Original odometry's maximum displacement from its first pose is 1.016861 m.
  Mean positions in predeclared start/far windows differ by 1.002561 m; this is
  consistent with the operator estimate but not a scale-error measurement.
  First/last poses differ by 0.159632 m and 5.735225 degrees. The planned 45-55 s
  hold has a 0.266258 m maximum radius around its mean; source images, trajectory
  and operator feedback show additional motion. These are pose variations, not
  isolated algorithm drift or ground-truth return error. Planned windows are not
  replaced with favorable intervals. Known translation/rotation cases and an
  independent SciPy orientation comparison pass the analysis math checks.

Observed failure and smallest fix:

- The first export check fails because final online graph membership (21 nodes)
  differs from saved optimized membership (20 nodes). Database `Admin.opt_ids`
  and native `rtabmap-export --opt 2` both exclude node 60. All other exported
  poses match the corresponding final online graph values within the original
  tolerance. The failed check/log and original source reports are preserved.
- `scripts/extract_mapped_rgbd.py` reads the saved ID set from the read-only
  database and checks the pinned 0.23.7 compressed matrix layout, compression
  integrity, positive unique IDs and online-graph membership. Export IDs must
  exactly match that set. The manifest explicitly lists online-only node 60.
  The local export checker reuses the helper and retains geometry/pose/hash checks.
- Six new cases test the observed endpoint mismatch, identical sets, bad IDs,
  unsupported formats, corrupted/truncated/extra payload and missing-file behavior.
  `tests/mapping`: 27 pass in 0.217 s; `tests/memory`: 29 pass in 0.567 s, both
  with `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest
  discover -s ... -v`. Native export membership agrees on old maps with 48/64
  nodes and the new map with 20; all three database hashes remain unchanged.

New map, memory, search and viewing:

- Database integrity passes with 60 stored nodes. Export has 20 saved camera/
  robot poses, 25,528 grayscale points and a 145 x 112 grid at 0.05 m: 1,486 free,
  3,600 occupied and 11,154 unknown cells. All 18,432,000 exported depth pixels
  equal original RGB-D source pixels. Node 60 is excluded before frame extraction.
- Finalization takes 6.891 s, selecting 19 nodes and excluding node 1's unavailable
  original online map TF. It preserves 90 detections (63 depth accepted, 27
  rejected), including online/final pose distinctions, without inference rerun.
  SQLite import takes 58.695 ms: 17 provisional records and 63 supports, comprising
  17 new records and 46 matches. Reopened SQL evidence/integrity and independent
  point checks pass; duplicate import adds zero frames and preserves memory bytes.
- Simulated start [3.05,-1.1257] m has 0.328650 m conservative clearance; 97 cells
  pass the assumed 0.25 m requirement. Bottle IDs/supports are 17/1, 8/7, 7/5:
  ID 8 has a 0.05 m preview route, ID 17 lacks clearance and ID 7 is disconnected.
  Chair/backpack are absent from memory and yield geometric frontier previews at
  the current simulated cell (zero translation). All 20 camera projections remain
  unknown; node 1 is refused. No new coverage, physical visibility or navigation
  is established. All 16 search PNGs decode; representative images were inspected.
- Viewing export retains 899 frames and source-time captions; MP4 duration is
  60.218616 s. VP8/WebM retains all frames with maximum 0.500 ms timestamp
  quantization and passes installed GStreamer decoding, exit 0. No decoder was
  installed. Source contact sheet, original odometry plot and map were inspected.

Evidence and limits:

- `data/outputs/femto_ros2/measured_line_20260915T224455Z/`: original bag,
  plan/feedback, both preflights, capture/cue/configuration/timestamp reports,
  source contract/timing, images and `video_review/line_01_review.webm`.
- `data/outputs/concurrent_rgbd/line_20260915/`: replay reports/snapshots,
  initial failed and corrected export checks, `motion_summary.json/png`,
  `frozen_ids_regression.json`, focused test logs, extracted frames, observations,
  memory, search reports and `integration.json` / `final_check.json`.
- New `docs/straight-line-capture.md` records commands and measured results.
  No dependencies, camera policies, inference settings or earlier artifacts were
  changed. Room data, weights and generated outputs remain local and ignored.
- This trial strengthens the functional pipeline evidence. Reported tracking
  continuity does not establish physical accuracy; operator motion cannot be
  separated from estimator drift without a controlled reference. The current
  physical-reference milestone remains pending rather than being marked complete.

Next action:

- Prepare ruler-measured camera positions and fixed endpoint holds for the
  outstanding physical scale/drift acceptance, with operator readiness before
  any further capture.

### 2026-09-15: Pipeline-First Direction And ROS Preview Interface

Milestone: M9 dry-run goal publication. Status: `VERIFIED`.

The user explicitly deferred scale/return-error refinement and requested continued
whole-pipeline integration. Precise physical accuracy remains unverified; it no
longer gates software work. The user also authorized official MobileCLIP-S0
weights and required inference dependencies in an isolated environment.

Changed: added `scripts/publish_search_preview.py`, a bounded independent ROS
receiver and eight focused tests. The publisher reuses all existing search
policies, retains all outcomes, and publishes only the selected checked path and
viewing goal. Missing routes emit only a decision; missing subscribers fail with
zero publication. Sources, map units, explicit starts and publication/source time
semantics remain visible. Added `docs/ros-search-preview.md` and public progress.

Verified: `source /opt/ros/humble/setup.bash` followed by
`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest discover -s tests/search -v`
passes 100 tests in 28.240 s. Real ROS localhost domain 54 tests receive two
messages per applicable topic: bottle ID 8 (0.05 m path), backpack frontier (zero
translation), and camera-node refusal (decision only). Every received path point,
final goal and stamp matches its source evidence. A fourth case times out without
subscribers, exits nonzero, and publishes zero messages. All four contexts close;
original memory/map/poses hashes remain unchanged.

Evidence: `data/outputs/search_publication/validation_20260915/`, particularly
`unit_tests.log` and `attempt_02/integration.json`. The initial integration exposed
an explicit-context/global-executor mismatch; its logs remain, and the publisher
now owns an executor bound to its context. No camera or motor commands ran.

Next action: persist and evaluate MobileCLIP crop embeddings and text queries,
then connect semantic candidates to the existing preview pipeline.

### 2026-09-15: MobileCLIP Persistence And Text-To-ROS Search

Milestone: M8 minimum integration. Status: `VERIFIED`.

Changed: `semantic_memory.py` builds a separate frozen SQLite index with original
RGB crops and 512-dimensional support vectors, fuses views without changing
geometric identity, and produces text rankings plus self-contained HTML review.
`run_semantic_search.py` selects explicit candidate IDs and reuses existing goal,
route, frontier and optional ROS preview code. The existing planner now supports
validated ID subsets; empty subsets retain `NO_SELECTED_OBJECTS`, not a fabricated
semantic absence claim. Ten semantic and three planner tests were added.

Dependencies: user-authorized official MobileCLIP commit
`48faa0fea4b08d74188b3841771aca6ff2c92852`, S0 checkpoint SHA256
`809b408eff74f8058843e86a1f92967097d42ba782450e85b8f4867b7f0ca0b7`,
215,934,653 bytes. New inference dependencies are isolated in
`~/projects/mobileclip-env`, pinned by `requirements-semantic.txt`; original
Jetson Torch 2.8.0/torchvision 0.23.0/NumPy 1.26.4 are reused. Software is MIT;
weights have upstream research-only terms. No model or room data is committed.

Verified: all 39 memory tests (0.768 s) and 103 search tests (29.003 s) pass.
Two GPU index builds encode all 63 geometric supports from 19 source nodes into
17 records, with identical per-view vector bytes. Independent crop pixels,
bounds, source stamps, file hashes, unit norms, scalar mean fusion and every
query score/order pass. Final build takes 23.732 s, including 10.096 s model load.
The 62 image calls after the first have median 37.245 ms / P95 51.758 ms. Peak RSS
is 1,478,696 KiB; PyTorch peak allocated GPU memory 237,129,216 bytes. These are
separate accounting measures, not additive Jetson system RAM. Ten warm text calls
range 14.559–29.448 ms; cold text call is 350.967 ms. No concurrent SLAM ran in
these measurements. Five native failure cases refuse changed memory/index,
wrong weights, excessive token length and output reuse, preserving originals.

The eleven-query set and 0.25 cosine / 0.02 top-window filter were declared before
scores were observed. Refrigerator/fridge retrieve ID 1; kitchen sink selects
9/10. Bottle/drinking-container/transparent-bottle retrieval fail the filter.
White-refrigerator attribute correctness is unverified; four unknown controls
remain below threshold. These results establish integration, not reliable semantic
recognition or absence detection. Existing YOLO errors remain visible in crops.

Three complete GPU/ROS runs verify fridge (ID 1, insufficient-clearance goal,
frontier published), sink (IDs 9/10, no route, decision only), and elephant (no
selected object, frontier published). Independent receivers get five copies of
each applicable message; all path points/stamps/terminal goals and semantic
provenance match. All publisher contexts close. Original source hashes remain
unchanged. The HTML review embeds 33 crop images across all eleven queries.

Evidence: `data/outputs/mobileclip/setup_20260915/` and
`data/outputs/mobileclip/line_20260915/`, including `index_02`, `queries_final`,
`integration.json`, independent harnesses, ROS receipts and
`failures/verification.json`. Commands and complete results are documented in
`docs/semantic-memory.md`.

Next action: complete the newly authorized CuTR official-sample feasibility trial
in its isolated environment, then evaluate an explicit Femto input adapter.

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
