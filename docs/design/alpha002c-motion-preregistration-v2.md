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
| subject spot **S** | **longitudinal 0.00 m** from the midpoint (±0.05) and **lateral 0.30 m** perpendicular to the axis (0.25–0.35), marked with tape |

The subject stands at **S for both conditions**. Only the arm moves. This is
the control that prevents the classifier from separating *body presence*
instead of *motion*.

### 1.1 Frozen directional hypothesis

* **H1:** the mean paired difference
  `roughness(hand) − roughness(stationary)` is **greater than zero**.
* **H0:** it is less than or equal to zero.

The permutation test is **one-sided in that direction**: the p-value is the
fraction of the 1 024 sign-flip assignments whose mean is at least the
observed mean. A negative effect is reported with its sign and is a
**FAIL**; it is never converted into a two-sided PASS.

### 1.2 Recorded geometry — a session fact, not an example

The values in the table above are the measured bench setup. Immediately
before GO the operator re-measures them and they are written to
`<session>.geometry.json`:

```json
{"distance_m": 1.50, "phone_height_m": 0.80, "esp32_height_m": 0.80,
 "spot_longitudinal_m": 0.00, "spot_lateral_m": 0.30,
 "s_phone_horizontal_m": 0.808, "s_esp32_horizontal_m": 0.808,
 "accuracy": "measured", "method": "tape measure",
 "phone_orientation": "...", "recorded_utc": "...", "confirmed_by": "..."}
```

The analysis **refuses** (INVALID) if the record is missing, a field is
absent, or any value is outside: axis **1.45–1.55 m**, each height
**0.75–0.85 m**, longitudinal offset **−0.05…+0.05 m**, lateral offset
**0.25–0.35 m**. It then **recomputes**

```
s_phone_horizontal = hypot(L/2 + longitudinal, lateral)
s_esp32_horizontal = hypot(L/2 - longitudinal, lateral)
```

and rejects the session if either measured distance disagrees with the
computed one by more than **0.03 m**, if the radial offset
`hypot(longitudinal, lateral)` is outside **0.25–0.36 m**, or if S is closer
than **0.70 m** to either antenna.

**All of these distances are horizontal (floor-plane) distances.** The 3D
slant from the S mark to an antenna at ~0.8 m is
`hypot(0.808, 0.80) ≈ 1.14 m`; it is computed and recorded for transparency
but is never an input and must never be entered as `s_*_horizontal_m`.

The recorded values are echoed into the result JSON, so the geometry travels
with the verdict.

### Amendment 1 — geometry only (2026-10-22, before any data)

