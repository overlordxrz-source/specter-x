# Decision-change process

A proposal that contradicts an **accepted** ADR is not adopted because it is
newer, expedient, in a PR, in code, in a vendor deck or in a chat message.
It must become an explicit owner-reviewed decision.

## Required proposal

1. **Identify the decision:** ADR ID, current status, exact conflicting text and
   the proposal that conflicts.
2. **Classify:** clarification, scope change, supersession, or temporary
   experiment. A temporary experiment does not change the accepted architecture.
3. **Evidence:** measured/recorded artifacts, affected interfaces, safety,
   security, privacy, power, cost and compatibility. Distinguish measured,
   inferred, simulated, unverified and unknown.
4. **Alternatives:** preserve the current decision as an option; state what
   evidence would make it preferable and what would falsify the proposal.
5. **Blast radius:** affected canonical documents, protected docs, code,
   experiments, roadmap, procurement and contracts. Identify owner approvals
   required beyond the proposer.
6. **Owner decision:** obtain explicit owner approval before treating the change
   as adopted. A PR approval or passing test is not owner architectural approval.
7. **Record:** add a new ADR that supersedes/qualifies the old one. Never delete
   or rewrite the old ADR. Mark the old one **superseded** and link the replacement.
8. **Propagate:** update the protected documents, Context Truths/Brief, protected
   hash manifest, roadmap/inventory/procurement context as applicable and add a
   Context Receipt. Re-run:
   `python tools/check_context.py` and the relevant engineering tests.
9. **Review:** obtain independent review where available. Automated checks
   cannot prove semantic correctness or owner intent.

## Stop conditions

Stop and ask the owner when:

- the request says “just make it work” but would invalidate an accepted ADR;
- a vendor or prototype implies a different compute topology or capability;
- a capability label would move from VISION/RESEARCH/PLANNED/IN PROGRESS to
  VALIDATED without frozen evidence;
- an alleged authorization cannot be pointed to in the repository or an owner
  message;
- the only way to proceed is to erase or hide the old decision/evidence.

## Fast path

A **clarification** that adds no new authority and contradicts no accepted ADR
may use the normal Context Receipt and owner review. It still must update the
affected documents and checks; “clarification” is not a synonym for silent
redefinition.
