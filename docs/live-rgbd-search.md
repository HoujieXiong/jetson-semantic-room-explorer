# Bounded live RGB-D to semantic search

Status: `VERIFIED` for a bounded live measurement, source-pixel/unit checks,
persistent events and an independently received refusal decision on Jetson Orin
Nano. Lossless transport, useful live object retrieval, continuous operation and
navigation are **not verified**.

The operator confirmed the stationary kitchen view, including the fridge, sink
and floor. No movement was requested. The final run kept the camera open for a
bounded 70-second interval, observed 64.696 seconds of source images, and completed
all processing/cleanup in 136.977 seconds including model startup. This is actual
camera input, not slowed replay. Four preceding failures remain saved.

## Contract and implementation

`tests/check_concurrent_perception.py` accepts exactly one of `--reference REPORT`
and `--live-config YAML`. Replay retains its exact reference and advancing-clock
checks. Live mode uses system time, rejects a simulated clock and stores the
actual camera configuration hash instead of inventing a bag reference. Original
source stamps and monotonic receipt times are retained for each topic.

Live measurement reports missing sensor and unmatched odometry messages explicitly.
It never reconstructs them as received data or validates unmatched odometry as a
tracked trajectory. `MEASURED` means the bounded measurement completed;
`contract_checks_passed` and sensor `message_completeness_passed` can still be
false. Calibration, units, source stamps and source-time TF checks remain active.
The ordinary camera/bag/replay checker still fails on missing interior messages.

The live journal uses a bounded 512-event queue and drains at most 16 already
queued events per SQLite transaction. It does not wait for a full batch. WAL and
`synchronous=FULL` remain enabled; a failed batch rolls back completely and
statistics count only committed events. `write_ms` describes transactions and
`committed_batch_sizes` records their sizes. The existing replay policy remains
16 queued events and one event per transaction. All policies used by the saved
failed live trials remain readable.

This change follows measured storage stalls, not a throughput claim. The final
queue reached 136/512; 759 transactions committed 1,162 events, with transaction
P50/P95/max 9.526/41.952/5,195.412 ms. A 512-item queue plus 16 active items has a
264 MiB serialized-payload ceiling under the existing 512 KiB event limit; decoded
objects and other process memory are additional. The supervisor guards 1 GiB
available RAM and 3 GiB available disk. Overflow remains fatal.

## Environments and reproducibility

Keep separate fresh shells for `scripts/femto_ros2_env.bash` and
`scripts/rtabmap_odom_env.bash`. Override the camera/recorder shell to
`ROS_DOMAIN_ID=43` so it shares localhost DDS with SLAM; do not mix their OpenCV
libraries. This run reused the installed driver, RTAB-Map 0.23.7, YOLOv8n and the
official MobileCLIP-S0 checkpoint. No dependencies were added.

Use the camera parameters from `config/femto_rgbd.yaml`. SLAM uses the existing
odometry/mapping YAML and `config/rtabmap_online_preview.yaml`, with explicit
`use_sim_time:=false` on both nodes and
`always_process_most_recent_frame:=true` on odometry. Queried native parameters
confirm these values and `latch: false`. The recorded-data defaults stay unchanged.

In the isolated SLAM shell, the actual observer invocation has this form:

```bash
../mobileclip-env/bin/python tests/check_concurrent_perception.py \
  --live-config RUN/femto_rgbd.yaml --model yolov8n.pt --duration 110 \
  --output RUN/measurement.json --memory-db RUN/online.db \
  --semantic-model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --capture-occupancy
```

`RUN` must be fresh. This command observes; it does not own or stop the camera.
Start it before the camera and stop the camera sufficiently before the observer
deadline to drain inference, pose waits, semantic work and storage. The local
`data/outputs/live_search/steady_20260916/run_live.py` owns the bounded child
processes. The final `attempt_05/used_run_live.py`, `run.json`, saved source/config
copies and native parameter reports retain the exact commands and cleanup.
Do not start a new capture without operator readiness. The operator subsequently
went to bed and authorized continued work on the saved data only.

## Measured result and limits

