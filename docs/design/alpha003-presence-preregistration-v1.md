# Alpha 003 presence preregistration v1

**Status:** **PLANNED — NOT RUN.** No human session, no presence claim, no
occupancy claim. This document is written before any Alpha 003 data.
**Parent evidence:** Alpha 002-C exploratory hand-vs-stationary result
(`a3c540d`); not empty-vs-occupied evidence.
**Frozen analysis:** `specter/sensors/esp32/presence.py`; synthetic-only
benchmark `tools/alpha003_presence_bench.py`; recorded-session runner
`tools/alpha003_presence_analyze.py`.
**Alpha 002-C replication protocol:** unchanged at
`docs/design/alpha002c-replication-protocol-v1.md`.

## 1. Questions and estimands

- **H1 (movement):** in held-out sessions, trials with a moving person are
  distinguishable from empty trials.
- **H2 (presence):** in held-out sessions, trials with a stationary person
  are distinguishable from empty trials. This is the presence question.
- **H3 (three classes):** empty, stationary and moving are jointly
  distinguishable. Exploratory; never a substitute for H1/H2.
- **H4 (phase):** differential-phase features add information beyond
  amplitude and RSSI features. Exploratory; reported as an ablation.
- **H5 (posture):** stationary presence is not specific to one posture.
  Standing and sitting are balanced; each is reported.

The estimand is **this link, this room, this protocol, these subjects**, not
"human presence" in general.

## 2. Design

### 2.1 Conditions

| label | action | notes |
|---|---|---|
| `empty` | no person in the room; door closed; chair fixed and empty | subject exits; 15 s settle before recording |
| `stationary` | at marked spot S; either standing or sitting, balanced | chair fixed; posture recorded; feet/torso still |
| `moving` | walk back and forth on a marked 1.5 m path near the link | normal walking, ~1 m/s; path marked; no hand-only motion |

The stationary condition deliberately mixes standing and sitting. A model
that only works for one posture does not establish presence; report both.
Posture is recorded in the run log and attached to each trial's `posture`
metadata before analysis; the condition label remains `stationary`.

### 2.2 Blocks and sessions

- **12 randomised blocks per session**, each block containing exactly one
  trial of each condition (36 trials/session).
- 30 s active window per trial; 0.10 s guard; 15 s room/transition settle;
  door closed during every recorded window.
- Order within block randomised by a recorded seed; order differs between
  sessions.
- **Minimum 3 sessions**, different days/times; target 4–5. A session is one
  continuous recording on one day with one geometry.
- The subject is one consenting adult per session. A second subject is a
  separate replication, not pooled silently.

### 2.3 Physical geometry

Use the same nominal link as Alpha 002-C, measured before the session:

| quantity | target | measured range |
|---|---:|---:|
| phone-to-board antenna distance | 1.50 m | 1.45–1.55 m |
| both antenna heights | 0.80 m | 0.75–0.85 m |
| S lateral offset | 0.30 m | 0.25–0.35 m |
| S longitudinal offset | 0.00 m | −0.05 to +0.05 m |
| S horizontal distance to each antenna | 0.808 m | ±0.03 m consistency |
| moving path | 1.5 m line, ~0.5 m from link | marked on floor |

Measure L and heights three times; record all values, mean and max
deviation. Mark the phone, board, S and the moving path with tape. The
chair stays in the same place for empty and stationary. Non-metallic
stands; phone screen facing the board; no metal in the link path.

### 2.4 Room controls

- Door closed for all recorded windows; door state recorded.
- No other people, pets, fans or moving objects during trials.
- Phone on a fixed stand, screen on, ping app foreground, auto-lock off.
- A fixed walk path; the subject does not step off it during moving trials.
- Record room, time of day, temperature if available, and any furniture
  change.

## 3. Confounds and controls

| confound | control / measurement | gate |
|---|---|---|
| channel drift | randomised order, empty at the start/end of each session, time-of-day recorded; drift-only session/segments | drift must not produce a false occupied verdict above the FPR gate |
| RSSI / shadowing | RSSI logged; **RSSI-only ablation**; do not require equal RSSI (a body changes it) | if RSSI-only matches full model (within 0.05 balanced accuracy), do not claim multipath presence |
| PHY rate | modal PHY per condition; per-frame rate recorded | modal PHY must be equal; otherwise INVALID |
| traffic rate | fixed ping app; payload rate per trial | relative rate difference ≤ 10 %; otherwise INVALID |
| posture | balanced sitting/standing; posture metadata | each posture recall ≥ 0.70 for a posture-general claim |
| environment | same room, door closed, fixed furniture; session/day as group | cross-session test only; cross-room later |
| temporal correlation | trial/block/session as unit; leave-one-session-out; block/session bootstrap; label permutation within session | no frame-level random splits; report autocorrelation |
| multiple comparisons | H1/H2 primary; H3/H4/H5 secondary with Bonferroni or clearly exploratory | no endpoint substitution |

## 4. Features and classifier

### 4.1 Primary feature set (fixed before data)

- `roughness_used` (normalised spectral change over time);
- `amp_volatility`;
- `phase_roughness` (temporal change of differential phase);
- `phase_std`;
- `profile_distance` (mean normalised spectrum distance from an empty
  reference fitted on training sessions only);
