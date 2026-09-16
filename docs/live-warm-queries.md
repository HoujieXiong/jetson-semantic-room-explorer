# Stationary live RGB-D with bounded warm queries

Status: `VERIFIED` for a bounded Jetson measurement, independently checked source
pixels, causal memory, four actual text requests and exact reopening. Useful
localized fridge retrieval, lossless transport, sustained throughput and physical
navigation are **not verified**. This supersedes neither the failures nor the
measurements in [the original live trial](live-rgbd-search.md).

## Scope and capture

After fresh operator readiness, the existing live supervisor was adapted locally
to use the current 1280 detector input, square-padded complete crops, separate
unlocalized RGB evidence, retained map nodes and one loaded text-query session.
No runtime script, model, threshold or dependency changed. Private supervisors,
recordings and reports are under `data/outputs/live_warm/20260916/`.

The declared camera interval was approximately 70 seconds, with requests at
18/30/42/54 seconds after camera-process launch: `a fridge`, `a bowl`,
`a kitchen sink`, `an elephant`. Models and observer/grid subscriptions became
ready before opening the camera. The observer deadline was 150 seconds after
readiness; guards were 1 GiB available RAM, 3 GiB available disk, 75 seconds for
query initialization and 15 seconds per response. Owned children receive SIGINT,
then TERM/KILL only after 15/5-second grace periods. Query ROS publication and
navigation stayed off; no operator movement was requested.

Attempt 01 retains four completed queries but is `INCOMPLETE`: the old live
resource sampler expected `VmRSS` during query-process exit and interrupted the
observer. All children closed without forced termination. Attempt 02 reuses the
existing warm supervisor's handling of `/proc` states `Z`/`X`; it changes no
camera or inference policy. Both attempts and exact source copies remain saved.

Attempt 02 requests camera closure at **70.484 seconds**, records **65.232 seconds**
of source RGB and finishes model startup, bounded observation and cleanup in
**178.879 seconds**. The camera is now closed. Native parameter queries confirm
system time, most-recent-frame odometry, stationary node retention and nonlatched
map publication. The power mode remains 25 W.

## Delivered evidence and processing

| Measurement | Attempt 02 |
| --- | --- |
| Hardware-selected profiles | 1280x720 MJPG RGB; 640x576 Y16 native depth; requested 15 FPS |
| Published grid | Registered 1280x720 RGB8 / 16UC1 depth, millimeters, zero invalid |
| Driver CSV | 994 records per stream; no SDK index gaps |
| Recorded / observer-received image pairs | 975 / 975; identical source bytes |
| RGB / depth header rate | 14.931 / 14.932 Hz |
| RGB-D skew median / maximum | 2.675 / 3.622 ms |
| Perception | 287 processed, 688 explicit queue drops, zero failed or pending |
| Source poses for processed frames | 76 accepted; 209 missing odometry; two missing map TF |
| Odometry | 235 tracked outputs, zero reported lost; 740 received image pairs without output |
| Map / graph / occupancy messages | 56 each; 56 final nodes |
| Memory | 1,199 events; final snapshot has 21 eligible frames and three provisional records |
| Semantic work | 21 encoded keyframes, 75 crops: 30 localized and 45 unlocalized |
| Refused semantic keyframes | 34 source observations dropped; one source pose refused |
| Detection-plus-depth median / P95 | 130.830 / 229.580 ms |
| Arrival-to-result median / P95 | 2,222.215 / 2,544.566 ms |

The CSV's 19 additional records per stream follow the last recorded image; none
are missing inside the recorded image interval. CSV entries alone do not prove
subscriber delivery. The bag contains 978 RGB and 974 depth CameraInfo messages;
the observer receives 979 of each. One RGB CameraInfo is missing inside the bag's
image interval. Extra metadata at shutdown also violates the strict boundary
allowance. Both sensor completeness and strict bag acceptance remain false;
`bag_check.json` is **INCOMPLETE**, with a separate loss-aware measurement.

The inherited odometry report derives `received_pairs=979` and
`input_frames_without_result=744` from **CameraInfo**, not image delivery. An
initial independent-check assertion exposed this distinction. Its failure is
preserved. Reconstruction from the 975 actual image pairs verifies all 235
odometry outputs and **740** image pairs without an output; four metadata-only
pair stamps occur after the final received image. Original reports are unchanged.

Nonzero depth coverage has median 47.41%; center median is 4.327 m, with recorded
outliers. Unit verification compares uint16 pixels and meter back-projections;
no new physical distance was measured. Depth rejection and the existing 5 m
object-depth policy remain active. This scene is not the historical measured-wall
accuracy test.

## Queries and incorrect identity

One-time query launch-to-READY is **11.059 seconds**, including 10.125 seconds of
model loading. Each complete response below includes actual text inference,
fresh committed snapshot, planning and applicable rendering.

