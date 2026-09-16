# Causal text-query to ROS search preview

Status: `VERIFIED` for causal decisions and bounded ROS previews during recorded
RGB-D replay on Jetson Orin Nano. Physical navigation and live operation remain
unverified.

For repeated queries, the [bounded session mode](warm-text-queries.md) keeps one
encoder loaded and reuses this planner with fresh snapshots. Session mode computes
previews without ROS publication; the existing single-query CLI remains available.

The online journal can retain received ROS occupancy grids alongside original
observations, embeddings and graph revisions. A text query requests planning
sources in the same SQLite read snapshot as its object associations. The online
planner reuses the existing stand-off, clearance, cardinal-route and frontier
functions without passing online object IDs to a frozen index.

## Input and decision contract

Opt in with `tests/check_concurrent_perception.py --capture-occupancy --memory-db
PATH`. The additional `/map` subscription uses reliable, volatile QoS, compatible
with the dedicated online publisher. Source cell order, resolution, origin,
frame, source timestamp and signed-int8 pixel hash are retained. Only axis-aligned
trinary cells (-1 unknown, 0 free, 100 occupied) are accepted. Grids are bounded to
65,536 cells and use the existing 512 KiB event and 16-entry writer queue limits.
A failed write, malformed map or budget excess fails the measurement explicitly.

