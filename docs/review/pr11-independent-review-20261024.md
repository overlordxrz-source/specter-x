# PR #11 independent review — 24 October 2026

**REQUEST CHANGES** at exact head `b58c96ef998e68e841b12d9ad671325053c009e4`.
Two reproduced integrity defects are corrected locally on
`review/pr11-context-audit`, pending independent re-review. Main, original PR
branches, hardware and frozen Alpha were not changed. This is review evidence,
not architectural approval.

## Exact checkpoints

| Scope | Commit |
|---|---|
| PR11 reviewed | `b58c96ef998e68e841b12d9ad671325053c009e4` |
| Main / integration base | `f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2` |
| Approved PR10, still open | `8a84369941c74d5f884c9ec6cc33d10395223597` |
| Original Brief source | `71a54ede6a295189bdaae67f30da86f5914ad231` |
| Regression-before-fix | `3f9c647` |
| Corrected code / source configuration | `2a5b7489330d4c0dd4c57717d5192c1a02e2a382` |
| Corrected generated Brief | `bd3433c8410dd0d3ac51de6f1a64760a00fd4521` |

Inspected AGENTS, ADR-007/008/009, authoritative handbook documents, context
artifacts, Hark, source/protected manifests, generator/checker/tests and CI.
Original source line numbers below refer to the exact PR head.

## Required corrections

**P2 — VERIFIED BUG: protected governance changes escape Brief freshness.**
`tools/check_context.py:67–91` does not enforce protected-source coverage.
Six protected files are absent from `docs/context/sources.json`: context README,
receipt, decision-change process, branch handoff template, automation limits and
ChatGPT recovery. Change `docs/context/DECISION_CHANGE.md`, refresh only the
protected manifest and commit in a disposable clone: the unchanged Brief still
passes, exit 0. Its source manifest cannot identify the revised governing process.
Fixed by including all six and requiring coverage of all 18 builtin protected
paths. The identical mutation now fails, exit 1, until Brief regeneration.

**P2 — VERIFIED BUG: pending-approval prefix becomes accepted.**
`tools/context_brief.py:100–103,122–123` validates/selects statuses with
`startswith`. ADR-007 status `accepted_pending_owner_approval`, followed by
manifest refresh, commit and Brief generation, passes and becomes active
accepted. Invalid accepted/proposed/superseded suffixes also pass. The generated
decision list drops the original draft-implementation qualifier.
Fixed with exact statuses, one explicit legacy alias (`accepted research policy`
for ADR-004), exact active selection and full status wording in the Brief.
Invalid-status generation and checking now fail; proper proposed ADRs remain
valid and are excluded from active accepted decisions.

## Freshness and CI negative controls

**VALIDATED:** every declared source and protected document has identical bytes
at `71a54ede…` and the reviewed final head. The older generation commit is valid
for that snapshot, not itself stale. Requiring generation from every new HEAD
would be unnecessary. The bug concerns subsequent omitted-source changes.

`.github/workflows/pytest.yml:25–41` runs offline pytest and the context checker,
fetching full history for provenance. Hosted exact-head CI was green. These are
independently executed local mutation controls using the same checker, not
uploaded mutant CI runs:

| Mutation | Original | Corrected |
|---|---|---|
| Baseline | PASS / 0 | PASS / 0 |
| Missing North Star source | FAIL / 1 | FAIL / 1 |
| Tampered Brief hash | FAIL / 1 | FAIL / 1 |
| State changed without Brief refresh | FAIL / 1 | FAIL / 1 |
| Nonexistent ADR reference | FAIL / 1 | FAIL / 1 |
| Protected change without manifest refresh | FAIL / 1 | FAIL / 1 |
| Protected process + manifest refreshed; Brief untouched | **PASS / 0, bug** | **FAIL / 1** |
| Pending-approval status + refreshed manifests/Brief | **PASS / 0, bug** | **FAIL / 1** |
| No approval, but all content/manifests/Brief refreshed | PASS / 0 | PASS / 0 |

The last row is a **documented manual authorization limit**, not an unexpected
checker defect: `docs/context/AUTOMATION_LIMITS.md:31–34` and
`docs/context/DECISION_CHANGE.md:21–30` explicitly require owner review. CI cannot
authenticate consent or semantic correctness. Accepted owner-directed design
intent is distinct from implementation draft and merge approval in current
ADR-007/008/009; the corrected Brief retains those qualifiers. Earlier owner
directives recorded in prose are assertions, not independent authentication.

