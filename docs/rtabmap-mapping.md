# Minimum RTAB-Map Mapping Integration

This step connects the verified Femto RGB-D recording and odometry to the ROS
mapping node. Its acceptance is a nonempty database that can be reopened, a
geometric export, and timestamped map-to-camera transforms for mapped
observations. Partial coverage is reported explicitly. Tracking continuity,
geometric accuracy, loop consistency and real-time throughput are later quality
goals; the next component after this contract passes is YOLO plus depth.

## Runtime And Input

Use the existing isolated environment in `scripts/rtabmap_odom_env.bash`.
RTAB-Map core and ROS nodes are version 0.23.7 with system Humble cv_bridge and
OpenCV 4.5d, separate from the camera overlay. The four approved additional
ARM64 packages were downloaded at their pinned versions, hash-verified and
extracted into `~/projects/rtabmap_odom_ws/deps`. Archive paths, links and potential
overwrites were checked before extraction. No system installation or maintainer
script ran. The manifest, download log and verified archive records are under
`data/outputs/rtabmap_slam/preflight_20260910/`.

The original 94.487476504-second `room_walk_02` bag contains 1411 verified RGB-D
pairs: rectified 1280x720 color and registered 1280x720 depth in millimeters,
with zero invalid. See [the camera contract](camera-ros2.md) and
[odometry evidence](rtabmap-odometry.md). This integration uses no live camera.

The mapping configuration layers the measured `Odom/GuessMotion="false"` setting
over the existing odometry configuration. Other odometry settings stay intact,
including 5 ms RGB/depth synchronization and disabled automatic reset.
The odometry node already publishes `/odom_rgbd_image` with the same aggregate
stamp as `/odom`. Mapping subscribes to that pair with exact synchronization,
reusing the accepted frame association without a second synchronization node.
The original individual RGB/depth stamps remain in the input bag.
The measured frame bundle and database contain a grayscale image, rather than
the original color image. Depth is stored with the upstream RVL codec. Use the
original color bag for YOLO; the geometric export is also grayscale. Neither
image encoding nor database compression should be assumed from the topic name.

Mapping updates at the upstream default 1 Hz in source time; this is separate
from the 15 FPS camera stream and the 0.25x replay rate. Local occupancy grids
are saved for export. No IMU, marker detections or external pose estimates are
provided. Their message libraries are declared dependencies of the mapping node.

## Run On This Jetson

Use a new output directory for every run and keep the camera driver stopped.
Source the environment in each of four fresh terminals. The commands below
assume `data/outputs/rtabmap_slam/NEW_RUN` does not exist yet.

Terminal 1 starts odometry:

```bash
source scripts/rtabmap_odom_env.bash
"${RTABMAP_ODOM_PREFIX}/lib/rtabmap_odom/rgbd_odometry" --ros-args \
  --params-file config/rtabmap_rgbd_odometry.yaml \
  --params-file config/rtabmap_rgbd_mapping.yaml \
  -r rgb/image:=/camera/color/image_raw \
  -r depth/image:=/camera/depth/image_raw \
  -r rgb/camera_info:=/camera/color/camera_info
```

Terminal 2 starts mapping with a new database:

```bash
source scripts/rtabmap_odom_env.bash
mkdir data/outputs/rtabmap_slam/NEW_RUN
"${RTABMAP_ODOM_PREFIX}/lib/rtabmap_slam/rtabmap" --ros-args \
  --params-file config/rtabmap_rgbd_mapping.yaml \
  -p database_path:="${PWD}/data/outputs/rtabmap_slam/NEW_RUN/map.db" \
  -r rgbd_image:=/odom_rgbd_image
```

Terminal 3 runs the bounded contract measurement:

```bash
source scripts/rtabmap_odom_env.bash
/usr/bin/python3 tests/check_rtabmap_mapping.py \
  --reference data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02_bag.json \
  --duration 403 \
  --output data/outputs/rtabmap_slam/NEW_RUN/measurement.json
```

Start Terminal 4 within about five seconds of the checker:

```bash
source scripts/rtabmap_odom_env.bash
ros2 bag play data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02 \
  --rate 0.25 --clock 30 --delay 2 --read-ahead-queue-size 40 \
  --wait-for-all-acked 5000 --disable-keyboard-controls
```

