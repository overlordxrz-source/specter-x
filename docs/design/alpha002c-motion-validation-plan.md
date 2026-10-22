# Alpha 002-C — real human sensing: pre-registered validation plan

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor` (continues from `0565b76`)
**Status:** **plan only. No trial has been run. No motion or respiration
detection is claimed.** This document is written before the data so that the
analysis cannot be chosen after seeing the result.

---

## 0. What this stage can and cannot claim

| question | what a PASS would mean | what it would not mean |
|---|---|---|
| Does motion perturb this channel reproducibly? | On this link, in this room, with this subject, the frozen feature set separates *still* from *hand motion* on held-out trials, better than the measured null | that motion is detected in general, in other rooms, or through walls |
| Respiration (stretch) | the CSI phase tracks a *paced* breathing rate and moves when the pace moves | that breathing was measured physiologically; a belt is still required for that |

The smallest experiment that can answer the first question is **Phase 1**
below. Everything else is conditional on it.

---

## 1. Audit of what already exists

### Reused unchanged

`specter/sensors/esp32/analysis.py` is already the machinery this stage
needs, and it was written for exactly this reason:

| capability | implementation |
|---|---|
| frozen feature set | `FEATURE_NAMES` = `roughness_used`, `amp_volatility`, `shape_shift`, `change_rate` |
| rationale pre-registered | `FEATURE_RATIONALE` |
| blinding | `blinded_order(n, seed)` shuffles trial order before features are computed |
| effect size | `cohens_d`, `cohens_d_ci` (bootstrap), `partial_eta_squared` |
| omnibus test | `omnibus` (one-way ANOVA F on the feature) |
| false-positive rate | `permutation_test` — label permutation, the procedure's own FP rate |
| held-out evaluation | `cross_validate` — leave-one-repetition-out, nearest centroid on z-scored features |
| power / sample size | `power_by_simulation`, `required_n` |
| one call | `analyse_blinded(trials, seed, n_perm, alpha)` |

The four features are computed from per-packet amplitude spectra, normalised
per packet so they do not simply track received power. That normalisation
matters: RSSI moved over ~30 dB in the earlier campus session, and a feature
that tracks power would be measuring the room, not the motion.

### Reused with one necessary change

`tools/esp32_csi_motion.py` records labelled trials **in a single port
session** (opening the CDC port repeatedly is a demonstrated stall trigger,
checkpoint 007) and emits `{label, samples:[{t, id, rssi, channel,
local_timestamp, amplitudes}]}`. That is exactly the schema `analysis.py`
consumes.

**The change:** each sample must also carry **`sig_len`**. On this link the
receiver hears two frame populations — payload frames (138 B, the ping) and
null-data frames (28 B, association upkeep) — and the PHY rate differs
between them. Checkpoint 011 established that the amplitude scale follows the
rate, so mixing them would inject a rate-dependent amplitude difference into
the features. **Features will therefore be computed on payload frames only**
(`sig_len > 32`), and the null-frame count will be reported as a data-quality
indicator, not as signal.

This is a host-side change. No firmware is touched.

### What the old experiment did not have

* A **controlled stimulus**. The campus design sensed the AP's own downlink
  traffic, which the experimenter did not control, and its own conclusion was
  that the Mac could not be the stimulus. The new link fixes this: the phone
  is the station *and* the stimulus, at a rate the app sets.
* A **measured null on this link**. The F ≈ 0.012 null control belongs to a
  different link at ~145 packets/s. It is not transferable. Phase 0
  re-measures it.
* Checkpoint 009's `max F = 1.454` was **not** a detection: it had no
  blinding, no held-out evaluation and no false-positive measurement. That
  is why `analysis.py` exists, and this plan uses it.

---

## 2. The link and the geometry

All of this is measured and written down **before** the first trial.

| element | value |
|---|---|
| transmitter | iPhone, SoftAP station, `SPECTER-LAB`, channel 6, 20 MHz |
| receiver | ESP32-S3, SoftAP role, same board as Alpha 002-B |
| stimulus | 10 Hz ICMP (`192.168.4.1`), payload frames 138 B |
| distance A→B | **1.5 m** (measured by the operator, line of sight) |
| height | **both endpoints 0.8 m** |
| orientation | phone screen facing the board, position fixed (operator confirmed) |
| subject spot **S** | fixed point marked with tape, ~0.5 m from the midpoint of A→B, ~0.3 m off the path axis |

**The critical control:** the subject stands at **the same spot S for both
conditions**. `still` and `hand` differ *only* in what the arm does. If the
still condition were seated out of the path, the classifier could separate
the classes by body presence rather than by motion, and the experiment would
not test what it claims to test.

`empty` (subject outside the room) is a separate control. `empty` vs `still`
is expected to differ — a body in a room changes the channel — and is
reported as **body presence**, never as motion.

---

## 3. Phase 0 — link stability, 5 minutes

**Shortened from 15 minutes** after the operator's first attempt showed a
15-minute stillness requirement was not practical. A 900 s capture was
started and stopped after ~27 s; that partial capture is kept as evidence
but is **not** a stability test. The reduced run still measures rate, gaps,
drops, malformed lines and short-term drift; it does **not** characterise
drift over a quarter of an hour, and that limitation is recorded rather
than glossed over.

**Purpose:** prove the link is stable enough to attribute a trial difference
to a trial, and measure this link's null.

**Procedure:** phone stationary at A, subject still at spot S (the `still`
condition, which is the state the null must represent), 10 Hz ping running,
one continuous 300 s capture under scoring v3.

**Recorded:** packets/s over time, payload/null counts, longest gap, queue
drops, malformed lines, sequence gaps, RSSI and amplitude drift over 5 min,
and the within-condition variability (the null the features will be judged
against).

**Acceptance:** 0 drops, 0 malformed, 0 sequence gaps, longest gap < 1 s,
payload rate within ±10 % of 10/s for the whole run, no monotonic amplitude
trend larger than the within-trial noise.

**Abort:** if the payload rate falls below 5/s, or a gap exceeds 5 s, stop
and diagnose before any trial.

---

## 4. Phase 1 — the exploratory screening experiment

**This phase is exploratory.** Its outcome is a hypothesis about this link,
not a confirmation. Only Phase 2 — an independent session with a second
operator — can turn it into a confirmatory claim. A Phase 1 PASS licenses
Phase 2; it does **not** license a detection claim.

**12 trials in the main session, 20 s each, ~10 s lead-in, one port session.**

| condition | n | subject action |
|---|---|---|
| `stationary` | 6 | stands at S, arms down, still |
| `hand` | 6 | stands at S, moves one hand across the path at ~1 Hz, feet and torso still |
| `empty` | 4 | a **separate** 4 × 20 s block afterwards, subject outside the room (the operator is also the subject, so this cannot be interleaved) |

The label is **`stationary`**, not `still`: the frozen `change_rate` feature
selects its noise floor by that exact label, and any other name silently
produces NaN for it. This was caught before the first trial.

**Duration, stated:** 20 s at the observed 10 payload frames/s is ~200
payload frames per trial. The four features are per-packet statistics, so
that is adequate, but it is half the packets of the original 30 s design and
is recorded as such.

Order: randomised within blocks by a recorded seed (`--shuffle --seed`), so
slow drift cannot be read as a condition.

**Sample size.** 6 per group gives 64 % power for d = 1.5 at α = 0.05, and
less for smaller effects. This is a **screening** run, sized to the
operator's available time: it is powered only for a large effect, and a null
result is reported as "no effect ≥ the detectable size", not as "no effect".

**Phase 0 changed one thing, before any condition data.** The null run showed
the total amplitude is unstable even when nothing moves (15 stationary bins:
between-bin spread 43 % of the mean; `amp_volatility` CV 48 %), while all
3 042 payload frames arrived at a single PHY rate (11) so the rate was not the
cause. The **primary feature is therefore pre-registered as
`roughness_used`** — the temporal change of the per-packet *normalised*
spectrum, which is insensitive to gain and power drift. The other three are
secondary, reported with a Bonferroni-corrected α = 0.0125.

**Primary endpoint, pre-registered:** the four frozen features, payload
frames only, `analyse_blinded(seed=…)` with 1 000 permutations.

**An exploratory PASS requires all five:**

1. permutation test `p < 0.01`;
2. held-out AUC (leave-one-repetition-out) **≥ 0.80**;
3. |Cohen's d| **≥ 1.2** with the 95 % bootstrap CI excluding 0.5;
4. confound check: payload rate within 10 %, RSSI mean within 2 dB, and the
   same dominant PHY rate in both conditions;
5. the `empty` comparison is reported separately and is not used to support
   the motion claim.

If (4) fails, the verdict is **INCONCLUSIVE** regardless of AUC.

**An exploratory PASS licenses Phase 2 and nothing else.** It is not reported
as "motion detected"; it is reported as "this link separated these two
conditions in this session, better than its measured null, and here is the
effect size".

**FAIL** is a valid, reportable outcome: it bounds the effect this link can
see and tells us the stimulus or geometry must change.

**False positives** are reported as measured, two ways: the permutation
p-value distribution (the procedure's own FP rate), and an `empty`-vs-`empty`
split which must sit at chance.

**Blinding, stated honestly.** Trial order is randomised by seed and the
analysis blinds the order before computing features. The analyst *does*
announce the conditions during acquisition, so the analyst is **not** blind
to the labels. The protections that do not depend on analyst intent are the
pre-registered feature set, the permutation test and the held-out
evaluation. Full operator blinding would need a second person to run the
session; that is the correct next step for a confirmatory run.

---

## 5. Phase 2 — confirmation, only if Phase 1 passes

Same protocol, second session on a **different day**, and a second geometry
(distance changed), with the same pre-registered analysis, run by a **second
operator** so the analyst is genuinely blind to the condition order. A result
that does not replicate is reported as not replicating. Walking trials are
added here, not before, because walking is a much larger perturbation and
would make a weak `hand` result look better than it is.

---

## 6. Phase 3 — respiration, stretch goal, conditional

**Prerequisites, none of which exist yet:**

1. **Phase extraction.** The pipeline stores amplitude only; `rec.iq` holds
   the complex samples. The plan is to compute, per packet, the phase of the
   used subcarriers, remove the best-fit **linear slope across subcarrier
   index** (sample-clock offset), and use the residual. The common-mode
   intercept (carrier offset plus the radio's per-packet phase offset) is
   removed by using the **differential phase between subcarriers**, not the
   absolute phase.
2. **A still subject**, seated, 60 s windows (≈ 12–18 breaths).
3. **A reference.** A respiratory belt is the right instrument. Without one,
   the only defensible protocol is **paced breathing**: the subject breathes
   in time with an audible cue at a fixed rate, then at a second rate. That
   is a *protocol* reference, not a physiological measurement, and any result
   is worded accordingly.

**Clock and phase limitations, stated now:**

* each packet's phase carries an unknown offset; only *differences* are
  meaningful;
* sampling clock offset adds a slope across subcarriers, hence the linear
  removal;
* the firmware's gain compensation rescales amplitude, not phase;
* 10 payload frames/s is ample for 0.2–0.3 Hz (33–50 samples/cycle) but the
  packet arrival times jitter, so the spectrum must be computed on the
  recorded arrival times, not on an assumed uniform grid;
* AGC changes between packets can move the amplitude, which is why the
  amplitude-only route is the wrong measurement for respiration — the
  scoping document already says this.

**PASS:** the phase spectrum peaks at the paced rate in at least 4 of 5
windows, the peak follows a **change** in paced rate, and the result is not
reproduced by a phase-shuffled control.

---

## 7. Physical actions required from you

Before Phase 0:

1. **Place the phone** at one end of a clear line, propped so it cannot
   move, screen facing the board. Measure the distance to the board and the
   height of each — I need both numbers.
2. **Mark the phone position** with tape. It must not move for the whole
   session.
3. **Mark spot S** for the subject, ~0.5 m from the midpoint, ~0.3 m off the
   line between phone and board.
4. **Keep the ping app** at 100 ms, **foreground**, **screen on**,
   **auto-lock off** — for the whole session, including the 15-minute
   stability run. Plug the phone in if possible; the screen must stay awake.
5. **Remove other motion sources**: fans off or fixed, door closed, no other
   people walking through, chair not rocking.
6. **Phase 0**: leave the room and stay out for 15 minutes.
7. **Phase 1**: I will announce each trial. Stand at S and do exactly the
   announced action; between trials, stand clear and still during the
   washout.

Tell me the measured distance and heights, and confirm the phone cannot move.

---

## 8. What will be reported, and what will not

* Every result separately: Phase 0 stability, then Phase 1 omnibus F,
  permutation p, held-out AUC, Cohen's d with CI, false-positive rate, and
  the confound table.
* Every trial's raw evidence, with hashes, replayable offline.
* **No simulated result will be reported as a real detection.** Synthetic
  data may be used to test the analysis code, and will be labelled as
  synthetic wherever it appears.
* No motion or respiration claim until the pre-registered criteria are met.