## Architecture, procurement and memory-free recovery

**VALIDATED by inspection and a bounded recovery exercise.**
`docs/handbook/decisions.md:110–138` mandates central command / AR headset /
distributed nodes. Workload placement is flexible, tiers mandatory; local safety
survives link loss. North Star, architecture, roadmap, Brief truths, root README's
historical compute clarification and Hark preserve the topology. ADR-009 at
`:163–184` separates coordinating OS, persistent evidence-grounded WORLD and
VIEW client; research is not shipped capability.

`docs/procurement/HARK_CONTEXT.md:3–11,13–23,85–105` is a planned question set,
not purchase/receipt/sponsorship or compatibility proof. Central candidates need
workload, interface, calibration, support, power/thermal and safety evidence.

One separate agent received no inherited conversation: only the exact checkout
path and instructions to start at AGENTS, using repository files only, with no
memory/remotes/other checkouts. It independently recovered all three tiers,
OS/WORLD/VIEW, evidence labels, research limits, draft adoption, owner-decision
process, branch-safe handoff and absence of hardware authority. Its original
checker passed (17 sources, 18 protected). This is one successful recovery test,
not proof every agent complies.

Residual inherited editorial ambiguity: `docs/handbook/hardware-inventory.md:88–98`
combines an owner-report-only preamble with an RP2040 verification row, then
lists serial/asset identity unknown despite a USB serial in the row. Reconcile
those specific labels in a separate owner-reviewed inventory update; this review
does not promote hardware status.

## Integration and accurately scoped coverage

Both PR heads descend from main `f2ef96b…`. A virtual `git merge-tree --write-tree`
finds one content conflict: `docs/handbook/agent-handoff.md`. `docs/README.md`
auto-merges. Choosing either handoff wholesale would lose facts.

A temporary-tree rehearsal preserves PR11's canonical context and relocates
PR10's historical handoff additions into a branch evidence handoff, with a
canonical pointer. All 24 other PR10 changed files (excluding the two combined
document paths) remain byte-identical to approved PR10. Initial relocation broke
six relative links; the checker caught this, and corrected link depth passed.
Reconciled protected hashes and Brief need refresh against the combined source
commit. **No actual branch merge occurred.**

| Tested tree | Offline Python | Other gates |
|---|---|---|
| Exact PR11 | **255 passed, 1 hardware deselected** | context / architecture PASS |
| Original + new regressions before fix | **7 failed, 1 passed** | failures preserved |
| Corrected PR11 checkpoint | **263 passed, 1 hardware deselected** | context / architecture PASS; 23 sources / 18 protected / 9 accepted |
| Temporary PR11 + approved PR10 + fixes + reconciled handoff | **322 passed, 1 hardware deselected** | context / architecture PASS; 24 preservation checks true |

Counts belong to separate trees; 322 is not PR11-only coverage. No browser or
physical acquisition claim is made. A future integration SHA still needs review.

## Reproduce / next action

From the isolated checkout, use the existing project Python environment or
`requirements-ci.txt`. Output directories must not already exist:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -m 'not hardware'
PYTHONDONTWRITEBYTECODE=1 python tools/check_context.py
PYTHONDONTWRITEBYTECODE=1 python tools/check_architecture.py
python tools/review_context_probes.py --ref b58c96ef998e68e841b12d9ad671325053c009e4 --out /tmp/pr11-original-probes
python tools/review_context_probes.py --ref bd3433c8410dd0d3ac51de6f1a64760a00fd4521 --out /tmp/pr11-fixed-probes
python tools/review_pr11_integration.py --corrections-ref bd3433c8410dd0d3ac51de6f1a64760a00fd4521 --out /tmp/pr11-integration
```

Probe mutations and synthetic commits stay in disposable clones; integration
creates virtual Git objects without merging or moving source branches. All refs
must exist locally. [Summary evidence](pr11-review-evidence-20261024.json) and
[branch handoff](../context/handoffs/review-pr11-context-audit.md) are retained.
Full logs, failed controls and binary correction diff remain in the local task's
`outputs/pr11-review/` directory.

**Re-review requested:** independently verify the two fixes and negative
controls before incorporation, then review the deliberately reconciled
integration checkpoint. Original PR remains REQUEST CHANGES. Corrections are
local; no remote change or review comment was posted, and no merge/hardware
operation was performed.