After playback and measurement finish, save each node's actual parameters. The
local `query_parameters.py` uses bounded direct service requests, avoiding the
CLI discovery failure observed in this session:

```bash
/usr/bin/python3 data/outputs/rtabmap_slam/query_parameters.py \
  /rtabmap data/outputs/rtabmap_slam/NEW_RUN/mapping_parameters.yaml
/usr/bin/python3 data/outputs/rtabmap_slam/query_parameters.py \
  /rgbd_odometry data/outputs/rtabmap_slam/NEW_RUN/odometry_parameters.yaml
```

Stop mapping with Ctrl-C and wait
for its database-save completion, then stop odometry. Inspect every exit code.
Do not overwrite a previous database or use `delete_db_on_start` for these runs.

The local bounded harness `data/outputs/rtabmap_slam/run_mapping.py` automates the
same process order, captures commands/configs/parameters/library mappings and
resource samples, and closes all children in a `finally` block:

```bash
source scripts/rtabmap_odom_env.bash
/usr/bin/python3 data/outputs/rtabmap_slam/run_mapping.py NEW_ATTEMPT 0.25
```

## Measurement Contract

`tests/check_rtabmap_mapping.py` reuses the odometry checker subscriptions,
source-pair/hash checks, simulated clock, pose validity and pose/TF equality.
It additionally records `/info`, `/mapGraph` and `map -> odom` TF, validates the
map-to-optical-camera chain at mapped source stamps, and records observations
excluded for missing timestamped TF. Invalid/lost poses must not become mapped
observations. An empty mapping graph cannot pass on odometry output alone.

RTAB-Map stores time as double-precision seconds internally. Its `/info` stamps
can differ slightly from the original integer nanoseconds: the first run measured
at most 218 ns. Association permits only two double-precision ULPs plus 1 ns
(478 ns at these epoch stamps), not a millisecond-scale synchronization window.
Both original and mapping stamps and their difference are retained. TF is queried
at the original source stamp. The odometry input/output stamp checks remain exact.

The JSON retains mapping statistics, graph versions, explicit losses and
source-time transforms. The companion trajectory CSV remains in the **odom**
frame; map-frame optical-camera observations are separately named in the JSON.
Online TF and final optimized graph poses have different meanings: later graph
optimization can revise historical poses. Do not silently mix those estimates.

`status: MEASURED` establishes the measurement contract only. Database reopening,
geometry export and artifact inspection are separate acceptance checks.
Reported loop closures are algorithm outputs, not independent geometric proof.

Focused tests:

```bash
source scripts/rtabmap_odom_env.bash
/usr/bin/python3 -m unittest discover -s tests/odometry -v
```

The mapping tests cover a known rotation/translation composition, timestamp
mismatch, lost/null poses, missing map TF, empty maps, unexpected TF publishers
and preservation of incomplete evidence.

## Measured Integration, 2026-09-10

The minimum integration contract is **VERIFIED** on this Jetson using the second
mapping run and subsequent database/export checks. This is a partial map.

| Measurement | Result |
| --- | --- |
| Input / processed RGB-D pairs | 1411 / 1410; final pair has no result |
| Tracked / lost odometry results | 858 / 552 |
| Observed loss, source offsets | 18.089–49.376 s; 88.772–94.467 s |
| Stored database nodes / final graph poses | 57 / 48 |
| Database size | 41791488 bytes |
| Mapping info / graph messages | 57 / 57 |
| Validated source-time map/optical-camera observations | 56 |
| Observations excluded for unavailable map TF | 1, the initial observation |
| Maximum map/source timestamp rounding difference | 218 ns |
| Exported point cloud | 45733 finite points, coordinates in meters |
| Exported robot / optical-camera poses | 48 / 48 |
| Occupancy grid | 222 × 138 cells at 0.05 m/cell |
| Reported global loop closures / proximity detections | 6 / 25; not independently confirmed |
| Odometry processing median / P95 / max | 215.34 / 258.28 / 301.75 ms |
| Mapping core processing median / P95 / max | 201.17 / 308.10 / 495.53 ms, for the 57 updates |
| Odometry RSS / descriptors / threads | 151476–331076 KiB / 19 / 31–36 |
| Mapping RSS / descriptors / threads | 172840–405704 KiB / 20 / 31–63 |

