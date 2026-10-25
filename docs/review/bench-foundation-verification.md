# Bench foundation verification

**PR-preparation addendum, 24 October 2026:** the current tested acquisition
implementation is `1a94fa7686c3e66c22a6de327a56e54b1bf154a3`, based on
freshly fetched remote main `f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2`.
The original 4e2e889 local checkpoint below is retained as history.

- Latest offline suite: **284 passed, 1 hardware deselected**, 3.16 s;
  **39 focused IMU/NODE/ownership controls**, architecture PASS.
- Latest actual-source rehearsal: **2,788,217 bytes, 681 reads, 7,290
  observations, zero rejected/unaccounted bytes**; raw hash remains
  `f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`.
- Error accounting preserves both read and close failures; parser counts
  survive partial derivation failure. CLI limits are validated before any
  serial-open request. Oversized transport results are rejected and counted.
- Cooperating second-process refusal and release/reopen verified on an
  OS-created pseudo-terminal. Fake-ioctl controls cover acquire/release errors
  and inactive DTR/RTS requested before open. Physical ports were not opened.
- The first kernel-only assertion **failed** on this Mac: TIOCEXCL returned
  success but a raw noncooperating open succeeded. That hypothesis was not
  declared passing or hidden. Its test/log are retained privately as
  `serial-owner-before.py` / `kernel-exclusivity-before.log`; the permanent
  [diagnostic](../../tools/node_ownership_probe.py) reproduces the limitation
  in [committed JSON](node-ownership-20261024.json). The passing regression
  now tests the enforceable cooperating-owner contract. Physical/alias and
  already-open noncooperating ownership remain unverified/preflight gates.
- A disposable mutation changing pyserial `exclusive=True` to `False`
  causes **one expected focused failure**; original source is untouched.
- Unchanged WORLD v2 `4e1c920` consumes the latest generated JSONL.
  First/middle/last envelopes match exactly at indices 0 / 3645 / 7289;
  browser record jumps work, READY/REPLAY count is 7,290, LIVE is false.
  This focused interface check was rerun; the earlier 52-check full UI
  regression run below was not needlessly repeated because UI/backend
  application code did not change.

Additional private artifacts: this task's `outputs/bench-foundation-pr/`
contains latest Python/architecture logs, ownership failure/mutation logs,
raw/receipt/observation rehearsal, interface JSON and screenshot. No raw
capture or device identity was added to Git. Remote publication is explicitly
authorized for this isolated draft; no merge or hardware permission follows.

Reproduction additions (no physical device):

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  tests/test_imu_validity.py tests/test_node_capture.py tests/test_serial_owner.py
PYTHONDONTWRITEBYTECODE=1 python tools/node_ownership_probe.py
# With unchanged WORLD v2 serving the NODE-generated JSONL:
WORLD_URL=http://127.0.0.1:PORT NODE_CAPTURE=/path/to/session.observations.jsonl \
  NODE_COUNT=7290 node tools/node_world_verify.cjs
```

Use the existing installed Playwright/Chromium paths via `NODE_PATH` and
`WORLD_CHROMIUM` when necessary, as in the WORLD v2 verification document.
The [first live plan](../design/node-esp32-first-acquisition-v1.md) is
prepared only. Exact port/current firmware are UNKNOWN; no physical test
has been authorized or performed.

---

24 October 2026 · branch `review/bench-foundation-20261024`, base `f2ef96b`.
This is an offline software acceptance record. No physical device, firmware,
Alpha protocol, CI workflow, remote branch or PR was modified.

## Results

| Check | Observed result |
|---|---|
| PR #7 exact-head offline suite | 266 passed, 1 hardware deselected |
| PR #8 exact-head offline suite | 290 passed, 1 hardware deselected |
| PR #9 exact-head offline suite | 265 passed, 1 hardware deselected |
| Architecture gate on each PR | PASS, 14-module offline WORLD closure |
| IMU controls against old `f2ef96b` implementation | **10 failed, 3 passed**, including malformed/NaN/Inf, extreme norms and consumed frame index |
| Same IMU controls after local fix | **13 passed** |
| NODE transport/recording controls | **19 passed**, fake transports only |
| Final candidate full offline suite | **277 passed, 1 hardware deselected**, 4.33 s on this Mac |
| Candidate architecture gate | PASS; WORLD still cannot import device ownership |
| NODE receive/provenance mutation | Replacing adapted output with the unmodified replay observation causes the serial mapping test to fail; **1 expected failure** in disposable copy |
| Actual source round-trip | **7,290 observations**, **2,788,217 raw bytes**, **681 reads**, **0 rejected bytes**, original/copy SHA-256 identical |
| WORLD acceptance of derived JSONL | READY / REPLAY, **7,290 observations**, `live_verified=false` |
| Existing UI candidate browser suite | **52 PASS**, Chromium 149.0.7827.55 / Playwright 1.62.1 |

The UI suite ran from unchanged `design/world-workbench-v2` at `4e1c920`,
with explicitly approved roots for raw evidence, generated NODE output,
handbook and synthetic fault controls. Before that suite changed selections,
a separate browser check opened the **NODE-generated JSONL**, asserted its
7,290-record count and original raw hash, and saved a screenshot. The full
52 checks include source-switch/delayed-response/evidence regressions. The
two optional default-launch checks from the prior UI pass were not rerun.
This branch does not incorporate the UI commits; the existing WORLD backend
consumes the same recording interface.

Source SHA-256, independently rechecked after all recording/browser operations:

```text
f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c
```

Input:
`/Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi`.
Adapter counters: 7,290 observations, 299 non-CSI lines, no recorded missing
sequence count. This is the existing Phase 0 dataset, not a new experiment.

## Reproduce candidate checks

Activate the existing project environment and run in this candidate checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  tests/test_imu_validity.py tests/test_node_capture.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -m 'not hardware'
PYTHONDONTWRITEBYTECODE=1 python tools/check_architecture.py
```

The [workflow runbook](../architecture/bench-device-workflow.md) gives the
exclusive-create file rehearsal and WORLD launch commands. The
[PR review](pr7-pr9-independent-review-20261024.md) gives exact reviewed
heads and probe commands. Those snapshots are independent; their passing
counts are not additive and do not mean all fixes are integrated.

Private local artifacts are in this Codex task's
`outputs/bench-foundation/`: `imu-before.log`, `python-final.log`,
`node-receive-mutation.log`, `rehearsal-status.json`, `node-to-world.png`,
`browser.log`, browser JSON/screenshots, and `csi-rehearsal/` with preserved
raw copy, receipts, derived observations and capture manifest. No raw capture
was added to Git. The test-only service was stopped after verification;
the user's existing UI preview service was not interrupted.

## Remaining gates

- PR #8/#9 require the reproduced fixes; #7 has a smaller direct-API
  validation gap and remains gated from WORLD. No approval was submitted.
- The IMU fix validates numerical input only. Existing accuracy-derived
  covariance/confidence remain heuristics, not calibrated uncertainty, and
  physical polling is still unimplemented.
- Serial uses a real optional-pyserial code path, but tests replace its
  constructor/transport. No actual open, reset behavior, exclusive ownership,
  sustained capture or USB reliability claim is established.
- No physical acquisition, live WORLD streaming, sensor discovery,
  authenticated identity, clock synchronization, motion/presence detection
  or fusion capability is promoted.
- Owner reports no camera/range/thermal sensor in hand. Second-sensor
  selection and calibrated bench work wait for receipt/identity evidence.
- Shrike toolchain/FPGA timing work remains separate; this branch neither
  programs that device nor claims timing accuracy.
