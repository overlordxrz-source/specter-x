# SPECTER-X engineering entry point

Read `docs/context/CONTEXT_BRIEF.md` first, then the relevant canonical
documents: `docs/handbook/north-star.md`, `docs/handbook/decisions.md`,
`docs/handbook/research-ideas.md`, `docs/handbook/experiment-ledger.md`,
`docs/handbook/agent-handoff.md`, `docs/handbook/architecture.md`,
`docs/handbook/hardware-inventory.md`, `docs/handbook/roadmap.md` and
`docs/architecture/ENGINEERING_CONTRACT.md`. The owner's explicit instructions
take precedence. This file grants no hardware, push, merge, deployment,
experiment, purchase or publication permission.

## Task-specific context preflight

Before changing architecture, research direction, procurement, capability
status, protected documents or behavior:

1. Run `python tools/check_context.py`. If it fails, report the failure before
   proceeding; do not “fix” it by deleting sources or editing the Brief by hand.
2. Read the generated `docs/context/CONTEXT_BRIEF.md` and the canonical sources
   relevant to the task. Verify the recorded commit/source hashes; fetch the
   repository if the commit differs.
3. Fill in a **Context Receipt** using
   `docs/context/CONTEXT_RECEIPT.md` in the task/PR/commit description: exact
   commit, sources, active ADRs, contradictions, unknowns, authorization and
   scope.
4. If the proposal contradicts an accepted ADR, use
   `docs/context/DECISION_CHANGE.md` and obtain owner approval before adoption.
   A PR, test, vendor claim or newer chat message is not architectural approval.
5. Use `docs/context/BRANCH_HANDOFF_TEMPLATE.md`; feature branches do not
   routinely edit the canonical `docs/handbook/agent-handoff.md`.
6. Procurement uses `docs/procurement/HARK_CONTEXT.md`; central command compute,
   the AR headset interface and distributed nodes are separate tiers. A quote,
   datasheet, TOPS number or demo is not a receipt or capability.
7. Report semantic contradictions and unknown evidence literally. Automated
   checks cannot detect them; see `docs/context/AUTOMATION_LIMITS.md`.

## Engineering rules

Use `docs/architecture/WORK_ORDER.md` to scope significant work. Inspect Git
status and worktrees first; preserve other agents' checkouts, uncommitted files
and frozen raw evidence. Keep changes in an isolated branch. Do not delete a
regression to make a suite green; explain a justified replacement and demonstrate
the same failure is still caught. Tests are software evidence, not physical
validation.

Run the focused negative control and offline suite, then
`python tools/check_architecture.py` and `python tools/check_context.py`.
Changes to WORLD require browser verification, including the
delayed-response/source-switch regression, with actual local capture replay when
available. Report source gaps and untested paths literally.

Do not import legacy team fusion, pose filtering, advisory safety heuristics or
experimental sensor stubs into WORLD as validated capabilities. See the audit
release blockers. Do not download models, open devices or launch acquisition
merely to inspect a recording. A package import or successful build is not a
device test.

## Protected context

The North Star, architecture, decisions, research ideas, experiment ledger,
roadmap, hardware inventory, engineering contract, canonical handoff and context
digests are protected by `docs/context/protected-docs.json`. An intentional
change requires semantic review and the decision-change process where applicable;
then update the manifest and regenerate the Context Brief. The hash check makes
change visible, not authorized.
