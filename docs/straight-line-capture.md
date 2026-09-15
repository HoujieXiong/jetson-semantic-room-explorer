# Forward/backward capture and full pipeline replay

Status: `VERIFIED` on the Jetson on 2026-09-15 for a new RGB-D recording,
continuous reported tracking during slowed replay, and its own frozen
map/memory/search. Physical scale and stationary drift accuracy remain unverified.

## Capture conditions

The operator estimated a distance of about 1 m, without a ruler measurement.
The requested 60-second sequence was 5 s still, 15 s outbound, 5 s still,
15 s return and 20 s still, keeping the camera heading unchanged. Afterward,
the operator reported that the main forward/return movements each took about
2-3 seconds and included additional small forward/backward movements. Retain
that report separately from the planned sequence. Camera height, exact endpoint
position and measurement uncertainty were not measured.

The first live preflight showed nearby paper/table surfaces and only 1.84%
median valid depth. After the operator raised and repositioned the camera,
the second preflight passed with 57.63% median valid depth and a clear room
view. The camera was on USB 3; approximately 24 GB of disk space was available.

The existing recorder was copied into a new ignored evidence directory and
given a bounded image-review gate, confirmation that all five bag topics were
subscribed, and timestamped movement cues. Its phase event times describe
console output, not measured chat delivery or human reaction. The original
recorder, camera configuration, driver and SDK were unchanged.

## Measured capture and replay

| Check | Result |
| --- | --- |
| Recorded bag duration | 60.224296496 s |
| RGB-D | 899 pairs; 1280x720 RGB and registered uint16 millimeter depth at nominal 15 FPS |
| Original depth acquisition profile | 640x576 Y16, registered to the color grid by the existing driver |
| RGB/depth header skew | Median 4.319 ms; maximum 4.941 ms, below the existing 5 ms bound |
| Pairing | No interior or boundary unmatched RGB/depth frames |
| Valid depth | Median 64.10%; minimum 51.71%; maximum 68.05% |
| Source timestamps | All recorded CameraInfo headers match SDK global timestamps; zero SDK frame-index gaps in either stream |
| Capture shutdown | Recorder, driver and live checker exit 0 |
| SLAM/perception replay | Existing baseline, 0.25x; 303.704 s total supervised wall time |
| Odometry | 898 tracked outputs, zero reported lost frames; one input pair without an output |
| Perception | 893 processed pairs, six explicit queue drops, zero inference failures |
| Online pose association | 887 accepted, six refused: one missing source odometry, five missing source map TF |
| Full concurrent detections | 3,558 accepted camera depth points, 896 depth rejections, 3,540 map-localized observations |
| Source identity | All 899 pairs received unchanged; original pixels/units and causal source-time TF independently checked |
| Replay shutdown | Perception, odometry, mapping and player exit 0; owned tegrastats exits after SIGINT; no forced termination or child PID remains |

Odometry processing median/P95 is 230.786/260.066 ms. This is a slowed recorded
workload, not real-time acceptance. Brief local data inspection also ran during
replay; the resource log is diagnostic rather than an isolated benchmark.

Original odometry estimates a maximum displacement of 1.016861 m from the first
pose. The predeclared start/far windows have a mean-position separation of
1.002561 m. These are compatible with an estimate of about 1 m but cannot establish
a scale error percentage without a measured reference.

The first/last estimated positions differ by 0.159632 m and orientations by
5.735225 degrees. The planned 45-55 s return window contains additional movement:
its maximum radius around the mean position is 0.266258 m. These differences
combine actual camera motion and estimation error; they are not a measured SLAM
drift or return-accuracy result. The original planned windows remain in the
report rather than being replaced with favorable stationary-looking intervals.

## Saved graph boundary correction

The initial export check failed because it assumed the final online graph and
saved optimized graph always contain identical node IDs. This recording's final
online graph has 21 nodes, including node 60. The database stores 20 optimized
poses, and the installed `rtabmap-export --opt 2` exports those same 20. All
exported poses match their corresponding final online poses within existing
rounding tolerances. Node 60 is retained as explicit online-only evidence.

