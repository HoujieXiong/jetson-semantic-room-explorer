# Offline Route To An Object Goal

Status: `VERIFIED` for minimum offline route validation on this Jetson,
2026-09-11. An explicit simulated start connects to both saved chair goals;
the recorded camera start is refused because its map cell is unknown.
Physical navigation and current localization remain unverified.

## Run And Inspect

The script consumes the preceding [goal preview](search-goal-preview.md), the
same read-only memory, and the frozen occupancy export. No dependency, capture,
ROS session, GPU inference or robot motion is needed. Start selection is required:
use either a recorded camera node or explicitly simulated map x/y coordinates.

Reproduce the recorded-start refusal:

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/preview_search_route.py \
  --preview data/outputs/search_goal/m9_20260910/chair/preview.json \
  --memory data/outputs/scene_memory/m6_20260910/memory.db \
  --mapping data/outputs/rtabmap_slam/mapping_02 \
  --start-node 1 \
  --output data/outputs/search_route/NEW_CAMERA_RUN
```

For the simulated planning fixture, replace `--start-node 1` with
`--simulated-start-xy 1.65 0.08366`, and choose another new output directory.
These coordinates were selected from the existing clearance mask: the lowest-y,
then lowest-x passing cell, [124,73]. They are not a relocated camera pose or a
measurement of where a robot stands. The same start is used for every query.

Each run saves `route.json` and an `object_ID.png` for every candidate; absent
targets save `overview.png`. The JSON retains the entire source goal preview,
its hash, start provenance, coordinate frame/units, endpoint checks, path,
length, minimum segment clearance, search expansions and planning time.
Existing output directories are refused. Open the measured route on the Jetson:

```bash
xdg-open data/outputs/search_route/m9_20260911/simulated_chair/object_2.png
```

The cyan star is the explicitly labeled start, purple line the checked route,
red cross the goal and orange diamond the remembered surface point. The red
arrow only shows the goal's facing direction; it is not an additional route.
PNG viewing uses the same normal image viewer as the preceding goal preview.

## Start, Goal And Route Contract

Before planning, the script reopens memory and requires its byte identity,
queried candidates and source context to match the saved goal preview. It
reuses the existing map/pose/export hash checks and reproduces each saved goal
decision with the original policy. Changed coordinates, omitted candidates,
incompatible provenance, changed policy and incomplete previews are errors.
Map and memory files remain read-only.

`--start-node` reads the selected frozen camera pose, checks its map ID and
export timestamp against the original nanosecond source timestamp, and retains
position, quaternion and pose-file hash. Only its map x/y translation is
projected into the planar check. A historical camera pose is not a robot-base
pose or current localization. `--simulated-start-xy` is explicitly labeled as
a planning fixture and carries no fabricated source time.

The grid decoding and fixed **0.25 m** conservative cell-center clearance
policy are reused from the goal preview. Start and goal cells must be free and
pass this policy; their exact metric points must also clear blocked cell areas
and map boundaries. An invalid start is never moved into a nearby free cell.
The goal must remain at the preceding preview's cell center. For a non-center
start, the output keeps its exact input coordinates and explicitly connects
to its cell center, moving x first then y and checking both segments.

Breadth-first search considers four cardinal neighbors in a fixed order, with
equal cost per cell. It visits each reachable cell at most once. There are no
diagonal moves, corner cutting or path smoothing. Each accepted edge is checked
against unknown/occupied cell **squares** and the map boundary, including its
interior. For an axis-aligned segment, interval distances in x/y give the exact
distance to each blocked square. This adds a segment check to the preceding
cell-center clearance check. The resulting grid path is shortest under these
movement/clearance rules; it is not a motion or turning plan for a physical base.

| Outcome | Meaning |
| --- | --- |
| `ROUTE_READY` | At least one candidate has a checked offline route |
| `NO_ROUTE` | No candidate has a route; inspect per-object decisions |
| `INVALID_START` / `INVALID_GOAL` | Per-object endpoint refusal with cell/clearance reason |
| `NO_GOAL` | The preceding target-absent/no-goal outcome remains unchanged |
| `INCOMPLETE` | Input/identity/processing error; nonzero process exit |

Completed refusals exit zero and contain no fabricated path or cost. Disconnected
valid endpoints return `NO_ROUTE: disconnected_under_route_policy`. Unknown,
occupied, outside and insufficient-clearance endpoints have distinct reasons.

## Measured Acceptance

Evidence: `data/outputs/search_route/m9_20260911/`.

The frozen 222x138 grid at 0.05 m/cell has 1122 free cells in **76** four-connected
components. The existing clearance mask has **168** cells in one component.
All **48** saved camera translations project into unknown cells. This is an
observed mismatch between the occupancy artifact and potential starts; it does
not establish that those real-world positions are physically obstructed.

Camera node 1 retains map x/y **[-0.002109,-0.03223] m**, cell **[91,71]**,
and original timestamp **1789080202178160000 ns**. Both chair candidates return
`INVALID_START: unknown_cell`, with no path. It is not silently snapped into
the nearby free component.

For the explicit simulated start **[1.65,0.08366] m**, both chair IDs 2/3 reach
their shared goal **[1.15,0.63366] m**. Each path has **22 grid cells**, **21
cardinal edges**, length **1.05 m**, and **163** search expansions. Its length
meets the Manhattan lower bound, independently establishing shortest length for
this start/goal pair. Exact minimum segment clearance is **0.257391 m**.

An independent check indexes original PGM pixels and evaluates point-to-square
distances along every segment, at spacing no greater than 2.5 mm. Subtracting
half each sample interval gives a continuous clearance certificate because
distance to the blocked set is 1-Lipschitz. The lower bound is **0.256141 m**,
above the assumed 0.25 m requirement. Both endpoints, cardinal connectivity,
metric length and free-cell membership also pass. This verifies map geometry,
not physical clearance or map accuracy.

Eight fresh bounded route CLI processes covered the camera start, simulated
chair route and repetition, refrigerator/sink/backpack no-goal cases, and two
deliberately altered preview copies. Changed goal coordinates and pose-export
identity fail with exit 1 and `INCOMPLETE`, before producing any route or PNG.
The other six runs exit zero. Repeated chair decisions are identical; all input
hashes remain unchanged. A separate original goal-preview CLI regression returns
the same candidates/decisions after the shared renderer change. Generated PNGs
decode, and route/refusal overlays were visually inspected.

The first independent verifier contained a chained floating-point comparison
that canceled its intended upper-bound tolerance. Its `INCOMPLETE` report and
traceback remain in `integration_initial.json` and `verification_initial.log`.
Correcting that assertion and rechecking the saved CLI artifacts passed;
the route implementation did not change to obtain this result.

The first two successful route searches took **307.954 / 307.605 ms**. Across
six successful mixed route/refusal/render commands, operation-time
min/median/P95/max was **1236.469 / 2493.287 / 3353.786 / 3354.477 ms**;
process wall time was **2022.933 / 3300.157 / 4177.882 / 4179.149 ms**.
These include hashing and rendering; wall time also includes dependency startup.
They are functional timings, not a live navigation or scaling benchmark.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/search -v
```

All **32 tests** pass: 16 preceding goal tests and 16 new route/start tests.
Known cases cover shortest open paths, a required detour, unknown/occupied
barriers, diagonal corners, segment interiors, map boundaries, exact-start
connectors, zero-length paths, invalid endpoints, repeatability and source
timestamp/map disagreement. `preflight.json`, `integration.json`, the local
verifier, unit log and per-command JSON/PNG/logs preserve measured evidence.
Generated room data stays local and ignored.

The pipeline now distinguishes object location, observation goal and an offline
route from an explicit start. Actual camera projections remain invalid starts
on this export; physical footprint, floor/map accuracy, target visibility,
turn feasibility, current localization and Nav2 remain unverified. The subsequent
[offline frontier fallback](frontier-search-preview.md) now uses these route
checks for missing targets or unavailable object goals.
