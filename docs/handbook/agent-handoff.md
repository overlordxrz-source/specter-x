# Agent handoff index

[Hub](../README.md) · **Current handoff · 23 October 2026.**

This is the short handoff for a new agent. Read it after the North Star and
the relevant memory entries; open the linked evidence before making a claim.
The older [documentation handoff](handoff.md) records how the handbook was
built and remains historical.

## Startup ritual

Read, in this order:

1. [North Star charter](north-star.md) — identity, doctrine and boundaries.
2. [Research ideas](research-ideas.md) — relevant **VISION/RESEARCH** entries.
3. [Decisions](decisions.md) — relevant **accepted** ADRs.
4. [Experiment ledger](experiment-ledger.md) — latest verified/exploratory gate.
5. This handoff — current branch, owner, blockers and next task.

Then inspect the actual repository and worktrees (`git status`,
`git log`, `git worktree list`). Do not rely on this page for a clean/dirty
state, and do not overwrite uncommitted work.

## Current state

| Item | State |
|---|---|
| Documentation branch / worktree | `docs/main-handbook-sync` in the documentation worktree. This memory update is documentation-only. |
| Alpha code / evidence branch | `feature/alpha002-esp32-supervisor` in the main research worktree. Latest verified Alpha handoff: `e7af1ad`; Alpha 002-C forensic record: `a3c540d`. |
| Alpha 002-C | **IN PROGRESS — exploratory positive, independent replication pending.** One 20-trial session, 20/20 valid; p = 1/1024, d_z = 1.69, CI [1.34, 2.91]. Original INVALID and corrected PASS preserved. Not confirmatory. |
| Alpha 003 | **PLANNED — protocols and offline code only; no human session.** Screening: 6 blocks × 3 × 20 s, seed `20261024`. Confirmatory: 7 sessions, session-level exact sign test. No presence claim. |
| FRONTIER-001 / SPECTER-WORLD | **Work-owned**, separate `specter-x-frontier001` worktree. Read-only from this documentation effort; do not touch, merge or overwrite. |
| Hardware/firmware | No Alpha 003 hardware run. Do not flash firmware or start a human session without explicit owner authorization. |

## Next single task

**No human session is authorized by this handoff.** The next physical task,
when authorized, is the one-session Alpha 003 screening in
[alpha003-screening-v1.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-screening-v1.md).
The next evidence task is independent replication of Alpha 002-C using the
frozen [replication protocol](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha002c-replication-protocol-v1.md),
also only with authorization.

## Do not

- Do not merge the documentation branch with feature/Work branches.
- Do not touch or modify Work's `specter-x-frontier001` worktree.
- Do not flash firmware or start human trials without explicit authorization.
- Do not rewrite a historical checkpoint, result or hash to make it cleaner.
- Do not promote a synthetic/offline result, an acquisition preflight or one
  exploratory session to a validated presence/motion claim.
- Do not treat a high-confidence single-sensor observation as new spatial
  information (ADR-003).

## Update triggers

Update this handoff and the relevant memory log when:

- a distinctive research idea or architectural decision appears;
- a protocol, seed, analysis or evidence gate changes;
- an experiment passes, fails, is aborted or is invalidated;
- a device/hardware status or ownership changes;
- a long agent session is about to be compacted or handed off;
- a checkpoint is created.

Keep entries short and link raw evidence. Avoid log spam for ordinary chat.

## Five-line recap

```text
Objective / current subtask:
Worktree + branch + tested commit:
Implemented and physically verified (with evidence IDs):
Unknown, exploratory, pending, or blocked:
Next action + coordination constraints:
```
