# Alpha 002-C analysis correction 01 — startup torn line

**Date:** 2026-10-23 (UTC), after the session and before reporting a verdict
**Scope:** raw-stream validity check in `tools/alpha002c_motion_v2.py` only
**Affects:** one session-level INVALID flag; no design, endpoint, feature,
test, threshold, exclusion or measurement was changed.

## What the raw stream contains

The accepted 20-trial session (`runs/alpha002c_motion_v2/session.json`, seed
`20261023`, 3 s lead-in per Amendment 4) recorded one malformed CSI line:
physical line 0. The line begins with a truncated record left over from
opening the port mid-record, immediately followed by the first complete
record, with no newline between them:

```
CSI_DATA,121885,...,-96,0CSI_DATA,125402,...,138,1,128,0,"[...]"
```

Feeding that physical line to `CsiParser.feed_resilient` returns
`records=1` (the complete `125402` record) and `malformed=True` (the torn
prefix). The session counter is `malformed=1`; `clock_resets=0` and
`late_frames={}`.

## The frozen rule

Commit `58aaf4b8` (the final preregistration review) states the raw-stream
rule as **"at most the first torn line allowed"**. The module docstring says
a **"malformed CSI record after the first valid one"** makes the session
INVALID. The session-level check also explicitly allows a recorder count of
`0` or `1` malformed line.

## The bug

`validate_raw` set `seen_valid = True` as soon as a line produced any record,
and only then tested `outcome.malformed` on that same line. A torn prefix
*plus* the first complete record on line 0 was therefore classified as
malformed **after** the first record. The frozen analysis returned:

```
verdict: INVALID
raw_problems: ["malformed CSI line 0 after the first record"]
```

That INVALID output is preserved verbatim as
`runs/alpha002c_motion_v2/result-frozen-invalid.json`.

## The correction

`validate_raw` now counts torn CSI lines and allows at most the first torn
line, only while no valid record has yet been seen. A torn line after a valid
record, or a second torn line, is still INVALID. No other analysis code was
touched.

Regression tests added to `tests/test_motion_v2_prereg.py`:

- `test_a_torn_first_line_is_tolerated` — torn prefix + first full record,
  followed by clean records, is accepted;
- `test_a_second_torn_line_is_rejected` — a second torn line is rejected;
- the existing `test_a_malformed_line_after_the_first_record_invalidates`
  still passes.

## Corrected result (unchanged raw evidence)

`runs/alpha002c_motion_v2/result.json`:

- **PASS**
- primary `roughness_used`: exact one-sided sign-flip p = 1/1024 =
  0.0009765625, d_z = 1.6946, 95% bootstrap CI [1.3414, 2.9061],
  mean paired difference +0.0003344; all 10 paired differences positive.
- confounds: payload rate 10.16 vs 10.24/s (0.8% relative difference);
  modal PHY 11 in both conditions with concentration 1.0.
- all 20 trials valid; no clock resets, no late in-window frames.

The correction changes only whether the known startup tear invalidates the
session. It does not alter the raw stream, trial selection, features, test,
thresholds or the pre-registered direction. Both the original INVALID result
and the corrected PASS result are retained, and this document records the
change so the result is not presented as if the first analysis had passed.

## Limitations that remain

- Geometry is **estimated** (visual), not measured: L = 1.50 m, heights
  0.80 m, lateral 0.30 m, longitudinal 0.00 m; derived S distances 0.808 m
  horizontal / 1.137 m slant.
- The 3 s lead-in is shorter than the original 8 s washout (Amendment 4,
  pre-data); carryover is a stated limitation.
- The ping app's numeric starting count was never supplied; the
  `app_start=NNN` placeholder remains, so the 9,999-ping budget is not
  independently verified.
- This is one session. It is not an independent replication, and the design
  is powered mainly for large paired effects.
