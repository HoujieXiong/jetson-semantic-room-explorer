# Codex CLI Task Prompt

Run Codex from the repository root and paste the prompt below. `AGENTS.md` is
the canonical source for project scope, workflow, and engineering standards;
this file contains only the current implementation task.

```bash
cd ~/projects/jetson-semantic-room-explorer
git pull origin main
codex
```

## Current Task: ROS 2 Camera Contract And Stationary Rosbag

```text
Read AGENTS.md and follow it strictly.

Work on the M3 ROS 2 camera contract and stationary rosbag smoke test, the Current
Next Task in AGENTS.md. Native RGB-D capture, coarse units and SDK registration
are verified in the Progress Ledger. Preserve that working capture path.

First inspect local ROS 2 Humble, the Orbbec ROS wrapper/source and its SDK
requirements, launch patterns and supported profiles. If a required component
cannot be found locally, ask me before downloading or installing it. Do not
assume the Python SDK's version or alignment settings apply to the ROS driver.

The required observable result is:
- publish supported 1280x720 color, registered depth and matching CameraInfo;
- measure image encodings, depth units, calibration/distortion, optical frames,
  TF, QoS, topic rates, timestamp domains/skew and dropped or unmatched frames;
- record about 60 seconds with the camera fixed, saving required topics and TF;
- stop the driver and replay the bag with simulated time, verifying recorded
  frame counts, timestamps, calibration and TF without reopening the camera;
- keep exact reproducible commands and measured evidence, preserve native capture,
  and leave room images and bags ignored and local.

Do not start SLAM, perception, room-walk recording or robot motion in this step.
Prefer a compatible maintained Orbbec driver over a new custom camera node.

Make the smallest coherent change, reuse existing SDK code and project
patterns, and avoid speculative abstractions or unused scaffolding. Run focused
verification on the Jetson, review the complete diff, and update the Progress
Ledger only with measured evidence.

Before editing, briefly explain in Chinese:
1. what already exists;
2. the smallest implementation plan;
3. which files will change;
4. how the result will be verified.

After completing the task, explain what changed, measured results, remaining
limitations, what I should learn from this step, and exactly one recommended
next action.
```

Replace the current-task section only after its observable result has been
verified and recorded in the Progress Ledger.
