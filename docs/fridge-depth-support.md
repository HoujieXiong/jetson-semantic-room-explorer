# Fridge depth support in existing recordings

Status: `VERIFIED` for a bounded source-data audit on Jetson Orin Nano.
The stationary fridge contains localized, repeatable depth patches, but remains
below the current inner-ROI acceptance gate. This does not block work on the full
pipeline or require another recording now. No runtime, threshold, camera profile,
image resolution or model was changed.

## Source selection and checks

The original node-21 fridge crop is the only operator-confirmed example in this
audit. Its RGB bounds are `[668,186,815,496]`; feedback and crop pixels remain
unchanged. Adjacent frames and motion-recording proposals have no new operator
labels. The spatial comparison uses the confirmed box as a fixed-scene proxy,
not a new segmentation or proof of identity across recordings.

The complete-crop stationary journal contains 604 processed frames over
64.628 seconds of source time. Each has exactly one refrigerator proposal with
IoU >=0.75 against the confirmed box. Before measuring spatial support, the audit
declared seven evenly spaced processed-frame indices (0, 100, 201, 302, 402, 502,
603), plus the minimum/maximum valid-fraction observations (563/564). These nine
frames and confirmed node 21 were decoded from the original bag. All source
RGB/depth bytes match their journal hashes.

Three additional comparison frames are the first, middle and last of 18 eligible
frames with depth-accepted refrigerator proposals in the frozen motion report:
nodes 9, 32 and 56. Their existing NPZ files pass manifest, source timestamp and
map/pose provenance checks. All 13 frames have identical stored calibration and
1280x720 aligned RGB8 / uint16 millimeter depth. Zero is invalid; the existing
valid range is `0 < depth < 5 m`. These are aligned-pixel counts, not counts of
independent native sensor measurements.

Every original proposal's `depth_observation` result reproduces exactly. The
audit separately measures its original inner ROI, full detector box and an
outer ring extending 10% of the box width/height on each side. Full-box/ring
measurements are diagnostics and never change runtime eligibility.

## Measured stationary support

| Region | Valid depth | Interpretation |
| --- | ---: | --- |
| All 604 original inner ROIs | 6.84–11.46%; median 8.58% | All retain `insufficient_valid_depth` against the existing 25% gate |
| Confirmed node-21 inner ROI | 1,059 / 11,315 pixels, 9.36% | Depth P10/P50/P90: 4.072 / 4.080 / 4.1152 m |
| Nine sampled full boxes | 36.36–37.99% | Includes borders and pixels outside the inner ROI |
| Nine sampled surrounding rings | 79.01–82.30% | Neighboring regions have much denser depth |

In confirmed node 21, 10,256 inner-ROI pixels are zero and none is rejected by
the 5 m range limit. Five four-connected valid components remain. The largest
contains 732 pixels, 69.12% of the valid support, at `[724,290,752,320]`; its depth
P10/P50/P90 is 4.071 / 4.076 / 4.095 m. Inspection of the original RGB overlay
places this component around the small light-colored patch on the fridge door.
Other support is sparse, including portions near the ROI's left edge. Much of
the shiny-looking door region remains invalid. This is an image observation,
not a material classification or a verified sensor failure mechanism.

Across the nine sampled stationary frames, the largest component has 676–740
pixels and inner-ROI median depth is 4.073–4.083 m. Within the fixed confirmed
ROI, 2,737 pixels are valid at least once, 638 in at least eight frames, and 542
in all nine. Of 1,673 pixels with at least three valid measurements, the median
per-pixel temporal P90-P10 spread is 0.0168 m (P10/P90: 0.0064/0.0368 m).
This uses fixed image coordinates without temporal registration; camera/view
jitter contributes. It is not a physical accuracy or sensor-noise measurement.

These results support the existence of a persistent surface patch near 4.08 m
**measured optical depth**. They do not establish the fridge's true distance,
object center, complete surface or an accepted map-frame target. Most of the
inner ROI remains unmeasured under the unchanged policy.

## Comparison with existing motion data

| Motion node | Inner-ROI valid pixels | Valid fraction | Existing robust inliers | Existing selected depth |
| --- | ---: | ---: | ---: | ---: |
| 9 | 4,144 | 52.22% | 3,430 | 4.920 m |
| 32 | 4,686 | 45.23% | 4,632 | 4.185 m |
| 56 | 6,702 | 82.52% | 3,782 | 4.776 m |

The inspected motion views contain much broader valid regions. Nodes 9 and 56
also include nearer foreground returns around 2.4–2.7 m inside the proposal;
the original robust estimator removes them before selecting the farther surface.
Neither detector confidence nor a high valid fraction alone identifies which
surface belongs to an object.

The same aligned dimensions and calibration coexist with very different depth
coverage. Resolution mismatch alone is therefore insufficient to explain the
stationary pattern. These recordings do not isolate viewpoint, range, surface
response or filtering as the cause. Native unaligned depth/IR for these exact
frames was not recorded, so this audit cannot separate acquisition failures
from later alignment/processing losses.

## Decision and verification

Keep the stationary fridge's localization unconfirmed and retain its explicit
depth rejection. Do not enlarge its ROI, fill zeros, lower the 25% gate or use
the diagnostic 4.08 m value as a navigation target. Existing data already supports
continued pipeline work with usable targets; new capture is not a prerequisite.
The audit does not certify the current sparse patch for automatic localization.

Independent scalar counts, interpolated percentiles and flood-fill connectivity
match all 13 spatial results. A separate per-pixel loop reproduces the temporal
statistics. Inverse-intrinsics projection agrees with direct pinhole projection
within 6.67e-16 m; this checks numerical geometry only. All 31 declared source,
feedback and prior-evidence inputs retain their hashes; all 25 runtime files are
unchanged. No runtime unit suite is rerun for this evidence-only change.

Source extraction takes 22.808 s, spatial/temporal analysis 1.747 s with 87,004 KiB
peak RSS, and independent verification 3.316 s. These are audit execution costs,
not live-pipeline benchmarks. No camera, GPU inference, ROS publication or motion
is used; no dependencies or weights are downloaded.

Private evidence is under `data/outputs/fridge_depth/20260916/`: predeclared
`acceptance.json`, `selected_sources.json`, source arrays, `extraction.json`,
`stationary_timeline.json`, `analysis.json`, `temporal_support.npz`,
`verification.json`, exact local scripts and logs. The inspected
`fridge_depth.png` / `.svg` summarize the audit; `review.html` embeds that figure
and expandable RGB/valid-depth/depth panels for all 13 frames. They require no
WebGL and remain local, along with the room images.

```bash
xdg-open data/outputs/fridge_depth/20260916/review.html
```

Next: make depth-rejected visual observations inspectable in text queries with
explicitly unconfirmed localization, while preserving the existing 3D planning
requirements and testing whether the correct fridge crop is retrieved.
