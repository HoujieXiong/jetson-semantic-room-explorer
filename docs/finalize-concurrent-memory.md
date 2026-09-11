# Concurrent observations to frozen memory and search

Status: `VERIFIED` on the Jetson Orin Nano on 2026-09-11 for post-run
finalization of the new concurrent SLAM/perception trial. The detector is not
rerun. This extends the [concurrent trial](concurrent-rgbd-perception.md) through
SQLite persistence and search against that trial's own final map.

## Contract

`scripts/finalize_concurrent_observations.py` matches original concurrent
observations to exported map nodes by exact source timestamp. It reuses
`load_frame`, `depth_observation` and the existing memory validator. Run/report,
map, poses, frame manifest, model, source pixel, calibration and depth checks
must agree before a completed report can be imported.

For each selected node, every detection and depth rejection is retained.
Accepted camera surface points are transformed by the final optimized pose.
The frame retains `online_pose` and the original result completion time; each
accepted detection retains `online_map_point_m` beside its final `map_point_m`.
Both versions refer to the same source observation. This is a frozen report
produced after SLAM finishes, not causal online memory or a second inference run.

Nodes without processed inference, an accepted online pose or a validated
mapping association are explicitly excluded. Missing online evidence is not
filled in from later poses. A mismatch raises an error and leaves an
`INCOMPLETE` report. An existing output directory is refused without rewriting
it. A valid run with no accepted observations returns `NO_VALID_OBSERVATIONS`
and CLI exit 2; it cannot be imported as measured memory.

## Reproduce with the existing local inputs

The verified source run is:

```text
data/outputs/concurrent_rgbd/trial_20260911/attempt_02
```

Its database was reopened, exported and checked using the existing local
`check_database.py`, `export_map.py` and `check_exports.py` helpers under
`data/outputs/rtabmap_slam/`, after sourcing `scripts/rtabmap_odom_env.bash`.
Those steps have already completed for this source. The original database hash
is unchanged. The original RGB-D pixels were then extracted with:

```bash
source scripts/rtabmap_odom_env.bash
trial_dir=data/outputs/concurrent_rgbd/trial_20260911/attempt_02
finalized_dir=data/outputs/concurrent_rgbd/REPLACE_WITH_NEW_FINALIZATION

/usr/bin/python3 scripts/extract_mapped_rgbd.py \
  --bag data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02 \
  --reference data/outputs/femto_ros2/room_walk_20260910T223548Z/room_walk_02_bag.json \
  --mapping-run "$trial_dir" --output "$finalized_dir/frames"

.venv/bin/python scripts/finalize_concurrent_observations.py \
  --run "$trial_dir" --frames "$finalized_dir/frames/frames.json" \
  --output "$finalized_dir/observations"

.venv/bin/python scripts/scene_memory.py --db "$finalized_dir/memory.db" \
  import "$finalized_dir/observations/observations.json"
.venv/bin/python scripts/scene_memory.py --db "$finalized_dir/memory.db" find bottle

.venv/bin/python scripts/run_offline_search.py \
  --memory "$finalized_dir/memory.db" --mapping "$trial_dir" \
  --label bottle --simulated-start-xy 1.5 0.43366000000000016 \
  --output "$finalized_dir/bottle_search"
```

Choose a fresh output name. These simulated coordinates belong only to this
map's measured test fixture; they are not a measured robot location. Replace
the simulated-start option with `--start-node 1` in a separate invocation to
reproduce the recorded-camera-start refusal. Use another output directory for
each search. The actual acceptance directory uses `primary/observations.json`
and `repeat/observations.json` for its two finalizations.

## Measured results

| Check | Result |
| --- | --- |
| Reopened map | SQLite integrity passes; 76 stored nodes |
| Final export | 64 optimized camera poses, 50,537 grayscale points, 64 depth images |
| Occupancy | 223 x 140 cells at 0.05 m; 1,422 free, 6,064 occupied, 23,734 unknown |
| Original RGB-D extraction | 64 frames; all 58,982,400 raw depth pixels equal the exported depth |
| Source selection | 62 nodes; node 1 lacks accepted online map TF, node 44 has no processed inference after a queue drop |
| Selected detections | 252 total: 189 accepted depths, 63 explicit depth rejections |
| Finalization time | 29.367 s for the first invocation, including source checks; no model inference |
| Independent projection | Maximum coordinate difference 8.882e-16 m; an arithmetic check, not physical accuracy |
| Online-to-final point shift | Median 0.022823 m, P95 0.081945 m, maximum 0.157852 m |
| New SQLite memory | 62 frames, 252 observations, 46 provisional records, 185 supporting observations |
| Association accounting | 139 nearest matches, 46 new records, four same-frame overlaps without extra support, 63 depth rejections |
| Initial import time | 128.575 ms |
| Repeated finalization/import | Identical report except elapsed time; zero added frames and byte-identical memory |

