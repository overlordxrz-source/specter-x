# Agent handoff index

[Hub](../README.md) · **Current handoff · 23 October 2026.**

**Canonical startup reference for every future agent — ChatGPT, OpenCode,
Work and any other coding agent.** Read it after the North Star and the
relevant memory entries; open the linked evidence before making a claim. The
older [documentation handoff](handoff.md) records how the handbook was built
and remains historical.

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
| `main` | Canonical handbook plus CI repair. Docs merged at **`49cb2e5`**; CI merged at **`4b09d40`**; this handoff commit is the current main head. |
| Documentation branch / worktree | `docs/main-handbook-sync` was merged into `main` at `49cb2e5`. The worktree remains available for historical documentation review. |
| Alpha code / evidence branch | `feature/alpha002-esp32-supervisor` at **`285bc2c`** in the main research worktree. The CI repair was integrated at `4d8e30b`; frozen Alpha evidence remains at **`e7af1ad`**, forensic record at `a3c540d`. |
| CI fix to main | **PR #4 merged at `4b09d40`.** Six files only; automatic GitHub Actions is green. |
| Automatic vs hardware tests | Automatic CI runs `pytest -m "not hardware"`; the real DI-188 test is `@pytest.mark.hardware` and runs only in the manual self-hosted `hardware-tests.yml` workflow. The automatic suite must never operate physical hardware. |
| Alpha 002-C | **IN PROGRESS — exploratory positive, independent replication pending.** One 20-trial session, 20/20 valid; p = 1/1024, d_z = 1.69, CI [1.34, 2.91]. Original INVALID and corrected PASS preserved. Not confirmatory. |
| Alpha 003 screening | **PREPARED — software rehearsal complete; no human session and no authorization yet.** Screening endpoints remain frozen at `e7af1ad`; execution checklist at `285bc2c` (`docs/design/alpha003-screening-execution.md`). Readiness: 32 targeted preflight/acquisition/cue tests and `414 passed, 1 deselected` for the automatic suite. |
| FRONTIER-001 / SPECTER-WORLD | **Work-owned**, separate `specter-x-frontier001` worktree. Read-only from this documentation effort; do not touch, merge or overwrite. |
| PR #5 re-review | **REQUEST CHANGES — not merged**, head **`36bba3f`**, base `main`. Independent re-review: **193 passed, 1 hardware deselected**; 67 targeted; **28 browser checks**; 7,290-record replay and source hash reproduced. Residual findings below. |
| Hardware/firmware | No Alpha 003 hardware run. Do not flash firmware or start a human session without explicit owner authorization. |

## PR #5 re-review findings (`36bba3f`)

**Verdict: REQUEST CHANGES.** The four original issues are substantially
remediated: resilient splice/torn recovery and quality flags are covered by
independent probes; `--replay` no longer authorizes its parent; delayed
inspection/evidence responses are guarded and the browser suite passes;
catalog traversal stops at 512. Residual evidence and lifecycle issues
remain:

- **P1 — evidence reader persists across session switches.** A browser probe
  opened a checkpoint in `phase0-short.raw.csi`, switched to
  `synthetic-control.observations.jsonl`, and found the Research evidence
  `<pre>` unchanged: old phase0 JSON remained visible. `openSession()` does
  not clear `evidenceText`/`evidenceId` or close the inspection modal. Clear
  that state and add a persistent-state (not only delayed-response) browser
  check.
- **P2 — silent catalog truncation.** A 537-file approved root returns a
  512-item catalog with no truncation flag, count or UI/API marker. Evidence
  users can reasonably mistake the list for the complete set. Expose a
  bounded/truncated indicator or refuse to present a truncated catalog as
  complete.
- **P2 — catalog traversal is not fully bounded.** The new DFS still does
  `sorted(directory.iterdir())` for each directory. A single very large flat
  directory is fully materialized and sorted before the global 512 cap is
  reached; the 552-file test does not exercise that bound. Scan with a
  bounded selection or document the per-directory limit.
- **P2/P3 — `recovered_records` is misleading.** A normal one-record source
  reports `recovered_records=1`; the counter increments for every parsed
  record, not only records recovered from splices/torn lines. Count only
  recovered records or rename it, and test a clean source.
- **P3 — undetectable boundary splice.** A splice exactly between metadata
  and IQ cannot be detected because the wire format has no checksum. This is
  documented in `feed_resilient`'s docstring but should also be stated in
  the user-facing FRONTIER/WORLD verification docs so it is not mistaken for
  a guaranteed integrity property.

No remote/LAN binding or arbitrary-path API was found; sibling, traversal,
symlink, Host/Origin and token tests pass. The `.github`, canonical handbook
and frozen Alpha files are unchanged. No merge occurred.

## Next single task

**PR #5 is not ready to merge.** Work should address the REQUEST CHANGES
findings and re-request review. Do not merge or amend Work's checkout from
this documentation branch.

**Alpha 003 screening is prepared but not authorized.** Read
[alpha003-screening-v1.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-screening-v1.md)
and the
[execution checklist](https://github.com/overlordxrz-source/specter-x/blob/285bc2c/docs/design/alpha003-screening-execution.md).
The owner must send the explicit authorization sentence in that checklist;
until then, do not start a human session or a pre-check that requires a
subject.

The next evidence task is independent replication of Alpha 002-C using the
frozen [replication protocol](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha002c-replication-protocol-v1.md),
also only with authorization.

## Do not

- Do not merge PR #5 while the review verdict is REQUEST CHANGES.
- Do not merge unfinished Alpha 003 or SPECTER-WORLD code.
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
