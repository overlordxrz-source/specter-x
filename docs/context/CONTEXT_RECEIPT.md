# Context Receipt template

Copy this into the task record, PR description or branch handoff **before**
materially changing architecture, research direction, procurement, capability
status or a protected document. A receipt is a report, not authorization.

```text
Context Receipt
- Agent/session:
- Task / owner request:
- Authorization limit (merge/flash/purchase/human trial/other):
- Repository commit reviewed:
- Context Brief generated commit / source hashes:
- Canonical sources read:
- Active accepted ADRs applied:
- Protected documents expected to change:
- Branch / worktree ownership:
- Contradictions found:
- Unknowns / unverifiable claims:
- Tests / adversarial controls planned:
- Rollback or stop condition:
- Decision-change required? (ADR id / owner approval):
```

Rules:

- Cite exact paths/commit; do not write “read the docs.”
- If a source is inaccessible, say so and mark the claim unverified.
- If the task would contradict an accepted ADR, stop and use
  [decision change](DECISION_CHANGE.md); do not treat the receipt as approval.
- If a protected document changes, update its hash manifest and regenerate the
  [Context Brief](CONTEXT_BRIEF.md) only after the semantic review.
- Do not include secrets, participant data, private RF identifiers, purchase
  terms or raw evidence in a public receipt.
