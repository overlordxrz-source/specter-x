# Next scoped work order: legacy team evidence validity

**IMPLEMENTED ON A SCOPED BRANCH — pending independent review · offline only.**
Read the engineering contract and current handoff first. No human session, device
operation, merge, push or Alpha change is authorized here. This task must not
enable team fusion in WORLD.

**Delivery note (24 October 2026):** stale/future/unknown-age peer reports are now
rejected, and shared/looped parent evidence cannot gain independent precision.
See [ADR-007](../handbook/decisions.md) and
[the regressions](../../tests/test_team_evidence_validity.py). Team fusion remains
gated. The recommended next work order is the no-fix GNSS state-mutation
blocker documented in the audit; this file remains the team-fusion record.

**Outcome:** old or duplicate evidence cannot become a fresh independent spatial
measurement merely because a fusion cycle ran.

**Owner/scope:** create a new isolated branch from a reviewed audit commit; record its
exact SHA and status. Limit work to `specter/fusion/team.py`, the relevant message/time
contract if necessary, focused tests and an ADR. Preserve all audit regression tests,
OpenCode's feature checkout, CI, frozen experiments and recordings.

**Starting failures (both now fixed):** `PYTHONPATH=. python tools/audit_legacy_probes.py`
demonstrated (1) a report stamped t=1 becoming current at t=100 and (2) the same parent
on local and peer reports shrinking covariance approximately in half. The original age
test only checked an empty next cycle; it did not test an old incoming report.

**Design first:** state what report time means, which clock mapping is established,
what acquisition time/epoch each local and peer input carries, and what to do when
age/frame/anchor/correlation is unknown. Do not subtract unrelated device clocks or
invent an anchor offset. Schema v1 lacks anchor identity. Unknown eligibility must
remain unknown or be rejected; a calibrated transform is not implemented by a hook.

**Acceptance:** deterministic controls for fresh/stale/future/unknown-age reports;
unchanged last observation time through repeated fusion calls; duplicate parent and
looped-peer reports must not gain independent precision; disjoint validated evidence
retains correct provenance. Include null/invalid covariance and mismatched-frame
controls. Define behavior for shared parents before picking a fusion method.

**Method:** add failing tests first, implement the smallest reviewed contract/fix,
run focused fusion/network tests and the full offline suite plus architecture gate.
Demonstrate deliberate restoration of current stale/double-count behavior fails the
new regressions. No packet counts as independent trial counts, invented confidence,
unrelated rewrite or new dependency without a measured need.

**Stop/checkpoint:** if a safe fix requires a new synchronized message schema or
physical reference, finish a concrete ADR and offline fixture first; report the
missing interface/evidence and keep the capability gated. Deliver exact before/after
results, changes, compatibility and remaining assumptions. Update the diagnostic
probe/report classification deliberately after closing a finding; do not preserve a
known bug merely because this audit documented it.
