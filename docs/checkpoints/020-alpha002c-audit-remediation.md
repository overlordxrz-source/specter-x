# Checkpoint 020 — Alpha 002-C audit remediation

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor` (from `699d199`)
**Basis:** independent audit of `699d199` (reproduction package inspected:
`trial-timing.json`, `property-probes.json`, `supplement.json`,
`recomputed.json`, `AUDIT.md`).
**Status:** **offline remediation complete. No firmware flashed, no human
trial run, no merge.** The next human trial stays stopped pending external
review of this report.

The audit's verdict is accepted without reservation: the Alpha 002-C
acquisition was contaminated, the held-out evaluation was invalid, and the
session cannot support an absence-of-motion conclusion. Checkpoint 019 is
retained as apparatus data and is marked as such.

---

## 1. Defect-by-defect remediation

| # | Audit finding | Root cause | Fix | Test that fails on the old code |
|---|---|---|---|---|
| 1 | Nominal 20 s trials held 43–55 s of sensor history | acquisition paused during cues/lead-in, so the port buffered | `TrialRecorder` drains continuously; trials cut by the device acquisition clock | `test_only_pre_trial_bytes_are_excluded` (pre-trial bytes → 0 payload, 10 excluded) |
| 2 | A trial absorbed pre-GO frames | frames were labelled by read order | window = `[go_sensor, stop_sensor]`, mapped from host time via the measured clock offset | same, plus `test_post_stop_frames_are_excluded` |
| 3 | Boundary uncertainty ignored | the cue marker is up to one frame old | `guard_s` band excluded at both edges and counted | `test_frames_inside_the_window_are_kept_by_sensor_time` |
| 4 | `actual_s` included the stop cue; wall clock used | `time.time()` around the cue | monotonic clock for boundaries; separate `active_s`, `sensor_span_s`, `delivery_span_s`; wall UTC recorded separately | recorder exposes all three; replay shows 20 s active vs 43–55 s sensor |
| 5 | No silence abort | absent | a window whose largest sensor gap > `max_gap_s` is marked invalid with a reason | `test_a_sensor_gap_invalidates_the_trial` |
| 6 | 20–23/s was buffering, not traffic | divided accumulated records by wall duration | payload rate reported against **sensor** time; replay prints both | replay reproduces 10.02–10.31/s |
| 7 | Held-out scaler fitted on the test fold | `_zscore(Xte)` | train-only `mu`/`sd` applied to the test fold | `test_a_held_out_prediction_cannot_depend_on_another_test_sample` |
| 8 | Folds destroyed the acquisition blocks | folds built from label order | explicit `block` ids; leave-one-block-out | `test_folds_are_the_acquisition_blocks` |
| 9 | `shape_shift` reference fitted on all trials | pooled over every trial | `fit_idx`: reference fitted on training trials only | `test_shape_shift_reference_excludes_the_held_out_trial` |
| 10 | `change_rate` floor used all true stationary labels | floor over every stationary trial | floor from `fit_idx` only; rebuilt under permutation | `test_change_rate_floor_excludes_held_out_stationary_trials` |
| 11 | Permutation did not rebuild supervised features | labels shuffled, features fixed | `permutation_test_crossfit` rebuilds them per permutation | `test_the_permutation_rebuilds_the_supervised_feature` |
| 12 | Permutations were unrestricted | `rng.shuffle(labels)` | within-block only; `min_attainable_p` and the number of assignments reported | `test_permutations_stay_inside_their_block`, `test_the_number_of_distinct_assignments_matches_the_design` |
| 13 | Held-out **AUC** declared but accuracy returned | no class-specific scores | out-of-fold scores, tie-correct AUC, accuracy alongside | `test_the_pipeline_detects_an_injected_signature_and_rejects_its_null` asserts AUC |
| 14 | Tied AUC returned 1.0 | distinct ranks assigned in argument order | average ranks for ties | `test_tied_scores_give_auc_one_half` |
| 15 | Constant groups gave d = 0 and F = 0 | `sp == 0 → 0`, `within <= 0 → 0` | ±inf for separated constants, 0 only when identical | `test_perfectly_separated_constant_groups_are_infinite_not_zero` |
| 16 | 52-carrier mask inconsistent across stages | `used = std > 0` in one place, 64 slots in another | one canonical `lltf_used_mask()` (64 − 12 nulls = 52) | `test_features_use_the_fifty_two_carrier_mask_by_default`; Phase 0 null now matches the audit's 52-mask value |
| 17 | Invalid-first-word flag ignored | not carried into samples | carried in every frame; mask drops carriers 0–1 when set | mask test (52 → 51 usable, carrier 0 is already null) |
| 18 | Vendor order documented as (I, Q) | wrong docstring | documented as **(imag, real)**; added `complex_subcarriers_c` = `real + 1j*imag` | `test_the_vendor_iq_order_is_imaginary_then_real` |
| 19 | No raw IQ / cue times / config preserved | amplitudes only | `.raw` stream, cue events in both clocks, design block (seed, order, blocks, guard, gap) | replay + recorder output |
| 20 | No machine-readable analysis entry point | ad hoc | `tools/alpha002c_replay.py` | used for §3 |

Firmware was **not** changed. The audit's note that `printed` increments on
queue pop is accepted and recorded as a limitation of that counter; it is not
delivered-packet truth under a failed write.

## 2. The acquisition fix in one paragraph

`specter/sensors/esp32/acquisition.py` runs a reader for the whole session,
including cues and between-trial pauses. Every frame carries the device's
`local_timestamp`; a trial is the interval `[go, stop]` in that clock, with
`go`/`stop` obtained by mapping the host monotonic cue time through the
median `host − sensor` offset of recent frames. Frames inside a `guard_s`
band at either edge are excluded and counted, and a window with a sensor gap
above `max_gap_s` is marked invalid. The raw bytes are written beside the
JSON. The old failure — a trial that begins with tens of seconds of already
acquired history — is now impossible without the trial being marked invalid,
and it is reproduced as a failing test against a fake source.

## 3. Replay of the existing evidence

`tools/alpha002c_replay.py` on `phase1-main.json`, blocks inferred as four
trials per block (the file predates block ids; the inference is labelled in
the output).

| trial | label | payload | sensor span | payload / sensor-s |
|---|---|---|---|---|
| 1 | stationary | 450 | 43.90 s | 10.25 |
| 2 | hand | 554 | 54.80 s | 10.11 |
| 3 | hand | 548 | 54.60 s | 10.04 |
| 4 | stationary | 469 | 45.60 s | 10.29 |
| 5 | hand | 558 | 55.30 s | 10.09 |
| 6 | stationary | 464 | 45.50 s | 10.20 |
| 7 | stationary | 442 | 44.10 s | 10.02 |
| 8 | hand | 534 | 52.00 s | 10.27 |
| 9 | hand | 540 | 52.40 s | 10.31 |
| 10 | stationary | 435 | 43.20 s | 10.07 |
| 11 | stationary | 452 | 44.10 s | 10.25 |
| 12 | hand | 349 | 34.50 s | 10.12 |

**Every trial is contaminated** (sensor span 43–55 s against a 20 s window).
This reproduces the audit's independent timing table.

Repaired analysis on the same stored frames:

| feature | F | block-preserving p | AUC | accuracy | d |
|---|---|---|---|---|---|
| `roughness_used` | 0.3832 | 0.5115 | 0.1806 | 0.4167 | −0.357 |
| `amp_volatility` | 0.2096 | 0.6344 | 0.0000 | 0.0833 | −0.264 |
| `shape_shift` | 1.5342 | 0.2458 | 0.6250 | 0.6667 | −0.715 |
| `change_rate` | 0.6303 | 0.4096 | 0.2917 | 0.3333 | −0.458 |

The primary p moved from 0.5435 (unrestricted, fixed features) to **0.5115**
(block-preserving, rebuilt features); accuracy moved from 0.50 to **0.4167**,
matching the audit's recorded-block diagnostic. `change_rate` changed most
(F 0.1608 → 0.6303) because its floor is now cross-fitted and rebuilt.

**Conclusion unchanged in direction, and now correctly labelled:** no
separation, on contaminated acquisition. It is apparatus data.

Phase 0 recomputed with the canonical 52-carrier mask:

| feature | mean | std |
|---|---|---|
| `roughness_used` | **0.00915121** | **0.00396538** |
| `amp_volatility` | 0.33728611 | 0.16052466 |
| `shape_shift` | 0.00522612 | 0.00342471 |

The roughness values reproduce the audit's independent 52-mask numbers to
every printed digit. `shape_shift` differs from the audit's 64-mask figure
(0.00431441) because the mask is now consistent — that difference is the fix.

## 4. The three gates before another human trial

| gate | status |
|---|---|
| **Trial-window assignment verified** | **PASS (offline).** Continuous drain, sensor-time windows, guard band, silence abort, all tested; the audit's pre-trial-buffer probe is a regression test. Not yet exercised on hardware. |
| **Leakage-free statistical evaluation** | **PASS (offline).** Train-only scaling, block folds, cross-fitted features, whole-pipeline block-preserving permutation, out-of-fold AUC, tie and degenerate fixes, all tested. |
| **Synthetic positive control detected, matched null not** | **PASS (offline).** End-to-end: synthetic CSI lines → recorder → JSON → analysis. Injected signature p < 0.05 with AUC ≥ 0.8; matched null p > 0.05. |

The third gate is the one that matters: it exercises the repaired pipeline
from raw bytes to p-value, not the statistics alone.

## 5. What is still not available

* **Phase 1 raw IQ, per-frame PHY/MCS and gain state** — never recorded;
  unrecoverable. Differential phase cannot be reconstructed from the stored
  amplitudes. `complex_subcarriers_c` is the correct starting point for
  *future* phase work; no phase analysis was attempted here.
* **Independent motion timing** — the only record of what the subject did is
  the cue log, which the old recorder did not keep.
* **Firmware delivered-packet truth** — `printed` counts queue pops. Not
  changed in this pass (no firmware work authorised).
* **A hardware run of the new recorder** — deliberately not done.

## 6. Evidence

| artefact | note |
|---|---|
| `tests/test_acquisition_windows.py` | 5 tests: pre-GO, post-STOP, late delivery, wrap, silence |
| `tests/test_analysis_leakage.py` | 10 tests: scaler, blocks, both leakages, permutation rebuild, block shuffle, AUC ties, degenerate d/F, mask |
| `tests/test_pipeline_positive_control.py` | end-to-end positive/null control |
| `runs/alpha002_hw_validation_20261022b/phase1-replay.json` | repaired replay of the stored session |
| `specter/sensors/esp32/acquisition.py` | the new recorder |
| `tools/alpha002c_replay.py` | reproducible replay entry point |

Full suite: **326 passed, 1 skipped** (was 310).

## 7. Stop point

No firmware flashed, no hardware reset, no new human trial, no merge to
`main`. The recording files under `runs/` are immutable and were not
rewritten. This report and the code changes are for independent review; the
next human trial remains stopped until that review accepts the three gates.
