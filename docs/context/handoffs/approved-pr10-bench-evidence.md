# Approved PR10 bench evidence (historical)

Approved PR10 head: `8a84369941c74d5f884c9ec6cc33d10395223597`.
This is the historical handoff addition preserved during the controlled
PR10 integration. The pre-approval wording below is retained as provenance;
PR10's review is complete and owner-approved. It is not a new physical test
authorization and does not promote a hardware capability.


**PR #10 corrected candidate — independent re-review required, 24 October:**
Reviewed head `2b54410508118ae4e2c75d0f162467ada98dba28`; OpenCode review
`760a3f6e6c98b46578f53cce712c06b97266b003` imported verbatim. Regression-first
commit `f99db9a10448cbd86e7af4e834885133af0d39a8` had 18 failing cases;
implementation `57c8be07a5e728808c998224f1712cf79b459dbb` closes the five
reported defects with **59 focused / 304 offline tests passed, 1 hardware
deselected**, architecture PASS, all five targeted mutants detected, and
7,290-record exact-byte replay. Read the [response and commands](../../review/pr10-remediation-20261024.md).
Raw/receipt write returns and persisted counts/hashes are enforced; interrupts
publish a terminal state then re-raise; clocks are checked; huge quaternion
conversion overflow becomes ValueError without state mutation. Complete but
dirty captures carry `clean_first_run=FAIL` and exit 2. Scientific acceptance
always remains NOT_EVALUATED here. Operator/device evidence and specific
ESP32-test authorization are still required; no physical acquisition, merge,
flash or Alpha evidence change. PR #7–#9 follow-ups below remain required.

**Local bench candidate — 24 October 2026, not integrated into main:**
`review/bench-foundation-20261024`, base `f2ef96b`. See the
[independent PR #7–#9 review](../../review/pr7-pr9-independent-review-20261024.md)
and [NODE recording-to-WORLD workflow](../../architecture/bench-device-workflow.md).
The review requests GNSS/radar changes; passing old suites did not close all
validity gaps. The separate candidate adds IMU finite-vector validation and
an offline-tested capture owner; it does not edit the pending PRs or operate
hardware. The owner confirms no camera/range/thermal sensor is in hand yet.
Physical NODE acceptance and any second-sensor integration remain pending.

**Owner-required OpenCode remediation — independent review follow-ups:**
All items below are required before accepting the respective fix; do not
interpret the earlier passing suites as closing these gaps. Preserve the
[exact reproducers/results](../../review/pr7-pr9-probes-20261024.json) and
[review source](../../review/pr7-pr9-independent-review-20261024.md).

| PR / exact reviewed head | Required follow-up / observed reproduction |
|---|---|
| #7 `939240eb34e158a9cf038291cb9c73c468ebe5d3` | Validate and snapshot the direct Python API before enqueueing: NaN confidence currently survives into a TeamTrack. Preserve stale/shared-parent controls. |
| #8 `9ca4f3aa32d410ebcc2e04ec30167fdda3234ba2` | Preserve/enforce UBX receiver validity (`gnssFixOK`); reject invalid NMEA checksums/unsupported quality; prevent duplicate Measurement IDs from adding precision. Flags-clear and bad-checksum fixes currently anchor GNSS; duplicate Pxx changes 12.5 → 8.333333333333332. |
| #9 `9e2f1d57bf1826f30b0c871284761388e46c3fc9` | Bound incomplete-frame assembly/recovery without mistaking magic-like payload bytes for a new frame. Plausible 4096-byte prefix blocks 11 complete frames until extra bytes arrive. Pin exact SDK behavior before physical compatibility claims. |

Reproduce from the bench checkout with the project's Python environment:

```sh
PYTHONDONTWRITEBYTECODE=1 python tools/review_pending_prs.py \
  --team /Users/overlord/.cache/review-pr7 \
  --gnss /Users/overlord/.cache/review-pr8 \
  --radar /Users/overlord/sideprojects/specter-x-radar
```

Review/reproducer commit: `97943c3e505cecc7e9ef76d5a9ea0d33d82634f5`.
IMU fix: `72bf6198e757ad2c0c6dfff20d9e56aa2c543c70`.
Original NODE pipeline: `4e2e889a61b2189342c02efcde334ba8e866bda6`.
Tested acquisition/ownership implementation:
`1a94fa7686c3e66c22a6de327a56e54b1bf154a3`, against current remote main
`f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2`.
**284 passed, 1 hardware deselected**, architecture PASS; 7,290 records /
2,788,217 identical raw bytes / zero rejected or unaccounted bytes.
Independent WORLD v2 `4e1c920` first/middle/last envelope checks pass through
the existing JSONL interface; no UI application changes are in this candidate.

Ownership: a second cooperating process is rejected and release/reopen
passes on virtual terminals. The Mac accepted `TIOCEXCL` but allowed a raw
noncooperating open; the failed probe is retained and physical exclusion
remains UNVERIFIED. [Measured ownership result](../../review/node-ownership-20261024.json).
Do not claim a universal exclusive-device guarantee or interfere with Alpha.

Next physical gate: [EXP-NODE-ESP32-001 v1](../../design/node-esp32-first-acquisition-v1.md),
one 15-second empty-bench recording with explicit identity/ownership,
4 MiB / 4096-read limits, then closed-port WORLD replay. **NOT AUTHORIZED /
NOT RUN**; the exact port and current firmware identity remain UNKNOWN.
Specific owner authorization for that test/port/implementation is required.
No flash, reset, network/stimulus change, automatic retry or human experiment.

This handoff is committed in the isolated bench draft; main is intentionally
unchanged until an owner-authorized review/integration. OpenCode should read
this branch's handoff and linked review before remediation, not the older
main-only packet. No remediation implementation was mixed into this PR.