The original S definition was ambiguous ("0.5 m from the midpoint, 0.3 m off
the axis" mixed radial and lateral distance), and its worksheet construction
was arithmetically wrong: A and B at ±0.30 m with 0.50 m radii intersect at
**0.40 m** perpendicular, not 0.50 m.

Amended, and refrozen before collection:

* S is **centred longitudinally** (0.00 m, tolerance ±0.05) and **0.30 m
  lateral** (0.25–0.35). At L = 1.50 m this gives
  `|S−phone| = |S−ESP32| = 0.808 m`, not 0.90 m.
* The worksheet construction is now A/B at ±0.30 m with **0.425 m** radii
  (√(0.30²+0.30²)).
* The analysis checks the measured distances against the geometry.

**Unchanged by this amendment:** H1 and its direction, the primary feature,
the exact one-sided sign-flip test, the p/d_z/CI thresholds, the confound
gates, the exclusions and the session length. No statistical rule moved.

### Amendment 2 — distance definition only (2026-10-22, before any data)

0.808 m is a **horizontal** distance from the floor mark to an antenna's
floor projection. The 3D slant from the same mark to an antenna 0.80 m above
the floor is **≈1.14 m**, and recording it in the horizontal field would be
a unit/definition error. The fields are therefore named
`s_phone_horizontal_m` and `s_esp32_horizontal_m`; the analysis validates
only those and records the slant separately as derived information.

Nothing statistical changed: same hypothesis, direction, feature, test,
thresholds, exclusions and session length.

### Amendment 3 — declared-estimate geometry class (2026-10-22, before data)

A tape may not be available. The operator may then record the geometry with
`"accuracy": "estimated"` and a `"method"` ("visual", "paced", "phone
measure app", ...). Accepted ranges widen to: distance **1.30–1.70 m**,
heights **0.60–1.00 m**, longitudinal **±0.15 m**, lateral **0.18–0.42 m**;
the consistency tolerance is **0.10 m** and the minimum S-to-antenna
distance is **0.60 m**. The derived S distances may be computed from the
estimated L and lateral offset rather than measured.

The result echoes `"geometry_accuracy": "estimated"`, and every document
describing the session must call the geometry **estimated**, never verified.
This amendment changes geometry precision only: the hypothesis, direction,
primary feature, exact test, thresholds, confound gates, exclusions and
session length are unchanged.

### Amendment 4 — 3 s lead-in (2026-10-23, before any analysed data)

At the owner's request, the settling/washout before every trial is reduced
from 8 s to **3 s**. The spoken cue is followed by 3 s of silence, then
`go`. Scheduled time becomes 20 × 25 s + 20 × 3 s = **560 s ≈ 9.3 min**, and
the ping budget becomes **≈5,600** pings (leaving ~4,400 of the 9,999 limit).
The host cue delivery was also corrected so the full explanation finishes
before the lead-in begins; that is a timing fix, not a measurement parameter.

Rationale and limitation: the spoken explanation itself takes several
seconds and ends immediately before the 3 s countdown, so the subject still
has that explanation time to settle. However, 3 s is a shorter washout than
the original 8 s and may carry more hand-motion or physiological state into
the start of the next trial. The 0.10 s guard band is unchanged; the
trial-level features, primary endpoint, exact test, thresholds, confound
gates and exclusions are unchanged. No session has been analysed under
either setting; attempts 1–3 were aborted before producing a complete
session and are preserved as apparatus evidence only.

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
| one-sided exact floor | **1/1 024 = 0.00098** |

The seed, the realised order and the block ids are written into the session
JSON by the recorder; they are not reconstructed afterwards.

## 3. Ping budget and traffic

* The app is **restarted immediately before the session** so its counter
  starts near zero. The app runs through the washouts too, so the budget is
  the whole 660 s: **≈ 6 600 pings**, leaving ~3 400 of the 9 999 limit in
  reserve for setup and restarts.
* The operator records the app's displayed count at the start; the analysis
  checks that the payload count is consistent with the elapsed sensor time.
* **Fail closed:** if any trial has fewer than **225** payload frames
  (9/s × 25 s), a payload rate outside **8.5–11.5/s** measured on the
  *sample* span, a boundary uncertainty or sensor gap that is not finite, a
  clock reset or a late frame, or a trial length outside 25 ± 0.5 s, the
  session is INVALID. There is no partial analysis.

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
the p-value is the fraction of assignments whose mean is **at least** the
observed, i.e. **one-sided in the pre-registered direction** (hand rougher
than stationary). Exact, no normal approximation, floor 1/1 024.

The direction is fixed *because* motion is expected to increase the
roughness of the normalised spectrum. A negative effect is reported, not
counted as a PASS.

**Effect size:** paired Cohen's `d_z` with a 2 000-sample bootstrap 95 % CI
over blocks.

## 7. Acceptance criteria — all must hold

1. A complete, in-range, internally consistent geometry record; all 20 trials valid; no malformed
   CSI line after the first valid record;
   every trial 150+ payload frames, rate 9–11/s, span within 0.5 s of active,
   gap ≤ 0.5 s, boundary uncertainty ≤ 0.10 s.
2. Exact one-sided **p ≤ 0.01**.
3. **d_z ≥ 0.8** (positive direction) and the bootstrap CI lower bound
   **> 0**. A zero-variance separation (all ten differences equal) gives
   `d_z = +inf` and is a PASS; a non-finite *input* is INVALID.
4. Confound gate: median payload rate differs by **≤ 10 %**; the **modal PHY
   rate over frames** is identical in both conditions and each condition has
   **≥ 90 %** of its frames at that mode; every payload frame carries a rate.
   A missing rate is INVALID, a modal difference INCONCLUSIVE.
5. The sign of `d_b` is reported for all ten blocks (descriptive, not a
   second gate).

A session that meets 1–4 is **PASS**. Meeting 1 but failing 2 or 3 is
**FAIL**. Failing the confound gate is **INCONCLUSIVE**. Failing 1 is
**INVALID** — no statistics are computed.

## 8. Secondary analyses (reported, never substituted)

`amp_volatility`, `shape_shift`, mean total amplitude, mean RSSI. Each gets
the same exact paired test, with **Bonferroni α = 0.0125** (0.05/4). They
cannot turn a primary FAIL into a PASS.

`change_rate` is reported **descriptively only**: its noise floor is fitted
on the true labels of the other trials, so a label-free p-value cannot be
computed for it without rebuilding the feature under every sign flip. It is
shown for completeness and carries no gate.

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

The tool has no option that changes the statistics. It reads
`<session>.geometry.json` automatically; without it the verdict is INVALID. It prints PASS / FAIL /
INCONCLUSIVE / INVALID with the reason, the ten paired differences, the exact
p, `d_z`, its CI, the confound table and the five Bonferroni secondaries.
Tests (`tests/test_motion_v2_prereg.py`) pin each verdict: a synthetic
10-block effect PASSes, a null FAILs, an invalid trial INVALIDates, a rate
confound is INCONCLUSIVE, and a malformed post-start line INVALIDates.

## 14. What a FAIL means

A FAIL does **not** mean "CSI cannot sense motion". It means: on this link,
geometry and session, no effect large enough for this design was found.

**Power, stated honestly.** With 10 pairs and α = 0.01 the exact test has
about **29 % power at d_z = 0.8**, 46 % at 1.0, 65 % at 1.2 and **80 % at
d_z ≈ 1.4**. The design is powered for a large paired effect. A FAIL
therefore does not rule out a moderate one; the observed CI is the bound to
report, and a larger design is a separate preregistration.

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
