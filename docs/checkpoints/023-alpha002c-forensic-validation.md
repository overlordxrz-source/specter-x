# Checkpoint 023 — Alpha 002-C forensic validation

**Date:** 2026-10-23 (UTC)
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** **Exploratory positive result; not confirmatory.** Independent
replication is **PLANNED**, not run.
**Session:** `runs/alpha002c_motion_v2/session.json`, seed `20261023`,
20 trials, 3 s lead-in (Amendment 4).

## Verdict first

The first completed Alpha 002-C session gave a **positive exploratory
result**: hand motion produced a larger `roughness_used` than stationary in
all 10 blocks (exact one-sided p = 1/1024 = 0.00098, d_z = 1.69, 95% CI
[1.34, 2.91]), with no payload-rate or PHY confound. A separate minimal
implementation reproduced every trial feature and the primary statistics to
floating-point noise.

It is **not** an independent replication and **not** confirmatory. The
analysis validator was corrected after the first INVALID output (disclosed),
the 3 s amendment was present before data but was **not committed before
data**, geometry was estimated, and the p-value sits at the design floor: a
single discordant block would make p = 11/1024 = 0.0107, above the 0.01 gate.
The result therefore establishes a concrete, reproducible *phenomenon in one
session*, not a general or confirmed capability.

## 1. Evidence freeze

A SHA-256 manifest is committed at
`docs/checkpoints/023-alpha002c-evidence-sha256.txt`. It covers every
successful and aborted attempt file, both pre-checks, the geometry sidecar,
both result files, the independent recomputation, the protocol and
correction documents, the analysis/recorder source, and the test files.

The large raw artifacts are gitignored and remain local:

| File | Bytes |
|---|---:|
| `session.json` | 12,744,733 |
| `session.json.raw` | 8,252,237 |
| `session.json.trials.jsonl` | 7,355,968 |

The accepted session contains 20/20 valid trials, 5,095 selected payload
frames, 6,459 null frames, 17,837 raw CSI lines, 0 clock resets and no late
in-window frames. The session counter records `malformed=1`, the single
startup torn line discussed below.

## 2. Timeline and protocol freeze

| Time (local, 2026-10-22) | Event |
|---|---|
| 21:46 | 10 s pre-check retry PASS |
| 21:50 | attempt 1 archived after 2 completed trials |
| 21:53 | attempt 2 archived after 1 completed trial |
| 21:54 | attempt 3 stopped before trial 1; raw archived |
| 21:55:29 | Amendment 4 text (3 s lead-in) written to the preregistration |
| 21:56:41 | first lead-in cue of the accepted session (01:56:41 UTC) |
| 22:09:13 | last stop of the accepted session (02:09:13 UTC) |
| 22:10 | first frozen-analysis output: INVALID (startup torn line) |
| 22:13 | raw-validation correction and tests |
| 22:14:25 | commit `294b014` containing the session result, amendment, cue fix and correction |

The amendment file has not been edited since 21:55:29, so its current text is
the pre-session text; the session records `design.lead_in_s = 3.0`. However,
`294b014` was committed **after** the session. The amendment was pre-data in
substance, but it was not cryptographically frozen before data. That is a
real limitation of the first result, and the replication protocol below
freezes its protocol and hashes before any session starts.

The cue-overlap fix is host-side only. The accepted session's stop-to-next-go
intervals are 10.44–15.60 s (median 15.05 s), consistent with a completed
spoken explanation plus the 3 s lead-in; the two-voice overlap seen in
attempt 2 is absent. No radio or sensor parameter depends on the cue.

### Owner's account of the amendment

The owner's account: during an earlier 20-trial attempt, at approximately
trial 4, the owner stopped because the 8 s cooldown felt unnecessarily long,
**not** because of any sensing result, and then requested 3 s. The completed
session used the amended 3 s protocol.

The preserved completed-trial records are: **2** trials in `aborted-01`,
**1** in `aborted-02`, and **0** in `aborted-03`. The earlier record shows
attempt 1 stopped with "restart it, I got confused", attempt 2 stopped on the
two-voice cue bug, and attempt 3 stopped with "make it 3s instead of 8". No
artifact contains four completed trials; `aborted-01` has 1,994 raw CSI lines
and may include a partially recorded later trial, which can explain an
"approximately trial 4" recollection. The discrepancy is recorded rather
than smoothed over.

