# Repository-wide audit — work in progress

Scope: integration `0929ad6` plus read-only Alpha `285bc2c`. Main `1edabbc` and draft PR #5 remain unchanged. Work branch `audit/world-os-hardening`. Ferret inspected read-only at `6a2eddeb5595`; no kernel modification or deployment.

A passing suite is not a certification. Maintain an exact file/hash/line inventory and distinguish semantic review, automated checks, runtime tests and hardware-unverified paths. Never label a file fully reviewed if output was truncated. No new hardware receipts are asserted.

Initial baseline: integration 189 passed / 1 hardware deselected (previous recorded integration run); Alpha snapshot rerun 414 passed / 1 hardware deselected / inherited NumPy warning. Baseline adversarial probes preserved in task artifacts. Verified defects so far: clock-domain mixing, negative variance tolerance, NumPy nonfinite JSON, signed-JSON whitespace mismatch, replay-guard invalid sequence acceptance and malformed-message poisoning, future timestamp freshness, catalog symlink replacement, fragmented DI188 echo, fragmented GNSS sync. Broader legacy fusion/calibration/stub risks remain under review.

Deliverables in progress: reproducing negative controls and targeted fixes; complete coverage ledger/report; upgraded desktop workbench; enforceable architecture/work-order contract and developer entry point. No push/merge/flash/physical acquisition in this audit scope.
