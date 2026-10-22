# Alpha 002-C — motion preregistration v2 (frozen before data)

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** frozen. No human trial has been run under this document. The
operator has not yet confirmed the physical setup.

Supersedes the six-block design in checkpoint 019/020, which **could not
reach p < 0.01**: six blocks of one stationary and one hand trial give
2⁶ = 64 within-block assignments, so the two-sided floor is 2/64 = 0.03125.

---

## 1. Fixed apparatus and geometry

| element | value |
|---|---|
| transmitter | iPhone, station on `SPECTER-LAB`, 100 ms ICMP to `192.168.4.1` |
| receiver | ESP32-S3, SoftAP role, firmware at the validated Alpha 002-B image |
| distance | **1.5 m**, line of sight |
| height | **0.8 m** at both ends |
| channel / width | 6, 20 MHz, LLTF |
| phone | fixed on its mark, screen facing the board, untouched |
| subject spot **S** | 0.5 m from the midpoint of the path, 0.3 m off the path axis, marked with tape |

The subject stands at **S for both conditions**. Only the arm moves. This is
the control that prevents the classifier from separating *body presence*
instead of *motion*.

## 2. Design

**10 randomised blocks. Each block contains exactly one `stationary` and one
`hand` trial, in an order drawn from a recorded seed.**

| | |
|---|---|
| trials | 20 |
| trial length | **25 s** |
| settling / washout | **8 s** before every trial (spoken cue, then `go`) |
| scheduled time | 20 × 25 s + 20 × 8 s = **660 s ≈ 11 min** |
| blocks | 10 |
| within-block assignments | **2¹⁰ = 1 024** |
| two-sided exact floor | **2/1 024 = 0.00195** |

The seed, the realised order and the block ids are written into the session
JSON by the recorder; they are not reconstructed afterwards.

## 3. Ping budget and traffic

* The app is **restarted immediately before the session** so its counter
  starts near zero. Twenty-five seconds × 20 trials × 10/s = **5 000 pings**,
  half the 9 999 limit.
* The operator records the app's displayed count at the start; the analysis
  checks that the payload count is consistent with the elapsed sensor time.
* **Fail closed:** if any trial has fewer than 150 payload frames, a payload
  rate outside **9–11/s**, or a sensor gap above 0.5 s, the session is
  INVALID. There is no partial analysis.

## 4. Acquisition rules (already implemented and bench-validated)

* one continuously drained serial reader for the whole session, including
  cues and washouts;
* trial windows assigned by the **device acquisition timestamp**, with the
  host cue mapped through the one-sided minimum delivery delay;
* a 0.10 s guard band excluded at each boundary and counted;
* GO is taken only after **at least 10 valid frames** exist;
* raw serial bytes, cue events in both clocks, and the design are preserved.

## 5. Preprocessing (frozen)

1. Payload frames only: `sig_len ≥ 33` (28 B frames are association upkeep).
2. 64-slot LLTF layout; the 12 structural nulls are excluded, and carriers
   0–1 are dropped if the hardware flags the first word invalid.
3. Each packet's spectrum is normalised by its own total.
4. No outlier removal, no smoothing, no per-trial trimming, no window
   selection after seeing the data.

## 6. Primary endpoint

**Feature:** `roughness_used` — the mean absolute change of the normalised
spectrum between consecutive packets. It is **trial-local**: it uses no
reference fitted on other trials, so it cannot leak across blocks.

**Test:** for each block `b`, `d_b = roughness(hand_b) − roughness(stationary_b)`.
Statistic = mean of `d_b`. The null is the exact set of **2¹⁰ sign flips**;
the p-value is the fraction of assignments whose |mean| is at least the
observed. Two-sided, exact, no normal approximation.

**Effect size:** paired Cohen's `d_z` with a 2 000-sample bootstrap 95 % CI
over blocks.

## 7. Acceptance criteria — all must hold

1. All 20 trials valid; no malformed CSI line after the first valid record;
   every trial 150+ payload frames, rate 9–11/s, span within 0.5 s of active,
   gap ≤ 0.5 s, boundary uncertainty ≤ 0.10 s.
2. Exact two-sided **p ≤ 0.01**.
3. **|d_z| ≥ 0.8** and the bootstrap CI lower bound **> 0**.
4. Confound gate: median payload rate differs by **≤ 10 %**, and the dominant
   PHY rate is the same in both conditions.
5. The sign of `d_b` is reported for all ten blocks (descriptive, not a
   second gate).

