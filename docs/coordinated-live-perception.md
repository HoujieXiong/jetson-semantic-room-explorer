# Stationary live validation with coordinated perception

Status: `VERIFIED` for one bounded live measurement on the Jetson, 2026-09-18.
New F/G operator feedback also passes saved-prefix refusal checks. Reliable fridge
localization, lossless recording, sustained throughput and navigation are not verified.

After the operator said the camera was ready and confirmed the displayed silver
fridge, the existing live supervisor ran with `--perception-selection odometry`.
The only supervisor changes were that existing option and the one-thread
OMP/OpenBLAS settings used in the verified replay. No runtime code, model,
threshold, calibration or dependency changed. The camera is now closed.

## Trial contract and delivery

The camera process ran for 70.109 seconds; recorded RGB covers 64.547 seconds.
The complete startup, observation and cleanup took 183.638 seconds. The operator
confirmed stationary placement; no motion was requested or commanded. The
15 FPS ROS configuration uses 1280x720 MJPG RGB and 640x576 native Y16 depth,
publishing rectified RGB8 and registered 16UC1 depth on the 1280x720 grid.
Depth is in millimeters, zero invalid. A separate SDK still established the view;
its 30 FPS software-alignment preview is not the ROS trial's depth measurement.

The existing 150-second observer deadline, 75-second query startup guard,
15-second response guard, 1 GiB available-RAM guard and 3 GiB free-disk guard
remained. Owned processes use the existing bounded SIGINT/TERM/KILL cleanup.
There was no forced termination, ROS query publication or navigation.

| Measurement | Result |
| --- | ---: |
| Observer RGB / depth images | 964 / 964 |
| Observer matched image pairs / synchronized four-topic groups | 963 / 961 |
| Processed / explicitly dropped groups | 203 / 758 |
| Processed sources with their own tracked odometry | 203 / 203 |
| Accepted map poses / missing source map-TF refusals | 198 / 5 |
| Tracked odometry outputs / reported lost | 213 / 0 |
| Final map nodes / encoded keyframes | 55 / 50 |
| Encoded localized / unlocalized crops | 125 / 52 |
| Final journal events | 1,181 |
| Arrival-to-result median / P95 | 418.367 / 1,106.473 ms |
| Detection-plus-depth median / P95 | 172.816 / 287.743 ms |

The 758 drops comprise 723 source-cache evictions, 25 source-odometry timeouts
and ten pending-inference overflows. All 213 selected frames have their own
tracked odometry. The selection cache peaks at 16; pending/inference/pose-wait
peaks are 1/1/7. There are no failed or unfinished inference jobs. Three mapped
sources were dropped and two had refused poses, leaving 50 encoded keyframes.
This is one live run, not a matched performance comparison with earlier scenes.

## Recording gaps remain explicit

The bag contains 964 RGB images, 965 depth images and 965 CameraInfo messages
per stream. Its strict verdict is `INCOMPLETE`: one interior RGB image is missing,
causing image/metadata and RGB-D completeness failures. Observer completeness
also fails. Equal RGB counts between bag and observer conceal different stamps:
each received one image that the other missed. Two recorded metadata pairs and
one recorded depth image were not received by the observer.

The driver CSV has 981 entries per stream and no SDK index gaps. Sixteen entries
per stream follow the recorded interval; one additional RGB entry inside it is
not recorded. Header rates are 14.919/14.935 Hz; RGB-D skew median/max is
4.107/4.854 ms. CSV logging does not establish subscriber delivery.

The inherited capture and per-frame checkers initially required every received
image to exist in the bag. Both failed on the missing RGB source. Their original
scripts and logs remain saved. Explicit stamp accounting identifies it as an
`odometry_cache_evicted` frame; it never reached inference or semantic encoding.
Corrected checks retain that unverifiable dropped-image gap, require complete
original images for all 203 processed frames, and verify every available frame.
The missing image is never reconstructed or reported as source-verified.

## Queries, identity and depth

One text encoder became ready in 13.105 seconds, including 11.289 seconds of model
loading. Four requests completed while the camera remained open:

| Phrase | Event / graph prefix | Full response | Planning |
| --- | --- | ---: | --- |
| `a fridge` | 228 / 199 | 3.836 s | No route from unknown start |
| `a bowl` | 398 / 395 | 2.132 s | Invalid unknown start |
| `a kitchen sink` | 638 / 632 | 4.490 s | Invalid unknown start |
| `an elephant` | 878 / 857 | 1.456 s | Invalid unknown start |