What is supported by the evidence: no aborted attempt was put through the
frozen analysis, no condition-level statistic was computed before the
amendment, and the stop reasons were operator/cue/timing, not a difference in
`roughness_used`. What is not supported: a claim that four complete trials
were recorded before the stop.

## 3. Analysis-correction audit

The frozen review commit `58aaf4b8` states the raw rule as **"at most the
first torn line allowed"**; the module docstring says a malformed CSI record
**after the first valid one** invalidates the session. The accepted raw
stream has a truncated prefix on physical line 0, immediately followed by
the first complete record:

```
CSI_DATA,121885,...,-96,0CSI_DATA,125402,...,138,1,128,0,"[...]"
```

`CsiParser.feed_resilient` returns one complete record and
`malformed=True` for that line. The old `validate_raw` set `seen_valid=True`
before testing `outcome.malformed`, so the startup prefix was treated as
malformed *after* the first record. The original output was INVALID; it is
preserved at `runs/alpha002c_motion_v2/result-frozen-invalid.json` with only
`raw_problems` non-empty (design, geometry and trial problems were empty).

The correction changes only `validate_raw`:

- it counts torn CSI lines;
- it allows at most the first torn line, and only before any valid record;
- it still rejects a torn line after a valid record, a second torn line,
  recorder `malformed > 1`, clock resets, late frames, missing/empty raw,
  and raw CSI records fewer than the selected payload frames.

`git diff 294b014^ 294b014 -- tools/alpha002c_motion_v2.py` shows no change
to the design, trial, geometry, feature, test, threshold or bootstrap code.
The 10 forensic tests in `tests/test_alpha002c_forensic.py` exercise each raw
INVALID condition; the existing 26 preregistration tests still pass. The full
suite is **398 passed, 1 skipped** (the unrelated DI-188 hardware test). The
correction is rule-consistent, but it was made **after** the INVALID output
and it is the reason a PASS is reportable. That is why the result is
classified exploratory, not confirmatory.

## 4. Independent recomputation

`tools/alpha002c_independent_recompute.py` does not import the frozen
analysis or feature module. It re-implements payload filtering
(`sig_len >= 33`), the LLTF used-subcarrier mask, row-normalised spectrum,
mean absolute packet-to-packet change, exact one-sided sign-flip and the
seeded percentile bootstrap.

| Block | `hand - stationary` |
|---:|---:|
| 0 | 0.0002539251 |
| 1 | 0.0001039040 |
| 2 | 0.0003774126 |
| 3 | 0.0002287845 |
| 4 | 0.0001870521 |
| 5 | 0.0006171158 |
| 6 | 0.0007014234 |
| 7 | 0.0001467361 |
| 8 | 0.0003160341 |
| 9 | 0.0004120399 |

- mean difference: **0.0003344427**
- exact p: **0.0009765625** (1/1024, 1 hit of 1024 sign assignments)
- d_z: **1.6946320**, 95% CI **[1.3414406, 2.9061289]**

Comparison with `result.json`: p identical; d_z differs by 1.3 × 10⁻⁸; CI
endpoints differ by 5.3 × 10⁻⁸ and 2.1 × 10⁻⁷; maximum per-trial
`roughness_used` difference is 1.7 × 10⁻¹¹; all labels, blocks and payload
counts match. This is floating-point accumulation, not a substantive
disagreement.

## 5. Carryover, order and correlated errors

These are **exploratory diagnostics**, not a new primary analysis.

- The 3 s lead-in is not the whole rest. Because the spoken explanation is
  blocking, the stop-to-next-go gap was **10.44–15.60 s** (median 15.05 s);
  the gap from stop to the start of the 3 s lead-in was 7.44–12.58 s.
- Position effect (second trial minus first within block, ignoring
  condition): mean **+0.0000181**, about 5 % of the primary mean difference;
  6 blocks positive, 4 negative. No consistent order bias.
- Hand-first blocks (n = 4): mean paired difference **0.0003955**;
  hand-second blocks (n = 6): **0.0002938**. The difference is +0.0001017.
  A simple hand→stationary carryover would tend to *reduce* the hand-first
  contrast (stationary is second), not increase it; the observed direction
  is therefore not a clean carryover signature, but the groups are small.
