# Causal observation memory during RGB-D playback

The online path writes original perception results and received map revisions to
an independent SQLite journal while ROS playback is running. A separate process
can query the committed prefix before playback ends. It never reads a final map
export or substitutes future poses into an earlier query.

This is a bounded, recorded-data integration. It retains YOLO labels and the
existing depth/association policies. Live camera operation, continuous operation,
online MobileCLIP retrieval, route publication from the changing map and physical
navigation remain separate work. A subsequent
[online MobileCLIP integration](online-semantic-memory.md) now verifies text
queries during recorded-data playback; the original journal below stays intact.

## Data and revision contract

`tests/check_concurrent_perception.py --memory-db PATH` enables one additional
writer thread. ROS callbacks and the inference pump enqueue serialized events into
a queue of 16; the writer owns SQLite and commits each event with WAL and FULL
synchronization. Queue overflow and writer errors abort explicitly. A fresh path
is required, and shutdown drains the queue and closes the connection. The existing
one-pending-frame/one-GPU-worker/eight-waiting-poses limits remain unchanged.

The journal stores three event types in availability order:

- Finalized observations: original RGB/depth timestamps and pixel hashes,
  calibration, camera points, original source-time pose and its receipt evidence,
  detections, depth rejections, and processing/drop outcomes.
- Mapping information: RTAB-Map node ID and its original mapping stamp.
- Graph revisions: received node poses and the fixed camera-link-to-optical
  extrinsic resolved at the graph stamp. Unavailable extrinsics remain explicit.

Every event has a sequence number and a monotonic availability time relative to
the session origin. The header identifies the source reference, model, inference
policy, frames and units. Source timestamps remain integer nanoseconds. The
existing RTAB-Map floating-point stamp-roundtrip tolerance is shared unchanged.
The journal has no fabricated frozen-map or exported-pose hash.

A query reads all events in one SQLite read transaction, then closes that
transaction and builds a private in-memory association snapshot. It uses the
latest graph in that prefix and only nodes whose corresponding finalized source
observations are available. Original pose rejection or dropped inference stays
excluded even if a later graph contains the node. Nodes removed from the current
graph are excluded from that query; their original observations remain on disk
and become eligible again if the node returns. Query absence is therefore not
proof that a room object is absent.

For every eligible keyframe:

```text
map_T_optical = received_graph_map_T_camera_link * fixed_camera_link_T_optical
map_point = map_T_optical * original_camera_point
```

All supports use the same graph revision before fusion. The original online map
point is retained alongside the revised point. The existing label/distance and
same-frame-overlap association code builds the query result; it does not average
points from different graph revisions. Objects are derived from persisted raw
observations on each query, rather than independently mutated in the journal.

Each result identifies its session, event-prefix sequence, graph sequence/hash,
included source observations and excluded node reasons. Object IDs are provisional
and valid only within that named snapshot. They are not stable cross-revision
identities and must not be passed into an old frozen semantic index or planner.
An initial query returns `NO_GRAPH`; an available graph with no matching candidate
returns `NOT_FOUND` with the retained coverage limitations.

The implementation is deliberately bounded: at most 600 graph nodes, 20,000 events,
512 KiB per event, 0.5 s SQLite lock wait and 600 s observer duration. Exceeding a
limit fails explicitly. Query cost grows with the retained trial prefix; this is
not an indefinitely running service or a new production ROS package.

## Run and query

Use the existing recorded SLAM setup and add the journal argument to the measured
producer command. The source bag and reference are already local; no download or
new recording is needed. From the repository root:

```bash
source scripts/rtabmap_odom_env.bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
.venv/bin/python tests/check_concurrent_perception.py \
  --reference data/outputs/online_memory/line_20260915/normalized_reference.json \
  --model yolov8n.pt --duration 301 \
  --memory-db data/outputs/online_memory/manual/online.db \
  --output data/outputs/online_memory/manual/measurement.json
```

This observer requires the existing RTAB-Map nodes and bag player. The measured
local supervisor starts and stops all of them, checks input hashes and performs
independent queries on schedule:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/online_memory/line_20260915/run_trial.py manual_run
```

Use a new output name. This local acceptance harness relies on the existing room
recording and is intentionally kept with ignored artifacts. Its exact commands,
configuration copies, source snapshots, process exits and resource samples are
retained in each run. It performs no physical capture or motion.

In another terminal, query either the active journal or the same file after the
writer has closed. The query needs no ROS initialization or GPU:

```bash
.venv/bin/python scripts/online_scene_memory.py \
  --db data/outputs/online_memory/line_20260915/attempt_07/online.db \
  --command find --label refrigerator
```

Use `--command list` without a label to list current candidates, or
`--command last_seen --label bottle` for candidates tied at the latest source time.
The old `scene_memory.py` reader intentionally refuses this journal schema. Its
frozen databases and the saved-data demo continue using their original commands.

## Replay transport and message identity

The original reference keeps the default `serialized_sha256` comparison. The
local typed-publisher acceptance harness uses a separately derived reference with
explicit `wire_comparison: message_content_sha256`: every ROS field participates,
including source stamps, frame IDs, calibration/ROI/binning and complete image
data hashes. Altered fields or missing messages still fail. Both hashes remain in
sensor evidence; this mode does not claim identical CDR wire bytes.

The derivation reads every original bag message, verifies the original aggregate
serialized hashes, and checks typed serialization roundtrip equality. This is
necessary because local CameraInfo messages can reserialize from 408 to 405 bytes,
and CDR padding bytes can change without changing decoded fields. The original
bag and reference are never overwritten. The derived reference also records the
original reference hash and every observed wire difference.

The local player waits for its actual publishers to match all expected
subscribers, publishes original typed messages in bag receipt order at 0.25x with
an advancing simulated clock, and requests final DDS acknowledgements. The
receiver's complete counts and content hashes are the delivery acceptance check.
Per-message acknowledgement was too slow in a bounded diagnostic; it is not used
in the final acceptance harness. This transport finding does not establish the
cause of the initial native-player frame loss.

## Focused verification

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/online_memory -v

source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/odometry -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/memory -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/ros2 -v
```

