# Persistent-context automation limits

The context checks are deliberately small, offline and reviewable. They are a
tripwire, not a semantic proof.

## What the checks can detect

- A declared source path missing from the repository.
- A source hash changed without regenerating the Context Brief.
- A generated Context Brief edited by hand or stale relative to its sources.
- A missing, duplicate or non-sequential ADR ID; invalid ADR status shape.
- A protected architectural document changed without updating its hash manifest.
- A local Markdown link in the declared context/procurement documents pointing
  to a missing target.
- Missing required context artifacts (brief, receipt template, decision-change
  process, branch handoff template, Hark profile).
- Basic AGENTS.md presence of the context-preflight obligations.

## What they cannot detect

- **Semantic contradiction.** “All AI must fit in the wearable” can be written
  in fluent prose that contains no broken link or hash mismatch. ADR-007 is the
  authority; automated text matching cannot understand paraphrase or implication.
- **Omitted context.** A summary can be factually true and still leave out the
  central-compute distinction, local safety, uncertainty or a superseding ADR.
- **Capability-label laundering.** Renaming simulated output “measured” or a
  track list “WORLD” may preserve hashes while corrupting meaning.
- **False or ambiguous provenance.** A hash proves bytes, not that the artifact
  is a real sensor recording, that its labels are true, or that the cited run was
  authorized.
- **Owner intent and approval.** A commit, passing test, PR approval or updated
  hash manifest is not proof that the owner approved a decision change.
- **Malicious edits to the checker, source manifest and protected manifest.**
  Those files are reviewable code/data, not a trust anchor.
- **Freshness of the working tree.** Uncommitted files, alternate worktrees,
  local branches and chat-only instructions may not appear in the checked tree.
- **Numbering quality.** Sequential ADR IDs can still be bad decisions.
- **Hardware, calibration, security, privacy, safety, cost or vendor support.**
  Those require physical/engineering evidence and human judgment.
- **Whether the reader actually read the brief.** A reported receipt can be
  fabricated; independent review is still required.

## Required human/agent response

When a semantic issue is suspected, produce a Context Receipt, cite the exact
ADR/source, stop material direction changes, and use
[decision change](DECISION_CHANGE.md) if the accepted decision would move. An
independent reviewer should check the summary against the canonical text, not
just the green check.

## Explicit adversarial example

A document can pass every hash check while saying “the wearable contains all
high-performance AI and WORLD is the map screen.” That is a semantic
contradiction of [ADR-007](../handbook/decisions.md) and
[ADR-009](../handbook/decisions.md), even if the files are freshly generated.
The check cannot reject it; the Context Receipt and review must. The
[recovery demonstration](RECOVERY_TEST.md) exercises this failure mode.
