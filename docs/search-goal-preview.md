# Offline Object Search Goal Preview

Status: `VERIFIED` for the minimum offline memory-to-goal interface on this
Jetson, 2026-09-10. Known objects produce either a map-cell-checked observation
position or an explicit no-goal result. This does not verify navigation.

## Run And View

Use the existing native environment; no dependency, model or driver was added.
The script reuses the read-only memory query and existing file-hash helper.
It needs neither a camera nor ROS, GPU access, WebGL or a desktop session.

```bash
cd ~/projects/jetson-semantic-room-explorer
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  scripts/preview_search_goal.py \
  --memory data/outputs/scene_memory/m6_20260910/memory.db \
  --mapping data/outputs/rtabmap_slam/mapping_02 \
  --label chair \
  --output data/outputs/search_goal/NEW_RUN
```

Choose a new output directory for each run; existing evidence is not overwritten.
`preview.json` retains all matching provisional objects, their source times,
support counts, detector confidence, last observations, map positions and source
identities. Each result links an `object_ID.png` overlay. An unknown label saves
an `overview.png` without an invented object location. Label lookup remains
exact after trimming and case folding, as in [scene memory](scene-memory.md).

Open the measured chair example on the Jetson display:

```bash
xdg-open data/outputs/search_goal/m9_20260910/chair/object_2.png
```

Gray cells are unknown, white free, and dark occupied. The orange diamond is
the remembered surface point; orange rings delimit the stand-off band. Blue
dots pass the cell checks. A red cross marks the selected cell center and its
arrow faces the target; the green circle shows the assumed 0.25 m clearance.
The two panels show the entire export and target detail. PNGs open in the normal
image viewer and require no 3D rendering support.

`PREVIEW_READY` means at least one result is a `PREVIEW_CANDIDATE`.
`NO_GOAL` is a completed offline decision and exits zero; inspect its reason and
cell counts. Invalid or incompatible inputs fail with a nonzero exit and an
`INCOMPLETE` report when the output directory was created. A changed map or pose
identity cannot silently become a valid empty-map result.

## Coordinates And Fixed Assumptions

The verified occupancy export is `mapping_02/export/room.pgm` with `room.yaml`:

- Size: **222 x 138**, resolution **0.05 m/cell**.
- Origin: **[-4.575, -3.59134, 0]**; the third YAML component is yaw, not height.
- `negate: 0`, `free_thresh: 0.196`, `occupied_thresh: 0.5`.
- **1122 free**, **6379 occupied**, **23135 unknown** cells. Source pixel values
  are respectively 254, 0 and 205. Most of the export is not usable free space.

Installed ROS `MapMetaData.msg` defines the origin as the bottom-left corner of
cell (0,0). `OccupancyGrid.msg` defines row-major order with x advancing first.
The PGM's first row is at the top, so decoding flips image rows. For this
axis-aligned export, `cell_xy = floor((map_xy - origin_xy) / resolution)`;
cell centers are `origin_xy + (cell_xy + 0.5) * resolution`. Upper map boundaries
are exclusive. Outside targets are rejected, never clamped to the map.
Only axis-aligned, 8-bit grayscale trinary maps are supported. Occupancy
probability is `(255-pixel)/255` for negate zero, and `pixel/255` for negate one;
strict threshold comparisons leave equality unknown.

Before using the grid, the script verifies the mapping/database check and export
manifest, hashes the actual database, PGM, YAML and camera poses, and compares
map/pose identity to memory. These frozen inputs and the memory are read-only.
The JSON records their hashes and the policy used to generate the result.

The initial policy is fixed in one code constant, selected before inspecting
goal results: horizontal stand-off **0.75–1.25 m**, preferred **1.0 m**, and
clearance **0.25 m**. A goal cell must be free. Unknown, occupied and outside-map
areas all block clearance. A padded Euclidean distance transform measures
distance to non-free cell centers; subtracting half a cell diagonal gives a
conservative lower bound to their areas. Of all free cells, **168** pass this
clearance check. Rank passing cells by distance to the preferred stand-off,
then greater clearance, then grid y/x to resolve exact ties.

These are offline planar assumptions, not measured robot dimensions. The target
may be in an occupied cell because it represents an object surface. Goal x/y
are in meters and yaw in radians facing that surface point; object z remains
in source evidence and is not repurposed as floor height. No goal height,
current robot pose, route or visibility guarantee is invented.

## Measured Results

Evidence: `data/outputs/search_goal/m9_20260910/`.

| Query / object | Free cells in band | Passing clearance | Result |
| --- | ---: | ---: | --- |
| `refrigerator` / 1 | 0 | 0 | `NO_GOAL`: no free cells in stand-off band |
| `chair` / 2 | 367 | 94 | Preview candidate |
| `chair` / 3 | 369 | 94 | Preview candidate; unresolved identity retained |
| `sink` / 7 | 140 | 0 | `NO_GOAL`: insufficient map clearance |
| `backpack` | N/A | N/A | `NO_GOAL`: target not in memory |

Both chair candidates select cell **[114,84]**, map x/y **[1.15,0.63366] m**.
Their respective stand-offs are **0.998861 / 0.999012 m** and facing yaw values
**-1.299565 / -1.269940 rad**. Each has two source-frame supports, first/last
timestamps `1789080208207783000` / `1789080265488456000` ns. The shared goal does
not resolve whether these detections represent separate chairs.

Independent checks against original PGM pixel **[114,53]** verify a free cell,
the image-row inversion, metric position and facing direction. Exact distance
from the goal center to every blocked cell square and the map boundary is
**0.257391 m**; the script's conservative lower bound is **0.256192 m**.
This checks the map computation, not real-world clearance or map accuracy.

Six bounded fresh CLI processes covered the four labels, a repeated chair
query, and a copied memory with deliberately incompatible pose identity. The
copy failed with exit 1 and `INCOMPLETE`, no goal or PNG. The five normal runs
exited zero, and repeated chair decisions were identical. All input hashes
remained unchanged. All generated PNGs decoded; both chair overlays and the
refrigerator/sink no-goal overlays were visually inspected.

Five successful mixed query/render runs had operation-time min/median/P95/max
**1308.761 / 1771.175 / 2753.912 / 2762.452 ms**, including hashing and PNG
rendering. Their process wall times were **2123.970 / 2573.909 / 3628.249 /
3628.538 ms**, including interpreter/dependency startup. These are small offline
functional measurements, not navigation or steady-state throughput benchmarks.
Runtime: Python 3.10.12, NumPy 1.26.4, OpenCV 4.11.0, SciPy 1.15.3,
Matplotlib 3.10.9 and PyYAML 6.0.3 on aarch64.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/search -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python \
  -m unittest discover -s tests/memory -v
```

All **16 search tests** and **17 memory regression tests** pass. Known synthetic
cases cover row direction, cell boundaries, threshold equality, conservative
clearance, deterministic selection, invalid/outside targets, no-free-space and
insufficient-clearance results, unsupported formats and changed input identities.
The actual missing-label and incompatible-memory CLI cases are recorded in
`integration.json`, alongside the independent geometry check. Detailed evidence
includes `verify_preview.py`, query subdirectories, logs and input hashes;
room data and generated images remain local and ignored.

The partial SLAM trajectory, provisional labels/identities and unverified floor
geometry still limit interpretation. This step does not check a route from a
known start, line of sight, physical footprint, current localization or Nav2.
An object location and an observation position are different quantities; even a
valid observation cell does not prove it can be reached. Next: validate an
offline grid route from an explicitly identified start to a candidate goal.
