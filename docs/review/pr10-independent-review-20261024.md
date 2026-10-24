# Independent review — PR #10

**Verdict: REQUEST CHANGES.**

24 October 2026. Read-only review of the exact draft head
`2b54410508118ae4e2c75d0f162467ada98dba28` against its base and current
`main` `f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2` (base and current main are
identical). No merge, push to the PR, physical device operation or ESP32 test
was performed.

## What passed

- Exact-head focused suite: **39 passed** (`test_imu_validity.py`,
  `test_node_capture.py`, `test_serial_owner.py`).
- Exact-head offline suite: **284 passed, 1 hardware deselected**.
- Architecture gate: **PASS**, 14-module offline WORLD closure; no WORLD
  import of NODE or serial ownership.
- Actual frozen CSI source `f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`
  (2,788,217 bytes) round-trips to **7,290 observations / 681 reads / 0
  rejected / 0 unaccounted**. Raw copy hash is identical; capture manifest is
  `df016fee004669809ce39221a896957d76e380a81534101f389de9528ff1b698`.
  WORLD backend opens it as **READY / REPLAY / 7,290**, `live_verified=false`;
  first/middle/last observations match the capture byte-for-byte.
- Mutation controls: reverting the IMU fix produces **10 failed, 3 passed**;
  removing the serial provenance override produces one expected failure;
  changing `exclusive=True` to `False` produces one expected failure.
- The independent PTY probe reproduces the documented ownership limit:
  cooperating second owner rejected, ownership released, raw noncooperating
  open **accepted**, physical exclusion **UNVERIFIED**.
- No frozen Alpha evidence, raw capture, UI application code, CI workflow or
  unrelated branch was modified in the reviewed diff.

## Reproduced defects and gaps

### P1 — a short raw write can still end as COMPLETE

`specter/node/csi_capture.py:167` increments the accepted byte count and writes
a receipt without checking the return value of `raw.write(chunk)`. The final
status computes `unaccounted_bytes` (`:214–219`) but only publishes it; it does
not fail the session.

An injected short-write file object that writes one byte less but reports the
full count reproduces:

```text
state=COMPLETE, bytes=406, raw_file_bytes=405,
unaccounted_bytes=1, observations=1, errors=[]
```

The CLI therefore exits 0 and the state says COMPLETE even though raw evidence
was lost. The 15-second acceptance script reads `unaccounted_bytes`, but the
recorder itself does not enforce it. This is a direct raw-integrity failure.

### P1/P2 — direct interruption leaves a stale nonterminal status

`record_session` catches `Exception` but not `BaseException`
(`specter/node/csi_capture.py:180`). A direct `KeyboardInterrupt` from
`reader.read` closes the reader and re-raises, but no terminal status is
published. Reproduced status after the exception:

```text
state=RECORDING, stopped_monotonic_ns=None, bytes=0, errors=[]
```

The CLI's installed SIGINT/SIGTERM handler normally converts the signal to the
`stop` event, so this is primarily a public-API / unhandled-interruption path.
It still contradicts the function's “truthful terminal status” contract and
the protocol's cancellation claim. A signal during finalization is also not
checked after the recording loop.

### P2 — nonmonotonic receipt completion times are accepted

The loop checks `completed < now` (`:148`) but not `completed` against the
previous completion. With an injected clock returning `[0,100,200,150,180,…]`,
the session completes with receipts `[200, 180]`:

```text
state=COMPLETE, reason=eof, observations=1
receipt_times=[200,180]
```

The protocol's predeclared acceptance requires monotonic completion times;
the recorder must reject this rather than emit COMPLETE.

### P2 — IMU quaternion boundary leaks `OverflowError`

`quat_measurement` catches `(TypeError, ValueError)` around
`np.asarray(..., dtype=float)` (`specter/sensors/imu/bno085.py:32–35`). A huge
finite integer raises an uncaught `OverflowError`:

```text
quat_measurement([10**1000, 0, 0, 0]) -> OverflowError: int too large to convert to float
```

The fix is correctly scoped to the quaternion boundary and preserves the frame
index on rejected reports, but malformed/non-representable input is not
uniformly rejected as `ValueError`. Add `OverflowError` (or a bounded numeric
conversion) and a control.

### P2 — parser counters do not make the clean-first-run gate fail

The malformed/spliced fixture set (`exact`, `truncated_1`, `truncated_2`)
records as COMPLETE with three observations and
`counters.sequence_missing=170`. The protocol says sequence gaps, malformed or
recovered records, unsupported layouts and clock discontinuities must fail the
clean first run; the recorder publishes the counters but leaves state COMPLETE
and exit code 0, and the example acceptance script checks only a subset. Add an
explicit `clean`/acceptance result or enforce the gate in the 15-second check.

## Residual physical gate — ownership

`tools/node_ownership_probe.py` reproduces:

```json
{
  "kernel_exclusive_request_succeeded": true,
  "cooperating_owner_rejected": true,
  "noncooperating_open_rejected": false,
  "ownership_released": true,
  "physical_exclusive_ownership": "UNVERIFIED; operator preflight required"
}
```

This is not a hidden claim: the PR documents it. It means the code enforces a
cooperating-owner contract only; it cannot evict, detect or exclude an
already-open/noncooperating reader. The operator `lsof`/identity preflight
remains mandatory and the physical test must stay unauthorized until it is
documented for the exact port.

## Required changes

1. Check `raw.write` and `receipts.write` results, and/or fail the session when
   `unaccounted_bytes != 0` or raw/receipt accounting does not reconcile.
2. Convert direct `KeyboardInterrupt`/other `BaseException` into a terminal
   `CANCELLED`/`FAILED` status, publish it and re-raise; add a test.
3. Reject nonmonotonic completion times against both `now` and the previous
   completion.
4. Catch `OverflowError` in quaternion conversion and add huge-finite-integer
   controls.
5. Make the clean-first-run acceptance gate explicit for counters/flags and
   update the 15-second acceptance script or status output.
6. Keep the noncooperating-ownership limitation explicit; do not claim
   physical exclusive ownership without operator evidence.

## Evidence

- Review checkout: `/Users/overlord/.cache/specter-pr10-review-2b544105`
- Exact head: `2b54410508118ae4e2c75d0f162467ada98dba28`
- Base/current main: `f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2`
- 7,290 capture: `/tmp/pr10-csi-review-JGnx3v/session`
- Ownership probe: `/tmp/pr10-ownership-probe.json`
- Mutation copy: `/tmp/pr10-mutations-54367`
