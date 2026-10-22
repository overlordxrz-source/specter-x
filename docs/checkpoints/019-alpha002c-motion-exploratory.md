# Checkpoint 019 — Alpha 002-C: real motion experiment, exploratory run

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor` (from `0565b76`)
**Status:** **exploratory.** One real human-subject session was run on the
SoftAP link. The pre-registered primary endpoint **did not separate motion
from stillness**, and the pre-registered confound check **fired**. No motion
or respiration detection is claimed.

---

## 1. What was measured

Link: iPhone (station) → ESP32-S3 (SoftAP), **1.5 m**, both endpoints
**0.8 m** high, channel 6, 20 MHz, LLTF. The phone was fixed and untouched;
the subject stood at the same marked spot S for **both** conditions, so only
the arm moved.

| phase | what ran | result |
|---|---|---|
| Phase 0 | 300 s stability, subject still at S | **PASS** |
| Phase 1 | 12 trials × 20 s (6 `stationary`, 6 `hand`), shuffled in blocks, seed `20261022` | see §3 |

Payload selection was applied before any feature was computed: **5 795
payload frames kept, 8 205 null-data frames dropped**, 0 ambiguous. The
selection was verified on the live link before the session (101 payload /
295 null in 10 s) and has four unit tests.

## 2. Phase 0 — link stability (PASS)

7 290 records in 300 s: 3 042 payload (10.1/s), 4 248 null, 0 ambiguous.
0 sequence gaps, 0 malformed, 0 queue drops, longest gap 0.211 s, USB/console
byte drift 0.01 %, device-vs-host record count 0.50 % apart, nulls
7 290/7 290, coverage 52/52.

**Null of the frozen features**, 15 stationary bins of 202 payload frames:

| feature | mean | std | CV |
|---|---|---|---|
| `roughness_used` | 0.00744 | 0.00322 | 43 % |
| `amp_volatility` | 0.33729 | 0.16052 | 48 % |
| `shape_shift` | 0.00431 | 0.00292 | 68 % |

This is a **noisier null than the campus link of checkpoint 009** (whose
between-trial drift was ~1.2 %). All 3 042 payload frames arrived at PHY
rate 11, so the rate was not the cause; the link's own amplitude is simply
unstable at the 20 s scale (RSSI −61…−69 dBm while nothing moved).

**One pre-registered decision followed from this, before any condition
data:** the primary feature became `roughness_used` — the temporal change of
the per-packet **normalised** spectrum, which is insensitive to gain and
power drift. The other three became secondary, with Bonferroni α = 0.0125.

## 3. Phase 1 — the exploratory result

### 3.1 Confound check (pre-registered, and it fired)

| quantity | `stationary` | `hand` | difference | threshold | verdict |
|---|---|---|---|---|---|
| payload rate | 20.1/s | 22.8/s | **+13.5 %** | < 10 % | **FAIL** |
| RSSI mean | −59.2 dBm | −56.4 dBm | **2.8 dB** | < 2 dB | **FAIL** |
| dominant payload rate code | 138 B | 138 B | same | same | PASS |

### 3.2 Pre-registered analysis (seed 20261022, 1 000 permutations)

| feature | F | perm p | measured FP rate | Cohen's d | 95 % CI | held-out acc. |
|---|---|---|---|---|---|---|
| **`roughness_used` (primary)** | 0.383 | **0.543** | 0.049 | −0.357 | **[−1.59, 1.46]** | **0.50** |
| `amp_volatility` | 0.210 | 0.661 | 0.048 | −0.264 | [−1.45, 1.40] | 0.33 |
| `shape_shift` | 1.654 | 0.237 | 0.037 | −0.743 | [−2.24, 0.32] | 0.67 |
| `change_rate` | 0.161 | 0.668 | 0.060 | −0.231 | [−1.69, 0.90] | 0.42 |

**Primary endpoint: FAIL.** p = 0.543, held-out accuracy exactly at chance
(0.50), effect size small with a confidence interval that spans zero. No
secondary feature reaches even the uncorrected α = 0.05, let alone the
Bonferroni-corrected 0.0125.

The permutation procedure behaved as designed: its measured false-positive
rate was 0.037–0.060 against a nominal 0.05.

### 3.3 Post-hoc finding (exploratory, NOT pre-registered)

The **level** of the signal does change:

| | `stationary` | `hand` |
|---|---|---|
| mean total amplitude | 138.4 ± 56.0 | 219.2 ± 72.0 |
| Cohen's d (hand vs stationary) | **−1.14**, 95 % CI **[−2.60, −0.24]** | |
| rank AUC of the trial mean | **0.778** | |

The trial values overlap heavily (stationary 67–214, hand 131–327), so this
is a moderate, not a clean, separation. It is also **confounded**: the same
arm motion that raises the level also changed RSSI by 2.8 dB and the payload
rate by 13.5 %.

**The important point is what this says about the frozen features.** They
normalise each packet's spectrum by its own total, precisely so that they do
not track received power. On this link the motion signature is mostly a
**level** change, so the gain-free features are blind to the very effect the
link shows. That is a statement about feature choice, not about the link.

## 4. Two protocol deviations, recorded

1. **The payload rate was ~20/s, not the declared 10/s.** Phase 0 measured
   10.1 payload/s; Phase 1 measured 20.1–22.8/s. The phone was restarted
   between phases, and the app's effective rate changed. The comparison
   *within* Phase 1 is internally consistent (both conditions ~20–23/s), but
   the stimulus was not the declared 10 Hz and Phase 0's rate does not apply
   to Phase 1.
2. **Trial windows ran 22–23 s, not 20 s**, because the recorder drains the
   port after the requested window. Every trial was affected equally.

Neither deviation is hidden in the analysis; both are reported because a
reader comparing this with a later run needs them.

## 5. Interpretation, stated carefully

* **Established:** under the pre-registered analysis, on this link, geometry
  and session, hand motion at spot S did **not** produce a separable change
  in the frozen features.
* **Established (post-hoc):** the same motion produced a moderate **level**
  change (d = −1.14), which the frozen features discard by construction.
* **Not established:** that motion is undetectable on this link. The
  confound check failed, the sample is 6 per condition (64 % power for
  d = 1.5), and the texture effect observed (|d| ≈ 0.36) would need on the
  order of 100 trials per group to resolve — which is a signal that the
  feature, not the sample size, is the problem.
* **Not claimed:** any motion detection, any respiration result.

## 6. What the next pre-registration must fix

1. **A stimulus whose rate cannot drift.** Verify the payload rate before
   and after each trial, and abort a trial whose rate moves. The iOS app's
   effective rate changed between phases, which is unacceptable for a
   controlled comparison.
2. **A level-sensitive feature, pre-registered as primary**, if the claim is
   "motion changes the channel". The current feature set was built to be
   gain-free for the campus link; on this link it removes the effect.
3. **Separate the two confounds.** The RSSI change is arguably *part of* the
   effect here (the body is in the same place in both conditions, so the arm
   is the cause); the payload-rate change is a genuine nuisance because it
   changes what is sampled. The next design should state which is which
   **before** the run, rather than treating both as disqualifying.
4. **Or use phase.** Differential phase across subcarriers responds to path
   length, not power, and is the measurement the respiration work needs
   anyway. That is the natural next feature family.
5. **More repetitions and a second operator**, so the analyst is genuinely
   blind.

## 7. Evidence

| artefact | note |
|---|---|
| `phase0-short.raw`, `.raw.csi`, `.json`, `.log` | 300 s stability, PASS |
| `phase1-main.json`, `.log` | 12 trials, raw per-packet amplitude + `sig_len` |
| `filter-check.json`, `filter-check2.json` | payload-selection verification on the live link |
| `phase0-stability.raw*` | the aborted 900 s attempt (~27 s), kept, not used |

All under `runs/alpha002_hw_validation_20261022b/` (gitignored).

**No simulated result is reported anywhere in this checkpoint.**