- `rssi_mean` is recorded but is **not** in the primary inference; it is an
  ablation.

`phase_resp_ratio` is reported descriptively for the respiration stage; it
is not a primary presence feature.

### 4.2 Classifier

Fixed **nearest centroid** on features standardised with training-session
means and standard deviations. No hyperparameter search, no feature
selection, no per-frame fitting. This is deliberately simple; if it fails,
that does not prove the physical signal is absent.

### 4.3 Ablations (pre-registered, descriptive)

- amplitude only (`roughness_used`, `amp_volatility`, `profile_distance`);
- phase only;
- RSSI only;
- all features without RSSI;
- all features.

A full-model advantage over RSSI-only is required for a multipath-presence
interpretation.

### 4.4 Reference / calibration

Two analyses, both reported:

1. **Uncalibrated (primary H2):** the empty reference is fitted on *training
   sessions only*; the held-out session contributes no empty baseline.
2. **Calibrated (secondary):** a short empty baseline from the held-out
   session is used. A calibrated PASS is reported as "presence with empty
   calibration", not general occupancy.

## 5. Analysis and decision rules

Every session is held out entirely; folds are sessions, never frames.
Predictions are out-of-fold. The primary classifier and features are fixed.

### 5.1 Screening session (exploratory)

A first session is **exploratory only**. Report:

- balanced accuracy and per-class recall;
- empty false-positive rate;
- session-bootstrap 95 % CI;
- label-permutation null;
- the five ablations;
- drift, rate, PHY, posture and RSSI tables.

No presence claim follows from one session, regardless of accuracy.

### 5.2 Confirmatory gates

A **presence** claim requires a new, independent session set (at least two
held-out sessions) and all of:

- H2 (empty vs stationary) balanced accuracy **≥ 0.80**;
- empty false-positive rate **≤ 0.10**;
- lower 95 % session-bootstrap CI for balanced accuracy **> 0.60**;
- label-permutation **p < 0.01** (session-preserving permutations);
- both standing and sitting recall **≥ 0.70**;
- full model beats RSSI-only by **≥ 0.05** balanced accuracy;
- modal PHY equal and payload-rate difference ≤ 10 %;
- no drift-only or empty-only session above the FPR gate.

H1 (empty vs moving) is reported separately; it does not substitute for H2.
H3 is exploratory and requires balanced accuracy ≥ 0.70 with all per-class
recalls ≥ 0.60; it is not a presence claim by itself.

A FAIL, INCONCLUSIVE or INVALID is reported as such. A null result bounds
the effect; it is not "no human effect" in general.

### 5.3 Uncertainty

- Session bootstrap (resample held-out sessions) for balanced accuracy and
  FPR; report 95 % intervals.
- Label permutation within each session, preserving class counts, for the
  null distribution; report p and the null 95th percentile.
- With 3 sessions the intervals are wide; that is the honest result. Do not
  replace session-level uncertainty with frame counts.

## 6. Sample size and power

No credible Alpha 003 effect size exists yet. The design is therefore a
**screening design**, not a powered confirmatory trial:

- 12 blocks × 3 conditions × 30 s = 18 min active per session;
- 3 sessions minimum = 36 trials/condition; 4–5 sessions preferred;
- the minimum detectable effect will be reported from the observed
  variability, not asserted in advance;
- a null is reported as "no effect ≥ the detectable size", not as proof of
  absence.

If a pilot shows a large stationary-vs-empty effect, the confirmatory
sample size will be recalculated from that pilot **before** the confirmatory
session, in a new dated amendment.

## 7. Exclusions and validity

A trial is excluded only for a pre-registered reason:

- fewer than **270 payload frames**, or active window outside **30 ± 0.5 s**;
- boundary uncertainty > 0.10 s, max gap > 0.5 s, clock reset, late frame;
- modal PHY change or payload-rate difference > 10 %;
- geometry outside the measured ranges or missing geometry;
- empty trial with a person in the room or door open;
- stationary trial with a posture/path violation;
- moving trial with the subject off the marked path.

Exclusions are recorded per trial with a reason. No trial is removed after
looking at its condition mean. Invalid sessions are preserved and reported.

## 8. Stop rules

- No session until the owner authorizes it and the 10 s pre-check passes.
- No analysis or condition means before the session ends.
- Stop for apparatus/cue failure, subject inability, or a pre-registered
  validity failure; not for an inconvenient preliminary result.
- Do not change endpoints, features, thresholds, exclusions or classifier
  after seeing data.
- Preserve every aborted attempt; a replacement needs a new session id and a
  written reason.
- No firmware flash for Alpha 003 unless separately authorized; the current
  acquisition pipeline is reused as-is.

## 9. What would count as evidence

Only the confirmatory gates, on held-out sessions, with the fixed analysis.
A first-session PASS is a hypothesis; a second independent session meeting
the same gates is the minimum for a presence claim. Alpha 002-C is not
re-used as presence evidence, and hand-motion trials are not relabelled as
occupancy.

## 10. Relation to Alpha 002-C

Alpha 002-C remains a positive **exploratory hand-motion vs stationary**
result with independent replication pending. Its replication protocol stays
frozen and separate. Alpha 003 does not pool Alpha 002-C data, does not
change its endpoints and does not reinterpret its `stationary`/`hand`
labels as `empty`/`stationary`/`moving`.
