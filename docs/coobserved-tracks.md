# Duplicate tracks supported by shared RGB-D evidence

Status: `VERIFIED` on Jetson Orin Nano for an optional query-time correction on
two saved stationary prefixes and a regression on the existing motion recording.
This consolidates duplicate proposals into provisional records; it does not
establish physical identity, stable recognition or live navigation.

The measurements below describe the original exact-sample rule. The subsequent
[shared-depth-region extension](shared-depth-association.md) adds a calibrated
region witness to the same optional mode and verifies the full recorded timeline.

## Evidence and association contract

The [bounded bowl replay](bowl-replay.md) selected both a bowl record and a sink
record whose best crops cover the same shallow bowl. At prefixes 871 and 932,
the records share eight source nodes: 4, 13, 25, 31, 41, 43, 44 and 45. Every pair
uses exactly the same sampled depth pixel and metric depth. Their box intersection
over union has a minimum of about 0.964487. Centroids differ by 1.160 mm and 1.126 mm,
respectively. These are numerical comparisons of recorded evidence, not measured
physical accuracy or eight new operator annotations.

The explicit `--merge-duplicate-tracks` option on the online semantic-query and
search-preview CLIs derives the ordinary snapshot first, then checks different-
label tracks that coexist in source frames. The original witness requires:

- At least two shared frames, with box IoU >= 0.9 and identical `pixel_uv` and
  `depth_m` in every shared frame. A conflicting shared frame blocks the merge.
- Agreement of the sampled map points within the existing 1e-6 m numerical
  tolerance, plus the existing 0.35 m centroid and running representative gates.
- Direct qualifying evidence for every pair in a candidate group. A chain of
  pairwise links does not justify merging endpoints without shared evidence.

Each merged record takes the highest original detector confidence per frame,
breaking ties by detection index. Geometry and semantic fusion use this one
representative. Other proposals remain linked as overlaps and add no vote.
Missing representative embeddings remain explicit; no duplicate embedding is
substituted. Raw observations, images, vectors and the journal stay unchanged.

The record keeps the lowest original object ID and its original detector label.
Here that is ID 2, **sink**, even though its best crop shows the bowl region.
`association_review` records both original IDs/labels and all witness frames;
`context.association_policy` names the optional policy. Labels are not corrected
by text similarity. IDs still belong only to their event-prefix/graph snapshot.
Label-only `find`/`last_seen` queries cannot use this mode because they would hide
one of the original labels. Default queries preserve the original association.

Depth, pose, keyframe eligibility, causal availability, 0.25 / 0.02 text filters,
freshness and planning gates remain unchanged. No dependency, schema migration,
camera access, permanent worker or motor interface is added.

## Measured results

These are reopened, contiguous prefixes of the original journal, not new queries
during playback. Only data already committed in each prefix contributes.

| Measurement | Actual-query prefix 871 | Source-cutoff prefix 932 |
| --- | ---: | ---: |
| Original bowl / sink supports | 28 / 11 | 29 / 11 |
| Merged geometric and semantic supports | 31 | 32 |
| Duplicate votes removed | 8 | 8 |
| Total provisional records, before / after | 3 / 2 | 3 / 2 |
| Merged bowl-region cosine | 0.252092 | 0.251910 |
| Selected records | ID 2 only | ID 2 only |
| Total geometric / semantic supports | 60 / 60 | 62 / 62 |

Both results retain the best crop `online.crops/37_1.png`, bounds
`[499,274,585,312]`. The other record is the earlier wrong refrigerator region;
it scores 0.118698 / 0.118344 for `a bowl`. The canonical sink label and marginal
scores are explicit limitations, not proof of a separate sink or reliable bowl
recognition. Fridge-depth failures and the detector's missing trash-can class
remain unresolved. Original operator rejections and confirmed node-21 crops are
preserved without assigning new human labels.

Independent source-event pose reconstruction and representative selection agree
with fused geometry within `2.23e-16` m. Scalar-normalized vector fusion/ranking
agrees within `3.13e-8`. Every retained crop hash and source input hash agrees;
the eight excluded votes remain traceable in the derived associations. Default
queries exactly reproduce both original snapshots, objects, rankings and planning
evidence. The separate `line_20260915` recording has zero qualifying merges:
its logical database remains identical, with 17 objects, 63 supports and all
11 frozen query rankings unchanged.

The 52 memory tests and 41 online-memory/semantic/search tests pass. New cases
cover one witness, conflicting frames, nearby objects, nested boxes, different
or missing depth samples, contradictory map points, incomplete transitive groups,
geometry drift and one vector per source frame. An earlier returned prefix cannot
gain witnesses from later commits.

A real GPU search-preview CLI on prefix 871 exits successfully and reproduces the
stored-vector result exactly. It takes 12.371 s including 11.190 s model loading;
the in-process snapshot query takes 251.632 ms. Peak process RSS is 1,377,320 KiB
and peak allocated CUDA memory is 228,483,584 bytes. This single functional run
is not a latency distribution or live throughput measurement.

Its current planning decision refuses `stale_or_future_map_evidence`. A separate
counterfactual at the original recorded read/decision times still returns
`NO_ROUTE` because the start is `unknown_cell`; it is explicitly marked as
retrospective. No ROS publication is requested. Native cleanup finds no remaining
query/capture/SLAM processes and 5,208,468 KiB available RAM. This is a bounded
cleanup check, not a long-duration leak test.

## Local reproduction and evidence

Private evidence is under `data/outputs/duplicate_tracks/steady_20260916/`:
`acceptance.json`, `audit.json`, `verification.json`, `gpu_verification.json`,
`cleanup.json`, `checkpoint_review.json`, both prefix databases and query/decision
reports, source-audit scripts and test logs. Initial audit-script serialization
and test-fixture failures remain in their logs; corrected complete runs pass.
Original room data and generated outputs are not committed.

From the repository root, use a fresh output directory:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../mobileclip-env/bin/python \
  scripts/online_search_preview.py \
  --db data/outputs/duplicate_tracks/steady_20260916/prefix_871/online.db \
  --model ../ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a bowl' --merge-duplicate-tracks \
  --output data/outputs/duplicate_tracks/manual_query
```

The saved prefix and its source crops must exist. A closed prefix should refuse
stale planning evidence; do not refresh its timestamps to obtain a route. Review
the generated `query/queries.html`, or the existing
`data/outputs/duplicate_tracks/steady_20260916/prefix_871/queries.html`.

Follow-up: the [temporal stability audit](query-stability.md) found a later
one-pixel sample change that reversed merging. The
[shared-depth extension](shared-depth-association.md) resolves that recorded split;
bowl selection still drops out. The optional mode remains disabled by default.