Known-case tests use real SQLite transactions and the actual association code.
They cover a delayed observation, reprojecting both old and new supports under a
revised graph, graph membership removal/restoration, rejected poses, dropped
frames, missing/changed extrinsics, rotated coordinates, a writer commit during
query derivation, duplicate-source failure, queue overflow and connection cleanup.

## Verified Jetson result, 2026-09-15

Evidence is in `data/outputs/online_memory/line_20260915/attempt_07/`.
The 60.224 s source recording plays at nominal 0.25x; the player runs 246.268 s
and the complete supervised trial runs 322.416 s including startup and cleanup.
No camera capture, physical motion, CuTR or new dependency is involved.

| Check | Measured result |
| --- | --- |
| Sensor delivery | All four streams: 899 messages each, matching original decoded fields/pixels; 899 synchronized pairs, no unmatched input |
| Perception | 893 processed, six explicit pending-queue drops, zero inference failures |
| Source-time poses | 888 accepted; five refused: one missing odometry, four missing map TF |
| Odometry/map | 898 tracked outputs, zero reported loss, one input without output; 60 database nodes, 21 nodes in last received graph |
| Persistent journal | 1,019 events: 899 observation outcomes, 60 mapping events, 60 graph revisions; 6,131,712 bytes |
| Writer | Queue peak 3/16; per-event write P50/P95/max 12.077/20.183/285.078 ms; thread closed |
| Final active-graph memory | 20 eligible frames, 88 detections, 64 supports, 14 provisional objects; node 1 retains original pose refusal, 39 other nodes outside current graph |
| Historical graph changes | 135 repeated-node translation updates above 1 micrometer; largest 0.002438 m, not physical accuracy |
| Reopen | Fresh CLI processes reproduce snapshot/results; journal file remains byte-identical |
| Cleanup | Observer, player, odometry and mapper exit 0; telemetry stops by SIGINT; no forced termination or remaining owned PID |

Three scheduled queries in separate processes completed before playback ended.
The table also includes initial and after-playback checks:

| Query | Event prefix / graph event | Eligible keyframes | Result | Query computation |
| --- | --- | --- | --- | --- |
| Initial bottle | 0 / none | 0 | NO_GRAPH | 3.147 ms |
| Bottle during playback | 170 / 157 | 2 | NOT_FOUND | 37.871 ms |
| Refrigerator during playback | 509 / 497 | 9 | One candidate, nine supports | 134.085 ms |
| Backpack during playback | 848 / 837 | 16 | NOT_FOUND | 227.862 ms |
| Bottle after playback | 1019 / 1006 | 20 | Two candidates | 261.127 ms |

CLI wall time, including process/import startup, is 718–818 ms for the three
during-playback queries. The table's computation time excludes that startup.
The earlier bottle result stays unchanged when later observations produce two
candidates. Candidate count is not a verified count of physical objects.

Independent verification rereads original RGB/depth pixels, checks millimeter
conversion and deprojection, reconstructs source-time TF using only transforms
already received, and recomputes each query's eligible supports and association
from its recorded event prefix. It also checks the reopened list of all 14
candidates. Fused-coordinate agreement is within 1.78e-15 m, a numerical check.
No final map export is used to justify an earlier query.

Perception arrival-to-result P50/P95 is 489.245/557.984 ms; callback P95 is
24.411 ms. Observed pending/inference/pose-wait queue peaks are 1/1/7 against
limits 1/1/8. Perception peak RSS is 1,307,452 KiB. Tegrastats system RAM peaks at
3,434 MB, available RAM stays above 4,125,184 KiB, and system swap is 878–879 MB
(including pre-existing system usage). Jetson shared memory accounting is not
additive. These are bounded trial measurements, not indefinite leak or real-time
acceptance.

Focused checks pass: 12 online-memory, 40 odometry/concurrency/message-identity,
39 frozen/semantic-memory and 18 ROS-contract tests. Compilation and whitespace
checks pass. Exact source/configuration copies, local helper scripts, parameters,
raw reports and independent `verification.json`, `online_verification.json` and
`reopen_check.json` remain with the trial. Raw bags, models and prior frozen
artifacts are unchanged.

Failures remain visible. Native-player attempts 01/02 miss the first two inputs
and remain INCOMPLETE, despite successful partial-prefix queries. Attempts 03–05
stop on a raw-message ACK timeout or typed serialization byte differences before
useful playback. Attempt 06 is intentionally interrupted because per-message ACK
overhead cannot fit the fixed deadline; its writer drains and owned processes
close without force. This also verifies the fix for repeated ROS shutdown after
SIGINT. No failed run is relabeled successful.

Remaining limits: only active-graph keyframes contribute to a query, object IDs
are snapshot-scoped, and this journal contains no online text embeddings or route
publication. Geometry/identity quality, physical scale, live camera throughput
and continuous operation still need separate validation. The subsequent
[MobileCLIP integration](online-semantic-memory.md) retains this label-query API
and verifies text retrieval with additional causal semantic events.
