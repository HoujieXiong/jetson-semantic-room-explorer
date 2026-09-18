# Refuse targets using exact operator identity feedback

Status: `VERIFIED` for bounded saved-data decisions and real Jetson GPU query
sessions, 2026-09-18. General recognition improvement and live operation remain
unverified. No camera capture, ROS query publication or navigation occurred.

The optional `--identity-feedback` file connects the existing A/B operator review
to target refusal. If a selected localized candidate contains an explicitly
rejected source support, planning returns `selected_identity_rejected` with no
goal, route or frontier fallback. All supporting views are checked, including
views that are no longer the best-ranked crop. The original retrieval scores,
selected retrieval IDs, object associations and geometry remain visible.

## Diagnosis and scope

The original fridge query selected a localized bin/cabinet at 0.272432 while
separately retrieving the actual unlocalized fridge at 0.298652. Localized objects
and unlocalized images use independent selection groups. A better visual-only
score does not remove the localized candidate. The original planner also had no
runtime consumer of the saved operator review. The original live route was already
refused because its start was unknown; no wrong-target navigation was executed.

The operator explicitly rejected source view A (`8:2`) and confirmed B (`8:0`).
Those exact source crops do not appear in either later coordinated-frame journal.
The operator subsequently reviewed the prepared C/D/E page and stated:
"D and E are fridge and c is not". Separate feedback files now bind C's rejection
and D/E's confirmations to their exact later-session sources. C is one identical
source crop shared by both runs; D/E are distinct views. These labels do not
justify a new score threshold, a spatial blacklist or labels for further views.
This change consumes explicit feedback; it does not train a recognizer.

Feedback binds an exact query phrase, journal session, semantic event, node,
detection index, source timestamp and PNG SHA256. Current object IDs are derived
again from the snapshot's actual supporting views, rather than carried across
graph revisions. Confirmation does not approve other views or supply geometry.
A rejected support causes a conservative veto of the current selection, without
claiming every view in that candidate depicts the same physical object.

The report retains the operator statement, canonical feedback hash, individual
view outcomes and blocked IDs in `identity_review`. Another phrase is explicitly
`NOT_APPLICABLE_TEXT`; an unavailable source or a source excluded from the current
graph is reported separately. Another session, changed source/hash, duplicate or
conflicting entries and malformed input fail explicitly. An explicit JSON `null`
file cannot silently disable the feature. The bounded file contains 1–128 views.

Feedback is an external input to the current query, not a backdated journal event.
Old reports and journals remain unchanged. Callers must supply the feedback file;
omitting it retains the previous behavior. A later view without reviewed source
support remains unreviewed. Synonyms and whitespace/case variants do not inherit
an exact-phrase label.

## Measured verification

- 24 original reports across the live, baseline and coordinated journals reproduce
  identical rankings, source associations, geometry and decisions. Recomputed
  CPU duration fields are excluded from decision equality. An initial checker
  omitted frontier `selection_ms` from that exclusion; its failed log and source
  remain, with the correction recorded. No runtime result was changed.
- Eight original live prefixes/closed snapshots reopen with identical feedback
  outcomes. A vetoes localized candidate 1; B stays a confirmed visual-only view
  with `insufficient_valid_depth`, without a new map point or object ID. Six
  unrelated bowl/sink/elephant prefix/closed decisions remain unchanged.
- Replanning the original fridge prefix at its explicitly recorded historical
  decision time gives `selected_identity_rejected`, replacing its old unknown-start
  route refusal. This is a post-feedback counterfactual, not a new live decision.
  Current-time queries of the old journal retain `stale_or_future_map_evidence`;
  the original monotonic timestamps are never refreshed to make the map usable.
- A real SQLite/known-free-grid test proves that an otherwise reachable target
  becomes refused when its source is rejected. Tests also cover non-best support,
  graph removal, exact phrase, wrong session/hash/stamp/event, duplicate feedback,
  stale-map priority, confirmed visual-only evidence, saved review/JSON and the
  explicit-null CLI failure. All 59 online tests and 15 semantic regressions pass.
- Sixteen attempts to apply original A/B feedback to the two other sessions fail
  explicitly. No label is propagated by matching class, box overlap or proximity.
  All 56 original ranked crop files match their committed hashes, and all 33
  predeclared input hashes remain unchanged.
