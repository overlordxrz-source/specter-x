# Checkpoint 024 — Alpha 003 preparation

**Date:** 2026-10-23
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** feasibility, preregistration and offline infrastructure complete.
**No Alpha 003 human session has been run. No presence, occupancy,
respiration, tracking or localization claim is made.**

Alpha 002-C remains a positive **exploratory** hand-motion result with
independent replication pending. Its replication protocol is unchanged and
still frozen at `docs/design/alpha002c-replication-protocol-v1.md`.

## Verdict first

- **Empty vs moving** is the physically strong case and the correct first
  experiment. It is still movement detection, not presence.
- **Empty vs stationary** is the hard presence problem. A still body changes
  the static multipath by a small amount that competes with drift, posture,
  door state, furniture and device orientation. It is plausible in a
  controlled room with an empty baseline; it is **not** established.
- **Three-class** is staged after the two binary questions.
- **Respiration** is exploratory: raw IQ exists, but commodity ESP32 phase
  is dominated by CFO/SFO/jitter. It needs a still subject, a controlled
  short link, long windows and a respiratory belt.
- **Tracking/localization** is not possible with one TX/RX link and one
  antenna each. It waits for multiple links/antennas and a synchronized
  clock.

## Deliverables

| file | purpose |
|---|---|
| `docs/design/alpha003-human-presence-feasibility.md` | physics, hardware inventory, what each feature can/cannot measure, staged plan, component requirements |
| `docs/design/alpha003-presence-preregistration-v1.md` | planned 3-condition, multi-session protocol; endpoints, gates, confounds, exclusions, stop rules |
| `specter/sensors/esp32/presence.py` | raw-IQ attachment, amplitude/differential-phase features, trial QC, session-independent nearest-centroid evaluation, bootstrap and permutation null, confound ablations |
| `specter/sensors/esp32/presence_synthetic.py` | synthetic empty/stationary/moving fixture with drift, PHY/RSSI variation and known truth |
| `tools/alpha003_presence_bench.py` | synthetic-only benchmark; explicitly not physical evidence |
| `tools/alpha003_presence_analyze.py` | recorded-session runner; refuses labels outside Alpha 003 conditions; applies trial QC; reports calibrated and uncalibrated presence |
| `tests/test_alpha003_presence.py` | phase, raw-IQ attachment, features, grouped folds, null control, calibration, QC |

## What the current hardware can test

- Raw IQ is already preserved by the Alpha acquisition. On the accepted
  Alpha 002-C session, all **11,554** trial samples matched raw records;
  IQ-derived amplitudes differed from stored amplitudes by at most **0.005
  ADC count**. Phase extraction is host-side; no firmware change.
- Empty vs moving, after owner authorization: no new hardware, one link,
  marked room, controlled door and baseline.
- Empty vs stationary **with a baseline**, after authorization: plausible
  but unproven; the protocol requires balanced standing/sitting and
  session-independent evaluation.
- Differential-phase micro-motion: plausible in a stable link; current
  phase is not calibrated and must not be treated as distance.
- Synthetic pipeline checks: complete; these do not count as physical
  evidence.

## What must wait

| capability | missing component |
|---|---|
| stationary presence without a baseline, robust across rooms | more independent sessions and a drift/room study; no single-link guarantee |
| multi-person counting | multiple links/antennas and labelled multi-person data |
| angle/range/tracking | antenna array or multiple synchronized receivers/transmitters; phase-coherent clock |
| respiration with physiological ground truth | respiratory belt on the same clock; still subject; 60 s windows; phase-quality study |
| through-wall claim | controlled wall/geometry study; not inferred from one link |

## Offline infrastructure and controls

- Features: `roughness_used`, `amp_volatility`, differential-phase
  `phase_roughness`/`phase_std`, `phase_resp_ratio`, normalised
  `profile_distance`, and `rssi_mean` (ablation only).
- Fixed classifier: nearest centroid on training-only standardisation. No
  feature selection or hyperparameter search.
- **Leave-one-session-out** evaluation; no frame-level random splits.
- Session bootstrap intervals for balanced accuracy and empty FPR.
- Label permutation within sessions for the null.
- Ablations: all, no-RSSI, amplitude-only, phase-only, RSSI-only.
- Calibrated presence (held-out session's empty baseline) is labelled
  separately from uncalibrated presence (training-only empty reference).
- Trial QC: 30 s window, 270 payload frames, gap/uncertainty/clock/late/
  label checks.

Full suite: **411 passed, 1 skipped** (the unrelated DI-188 hardware test).

### Synthetic smoke benchmark — not physical evidence

Command:

```
.venv/bin/python tools/alpha003_presence_bench.py \
  --sessions 5 --blocks 6 --seconds 8 --permutations 50
```

Five synthetic sessions, 90 trials. The fixture gave empty-vs-moving
balanced accuracy 1.00; empty-vs-stationary 0.933 with all features, 0.983
amplitude-only, 0.517 phase-only and 0.583 RSSI-only. The stationary result
is a property of a favourable synthetic static profile, not a room
measurement. The useful result is that the pipeline runs, the phase-only
path is not automatically sufficient, and the RSSI-only ablation is
reported. No accuracy number here is a presence claim.

## Preregistration summary

- 12 randomised blocks/session, one trial each of `empty`, `stationary`
  (balanced standing/sitting), `moving`; 30 s per trial; 3 s cue lead-in;
  15 s settle.
- Minimum 3 sessions, target 4–5; leave-one-session-out.
- H1 empty vs moving; H2 empty vs stationary (the presence question); H3
  three-class exploratory; H4 phase ablation; H5 posture.
- Confirmatory H2 gate: balanced accuracy ≥ 0.80, empty FPR ≤ 0.10, lower
  95% session-bootstrap CI > 0.60, permutation p < 0.01, both postures
  recall ≥ 0.70, full model beats RSSI-only by ≥ 0.05, rate/PHY gates
  clear.
- A single session is exploratory. Calibrated presence is reported
  separately from uncalibrated presence.
- Drift, posture, environment, RSSI/PHY, traffic rate, temporal correlation
  and false positives are explicit controls, not post-hoc explanations.

## What this checkpoint proves

It proves that the project now has a runnable, testable offline foundation
for the Alpha 003 question, and a preregistered plan that separates movement
from stationary presence and separates code checks from physical evidence.

It does **not** prove that a person can be detected, counted, tracked or
localized, and it does not upgrade Alpha 002-C from exploratory to
confirmatory.

## Guardrails

- No human experiment was started.
- No firmware was flashed.
- No branch was merged.
- The FRONTIER/SPECTER-WORLD worktree was not touched.
- The Alpha 002-C replication protocol remains frozen and available.