The database passes SQLite integrity checks. All stored node times associate
with tracked source outputs within floating-point timestamp precision. All 57
nodes retain image, depth and calibration data. The upstream exporter decoded
the RVL depth; all 921600 pixels of the first exported depth frame equal the
corresponding original bag image, including invalid zeros. This retains the
previously verified millimeter unit contract.

The exporter reused stored optimized poses (`--opt 2`). Exported robot poses
match the final published graph within text-export precision. A copy of the
database was opened in read-only localization mode and queried through the ROS
map service: the same 48 graph node IDs and 72 links were returned. The requested
mapping settings match the directly queried parameters. Exporting and reopening
left the respective database files unchanged. The initial observation lacks
online map TF and is excluded from the validated-observation list; do not treat
the later availability of a final optimized pose as proof of earlier live TF.

All replay/checker/odometry/mapping processes exited 0 in the second run, without
forced termination, and the final process inspection found none remaining. The
run took 419.274 s including startup and shutdown. **Its original harness report
remains `INCOMPLETE`** because a late CLI mapping-parameter query returned 1.
Parameter queries and configuration loading were then verified through direct
ROS services during database reopening. The local harness now uses that service
helper and retains query logs; the revised whole harness was not replayed again.

The first full run remains separately recorded as `INCOMPLETE`: its checker
incorrectly required exact nanosecond equality for mapping statistics. The
measured rounding difference was at most 218 ns. After the bounded precision
fix, 22 tests passed and the second full replay's measurement passed. A real ROS
no-input check exited 1 and retained an `INCOMPLETE` report with empty mapping
evidence. An earlier startup CLI timeout and an initial database inspection that
assumed RGB/PNG storage are also preserved; direct node inspection and upstream
image decoding resolved those assumptions without a new dependency.

Known limits: the map has substantial tracking gaps, the retained images/cloud
are grayscale, and loop detections have no independent geometric confirmation.
The grid is an export for inspection, not a navigation acceptance result. The
integration uses extra serialization and mapping work, so this run is not a
controlled performance comparison with odometry alone. No real-time or long-run
resource-leak result is claimed. Further tuning is deferred under the user's
pipeline-first direction.

## Artifacts And Export Reproduction

Evidence root: `data/outputs/rtabmap_slam/` (ignored and local):

- `preflight_20260910/`: dependency manifest/preparation, node inspection, test
  logs and real no-input failure evidence.
- `mapping_01/`: original checker failure, database and stamp diagnosis.
- `mapping_02/`: `measurement.json` / `.csv`, `map.db`, all process logs, resource
  samples, exact configuration and implementation snapshots, database/depth/
  export checks, `reopen/`, `integration.json` and the final process check.
- `mapping_02/export/`: `room_cloud.ply`, `room.pgm` / `.yaml`, robot/camera pose
  text files, decoded image/depth folders and calibration exports.
- `mapping_02/map_preview.png` / `.pdf`: inspected partial-map preview, with
  optimized keyframes and the exported occupancy grid.
- `run_mapping.py`, `query_parameters.py`, `check_database.py`, `export_map.py`,
  `check_depth_source.py`, `check_exports.py`, `reopen_map.py`: actual local
  orchestration, export and artifact verification. `run_mapping_used.py` in the
  second run preserves the harness used before its metadata-query correction.

After shutting down the mapping node, this reproduces the upstream export into
a **new** directory, leaving the database unchanged:

```bash
source scripts/rtabmap_odom_env.bash
mkdir data/outputs/rtabmap_slam/NEW_RUN/export
"${RTABMAP_ODOM_PREFIX}/bin/rtabmap-export" \
  --cloud --poses --poses_camera --map --images_id --ascii --opt 2 \
  --decimation 4 --max_range 5 --voxel 0.05 --output room \
  --output_dir data/outputs/rtabmap_slam/NEW_RUN/export \
  data/outputs/rtabmap_slam/NEW_RUN/map.db
```

Next: use original color RGB-D frames associated with valid mapped node IDs to
run YOLOv8n and produce the first camera-frame and map-frame 3D object observation.
For an offline result, identify the frozen optimized graph/database used and join
poses by node ID; rounded pose-text timestamps are not original nanoseconds.
