# Next scoped work order: legacy team evidence validity

**PLANNED · offline only.** Read the engineering contract and current handoff first.
No human session, device operation, merge, push or Alpha change is authorized here.
This task must not enable team fusion in WORLD.

**Outcome:** old or duplicate evidence cannot become a fresh independent spatial
measurement merely because a fusion cycle ran.

**Owner/scope:** create a new isolated branch from a reviewed audit commit; record its
exact SHA and status. Limit work to `specter/fusion/team.py`, the relevant message/time
contract if necessary, focused tests and an ADR. Preserve all audit regression tests,
OpenCode's feature checkout, CI, frozen experiments and recordings.

**Starting failures:** `PYTHONPATH=. python tools/audit_legacy_probes.py` demonstrates
(1) a report stamped t=1 becomes current at t=100 and (2) the same parent on local and
peer reports shrinks covariance approximately in half. The existing age test only
checks an empty next cycle; it does not test an old incoming report.

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