Fridge selects localized object 1 at 0.279700 and eight unlocalized views, best
0.298919. Assistant inspection of the exact best crops finds a bin/cabinet in F
(`8:1`) and the fridge in G (`7:0`). After inspecting the new review page, the
operator confirmed: **F is not the target fridge; G is the target fridge.**
Historical A–E labels are not transferred to this session. G has
`insufficient_valid_depth` and no 3D target. The other phrases have no selected
candidates; bowl/sink visibility is not established. No selected goal or route
was published or executed.

F's depth-valid inner-ROI fraction is 73.06%, yet its identity is wrong. G has
2,150 valid pixels out of 12,000 (17.92%), below the unchanged 25% gate. These
exact sources illustrate why geometric support and correct identity are separate.

Closed queries reuse the original GPU text vectors without new inference.
The fridge still selects object 1 at 0.279131, plus 50 unlocalized views; the
other phrases remain unselected. All four closed decisions refuse stale maps.
Eight copied-prefix/closed reopening comparisons preserve answers exactly.

The new per-session `feedback.json` binds only those two exact source views.
Eight further feedback queries reopen identically, preserving original rankings,
geometry and source associations. F vetoes object 1; G remains unlocalized without
invented geometry. Six unrelated phrase/phase decisions are unchanged. Replanning
at the original fridge decision time yields `selected_identity_rejected`; this
is an explicit post-feedback counterfactual, not a new live decision. Current-time
queries retain stale-map refusal. Original journals, queries and the reviewed page
remain unchanged. Feedback must accompany the query; recognition is not retrained.

Whole-image nonzero depth has median coverage 64.97%; center median is 5.074 m.
These are pixel measurements, not a physical distance accuracy test. A separate
assistant-defined spatial diagnostic covers 203 central-fridge-region proposals:
202 fail the unchanged depth gate, with median inner-ROI valid fraction 20.82%.
One passes at 26.73%, with a selected source pixel of 4.108 m and an accepted pose,
but that source is not a semantic map keyframe. This diagnostic does not label
every proposal or provide stable localized fridge memory.

## Verification and evidence

All 51 odometry/concurrency tests and 59 online-memory tests pass. Independent
checks verify causal TF, original pixels for every processed frame, all 177 crop
PNGs, scalar geometry/vector fusion, all 55 committed graph/grid pairs and eight
original reopened queries, plus eight feedback reopenings. Maximum scalar
geometry/localized-score/visual-score errors are 6.66e-16 m / 4.57e-8 / 6.02e-8
within the predeclared numerical tolerances.
These do not measure physical geometry or identity accuracy.

Peak system RAM is 5,873 MB; minimum available RAM is 1,630,908 KiB. Query RSS
peaks at 1,406,216 KiB. Observer CUDA allocated/reserved peaks are
330,952,704/356,515,840 bytes; query peaks are 228,483,584/243,269,632 bytes.
GPU temperature peaks at 54.093 C. The journal queue peaks at 69 of 512 events;
semantic pending/cache peaks are 2/32. All owned children exit, telemetry with
expected SIGINT. Native cleanup finds no runtime process and 4,507,132 KiB
available RAM. This is not a long-duration leak test.

Private evidence is under `data/outputs/coordinated_live/20260918/`: predeclared
acceptance, operator preview confirmation, preview and live data, exact commands
and source/configuration snapshots, original checker failures and corrected loss
accounting, independent checks, tests, `summary.json` and `cleanup.json`.
The existing local supervisor and checkers are retained for reproduction; do not
repeat capture without fresh operator readiness. Raw room data stays outside Git.

The confirmed browser review has eight query sections and 57 verified embedded PNGs:

```bash
xdg-open data/outputs/coordinated_live/20260918/confirmed_review.html
```

The original `target_review.html` and `pending_target_review.json` stay immutable.
`operator_target_review.json` preserves the exact reply and reviewed hashes;
`feedback_verification.json` records the eight new comparisons. No WebGL is needed.

Learning: coordinated source selection works with live capture, but useful poses,
correct identity, usable target depth and traversable routes remain separate
requirements. Matching message counts alone cannot prove matching source data.

Next action: after fresh operator placement/readiness, check a closer or oblique
stationary fridge view for usable target depth before another full live trial.