- After the explicit C/D/E confirmation, sixteen additional prefix/closed queries
  with the correct per-session files reopen exactly. Both later fridge prefixes
  veto candidate 1 using C; D/E retain insufficient-depth refusal and no geometry.
  Twelve unrelated query decisions remain unchanged. In total, 24 feedback
  reopening comparisons pass across the three journals. The two rejected source
  views A/C are vetoed; all three confirmed views B/D/E remain inspectable.
- Four actual GPU CLI requests with the feedback file return exact original text
  vectors and rankings. Separate encoder initialization is 21.756 s; full responses
  for fridge/bowl/sink/elephant take 2.952/0.270/0.281/0.279 s. Fridge records blocked
  ID 1; the other phrases record non-applicability. All four retain old-map refusal.
  There is no concurrent SLAM, so these are not live performance measurements.
- Available RAM stays at least 4,119,768 KiB; sampled query RSS peaks at
  1,438,192 KiB. CUDA allocated/reserved peaks are 228,483,584/243,269,632 bytes.
  The bounded 28.646 s supervisor closes its child with exit zero and no forced
  termination. Native inspection after this session finds no runtime process and
  4,920,028 KiB available RAM. Long-duration resource behavior is not tested.
- Two additional real GPU fridge queries exercise the newly supplied labels in
  both later journals. After separate 11.002 s initialization, responses take
  0.645/0.398 s and exactly preserve the original vectors, rankings and geometry.
  Both record blocked ID 1 and keep the stale/future-map refusal. Their bounded
  supervisor finishes in 14.569 s with exit zero and no forced termination;
  available RAM stays at least 3,648,880 KiB, query RSS peaks at 1,426,968 KiB and
  CUDA peaks match the first session. Final native cleanup finds no runtime process
  and 4,439,432 KiB available RAM. No capture or motion is performed.

For the five exactly labeled views, both negative supports are vetoed and all three
positive visual views are retained. This is not a recognition accuracy estimate.
False acceptance/refusal rates over other views remain unmeasured; confirmed
unlocalized views still cannot be navigation targets.

## Run and inspect

The local measured feedback file is
`data/outputs/identity_refusal/20260918/feedback.json`. Its schema is:

```text
schema_version: 1
session_id: exact journal session
text: exact query phrase
operator_statement: recorded human feedback
views: node_id, detection_index, source_stamp_ns, semantic_event_seq,
       crop_sha256, verdict (confirmed or rejected)
```

Example using that verified file and the original closed journal; choose a fresh
output directory on each invocation:

```bash
source scripts/rtabmap_odom_env.bash
~/projects/mobileclip-env/bin/python scripts/online_search_preview.py \
  --db data/outputs/live_warm/20260916/attempt_02/online.db \
  --model ~/projects/ml-mobileclip/checkpoints/mobileclip_s0.pt \
  --text 'a fridge' \
  --identity-feedback data/outputs/identity_refusal/20260918/feedback.json \
  --output data/outputs/identity_refusal/manual_query
```

The same flag works with the existing bounded `--session-requests` mode. Reports
show the veto even when an earlier map-freshness check supplies the primary refusal.
The browser review marks blocked targets while keeping original diagnostic crops.
The later journals require their own `baseline_feedback.json` or
`odometry_feedback.json` from the same evidence directory.

Private evidence under `data/outputs/identity_refusal/20260918/` includes the
predeclared comparison, exact feedback, initial/corrected checker, copied source
prefixes, verification reports, GPU requests/sessions, tests, runtime source
snapshots and cleanup. `operator_review_cde.json` preserves the user's exact reply
and the hash of the page they reviewed; the initial pending review stays unchanged.
The final null-file CLI guard was added after the first GPU run, tested separately,
and present in both later GPU queries. The source distinction is recorded.
The final review contains 22 verified embedded PNGs and needs no WebGL:

```bash
xdg-open data/outputs/identity_refusal/20260918/confirmed_review.html
```

Learning: an operator rejection is actionable evidence with a precise scope.
Retrieval similarity and valid depth do not establish identity, and positive
identity feedback cannot repair missing depth.

Next action: after fresh operator camera readiness, run a bounded stationary live
validation of coordinated source selection and source-reviewed target refusal,
checking whether the confirmed fridge view has usable depth.