The 46 records do not establish 46 distinct physical objects. Query and search
results are based on the existing closed-vocabulary labels and geometric
association policy, with no manual identity labels.

Fresh-process queries return six bottle candidates and four chair candidates.
Bottle IDs/support counts are `13/8, 38/2, 4/13, 3/5, 29/1, 14/1`; chair results
are `10/16, 11/12, 30/1, 28/1`. Backpack is absent from this memory, which does
not prove it is absent from the room.

The explicit simulated start `[1.5, 0.43366000000000016]` m is the free-cell
center with maximum conservative clearance, with ties resolved by grid y/x.
Its clearance lower bound is 0.523662 m; 186 free cells pass the assumed 0.25 m
requirement. Existing goal, route and frontier policies are unchanged.

| Search invocation | Checked outcome |
| --- | --- |
| Bottle, simulated start | `ROUTE_READY` for all six candidates; route lengths 0.15-0.55 m |
| Chair, simulated start | `ROUTE_READY` for all four candidates; route lengths 0.15-0.45 m |
| Backpack, simulated start | `EXPLORATION_READY`; geometric frontier fallback with a 0.05 m preview route |
| Bottle, recorded camera node 1 | `NO_ROUTE`; all six candidates have `INVALID_START: unknown_cell` |

All 64 recorded camera translations project into unknown cells. No start is
snapped to free space. That observation alone does not diagnose floor alignment;
coverage and the relation between a handheld camera and traversable floor also
need physical validation. No route was executed or new coverage collected.

## Verification and artifacts

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/memory -v
```

All 29 tests pass in 0.519 s, including 12 new finalization cases. They use real
depth validation and SQLite across a controlled mapped-frame loading boundary.
Known transforms check online/final separation and reopened metric means;
failure cases cover missing/duplicate sources, corrupt hashes, pixels, timestamps,
depth evidence, policy, units, changed weights, mid-run mutation and output reuse.

The Jetson integration additionally checks real source pixels and every retained
detection, independently projects the depth samples, compares repeated outputs,
reopens SQLite, checks duplicate imports and validates matching-map search stages.
Wrong-map finalization and output reuse both exit 1 as expected. All 34 search
PNGs decode. The map overview, bottle route, frontier preview and actual-start
refusal were visually inspected. Source bag, model, map and observation evidence
remain unchanged.

Local evidence, excluded from Git:

- `data/outputs/concurrent_rgbd/trial_20260911/attempt_02/`: database/export
  reports and logs, `export/`, `sample_database_image.png`, `map_preview.png`.
- `data/outputs/concurrent_rgbd/finalization_20260911/`: extracted frames,
  primary/repeat observations, memory, import/query reports, start fixture,
  four search directories, expected-failure output, `verify_finalization.py`,
  `integration.json`, test/command logs and `final_check.json`.

For example, open the ordinary PNG in the Jetson desktop image viewer:

```bash
xdg-open data/outputs/concurrent_rgbd/finalization_20260911/bottle_search/route/object_13.png
```

## Remaining acceptance and next data collection

The full existing-data slice now runs concurrent perception/SLAM, freezes its
final map, persists source-associated observations and previews search. Tracking
failures in the old recording remain; 0.25x playback does not establish real-time
throughput. The system still lacks causal online memory/search, measured object
identity/physical geometry, open-vocabulary queries, CuTR feasibility results and
physical navigation. A mobile base is not present.

The next action is one controlled, measured camera translation recording, with
human help. A proposed 60-second sequence is: remain still for five seconds,
translate slowly between marks about 1 m apart over 15 seconds while keeping
the camera level and its heading fixed, remain still for five seconds, translate
back over 15 seconds, then remain still until recording closes. Use a clear,
cable-safe lateral path; a full room loop or a fast turn is unnecessary. Record
the actual mark spacing and uncertainty, camera reference point/height and any
handling deviations. The operator must confirm readiness before capture starts.

The existing local bounded recorder and source-contract checks are available
under `data/outputs/femto_ros2/room_walk_20260910T223548Z/run_check.py` and
`tests/check_femto_rosbag.py`; use a fresh evidence directory. Predeclare the
measurement windows and quality criteria before the new trial. Compare tracked
and lost intervals, endpoint displacement and return error with that measured
reference, then run the existing pipeline on the new bag. The present source
does not contain a precise physical displacement reference, and software checks
cannot supply one retroactively.

The lesson from this step is that an unchanged camera observation can move in
map coordinates after graph optimization. Source time and a consistent pose
version are necessary for meaningful fusion; internally consistent arithmetic
alone does not establish room-scale accuracy.
