# Offline Frontier Search Fallback

Status: `VERIFIED` for minimum offline geometric exploration proposals on this
Jetson, 2026-09-11. Missing targets and unavailable object goals can now produce
a frontier observation goal and a checked route, with explicit start provenance.
No observation, new coverage or physical navigation has been performed.

## Run And View

Use the existing native environment and frozen goal preview, memory and map:

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/preview_frontier_search.py \
  --preview data/outputs/search_goal/m9_20260910/backpack/preview.json \
  --memory data/outputs/scene_memory/m6_20260910/memory.db \
  --mapping data/outputs/rtabmap_slam/mapping_02 \
  --simulated-start-xy 1.65 0.08366 \
  --output data/outputs/frontier_search/NEW_RUN
```

The start is the same explicitly simulated fixture used in the preceding
[route validation](search-route-preview.md). Replace it with `--start-node 1`
to reproduce the historical camera-start refusal. A camera projection is not
current robot localization, and invalid starts are not snapped into free space.
Choose a new output directory for every run; existing evidence is preserved.
No dependency, model, camera capture, ROS session or GPU inference is needed.

`frontier.json` retains the complete source preview and hash, original object
candidates and rejection reasons, map/pose identity, start provenance, frontier
groups, candidate counts, selected viewing ray and checked route. It explicitly
records `observation_executed: false` and `new_coverage_measured: false`.
`frontier.png` shows the map and the selected exploration detail when available.

```bash
xdg-open data/outputs/frontier_search/m10_20260911/backpack/frontier.png
```

Yellow squares mark free/unknown frontier cells. The cyan star is the start,
red cross the observation goal, orange diamond the selected frontier cell, and
orange outline the first unknown neighbor. The dashed orange arrow indicates
the assumed viewing direction; purple is the checked travel route. When start
and goal coincide, their markers overlap and no substantial route is visible.
This is an ordinary PNG and needs no WebGL.

## Boundary, Viewpoint And Search Rules

The existing read-only goal-preview loader revalidates memory, map/pose/export
hashes and original goal decisions. If any object goal is available, the result
is `NOT_NEEDED: object_goal_available`; this tool does not replace it with an
exploration goal or claim its route has been checked. When the source is
`NO_GOAL`, its absent-target or per-object rejection evidence remains intact,
and a separate geometric exploration proposal is attempted.

A frontier is a **free cell with an in-map cardinal unknown neighbor**.
Occupied cells and outside-map space are not frontiers. Four-connected frontier
cells form groups; diagonal contact does not join groups. IDs follow ascending
map-grid y/x order on this fixed artifact and are not permanent map identifiers.

Observation goals must pass the original **0.25 m** conservative clearance
policy. Frontier cells themselves need not pass it and are never relabeled as
safe goals. The initial viewing policy is fixed in one code constant:

- Look only along the four map axes, with a zero-width planar ray.
- All ray cells through the selected frontier must be free; the next cell must
  be unknown. Stop at the first unknown, occupied cell or map boundary.
- Keep the goal **0.30–0.75 m** from the frontier cell center. This stand-off is
  separate from the preceding object's 0.75–1.25 m stand-off policy.
- Rank candidates by straight-line start displacement, then frontier ID, goal
  y/x and frontier y/x. Use the first candidate whose route passes the existing
  four-direction whole-segment checks; retain any route rejections.

This is a restricted geometric baseline, not a sensor field-of-view model or
a prediction of information gain. Ranking does not optimize global path cost
across all candidates. A zero-length travel proposal is valid: an observation
direction can be proposed at the start, without inventing a need to move.
The starting heading is unknown, so no measured rotation angle is claimed.

| Result | Meaning |
| --- | --- |
| `EXPLORATION_READY` | A geometric observation goal and checked offline route exist |
| `NOT_NEEDED` | The source already supplies an object goal; no exploration attempted |
| `INVALID_START` | Start fails the existing grid/clearance checks |
| `NO_FRONTIER` | No free/unknown boundary or no viewpoint under the fixed policy |
| `NO_ROUTE` | Viewing candidates exist but none has a route from the explicit start |
| `INCOMPLETE` | Input, identity or processing error; nonzero exit |

Completed decisions and refusals exit zero. Input/provenance errors fail before
producing a valid proposal. The success status is recorded only after rendering
and final preview/memory hash checks. An exploration goal is not a newly found
object or proof that a remembered object is still present.

## Measured Acceptance

Evidence: `data/outputs/frontier_search/m10_20260911/`.

The unchanged 222x138 map contains **102 frontier cells in 70 groups**. None of
those boundary cells passes the original clearance requirement. Its 168
clearance-passing free cells produce **123 cardinal viewing candidates at 115
distinct goal cells** under the fixed range/visibility policy.

| Explicit simulated start | Selected goal | Frontier / first unknown cell | View / travel |
| --- | --- | --- | --- |
| [1.65,0.08366] m, grid [124,73] | Same grid cell | Group 39: [124,64] / [124,63] | -Y, yaw -pi/2; 0.45 m stand-off; approximately zero travel |
| [1.05,0.13366] m, grid [112,74] | [1.05,0.18366] m, grid [112,75] | Group 49: [106,75] / [105,75] | -X, yaw pi; 0.30 m stand-off; 0.05 m travel |

The first fixture is unchanged from M9. The second is the first clearance-valid
cell in y/x order that has no cardinal viewing candidate itself, chosen explicitly
to exercise the route handoff. Neither is measured robot localization.
The first ray contains 10 free cells and the second seven. Each selection needs
one route attempt. Exact minimum route clearances are **0.257391 / 0.275000 m**;
independent continuous lower bounds are **0.257391 / 0.273810 m**, both above
the assumed 0.25 m. The near-zero first length is approximately 5.13e-16 m from
floating-point representation of the explicit start and its cell center; it
is not a physical movement measurement.

Nine fresh frontier CLI processes cover:

- `backpack` absent, `refrigerator` without free cells in its stand-off band,
  and `sink` without sufficient goal clearance. All retain their different
  source reasons while returning the same geometry-only proposal from the same
  start. This is not semantic prioritization of unknown space.
- Repeated backpack selection, with identical decisions apart from timing;
  the second simulated start, with its 5 cm route; and camera node 1, refused
  as `INVALID_START: unknown_cell` without a goal.
- `chair`, returning `NOT_NEEDED` and preserving both existing object candidates.
- Two deliberately altered source previews: changed pose-export identity and
  reduced source clearance policy. Both exit 1 with `INCOMPLETE`, no proposal
  and no PNG. The other seven commands exit zero.

Independent code reads original PGM rows and reconstructs every frontier group
using a separate queue/set implementation. All groups and IDs match. Selected
ray cells, first unknown neighbors, cardinal orientation, metric stand-off,
goal coordinates, route endpoints and free-cell membership pass. Point-to-square
distances sampled along each travel segment at no more than 2.5 mm spacing,
minus half the sample interval, certify clearance between samples as well.
All input hashes remain unchanged; generated PNGs decode and both proposal
overlays were visually inspected.

The seven successful mixed frontier/refusal commands had operation-time
min/median/P95/max **1264.754 / 1783.776 / 1827.173 / 1836.712 ms** and process
wall-time **2071.637 / 2574.809 / 2623.049 / 2623.705 ms**, including hashing
and PNG rendering; wall time also includes dependency startup. These functional
timings do not establish sustained performance or active exploration.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/search -v
```

All **48 tests** pass: 16 new frontier tests and the 32 goal/route regressions.
Known cases cover four-connected boundaries, outside/occupied/diagonal handling,
ray occlusion and first unknown, range/clearance limits, absent or too-small
frontiers, disconnected viewing regions, invalid starts and deterministic ties.
Separate original goal and route CLI regressions also reproduce their previous
decisions after the shared backdrop/direction changes. See `integration.json`,
`verify_frontiers.py`, `unit_tests.log` and per-command JSON/PNG/logs. All room
data, generated outputs and altered-input fixtures remain local and ignored.

The existing map/floor uncertainty, tracking gaps and provisional object labels
remain. Actual camera starts still fall in unknown cells. This step proposes
where to look using map geometry; it does not acquire an image, measure new
coverage, resolve object identity or execute a robot maneuver. Next: connect
the existing goal, route and frontier tools into one reproducible offline
search-demo command with a single inspectable result.
