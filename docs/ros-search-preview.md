# ROS 2 search preview

Status: `VERIFIED` on the Jetson for bounded publication from frozen memory/maps.

`scripts/publish_search_preview.py` runs the existing search stages, chooses the
shortest reachable object route (object ID breaks ties), or the existing frontier
viewpoint, and publishes:

| Topic under `/semantic_explorer/preview/` | Type | Content |
| --- | --- | --- |
| `decision` | `std_msgs/msg/String` | JSON with all outcomes, selected candidate, start provenance and evidence hashes |
| `goal` | `geometry_msgs/msg/PoseStamped` | Selected planar map goal and viewing yaw |
| `path` | `nav_msgs/msg/Path` | Original checked metric route, retaining its exact start |

These are visualization topics. They are not connected to Nav2 or motor commands.
A refusal publishes only `decision`; consumers must clear any previous displayed
selection when that decision has `selection: null`. All messages use publication
time, not camera acquisition time; original observations remain in search evidence.
The planar z coordinate is zero, not a measured floor height. Path headings face
the following waypoint, ending at the goal's viewing yaw; rotation feasibility is
not established. A zero-length frontier route retains its viewing orientation.

The publisher uses reliable, transient-local depth-one QoS and requires a matched
subscriber for every topic it will publish. It repeats the same preview at 1 Hz
for a bounded duration, then checks DDS acknowledgements and destroys its executor,
node and context. `PUBLISHED` does not imply application acceptance or movement.
A missing subscriber is an explicit nonzero timeout, with `INCOMPLETE` evidence.
Use the `decision` hash/stamp to associate messages across topics. The preview is
valid only for its frozen source data; it is not a live localization interface.

## Run on this Jetson

In two fresh terminals at the repository root:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=54 ROS_LOCALHOST_ONLY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
```

Start the receiver first, with a fresh output path:

```bash
.venv/bin/python tests/check_search_publication.py \
  --output data/outputs/search_publication/manual_receiver --duration-s 45
```

Then publish the existing bottle search, again using a fresh output path:

```bash
.venv/bin/python scripts/publish_search_preview.py \
  --memory data/outputs/concurrent_rgbd/line_20260915/memory.db \
  --mapping data/outputs/concurrent_rgbd/line_20260915/attempt_01 \
  --label bottle --simulated-start-xy 3.05 -1.1256999999999997 \
  --output data/outputs/search_publication/manual_bottle
```

`publication.json` references the complete `search/` evidence. The receiver writes
`received.json`. RViz can display the goal and path using fixed frame `map`; a
consumer of the decision topic is also required. No new camera capture is needed.

## Measured acceptance, 2026-09-15

- 100 search tests pass, including eight new selection/message tests and ROS
  serialization of known positions, yaw, source-independent publication stamps,
  zero-length views and refusals.
- Independent ROS processes receive two copies of bottle goal/path/decision:
  object 8, route length 0.05 m. All received waypoints and terminal poses match.
- Backpack produces two copies of the existing zero-translation frontier preview.
- Recorded camera node 1 publishes two refusal decisions and zero goals/paths.
- Missing subscribers produce a nonzero timeout and zero published messages.
- All four publisher contexts close; source memory/map/poses remain byte-identical.
- The first integration attempt exposed an executor/context ownership error. An
  explicit executor bound to the node's context fixes it; the failed evidence is
  retained alongside the successful rerun.

Evidence: `data/outputs/search_publication/validation_20260915/`, including
`attempt_02/integration.json`, receiver outputs, logs and the original failure.
Physical scale, current localization, visibility, traversal and autonomous
navigation remain unverified. The user deferred further physical-reference
capture in favor of completing pipeline interfaces.
