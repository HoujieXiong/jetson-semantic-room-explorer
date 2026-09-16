# Shared depth regions for duplicate association

Status: `VERIFIED` on Jetson Orin Nano for an optional saved-data association
correction. The [previous timeline audit](query-stability.md) found that a
one-pixel sample change split the bowl/sink proposals at event prefix 941.
The extended rule keeps them merged through the final prefix, without changing
the default association or semantic/planning thresholds. Physical identity and
stable recognition remain unverified.

## Source evidence and minimal change

All accepted, mapped, cross-label proposal pairs with box IoU >= 0.9 were checked
against the original aligned RGB-D bag: 11 pairs in nodes 4, 13, 25, 31, 41, 43,
44, 45, 51, 53 and 57. Selection did not use text scores. Every RGB/depth hash and
producer depth summary reproduces exactly. Source depth is uint16 millimeters
with zero invalid, on the calibrated 1280x720 color grid.

At node 51, the two inner ROIs are `[528,284,571,303]` and `[529,284,571,303]`
(exclusive upper bounds). All 817 / 798 pixels are valid inliers; the actual
intersection has 798 pixels, or 97.6744% of the larger set. Both selected depths
are 1.439 m, although the pixels are `[549,296]` and `[550,296]`. Their calibrated
point separation is 1.918 mm. Common depth P10/P50/P90 is 1.433/1.439/1.447 m.
The original RGB shows overlapping bowl proposals; this is assistant inspection,
not a new operator annotation or physical distance measurement.

`scripts/scene_memory.py` extends the existing `--merge-duplicate-tracks` mode
using stored ROI, count and calibration evidence. No mask storage, new option,
schema, model, dependency or worker is needed. For inlier pixel sets A and B
contained in their respective ROIs in the **same source depth image**:

```text
shared inliers >= max(0, count(A) + count(B) - area(ROI_A union ROI_B))
```

This is a guaranteed lower bound; rectangle overlap alone is insufficient.
The new witness requires at least 20 guaranteed shared pixels and a lower bound
of at least 90% of the larger inlier set. It also requires equal sampled metric
depth, both samples inside the common ROI, each P90-P10 <= 0.02 m, and calibrated
camera points agreeing with the recorded points. Camera/map pair distances must
agree within the existing 1e-6 m numerical tolerance and remain within 0.35 m.
The 20-pixel and 0.02 m values reuse the depth policy's minimum count and minimum
outlier gate; they are not new physical-accuracy estimates.

The [original exact-sample witness](coobserved-tracks.md) remains valid. Both
paths retain box IoU >= 0.9 in every shared frame, at least two shared frames,
complete pairwise group evidence, and centroid/running geometry gates. Missing
region evidence refuses the new path; inconsistent ROI/count evidence raises an
explicit error. One confidence/index-selected representative per frame supplies
geometry and its own available embedding. Original IDs/labels remain traceable;
the canonical record here still carries detector label **sink**.

## Measured comparison

The same 392 prefixes across three journals give 784 snapshots and 2,602 rankings.
Every default-mode result is unchanged. Optional-mode results change only at
29 complete-crop stationary prefixes from 941 onward, and only for the bowl/sink
group. Other records, source eligibility and planning evidence are unchanged.

| Complete-crop stationary measurement | Previous exact-sample rule | Shared-region extension |
| --- | ---: | ---: |
| Sampled prefixes with merged tracks | 80 | 109 |
| Split at prefix 941 | Yes | No |
| Final provisional records | 5 | 4 |
| Final total frame supports | 94 | 83 |
| Final bowl-region supports | 18 + 37 | 44 |
| Final best bowl-region cosine | 0.253747 | 0.254142 |
| Bowl selected in rankable sampled prefixes | 113 / 126 | 113 / 126 |

Merging still begins at prefix 232; prefixes 871 and 932 retain their prior
31/32-support results and 0.252092/0.251910 scores. Final best crop remains
`online.crops/37_1.png`. Thirteen rankable snapshots still fall below the unchanged
0.25 text threshold. These correlated snapshots are not accuracy trials.

All 133 original-stationary and 125 motion optional-mode results remain unchanged.
Stationary fridge/trash queries still select the previously rejected region in
all 125/126 rankable samples. Motion fridge synonyms still pass in all 113
rankable samples; bottle and elephant never pass. No new human labels are inferred.

## Verification and local reproduction

- All 57 memory and 41 online-memory/semantic/search tests pass. New controlled
  depth images exercise sample jitter, sparse pixels, competing depth layers,
  containment, conflicting calibration/geometry, missing evidence and late
  conflicts. Existing nearby-object, incomplete-group and causal tests pass.
- Independent raw inlier sets validate all 11 region bounds; the smallest
  guaranteed shared fraction is 0.922604. Only node 51 needs the new witness.
- Independent source transforms, inverse-intrinsics projection, matrix group
  connectivity and scalar vector fusion verify 120 boundary snapshots, including
  232, 871, 932, 941 and final. Maximum coordinate error is 8.89e-16 m and score
  error 6.33e-8. Four hundred standalone API calls match the batched audit.
- A native GPU CLI on the final journal reproduces the stored-vector query
  exactly, including its text vector, representatives and ranking. Search takes
  11.611 s including 10.756 s model load; snapshot query takes 368.188 ms. Peak
  RSS is 1,365,568 KiB; peak allocated CUDA memory is 228,483,584 bytes. This is
  one functional run, not a latency distribution.
- All 784 timeline planning decisions still refuse: 400 stale, 130 graph/grid
  stamp mismatches, four missing graphs and 250 incompatible older grid policies.
  The GPU query refuses stale evidence. No camera, ROS publication or motion is
  used. Native cleanup finds no remaining matching runtime/audit processes and
  4,913,916 KiB available RAM; this is not a long-duration leak test.

Private evidence: `data/outputs/shared_depth/20260916/`, including predeclared
`acceptance.json`, raw `node_*.npz`, `raw_depth_audit.json`,
`region_witnesses.json`, `timeline/measurement.json`, `timeline/verification.json`,
`comparison.json`, `gpu_final/`, `cleanup.json`, check scripts and test logs.
The main timeline audit takes 205.589 s / 188,068 KiB peak RSS; independent checks
take 56.370 s. These are audit costs, not live throughput. Baseline snapshots,
original journals, feedback, bag and model hashes are preserved. Initial audit
IoU truncation and depth-test fixture failures remain logged; corrected runs pass.
`review.html` embeds the inspected `shared_depth.png`; an SVG export is available.
Room data and generated artifacts remain local and uncommitted.

From the repository root, choose a fresh output path:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../mobileclip-env/bin/python \
  scripts/online_search_preview.py \
  --db data/outputs/stationary_memory/steady_20260916/bowl_1280_pad_01/online.db \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a bowl' --merge-duplicate-tracks \
  --output data/outputs/shared_depth/manual_query
```

The original local journal, crops and model must exist. Historical planning
evidence should refuse as stale; do not refresh timestamps to obtain a route.

Focused test commands used:

```bash
.venv/bin/python -m unittest discover -s tests/memory -v
.venv/bin/python -m unittest discover -s tests/online_memory -v
```

Next: audit existing RGB-D support for the operator-confirmed fridge region to
decide whether localization is justified or a new camera view is needed.
