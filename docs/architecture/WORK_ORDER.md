# Agent work-order template

Copy into a task-specific dated document; fill the blanks before substantial code.
The owner can authorize a smaller scope directly. This template does not grant
hardware, experiment, push, merge, spending or publication authority.

- **Outcome:** one observable behavior; who needs it and why.
- **Base / branch / owner:** exact commit, isolated checkout, protected dirty paths.
- **Canonical context:** handbook/ADR/experiment links actually read.
- **Inputs:** exact files, hashes, layout/units, clock and provenance assumptions.
- **Outputs / interface:** schema, lifecycle, error states, bounded resources.
- **Scope:** allowed files/modules; explicit exclusions and other agent ownership.
- **Acceptance:** measurable behavior and exact reproducible commands.
- **Adversarial control:** baseline failure; synthetic positive and null if numerical;
  mutation that must fail. Trial/session split and confound handling if empirical.
- **Risk / rollback:** compatibility, data loss, privacy, hardware effects; reversible
  local rollback that preserves user diffs and recordings.
- **Checkpoint / stop:** small first verification milestone; stop on missing evidence,
  changing protocol, ownership conflict or failure outside the scoped component.
- **Delivery:** exact diff/commit, test outcomes including failures, limitations,
  readiness state and next smallest task. No unsupported “all code is good” claim.

Review checklist: no phantom source, invented covariance, implicit downloads,
unbounded read/queue, second device owner, packet leakage, removed regression,
retroactive preregistration or changed frozen evidence. The architecture gate is a
limited automated check; review all checklist items that actually apply.
