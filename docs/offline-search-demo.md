# Single-Command Offline Search Demo

Status: `VERIFIED` on the Jetson, 2026-09-11, using frozen scene memory and map
artifacts. One command queries memory, generates object goals, then checks
object routes or proposes geometric exploration. It saves a decision summary
and the existing stage reports and PNGs. This does not execute observations or
motion, update memory, or rebuild the map.

## Run And Inspect

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/run_offline_search.py \
  --memory data/outputs/scene_memory/m6_20260910/memory.db \
  --mapping data/outputs/rtabmap_slam/mapping_02 \
  --label chair \
  --simulated-start-xy 1.65 0.08366 \
  --output data/outputs/offline_search/NEW_RUN
```

Choose a new output directory for each invocation; reusing one fails without
overwriting evidence. This example start is an explicit simulated fixture, not
measured localization. Replace the label with `backpack`, `refrigerator` or
`sink` to exercise exploration. Replace `--simulated-start-xy 1.65 0.08366`
with `--start-node 1` to reproduce the recorded-camera refusal. A start is
required: there is no automatic choice or relocation into free space.

Open the generated `search.json` to see the branch, reason, original query
candidate IDs, no-goal reasons, exact start provenance and per-candidate outcomes.
Its `stages` entries link to JSON reports and PNGs **relative to `search.json`**,
and include report SHA256 hashes for completed runs. Full source observations,
map/pose identity, policies, route points and frontier-ray witnesses remain in
those existing reports. Console output includes the summary path and outcomes.

Already measured examples can be opened directly on the Jetson display:

```bash
xdg-open data/outputs/offline_search/demo_20260911/chair/route/object_2.png
xdg-open data/outputs/offline_search/demo_20260911/backpack/frontier/frontier.png
```

These ordinary PNGs use the existing viewers. The command needs only the local
Python environment, memory and frozen map; it does not start ROS or inference.

## Decision Contract

| Goal-preview result | Branch | Behavior |
| --- | --- | --- |
| `PREVIEW_READY` | `object_route` | Check routes to all object goals; retain every candidate outcome |
| `NO_GOAL`, absent target | `frontier` | Retain `target_not_in_memory` and propose geometric exploration |
| `NO_GOAL`, remembered candidates | `frontier` | Retain each object-goal rejection and propose exploration |
| Source or processing error | No completed decision | Raise the error; preserve `INCOMPLETE` and the failed stage |

The top-level `status` preserves the selected stage's result. In the object
branch, `ROUTE_READY` means at least one candidate route exists; `NO_ROUTE`
means none exists. Read **every `outcomes` entry**: camera node 1 produces
top-level `NO_ROUTE` with `INVALID_START: unknown_cell` for both chairs. A route
failure does not switch to frontier search. The frontier branch retains
`EXPLORATION_READY`, `INVALID_START`, `NO_FRONTIER` or `NO_ROUTE` directly.

Completed proposals and refusals exit zero. Input/provenance/processing errors
exit nonzero. Once a new run directory exists, `search.json` stays `INCOMPLETE`
on error, with `active_stage`, attempted report paths and an error message for
expected input/I/O/database failures; the exception still propagates to the log.
Child files may be partial and must not be treated as an accepted result.
Argument errors and an already existing output directory fail before creating
new evidence. Reusing a directory leaves its previous result untouched; an old
successful report is not success for the rejected invocation.

`dry_run` is true; `observation_executed`, `motion_executed` and
`new_coverage_measured` are false. Labels use the existing trimmed, case-folded
exact label query. No open-vocabulary matching or object-identity resolution is
added. Goal stand-off, clearance, route checks and frontier rules are unchanged;
see [goals](search-goal-preview.md), [routes](search-route-preview.md) and
[frontiers](frontier-search-preview.md).

## Measured Acceptance

Evidence: `data/outputs/offline_search/demo_20260911/`, including `integration.json`,
`verify_demo.py`, `verification.log`, `unit_tests.log`, `final_check.json`,
per-command logs and generated run directories. Room evidence remains ignored.

All **63 search tests** pass, including 15 new composition tests. The new tests
exercise real temporary SQLite memory and synthetic map files through the
existing search functions; only PNG rendering is stubbed for unit tests. Real
CLI acceptance includes rendering. Source corruption, a changed generated goal,
image-write failure, missing memory, invalid starts, disconnected routes,
unavailable frontiers and output reuse have explicit assertions.

Twelve fresh CLI processes, each bounded at 60 seconds, verify:

- Chair: both provisional IDs 2/3 retain the same [1.15,0.63366] m goal and
  **1.05 m / 22-cell** route from simulated [1.65,0.08366] m.
- Backpack, refrigerator and sink: the same in-place -Y proposal to frontier
  group 39, preserving absent-target/no-free-cell/insufficient-clearance reasons.
- Repeated chair and backpack queries: identical decisions apart from timing.
- Backpack from simulated [1.05,0.13366] m: the preceding **0.05 m** route to a
  -X view of group 49.
- Camera node 1 for chair and backpack: original [-0.002109,-0.03223] m and
  timestamp 1789080202178160000 ns retained; unknown-cell start refused.
- An isolated memory copy with an incompatible pose identity: exit 1,
  `INCOMPLETE` at the goal stage, no route/frontier branch or PNG.
- Missing start: argument-parser exit 2, no output directory.
- Reused chair output directory: exit 1, all earlier evidence unchanged.

Nine normal commands exit zero. All new goal decisions and the corresponding
route/frontier decisions match the preceding measured outputs; the three
existing planning scripts are byte-identical. All input hashes remain unchanged.
All **24 PNGs** decode; chair route, backpack frontier and camera-chair refusal
overlays were visually inspected.

Across the nine normal commands, operation-time min/median/P95/max is
**1801.753/2708.615/5378.207/5385.983 ms**; process wall time is
**2573.439/3527.471/6185.650/6185.835 ms**. These mixed queries include repeated
source validation and one or two images per stage; wall time includes Python
dependency startup. They are functional measurements, not a live throughput or
sustained resource benchmark. Runtime: Python 3.10.12, NumPy 1.26.4 and OpenCV
4.11.0 on aarch64, using the existing SciPy/Matplotlib/PyYAML dependencies.

The result connects frozen search interfaces. Tracking gaps, provisional labels
and chair identity, map/floor accuracy, sensor visibility and real localization
remain unresolved. The next validation is chronological replay of the saved
observations into a separate memory, checking how new evidence changes the search
decision without claiming that replayed observations were caused by these goals.