Apply `config/rtabmap_online_preview.yaml` after the existing mapping parameters
when starting RTAB-Map for this path. It sets `latch: false`, so every processing
cycle supplies a freshly stamped graph/grid, including stationary periods.
The ordinary saved-map configuration is unchanged. The observed default latching
behavior agrees with the official ROS 2
[graph publication](https://github.com/introlab/rtabmap_ros/blob/ros2/rtabmap_slam/src/CoreWrapper.cpp)
and [grid publication](https://github.com/introlab/rtabmap_ros/blob/ros2/rtabmap_util/src/MapsManager.cpp)
logic; this source comparison is not a claim that the branch is byte-identical
to the installed 0.23.7 binary. Queried native parameters and received messages
provide the run-specific evidence.

Planning requires the latest received graph and grid to have exactly matching
source timestamps. It validates the named graph hash, session, committed prefix
and corresponding mapping event. Map/start records must be no older than ten
wall-clock seconds; a source-time lag beyond ten seconds is also refused.
These are explicit experimental limits for slow recorded replay, not navigation
safety guarantees. The current mapped `camera_link` x/y projection is the default
start. `--simulated-start-xy X Y` instead declares a test fixture; neither input
establishes current robot-base localization. Missing nodes, incompatible
snapshots, missing maps and stale evidence yield a decision with no selection.

Selected semantic objects use the original 0.75–1.25 m stand-off band and 0.25 m
clearance policy. If an object goal exists, the original route checker validates
the exact start and each cardinal segment; the shortest reachable candidate wins.
If no object goal exists, the original frontier policy may propose exploration.
An unknown text query therefore cannot invent an object identity, but may still
produce an explicitly geometric exploration preview. Invalid starts and
unreachable/unsupported goals retain their reasons.

The existing ROS publisher sends decision JSON and, only for a valid selection,
a map-frame pose and path. Publication refuses an expired online selection before
each send. There is a five-second subscriber deadline, one-second publication
window and the existing DDS acknowledgement deadline. This is a bounded preview;
no navigation action or motor command is issued. Reports retain the snapshot and
evidence deadline, and a PNG is rendered after publication to keep plotting out
of the goal-age budget.

## Local commands

The already installed MobileCLIP environment and checkpoint are reused; no new
model, library or recording is required. Start the existing SLAM nodes/player
with the online mapping overlay and add `--capture-occupancy` to the concurrent
observer described in [online semantic memory](online-semantic-memory.md).
The measured local supervisor launches this whole bounded trial:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  data/outputs/online_search/line_20260915/run_trial.py fresh_attempt
```

Against its active journal, use a fresh output directory:

```bash
source scripts/rtabmap_odom_env.bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../mobileclip-env/bin/python \
  scripts/online_search_preview.py \
  --db data/outputs/online_search/line_20260915/fresh_attempt/online.db \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a refrigerator' \
  --output data/outputs/online_search/manual_query \
  --publish-preview
```

The receiver must subscribe within the publication deadline. For a manual check,
start this first in another shell with the same ROS environment:

```bash
.venv/bin/python tests/check_search_publication.py \
  --output data/outputs/online_search/manual_received --duration-s 30
```

Outputs include `search.json`, `query/query.json`, embedded source-crop
`query/queries.html`, and `preview.png` when planning reaches a geometric branch.
Closed journals remain useful for retrieval, but old map evidence is refused for
publication. Use the existing text-only command for retrospective queries.

## Verification

The focused online tests use real SQLite commits and known geometry to cover
matching maps, delayed grids, a commit during a query, changed graph revisions,
source/prefix mismatch, paused/future evidence, missing starts, explicit unsnapped
simulated starts, invalid starts, unknown-query frontiers, grid row ordering and
metadata/cell integrity. The existing frozen search and memory suites remain
required regressions.

Native evidence is retained under
`data/outputs/online_search/line_20260915/`. An independent process records raw
`/map` and `/mapGraph` messages; separate subscribers retain actual ROS decision,
goal and path messages. The verifier compares raw grid cells/metadata and graph
poses with journal events, rechecks causal prefixes, and independently checks
path coordinates, blocked-square distances, stand-off, frontier rays and ROS
goal orientation. Existing source-pixel, TF, geometric association and scalar
semantic-ranking verifiers are also reused.

Retained attempts before final acceptance:

- Attempt 01 uses the default `latch: true`. During-query map ages are 18.257 s
  and 42.551 s; both queries publish refusal decisions. The trial is intentionally
  interrupted after this diagnosis. Owned processes exit and writers close; it
  remains INCOMPLETE.
- Attempt 02 uses the explicit online overlay. Graphs/grids refresh together, but
  the current camera projection is unknown and the old simulated start lacks
  clearance. The observer remains bounded. A telemetry read races with a query
  process that has exited 0: `/proc/PID/status` loses `VmRSS` before its state is
  observed as zombie. The supervisor aborts and closes all owned children. It now
  confirms process exit with a bounded 0.2 s wait before recording this specific
  sampling race; a still-live process without RSS remains an error.
- The additional simulated point `[2.9, -1.0757]` is declared before attempt 03
  from the already received attempt-02 grid, whose nearby cell has a measured
  0.314645 m clearance lower bound. Both failed earlier starts are retained. The
  point is a planning fixture, not camera/robot localization. No semantic or
  geometric thresholds are changed to make it pass.


## Measured acceptance, 2026-09-15

Successful trial: `data/outputs/online_search/line_20260915/attempt_03/`.
The unchanged 899-pair, 60.224 s recording runs at nominal 0.25x; full trial wall
time is 399.944 s including cold query processes, receivers and cleanup.

| Check | Measured result |
| --- | --- |
| Inputs | All 899 synchronized pairs; no unmatched image/CameraInfo stamps |
| YOLO/source poses | 887 processed, 12 explicit drops, zero inference failures; 880 accepted poses, two missing-odometry and five missing-map-TF refusals |
| SLAM | 897 tracked outputs, zero reported lost, two inputs without output; 60 database nodes, 21 nodes in final received graph |
| Semantic evidence | 58 encoded keyframes, 223 original source-verified crops; one original pose refusal and one dropped-source refusal |
| Map evidence | 60 occupancy grids and 60 graphs, checked against a separate raw-message receiver; 11,520–16,240 cells per grid |
| Journal | 1,139 events, 11,563,008 bytes, integrity passed; 20 final eligible frames / 14 provisional objects / 65 semantic supports |
| Bounds | RGB cache 32, semantic request peak 1/8, writer queue peak 3/16; pending/inference/pose-wait peaks 1/1/8 |
| Cleanup | Observer, player, SLAM, grid witness and all query/preview receivers exit 0; telemetry SIGINT; no forced termination or remaining owned PID |

The complete query outcomes are retained. Selection uses the unchanged cosine
0.25 / top-score-window 0.02 policy:

| Phase / query | Prefix / graph | Text result | Planning / received ROS result |
| --- | --- | --- | --- |
| Before: `a fridge` | 0 / none | No semantic supports | Missing graph; decision only |
| During: `a fridge` | 76 / 61 | Refrigerator ID 1, 0.277017 | Camera projection in unknown cell; decision only |
| During: `a refrigerator` | 458 / 441 | Refrigerator ID 1, 0.301202 | Earlier simulated fixture lacks clearance; decision only |
| During: `a kitchen sink` | 663 / 649 | IDs 9/10, top sink 0.258034; second oven 0.251973 | Revised simulated fixture also lacks clearance in this revision; decision only |
| During: `an elephant` | 903 / 898 | No selected object; top 0.165465 | Geometric frontier preview; one decision, goal and path received |
| After: `a bottle` | 1139 / 1125 | No selected object; top appliance 0.245764 | Map age 74.190 s; decision only |

All four during-playback queries finish before the player ends. Map evidence
ages are 3.579, 4.246, 3.539 and 1.431 s. The two middle grids have maximum
clearance lower bound 0.233903 m, below the required 0.25 m; the later grid permits
a 0.318198 m-clearance frontier goal. These changing-grid results are preserved,
including the sink query's appliance distractor.

The frontier goal is `[2.9000000414, -1.0756973978]` m, yaw -pi/2, with a 0.35 m
cardinal view toward its free/unknown boundary. It nearly coincides with the
explicit simulated start `[2.9, -1.0757]`: the three-point path is only
**0.000002644 m** long, a numeric cell-center connector. This verifies an
observation orientation and the ROS path interface, not meaningful room travel
or a route to a found elephant. Independent checks confirm exact received path
coordinates, yaw, blocked-square clearance and frontier-ray cells. The saved PNG
visually agrees with the overlapping start/goal and downward viewing direction.

Full during-query CLI times, including Python/model startup, publication and PNG
rendering, are **18.135, 20.750, 18.336 and 19.138 s**. Text-model loads take
11.182–12.337 s; snapshot/ranking computation takes 51.004–400.589 ms. A warm query
service is not measured. First image crop encode is 381.962 ms; remaining 222
encodes P50/P95 are 84.215/123.801 ms. Perception arrival-to-result P50/P95 are
495.725/558.251 ms. Writer commit P50/P95/max are 11.701/26.077/147.811 ms.
Producer RSS peaks at 2,030,400 KiB; system RAM at 5,119 MB, swap at 1,153–1,199 MB
including prior system use. GPU temperature peaks at 61.468 C. These measurements
are one bounded slow replay, not real-time throughput or leak-freedom evidence.

Independent source/TF/geometry/semantic checks pass: all 223 PNG crops match
original bag pixels; maximum scalar cosine error is 3.88e-8 and point consistency
error 8.89e-16 m. There are 135 historical graph translation updates above
1 micrometer, maximum 0.002461 m. Those errors describe numerical consistency,
not physical accuracy. A separate process reopens the new journal and the prior
semantic journal with identical geometry/rankings and unchanged file hashes.
The new journal SHA256 is
`6f0d2ade438fe47e0e033a75b97df2ea635083f8b8deafc76d837c9706faea48`.
Original recording, model, frozen index and older journals remain unchanged.

All **217 focused tests** pass: 35 online-memory, 40 odometry/concurrency, 39
memory/semantics and 103 frozen search. Native failure checks separately confirm
that an expired selection transmits zero messages and that no subscriber causes
a bounded timeout; both ROS contexts close. An explicitly synthetic known-map,
known-vector fixture additionally verifies a 1.5 m route through the same
online planner and native ROS boundary. It is not a room-data result. Its first
local harness run lacked a receiver-ready wait and timed out; the retained second
run waits for READY before constructing fresh fixture evidence. No incomplete
attempt is relabeled successful.

Evidence includes `verification.json`, `geometry_verification.json`,
`semantic_verification.json`, `search_verification.json`, `reopen_check.json`,
`preview_review.json`, raw map/graph messages, crop/query/preview outputs, exact
source/config/helper copies, queried parameters, process exits and resource logs.
Native boundary checks are in the sibling `publication_failures/` and
`controlled_route_02/` directories. Focused test logs are in the parent directory.

Open the measured preview on the Jetson display:

```bash
gio open data/outputs/online_search/line_20260915/attempt_03/during_unknown/preview.png
```

Learning: a semantic match, a usable map/start and a feasible geometric goal are
separate decisions. A pipeline can correctly refuse motion while still completing
retrieval, persistence, planning checks and publication. Next action: prepare one
operator-assisted live validation with both floor and familiar furniture visible,
keeping physical motion and scale claims separate.