`scripts/extract_mapped_rgbd.py` now reads the saved `Admin.opt_ids` membership
from the read-only database. The supported RTAB-Map 0.23.7 matrix layout is checked
explicitly, along with compression integrity, unique positive IDs and membership
in the online graph. Exported IDs must exactly equal that saved set; arbitrary
missing or additional exported nodes still fail. The frame manifest records
`online_graph_nodes_not_in_frozen_map`. The local export checker reuses this
helper while retaining its pose, geometry, calibration and hash checks.

Six new tests cover online-only endpoints, identical sets, invalid/duplicate/
unknown IDs, unsupported versions/layouts, truncated/extra compressed data and
read-only missing-file behavior. All 27 mapping tests pass in 0.217 s and all
29 memory tests pass in 0.567 s. Independent comparison with native exports on
three saved databases gives 48, 64 and 20 matching IDs. Both old maps retain
identical membership; none of the three databases changed.

## New map, memory and search

The new database contains 60 stored nodes and 20 saved optimized poses. Its
export has 25,528 grayscale points and a 145 x 112 grid at 0.05 m: 1,486 free,
3,600 occupied and 11,154 unknown cells. Original RGB-D extraction checks all
18,432,000 exported raw depth pixels against the bag.

Finalization selects 19 saved nodes and excludes node 1 because its original
online map TF was unavailable. Node 60 is separately excluded at the saved-graph
boundary. All 90 selected detections remain: 63 accepted depth observations and
27 explicit rejections. Finalization takes 6.891 s without rerunning inference.
SQLite import takes 58.695 ms, creating 17 provisional records with 63 supporting
observations. These records are not independently confirmed physical identities.
Original online poses/points remain beside final optimized coordinates.
Repeated import adds zero frames and leaves the database byte-identical.

The explicit simulated start `[3.05,-1.1257]` m has 0.328650 m conservative
clearance; 97 free cells pass the assumed 0.25 m clearance. All 20 exported camera
positions project into unknown cells. Existing search policies remain unchanged.

| Query/start | Result |
| --- | --- |
| Bottle / simulated | Three candidates: ID 8 has a 0.05 m route, ID 17 lacks clearance, ID 7 is disconnected under the route policy |
| Chair / simulated | Absent from memory; geometric frontier preview |
| Backpack / simulated | Absent from memory; geometric frontier preview |
| Bottle / recorded camera node 1 | `NO_ROUTE`; available goals are refused because the start cell is unknown |

The frontier observation goal is already at the simulated start cell, so its
route length is zero. It is an orientation/observation preview, not evidence of
new coverage or physical navigation. All 16 search PNGs decode; the map,
trajectory, source contact sheet, bottle route and frontier preview were inspected.

## Inspect and reproduce

The viewing copy uses VP8/WebM, already supported by this Jetson's GStreamer
decoder. All 899 frames decode, with maximum timestamp quantization of 0.500 ms.
The H.264 source viewing copy is also available; metric depth remains in the bag.
Open the WebM from the Jetson desktop terminal:

```bash
cd ~/projects/jetson-semantic-room-explorer
gio open data/outputs/femto_ros2/measured_line_20260915T224455Z/video_review/line_01_review.webm
```

Local evidence roots:

- `data/outputs/femto_ros2/measured_line_20260915T224455Z/`: original bag,
  preflights, configuration, SDK timestamp CSV, plan, operator feedback, capture
  process/cue report, source-contract/timing checks, RGB samples and video copies.
- `data/outputs/concurrent_rgbd/line_20260915/`: bounded replay harness and
  verifier, `attempt_01/` with exact commands/configuration/runtime snapshots,
  original failed export check and corrected result, extracted frames,
  `motion_summary.json/png`, `frozen_ids_regression.json`, test logs, observations,
  SQLite memory, queries/searches, `integration.json` and `final_check.json`.

To run another offline replay of this same bag, source
`scripts/rtabmap_odom_env.bash` and invoke the saved `run_trial.py` with a fresh
attempt name. The saved `verify_trial.py` checks that attempt. The local
`check_exports.py` uses the corrected saved-node boundary; `evaluate_motion.py`
and `verify_pipeline.py` describe this acceptance's exact analysis and commands.
Generated outputs and room data remain local and ignored.

The next physical acceptance still needs ruler-measured camera positions and
fixed endpoint holds. The new recording validates the software path and this
trajectory's reported tracking; its estimated distance and additional movement
do not supply that physical reference.
