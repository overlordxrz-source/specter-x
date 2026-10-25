# Branch-safe handoff template

Feature agents should not routinely edit the canonical
[main handoff](../handbook/agent-handoff.md). Parallel branch edits to that file
create competing “current” states and merge conflicts. Use a branch-local
handoff instead.

## Where

- Preferred: `docs/context/handoffs/<branch-name-with-slashes-replaced-by-dashes>.md`
  in the feature branch (for example, `docs/context/handoffs/docs-persistent-context-protocol.md`).
- Or the PR description / final task report.
- The canonical `docs/handbook/agent-handoff.md` is updated only by an
  integration owner after review/merge/checkpoint, using this template’s facts.

## Template

```text
Branch handoff
- Branch / worktree:
- Base commit:
- Head commit:
- Owner / task:
- Context Receipt:
- Scope completed:
- Canonical documents read:
- Accepted ADRs applied:
- Protected docs changed (approved?):
- Tests / adversarial controls / exact results:
- Evidence artifacts and hashes:
- Known gaps / unknowns / failed attempts:
- Rollback:
- Next smallest task:
- Integration constraints (do not merge/flash/buy/human-trial without):
- Compaction/checkpoint trigger: update this handoff before a long session is
  compacted or a checkpoint is created; preserve open contradictions and unknowns.
```

## Canonical update

The integration owner merges the factual fields into the canonical handoff only
when the branch is accepted or a checkpoint requires it. Do not copy a branch's
optimistic status into the canonical handoff; preserve failures, unknowns and
superseded claims. A branch handoff is not evidence and cannot promote a
capability.

## Parallel-work rule

If two branches would both edit the canonical handoff, the integration owner
reconciles them after review. Do not resolve that conflict by overwriting the
other branch. Preserve each branch's commits and handoff as provenance.
