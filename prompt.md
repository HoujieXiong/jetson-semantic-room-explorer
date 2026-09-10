# Codex CLI Task Prompt

Run Codex from the repository root and paste the prompt below. `AGENTS.md` is
the canonical source for project scope, workflow, and engineering standards;
this file contains only the current implementation task.

```bash
cd ~/projects/jetson-semantic-room-explorer
git pull origin main
codex
```

## Current Task: Supervised Room-Walk RGB-D Recording

```text
Read AGENTS.md and follow it strictly.

Work on the M3 supervised room-walk recording task. The stationary ROS contract
and exact simulated-time replay are verified in the Progress Ledger. Preserve
the accepted 15 FPS profile, source resolutions, rectified RGB-D calibration,
clock/TF contract and separate native SDK capture path.

First inspect the repository, existing ROS workspace and final stationary
recording evidence. Confirm I am present and determine how the fixed camera and
Jetson can be moved with secure power and cabling. I will perform physical camera
motion; do not assume the setup is portable or actuate a robot.

The required observable result is:
- record a bounded 60–120 second slow room loop with useful overlapping views;
- retain image/CameraInfo, static TF, source timestamp CSV and exact configuration;
- verify units, calibration, frames, TF, rates, synchronization and gaps;
- preserve the stationary wall-unit test, but do not require every moving frame's
  center to remain in the old 2–3 m wall interval;
- stop the driver and verify exact recorded content through simulated-time replay;
- keep room images/bags ignored and local and update progress on GitHub.

Do not start SLAM, perception or robot motion in this step. Ask before downloading
any newly required component that is absent locally; do not repeat approvals
already granted for the existing driver and its six dependencies.

Make the smallest coherent change, reuse existing SDK and project patterns, run
focused Jetson verification, review the complete diff and update the Progress
Ledger only with measured evidence.

Before editing, briefly explain in Chinese what exists, the smallest plan, the
files that will change and how the result will be verified. After completing the
task, explain changes, measured results, limitations, what I should learn and
exactly one recommended next action.
```

Replace the current-task section only after its observable result has been
verified and recorded in the Progress Ledger.
