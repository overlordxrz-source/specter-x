# CLEAN AUDIT/OS HARDENING INTEGRATION

This document is the **integration entrypoint** for the audit/OS hardening
branch. It is deliberately separate from the original audit report. The
original audit branch remains untouched; this PR is a separate integration
branch only.

- **Source audit commit:** `c419216` on `audit/world-os-hardening`.
- **Integration base:** current `main` at `b92aa4d`, including the merged PR #5
  branch (`integrate/frontier-world-main` at `cf05def`).
- **Reconciliation:** merge from `c419216` into `origin/main` with no conflict.
- **Preservation:** original audit branch, CI configuration, frozen Alpha
  evidence, canonical handbook and branch ownership untouched.
- **PR intent:** prepare a reviewable integration of audit hardening.
- **Not included:** hardware operations, new experiments, feature expansion,
  Alpha modification, or any merge decision.

## Reconciliation verification

- **Offline suite:** `245 passed, 1 deselected`.
- **Targeted hardening suite:** `68 passed`.
- **Architecture gate:** `tools/check_architecture.py` `PASS`.
- **Legacy P1 probes:** all five still reproduce (`true`) in
  `tools/audit_legacy_probes.py`.
- **Source-evidence replay:** `7290` observations, source SHA-256
  `f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`
  unchanged from the frozen real evidence. Independent route matches the
  main replay route, `source_unchanged=true`, `hardware_access=false`.
- **Browser regression checks:** `37 checks PASS`.
- **Automation view:** the audited source files were kept identical to the
  original audit branch; the merge introduced the newer main handbook and
  ledger only.

## Fixed defects in this branch

The audited hardening fixes remain intact:

- strict evidence contract and validation, including clocks, PSD
  covariance, finite/timestamp and replay-state guards
- strict security/network parsing and freshness handling
- persistent event-session and sensor parsing fixes
- path/tree security and evidence-state correctness fixes
- catalog path/symlink/escape revalidation and delayed-response guards
- bounded catalog enumeration and scan-error disclosure
- retention of existing evidence lifecycle regressions

## Still-open P1 legacy blockers

These are **deliberately unfixed in this branch**. They remain executable
legacy blockers; fixed defects do not close these.

1. **Stale peer report becomes fresh** —
   `specter/fusion/team.py:119`.
2. **Shared parent evidence double-counted** — same evidence on local and peer
   paths halves covariance in team fusion.
3. **No-fix GNSS anchors the EKF and claims GNSS mode** —
   `specter/localization/ekf.py:117`.
4. **Impossible radar packet length accepted** —
   `specter/sensors/radar/tlv.py:41`.
5. **Non-finite quaternion accepted** —
   `specter/sensors/imu/bno085.py:23`.

## Engineering contract and next work order

The branch already includes:

- [Engineering contract](../architecture/ENGINEERING_CONTRACT.md)
- [Next scoped work order](../architecture/NEXT_WORK_ORDER.md)
- [Audit report and controls](README.md)
- [Reproduction commands](REPRODUCE.md)

Use them unchanged as the contract for further engineering work. Do **not**
treat the green suites as certification; the audit branch still does not claim
end-of-line safety. Do not enable the five P1 legacy paths as validated WORLD
capabilities.