- Mean `roughness_used` by current/previous condition: hand after stationary
  0.002320 (n = 6), hand after hand 0.002711 (n = 4), stationary after hand
  0.002232 (n = 5), stationary after stationary 0.002153 (n = 4). The
  hand-after-hand elevation could be drift or carryover; it is not
  distinguishable here.
- Lag-1 correlation: **0.578** for raw trial values, **0.712** after
  removing condition means. Gap length versus the next trial's residual:
  r = **−0.067**. The serial correlation is real but is not explained by the
  3 s interval; it is more consistent with slow session drift.
- Block trend: correlation of paired difference with block index **0.335**;
  first-half mean difference 0.000230, second-half 0.000439. All ten
  differences remain positive.
- Leave-one-block-out: every 9-pair subset gives p = 1/512 = 0.00195,
  d_z 1.57–1.89, CI lower 1.25–1.53. No single block creates the PASS.

Interpretation: the session does **not** show a detectable short-term
carryover attributable to the 3 s lead-in; the actual movement-free gaps were
longer than 3 s, and gap length was unrelated to the next residual. It does
show serial correlation/drift and a modest hand-first/hand-second difference.
With one session and 10 pairs, small carryover cannot be ruled out. The
primary result was not changed by these diagnostics.

## 6. What the result proves and does not prove

**Proves, conditional on the corrected raw gate and this session:**

- In this room, with this ESP32-S3/phone/firmware/subject and the frozen
  instructions, `roughness_used` was higher during hand motion than during
  stationary in 10/10 blocks.
- The exact one-sided test reaches its minimum p, the paired effect is large
  (d_z = 1.69), the bootstrap interval excludes zero, and the rate/PHY
  confound gates are clear.
- The acquisition and analysis pipeline can produce a complete, valid,
  independently recomputable session.

**Does not prove:**

- Independent replication or generality across subjects, rooms, phone/board
  orientations, distances, firmware or motion types.
- A spatial, through-wall, localization or presence-detection capability.
  This is a single-link CSI amplitude/roughness contrast with an instructed
  hand movement.
- That the 3 s washout is sufficient in general. The effective gaps were
  longer, no short-term effect was detected, but power is low and serial
  correlation is present.
- A confirmatory result. The post-data validator correction, the uncommitted
  pre-data amendment, the estimated geometry, the lack of operator blinding
  and the p-at-floor fragility all stand against that label.
- That `roughness_used` is specific to hand motion rather than body motion,
  presence or slow environmental drift. The stationary/hand contrast is
  instructed, not blinded to the subject.

## 7. First result versus independent replication

The accepted session is the **first completed positive exploratory result**
and the reference protocol. It is not the independent replication. The
replication must be a new session with its own pre-registered and hashed
protocol, a measured geometry, a complete ping-counter record, and an
analyst who is not the subject; it must report PASS/FAIL/INCONCLUSIVE/INVALID
under the same primary feature and decision criteria, without pooling or
retrospective endpoint changes.

The replication protocol is in
`docs/design/alpha002c-replication-protocol-v1.md` (status **PLANNED**, no
session run).

## 8. Evidence

- `docs/checkpoints/023-alpha002c-evidence-sha256.txt` — SHA-256 manifest
- `runs/alpha002c_motion_v2/session.json`, `.raw`, `.trials.jsonl`
- `runs/alpha002c_motion_v2/result.json` — corrected PASS
- `runs/alpha002c_motion_v2/result-frozen-invalid.json` — original INVALID
- `runs/alpha002c_motion_v2/independent-recompute.json`
- `runs/alpha002c_motion_v2/carryover-diagnostics.json`
- `runs/alpha002c_motion_v2/precheck-10s-retry.json` — PASS
- `runs/alpha002c_motion_v2/aborted-01/`, `aborted-02/`, `aborted-03/`
- `docs/design/alpha002c-analysis-correction-01.md`
- `docs/design/alpha002c-motion-preregistration-v2.md` (Amendment 4)
- `tools/alpha002c_independent_recompute.py`
- `tests/test_alpha002c_forensic.py`