A session that meets 1–4 is **PASS**. Meeting 1 but failing 2 or 3 is
**FAIL**. Failing the confound gate is **INCONCLUSIVE**. Failing 1 is
**INVALID** — no statistics are computed.

## 8. Secondary analyses (reported, never substituted)

`amp_volatility`, `shape_shift`, `change_rate`, mean total amplitude, mean
RSSI. Each gets the same exact paired test, with **Bonferroni α = 0.01**
(0.05/5). They cannot turn a primary FAIL into a PASS.

## 9. Motion-induced level changes vs artifacts

| observation | interpretation |
|---|---|
| normalised-texture change (`roughness_used`, primary) | the claim |
| RSSI / mean-amplitude change | a **genuine** channel effect of the arm in the path (the body is at the same spot), but **secondary**: it is a level change, not the texture claim. Reported, not gated |
| payload-rate change | **artifact**: the sampling changes. > 10 % → INCONCLUSIVE |
| dominant PHY-rate change | **artifact**: the amplitude scale follows the rate. Different → INCONCLUSIVE |
| gain/AGC change | the firmware applies gain compensation and the gain state is not recorded. The per-packet normalisation removes a common gain; a per-subcarrier gain change would surface in `shape_shift`, which is secondary. Stated as a limitation |

A level difference is therefore *expected* and is not treated as a failure;
it is also not evidence for the primary claim. The primary is deliberately
insensitive to it.

## 10. Exclusions

**None after the fact.** A trial is excluded only by the validity rules in
§7.1, which are evaluated before any feature is computed. If any trial is
invalid, the whole session is INVALID — the protocol does not analyse "the
good trials", because doing so would let the data choose its own exclusions.

## 11. Attach-time transport corruption

Every splice in the preserved evidence occurred on **line 0** of a capture:
the device truncated a record while no host was reading. Under this protocol:

* GO requires 10 valid frames, so the offset is never estimated from one;
* the parser counts a torn first line as malformed and the raw preserves it;
* the analysis **allows at most the first torn line** and declares the
  session INVALID if any malformed CSI line appears after the first valid
  record;
* a malformed record can never enter a trial: the parser rejects it before
  the window selection.

**Status of the underlying defect: OPEN at the device side.** The fix is a
firmware write-retry; no firmware will be flashed for this trial.

## 12. Skipped test disposition

`tests/test_alpha001_acceptance_real.py:46` is skipped because no DI-188 is
attached (it needs the real instrument). It is unrelated to this protocol,
remains correctly skipped, and none of the motion gates depends on it.

## 13. Machine-readable analysis

```bash
python3 tools/alpha002c_motion_v2.py \
  runs/alpha002c_motion_v2/session.json \
  --out runs/alpha002c_motion_v2/result.json
```

The tool has no option that changes the statistics. It prints PASS / FAIL /
INCONCLUSIVE / INVALID with the reason, the ten paired differences, the exact
p, `d_z`, its CI, the confound table and the five Bonferroni secondaries.
Tests (`tests/test_motion_v2_prereg.py`) pin each verdict: a synthetic
10-block effect PASSes, a null FAILs, an invalid trial INVALIDates, a rate
confound is INCONCLUSIVE, and a malformed post-start line INVALIDates.

## 14. What a FAIL means

A FAIL does **not** mean "CSI cannot sense motion". It means: on this link,
geometry and session, with a design powered for a large paired effect
(|d_z| ≥ 0.8), no such effect was found. The detectable effect can be bounded
from the observed CI and reported as such.

## 15. Physical instructions for the operator

**Before the session**

1. Leave the phone and board exactly on their marks (1.5 m, 0.8 m, both
   fixed). Do not move either.
2. **Restart the ping app**: 100 ms, `192.168.4.1`, continuous. Keep it in
   the foreground, screen on, auto-lock **off**, plugged in.
3. Note the app's starting count and tell me; it must be far below 9 999.
4. Stand at the taped spot S and stay there.

**During the session (~11 minutes)**

5. You will hear, for each of 20 trials: *"Trial N of 20. [condition].
   Starting in 8 seconds."* then **"go"**, then 25 s later **"stop.
   relax."**
6. **stationary:** arms down, feet still, breathe normally.
7. **hand:** stay at S, sweep one hand across the line between the phone and
   the board about once per second; feet and torso still.
8. Between trials stay at S; do not touch the phone or the board.
9. No other person enters the room; the door stays closed.
10. If the phone locks or the app stops, say so immediately — the session
    will be INVALID rather than analysed.

**Do not start until the operator confirms the setup.**
