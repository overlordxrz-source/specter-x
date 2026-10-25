# PR #10 — response to independent REQUEST CHANGES

24 October 2026. Re-review required; this response is not an approval.
Reviewed head: `2b54410508118ae4e2c75d0f162467ada98dba28`.
OpenCode review: `760a3f6e6c98b46578f53cce712c06b97266b003` on
`review/pr10-findings-2b544105`. Its
[original review](pr10-independent-review-20261024.md) was imported verbatim
(Git blob `a1570ca557f534fe86110899c5f850fab31520ca`), without merging or
changing that branch.

Regression-first commit: `f99db9a10448cbd86e7af4e834885133af0d39a8`.
The first **18 reconstructed cases all failed** before implementation.
Additional startup-interruption and equal-size corruption controls each failed
before their corresponding fixes. Tested implementation:
`57c8be07a5e728808c998224f1712cf79b459dbb`.

## Changes and executable coverage

| Finding | Remediation | Regression |
|---|---|---|
| P1 short raw/receipt writes and accounting | Check return lengths; reconcile persisted raw size, read/written/rejected bytes, receipt size/count/end offsets, monotonic times and transport labels before completion. Compare incremental expected hashes to persisted raw/receipts, including equal-size corruption. Revalidate derived manifest/count and raw after finalization. Mismatch → FAILED / nonzero CLI. | `test_short_writes_never_complete` (honest and lying writers; raw/receipts; API and CLI), `test_equal_size_raw_corruption_cannot_complete` |
| P2 BaseException/KeyboardInterrupt | Terminal CANCELLED for interruption or FAILED for other failures; close transport; publish terminal status, then re-raise original BaseException with traceback. Cancellation checks also run during and after derivation. Unavailable timing remains unknown. | `test_baseexception_publishes_terminal_and_reraises` (read/finalization, KeyboardInterrupt/SystemExit), `test_startup_clock_interrupt_closes_and_publishes`, `test_stop_during_finalization_cannot_be_success` |
| P2 receipt clock order | Validate integer nonnegative monotonic times against loop/previous completion; independently audit persisted receipts; reject reversed stop time. | `test_previous_completion_is_a_monotonic_bound` |
| P2 quaternion OverflowError | Catch conversion overflow as ValueError before updating driver index/state. No change to heuristic calibration/uncertainty claims. | `test_nonrepresentable_integer_is_valueerror_without_state_mutation` (positive/negative huge integers) |
| P2 clean-first-run acceptance | Explicit `acquisition_complete`, `clean_first_run.status/reasons`, `scientific_acceptance=NOT_EVALUATED`. Gate rejects sequence gaps, malformed/spliced/recovered/unsupported records and clock discontinuities. CLI returns 2 for dirty captures even if raw acquisition/derivation completes. Diagnostic artifacts remain. | `test_dirty_capture_is_complete_but_not_accepted` (five independent defects), `test_dirty_cli_is_unsuccessful` |

## Observed verification

- **59 focused tests passed**; **304 passed, 1 hardware deselected** in the
  full offline suite. Architecture PASS, same 14-module offline WORLD closure.
- Five disposable mutations, one per finding, all detected with test failures:
  write/accounting removal, BaseException handling removal, receipt-clock guard
  removal, OverflowError removal, and unconditional clean PASS. No working
  source was mutated. The first write mutation initially produced an unrelated
  missing-key error; its fixture was corrected to populate the required hash
  metadata so only the intended integrity checks are disabled. That initial
  run and final logs are both retained.
- Final preserved-source replay: **2,788,217 exact bytes, 681 reads, 7,290
  observations**, zero rejected/unaccounted bytes. In-memory expected and
  persisted raw hashes match
  `f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`;
  expected/persisted receipts hashes match. Independent byte comparison,
  receipt bounds/order and capture manifest/count checks pass.
- Exact frame populations: 4,248 null (`sig_len=28`), 3,017 payload
  (`sig_len=138`), 25 other. These are byte-field counts, not a new Alpha
  interpretation or sensing result. `clean_first_run=PASS` for software
  replay quality; scientific acceptance remains NOT_EVALUATED.
- Unchanged WORLD v2 `4e1c920` consumes the new NODE JSONL; first/middle/last
  envelopes match exactly. No UI application changes or physical device opens.

## Reproduce

In PR #10's checkout, using the existing project environment:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  tests/test_pr10_remediation.py tests/test_node_capture.py \
  tests/test_imu_validity.py tests/test_serial_owner.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -m 'not hardware'
PYTHONDONTWRITEBYTECODE=1 python tools/check_architecture.py
PYTHONDONTWRITEBYTECODE=1 python tools/pr10_mutation_verify.py --out /tmp/pr10-new-mutation-results
python -m specter.node.csi_capture \
  --input /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi \
  --out /tmp/pr10-new-replay --max-bytes 4194304 --max-reads 4096
```

For UI consumption, start unchanged WORLD v2 on `/tmp/pr10-new-replay/session.observations.jsonl`,
then run `tools/node_world_verify.cjs` with WORLD_URL, NODE_CAPTURE and
NODE_COUNT=7290 as documented in the earlier verification. Node/Playwright
dependencies are development-only and unchanged.

Private logs/artifacts: this Codex task's `outputs/pr10-remediation/` contains
initial failing cases, supplemental failing controls, final test/architecture
logs, both mutation runs, replay raw/receipts/JSONL, interface JSON/screenshot.
No raw recording was added to Git.

## Compatibility and retained limits

- CLI formerly exited 0 on dirty but parseable captures; it now exits 2.
  `state=COMPLETE` means the acquisition/derived artifacts completed, **not**
  clean-run or scientific acceptance. Callers must read the explicit gates.
- Status gains additive receipt/hash/quality/acceptance fields. Observation
  v1 and completed JSONL/manifest interfaces are unchanged. Short writes are
  rejected, not silently retried. Failed/partial files remain for diagnosis.
- Direct KeyboardInterrupt/SystemExit still propagate after cleanup/status
  publication. SIGINT/SIGTERM handled as stop requests produce CANCELLED and
  nonzero CLI. Uncatchable termination/power loss cannot guarantee a terminal
  status; permanent storage failure may prevent status publication and is
  raised rather than reported successful.
- A fully written derived file/manifest can survive cancellation during late
  finalization. The terminal session state/gate controls acceptance; file
  existence alone does not establish a successful session. No artifacts are
  silently deleted to conceal failure.
- Noncooperating serial consumers may bypass ownership requests. Existing
  readers, USB aliases and physical identity remain unverified. Operator/device
  evidence and specific authorization remain mandatory before the prepared
  ESP32 test. No merge, flash, reset, physical acquisition or frozen Alpha
  experiment change occurred.