| Measurement | Final attempt |
| --- | --- |
| Recorded RGB/depth images | 947/947; 947 source-matched pairs |
| Camera selection | 1280x720 MJPG RGB, 640x576 Y16 native depth, requested 15 FPS |
| Published registered grid | 1280x720 RGB8 and 16UC1 millimeters, zero invalid |
| Recorded header rate | RGB 14.622 Hz, depth 14.623 Hz; largest period about 469 ms |
| RGB/depth source skew | Median 3.576 ms, max 4.306 ms |
| Depth nonzero coverage | Median 65.55%; center median 4.118 m |
| Observer arrivals | 947 RGB, 946 depth, 947 CameraInfo per stream |
| Synchronized perception pairs | 946; 285 processed, 661 explicitly dropped |
| Source poses for processed perception | 68 accepted; 215 missing odometry, 2 missing map TF |
| Odometry | 221 matched tracked outputs, zero reported lost; 726 input pairs without output |
| Processing rate over source interval | About 4.41 perception results/s and 3.42 odometry results/s |
| Perception arrival-to-result P50/P95 | 2,203.268/2,564.299 ms, including refused pose waits |
| Mapping | 54 mapping/graph/grid events; final graph retains only node 1 |
| Semantic work | 12 encoded keyframes, 11 nonempty source crops; 42 refused keyframes |
| Memory | 1,162 events; 3,653,632-byte SQLite journal; reopening identical |
| Actual query | `a fridge`, 20.374 s CLI wall time, including 13.991 s encoder load |
| Query outcome | No semantic support; current start node absent from graph |
| Independent ROS receiver | 1 decision, 0 goals, 0 paths |
| Resources | Peak RAM 5,011 MB, producer RSS 2,022,544 KiB, GPU temperature 61.406 C |

The driver timestamp CSV has 963 frame records per stream. Sixteen records follow
the last recorded image at shutdown; none are missing inside the recording's CSV
interval. SDK index gaps are also retained (19 RGB, 11 depth); these are distinct
from ROS subscriber loss and inference queue drops. CSV entries alone do not
prove delivery to DDS subscribers.

The bag contains only 945 RGB and 946 depth CameraInfo messages: two RGB and one
depth CameraInfo messages are absent inside the interval. Its strict
`bag_check.json` remains `INCOMPLETE`. `bag_measurement.json` measures the gaps
without changing that result. All 947 image pairs are present; constant matching
intrinsics are retained. The observer separately missed one depth image.
The bag is reusable with explicit missing-message handling, not as a lossless
four-topic replay reference. No physical distance was remeasured in this scene;
mm conversion inherits the prior driver/unit validation and was checked against
stored uint16 pixels and metric back-projections.

The query used only committed prefix 602 and graph event 585, with map evidence
age 1.204 s. The first observation lacked source-time map TF. RTAB-Map subsequently
reported rehearsal merges into node 1; the current memory policy excludes
observations attached to nodes absent from the latest graph. Thus the active
snapshot has zero eligible objects despite successful crop encoding. This is a
measured graph/observation association limitation, not proof that the fridge is
absent. Some retained detector proposals depict the left trash bin, so detection
labels also cannot establish identity.

The final occupancy grid has 118x95 cells at about 0.05 m: 764 free, 745 occupied
and 9,701 unknown. Its maximum clearance is only 0.115 m, below the unchanged
0.25 m requirement. The original preview visibly contains floor, but this does
not establish navigable free space. No simulated start, goal, path or motor
command was used. Even after fixing node association, this grid cannot justify
a route under the existing clearance requirement.

## Verification and retained failures

All 103 focused tests pass: 44 odometry/perception, 39 online-memory/semantic/search,
and 20 ROS sensor tests. They cover live/replay clock separation, missing-message
accounting, source-time rejection, bounded bursts, transaction rollback and old
journal compatibility. Independent checks decoded source images and all 11 PNG
crops, reconstructed causal TF, checked mm-to-meter points, verified all 54 raw
received grids/graphs and the actual ROS decision, and reopened old/new journals
without changing their bytes. Every owned child exited; no forced termination or
camera/SLAM process remained. Long-duration resource stability is still open.

The preceding attempts remain `INCOMPLETE`: attempt 01 exceeded the original
16-event queue; attempt 02 completed capture but exposed an unmatched odometry
message under the old strict replay check; attempt 03 exceeded 128 entries;
attempt 04 showed consecutive 5.789 s and 2.907 s storage stalls even with batching.
They are not counted as successful runs. The final run still reports transport
loss and a refusal, rather than claiming a working live object-search route.

Evidence: `data/outputs/live_search/steady_20260916/` (ignored/private), including
`failed_attempts.json`, source/config snapshots, timestamp CSV, rosbag,
`calibration.json`, `first_rgb.png`, raw `first_depth_mm.png`, `occupancy.png`,
source crops, the live query/receiver reports and six independent verification/
reopen reports. Journal SHA-256:
`e6f9a15fe76f542ad00d88c4b6650237fb0dd1c39b4db186c4aa5b5b121da41e`.
Only source, tests and documentation are committed.

Next: use this recording to resolve stationary map-node/observation association,
while keeping missing-source and unsafe-route refusals explicit.
