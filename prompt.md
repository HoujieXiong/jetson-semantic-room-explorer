# Codex CLI Task Prompt

Run Codex from the repository root and paste the prompt below. `AGENTS.md` is
the canonical source for project scope, workflow, and engineering standards;
this file contains only the current implementation task.

```bash
cd ~/projects/jetson-semantic-room-explorer
git pull origin main
codex
```

## Current Task: Femto Mega Depth-to-Color Registration

```text
Read AGENTS.md and follow it strictly.

Work on calibrated Femto Mega depth-to-color registration, the Current Next Task
in AGENTS.md. M2 native capture and its coarse physical unit check are verified
in the Progress Ledger. Preserve existing work and the verified raw capture
contract.

First inspect the existing capture code, installed SDK alignment examples, and
supported profile combinations. Do not assume hardware alignment support or
equal native RGB/depth resolutions.

The required observable result is:
- preserve a synchronized 1280x720 color / 640x576 raw-depth pair and its metadata;
- use supported SDK calibration to save depth registered to the color pixel grid;
- export actual aligned intrinsics, depth scale, timestamps and camera frame;
- save an alignment overlay, inspect multiple visible object boundaries, and
  record occlusions, invalid pixels and measured registration mismatch;
- verify metric depth remains plausible and affected capture/lifecycle checks
  pass without silent fallback; resizing raw depth is not registration.

Do not start ROS integration, SLAM, or perception work in this step.

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
