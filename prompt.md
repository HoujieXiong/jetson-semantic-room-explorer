# Codex CLI Task Prompt

Run Codex from the repository root and paste the prompt below. `AGENTS.md` is
the canonical source for project scope, workflow, and engineering standards;
this file contains only the current implementation task.

```bash
cd ~/projects/jetson-semantic-room-explorer
git pull origin main
codex
```

## Current Task: Femto Mega RGB-D Capture

```text
Read AGENTS.md and follow it strictly.

Work on the Femto Mega RGB-D capture milestone.

First inspect the repository, installed Orbbec SDK, connected camera, and
supported RGB/depth stream profiles. Do not assume both streams use the same
resolution.

The required observable result is:
- capture one hardware-supported synchronized RGB-D frame pair;
- use 1280x720 RGB if the camera supports it in the synchronized profile;
- save the RGB image, raw depth image, camera intrinsics, timestamps, depth
  scale, and selected stream profiles;
- verify depth values and units;
- complete ten open/capture/close cycles without crashes, resource leaks, or
  silent failures.

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