| Phrase | Event / graph prefix | Response | Selected evidence | Planning |
| --- | --- | ---: | --- | --- |
| `a fridge` | 194 / 186 | 7.369 s | One localized record, score 0.272432; four unlocalized views, best 0.298652 | No route from unknown start |
| `a bowl` | 455 / 438 | 0.793 s | None above threshold | Invalid unknown start |
| `a kitchen sink` | 673 / 655 | 0.802 s | None above threshold | Invalid unknown start |
| `an elephant` | 828 / 813 | 3.229 s | None above threshold | Invalid unknown start |

First text inference still takes 4.742 seconds despite a loaded model; subsequent
encodings take 29.344–39.684 ms. Snapshot work takes 108.362–2538.757 ms. Four
requests are too few for a service-latency guarantee. This is not a controlled
performance comparison with the earlier replay or live configurations.

The localized fridge candidate's best crop, `8:2`, is at `[199,317,360,704]` and
visually contains a black bin and cabinet. The best unlocalized view, `8:0`, is
at `[462,192,609,502]` and visually contains the fridge. Both come from the same
source frame. After the operator initially could not see the tool images, a
standalone A/B page and its exact local path were provided. The operator then
confirmed: **A is wrong; B is the correct fridge.** This feedback is retained
against both exact source views and crop hashes in `visual_review.json`.
**The localized answer is incorrect; fridge localization has not succeeded.** The
unlocalized fridge keeps `insufficient_valid_depth` and cannot supply a 3D target.
The current scene's bowl/sink visibility is not established by these queries.

After shutdown, the exact original GPU text vectors query prefix 1199 / graph
1190. The localized fridge score is 0.276445, with 21 selected unlocalized views;
other phrases remain unselected. All closed decisions refuse stale map evidence.
These four API queries do not benchmark fresh text inference. All eight original
and closed answers reopen identically from copied actual prefixes. No goal/path
is selected, published or executed. Available free space elsewhere in the map
does not make the camera projection a valid robot start.

## Verification, resources and review

Independent checks verify all received image pixels, all 75 crops, causal TF,
metric depth, scalar geometry/vector fusion, per-view ranks and all 56 graph/grid
messages against separately received ROS witnesses. Maximum geometry / localized
score / visual score differences are 4.45e-16 m / 4.99e-8 / 5.87e-8, within the
declared 1e-12 m / 1e-6 tolerances. All 52 existing online tests pass in 12.552 s.
All 27 archived runtime hashes, two model hashes and four preserved input hashes
match. Every one of the 56 distinct ranked source crops was visually inspected.

Writer queue peak is 132/512; semantic pending/cache peaks are 2/8 and 32/32.
Independent inference/pending/pose-wait peaks are 1/1/8. SQLite commit
median/P95/max is 10.941/59.705/7149.619 ms. Batching remains bounded at 16 events;
no queue failure or unfinished work occurs. Long storage stalls are still present.
By frame-arrival time, query intervals contain 55 processed / 124 dropped frames;
outside them there are 232 processed / 564 dropped. This does not establish
query-induced loss.

System RAM peaks at 5359 MB; sampled available RAM stays above 2153648 KiB. Query
RSS peaks at 1423560 KiB. Query CUDA allocated/reserved peaks are
228483584/243269632 bytes; observer peaks are 330952704/379584512 bytes. GPU
temperature peaks at 55.625 C; already nonzero swap ranges from 1829 to 1888 MB.
Every owned process exits normally, with expected SIGINT for telemetry, and no
forced termination. A final native check finds no runtime processes and
4791244 KiB available RAM. This does not prove long-duration leak freedom.

Open the self-contained review without WebGL:

```bash
xdg-open data/outputs/live_warm/20260916/review.html
```

It contains eight query sections, four map decisions and 59 embedded PNGs.
`compare.html` shows the two fridge-query crops side by side; `ranked_views.png`
shows all distinct ranked crops. Raw room data remains private and outside Git.
The saved `attempt_02/used_run_live.py`, `run.json`, native parameters, calibration,
source/config snapshots and verification logs retain exact reproduction inputs.
Do not rerun the capture without fresh operator readiness. Offline checks use
`scripts/rtabmap_odom_env.bash`, then the saved `measure_bag.py`,
`closed_queries.py`, `verify_capture.py`, `verify_trial.py`, `verify_semantic.py`
and `verify_search.py` with `attempt_02`; reopening commands require fresh output
paths. The original failed run and initial accounting-check failure stay intact.

The next action is a saved-data experiment coordinating perception and SLAM frame
selection, measuring how many processed frames acquire their own source-time pose
and reach memory. Valid geometry must remain separate from object identity; the
wrong fridge candidate must remain visible in regression evidence.
