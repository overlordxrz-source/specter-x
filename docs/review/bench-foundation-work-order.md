# Bench foundation — 24 October 2026

Owner: Codex, authorized by the user's “Get on it” following the proposed
review → dependable device workflow → two-sensor bench sequence.
Base: `f2ef96b`; isolated branch `review/bench-foundation-20261024`.
Main's untracked SoftAP directory, Alpha, PR #7–#9, SYNC and UI worktrees
are protected. No merge, push, PR comments, device operation or human trial.

## Accepted design and scope

1. Independently review exact pending heads, execute offline suites and
   adversarial probes, record findings with source lines and a verdict.
2. Close the remaining finite-quaternion defect locally with adversarial
   tests, including rejection without advancing driver state. Keep the
   existing heuristic uncertainty explicitly unvalidated.
3. Implement a small standalone NODE capture owner outside WORLD. It owns
   one bounded-timeout byte transport, writes raw bytes and read-completion
   monotonic timestamps, exposes lifecycle/accounting, and finalizes into
   the existing Observation/capture format for WORLD replay. Serial is
   explicit opt-in, never opened from browser/import/tests by default.
   File input is an offline rehearsal, never LIVE. No second observation
   schema, inference, firmware changes, or duplicate port reader.

Prefer a standalone capture owner over giving the browser serial access or
bulk-importing Alpha. This preserves the static offline WORLD boundary and
lets acquisition and replay share the existing parser/Observation contract.
Finished-session handoff comes first; live streaming into WORLD is a later
reviewed interface. No automatic reconnect: a failed link ends the session.

## Acceptance

- Exact reviewed heads, reproduced suites, executable probes and explicit
  distinctions between old bugs fixed and remaining validity gaps.
- Invalid quaternion shape, zero, NaN/Inf rejected; extreme finite nonzero
  quaternions normalize safely; subsequent valid reports still work.
- Capture preserves exact input bytes, cancellation/stall/duration limits,
  read exceptions, size bounds, exclusive output creation and transport
  closure. A failed capture is recorded as failed, never silently complete.
- Existing CSI adapter handles framing/IQ; derived observations retain raw
  hashes/lines, acquisition clocks and truthful origin. Offline feed times
  are not substituted for original physical reception times.
- Actual preserved CSI records round-trip through capture and WORLD,
  retaining 7,290 records/hash; unit controls use deterministic fake clocks
  and byte transports. No physical hardware operated.
- Run focused tests, relevant offline suite and architecture gate. Preserve
  failures and disclose dependencies/physical acceptance still outstanding.

## Next physical gate

Owner-authorized empty-bench capture with an exclusively owned ESP32 port,
fixed stimulus, no experiment labels/inference, and explicit disconnect/stall
checks. Select a second sensor only from verified receipts and electrical
readiness; the parts list alone does not establish availability. Shrike timing
characterization remains separate and does not block this software seam.
