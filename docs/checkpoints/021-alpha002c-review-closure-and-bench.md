# Checkpoint 021 — Alpha 002-C: adversarial review closure and 5-minute bench

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor` (from `ed51801`)
**Status:** **offline review closure PASS; 5-minute no-human bench PASS
(15/15 checks); transport-integrity event characterised and still OPEN at
the device side.** No firmware flashed, no human-motion trial, no merge.

---

## 1. Adversarial review — second pass

The reviewer attacked the fixes at `31a4dd4`. Results and disposition:

| target | verdict | disposition |
|---|---|---|
| T1 block alignment | PASS (could not falsify) | accepted |
| T5 per-fold CV / multivariate | PASS (could not falsify) | accepted |
| T2 clock offset | **probe reference error** | refuted with a corrected probe; residual bias documented |
| T3 reset detection | FAIL (real) | fixed |
| T4 late frames | FAIL (real) | fixed |
| T6 mutation coverage | 5/8 new mutations survived | 4 gates added; gate now 14/14 |

### T2 — why the probe's conclusion does not hold

The probe measured "pre-GO" frames against **host** time. With a constant
delivery lag `d`, a frame acquired at true time `t` is stamped `host = t+d`,
so the cue at host 10 corresponds to acquisition time **10−d**. The
estimator returns exactly that, and a corrected test pins it: with `d = 2 s`
and the cue at host 10, `go_s = 8.0 ± 0.15` and **no** sample was acquired
before the cue
(`test_a_constant_delivery_lag_maps_to_the_cue_acquisition_time`).

The genuine residual is narrower: a **changing** delay biases the boundary by
`(delay at cue − minimum delay)`, which the reported spread
(`median − minimum`) bounds. On USB this is milliseconds; the guard is
100 ms.

### T3 — reset detection (fixed)

A reset after 35.8 min of uptime was classified as a uint32 wrap, and one
late frame could move the epoch. Now a wrap requires starting within 2 s of
2³², a reset must be confirmed by the next frame inside the new epoch, and a
pre-wrap straggler is recognised by the top-half/bottom-half transition.
Gates: reset at 36 min invalidates; one late frame does not reset; a
pre-wrap straggler does not double the offset.

### T4 — late frames (fixed)

Stragglers behind newer frames were dropped before `settle()` could see
them, and `late_frames` was hardcoded 0. Now a straggler is **kept** with its
own sensor time and sorted into the window; a held reset candidate that is
not confirmed is emitted as a straggler; `settle()` flushes an unresolved
candidate; `late_frames` is null at close and patched after the session.

### T6 — the gate itself

`tools/mutation_check.py` now re-injects **14** historical defects and
requires the named test to fail. It exposed two tests that passed without
enforcing their fix (change-rate self-reference, permutation rebuild), and
two validity checks that had no test at all (uncertainty, sample span). The
span check was itself useless — it compared two host-derived values — and now
compares the selected frames' sensor span with the active window.

**Gate: PASS, 14/14 killed.**

## 2. Five-minute no-human bench

Setup unchanged: iPhone (station) → ESP32-S3 (SoftAP), 1.5 m, both 0.8 m,
channel 6, 20 MHz, 100 ms ping to 192.168.4.1, phone fixed, no person in the
path. The phone's battery had died in an earlier attempt; after recharging,
a 10 s check confirmed 100 payload frames in 10.0 s before starting.

12 windows × 25 s, 0.5 s settling, one continuous drained stream.

| check | measured | result |
|---|---|---|
| every trial valid | 12/12 | PASS |
| sensor span vs active window | worst 0.022 s | PASS |
| largest sensor gap | 0.134 s | PASS |
| payload rate | 9.96–10.88/s | PASS |
| torn status line after attach | 0 | PASS |
| torn line only at attach | line 0 of 309 | PASS (known, see §3) |
| host records + exclusions vs device `printed` | 8118 + 322 = 8440 vs 8362 (0.93%) | PASS |
| host payload + estimated exclusions vs device `data` | 3078 + ~122 = 3200 vs 3175 (0.79%) | PASS |
| device queue drops | 0 | PASS |
| raw stream | 3 432 770 B | PASS |
| malformed CSI in raw | 0 | PASS |
| raw CSI count | 8 401 lines vs 8 118 records | PASS |
| design metadata | seed/order/blocks/guard/gap | PASS |
| cue events | 36 | PASS |
| per-frame metadata | all fields | PASS |

**Ping count:** 3 078 payload frames over ~307.8 s at 10 Hz. The app's
counter therefore advanced about 3 078, well below the 9 999 limit that
stopped the earlier attempt.

**What the bench proves:** the repaired recorder works on hardware — windows
map to sensor time to within 22 ms, no backlog is absorbed, excluded frames
are accounted for, and the host counts are corroborated by the device's own
counters to <1%.

**What it does not prove:** anything about human sensing; no person was in
the path.

## 3. Transport-integrity event (OPEN at the device side)

Scanned all 15 preserved raw captures (Phase 0, Phase 1, preflight, and the
bench):

| observation | value |
|---|---|
| malformed CSI lines | 1 (seq 38412, in a 10 s check) |
| splices | 4 |
| splices **not** on line 0 of a capture | **0** |
| continuous captures damaged | **0** (Phase 0 7 291 lines; bench 8 401 lines) |

The damaging event is
`CSI_DATA,38412,…,−96,0,SPECTER_STAT,…`: a CSI record truncated at the
channel field, with the next status line concatenated **without a newline**.
That record is lost; the bytes are preserved verbatim in
`bench-check3.json.raw`.

**Cause, as far as the evidence establishes it:** the truncation happens at
**attach**, while no host is reading. The firmware is single-writer, so this
is not the old interleaving; it is a shortened write when the USB console has
no reader. A host-side drain was tried and **rejected** — it discards a good
first line whenever a capture starts cleanly (six tests caught it). The
parser already counts the torn line as malformed and the raw preserves it.

**Impact bound:** at most one record, at session start, and only if that
record is CSI. Never mid-capture in any preserved session.

**Status: OPEN.** The real fix is a firmware write-retry or
terminate-on-short-write, which requires a flash and is out of scope. A
checksummed wire format would make mid-stream loss detectable; neither is
proposed here.

## 4. Are the earlier verification standards actually enforced?

| standard | enforced? | by what |
|---|---|---|
| windows assigned by acquisition time | **yes** | 6 acquisition gates incl. the audit's pre-trial-buffer probe; hardware bench: 22 ms worst deviation |
| no backlog absorbed | **yes** | continuous drain + span check, mutation-gated |
| leakage-free held-out evaluation | **yes** | per-fold fitting, train-only scaling, block folds; mutation-gated |
| supervised feature rebuilt under permutation | **yes** | spy test + mutation |
| block-preserving permutations and honest p floor | **yes** | tests + 2/n_assign clamp |
| degenerate statistics | **yes** | ±inf/inf, tie AUC 0.5, NaN groups |
| synthetic positive control through the whole pipeline | **yes** | end-to-end raw-lines → recorder → analysis |
| raw IQ and metadata preserved | **yes** (raw) / **partly** (JSON) | raw carries IQ, MCS, noise floor, flags; JSON carries derived amplitudes plus PHY fields |
| operator blinding | **no** | the analyst announces the conditions; unchanged, and stated |
| mid-stream byte loss detectable | **no** | no checksum in the wire format |
| device-side short write | **not fixed** | firmware change required |

## 5. Remaining limitations

1. One torn record at attach remains possible; bounded, counted, preserved.
2. A changing delivery delay biases the boundary by
   `(delay at cue − minimum delay)`; bounded by the reported spread.
3. No checksum: a splice at the metadata/IQ boundary remains undetectable.
4. The app's 9 999-ping limit means any human session longer than ~16 min at
   10 Hz needs a restart; plan blocks below that.
5. Single bench session, one device, one USB topology. No long-run soak.
6. No human-motion or respiration claim of any kind.
