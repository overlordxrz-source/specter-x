# SPECTER-X engineering entry point

Read `docs/handbook/north-star.md`, `docs/handbook/decisions.md`,
`docs/handbook/experiment-ledger.md`, `docs/handbook/agent-handoff.md` and
`docs/architecture/ENGINEERING_CONTRACT.md` before changing behavior.
The owner's explicit instructions take precedence. This file grants no hardware,
push, merge, deployment, experiment or publication permission.

Use `docs/architecture/WORK_ORDER.md` to scope significant work. Inspect Git status
and worktrees first; preserve other agents' checkouts, uncommitted files and frozen
raw evidence. Keep changes in an isolated branch. Do not delete a regression to
make a suite green; explain a justified replacement and demonstrate the same
failure is still caught. Tests are software evidence, not physical validation.

Run the focused negative control and offline suite, then
`python tools/check_architecture.py`. Changes to WORLD require browser verification,
including the delayed-response/source-switch regression, with actual local capture
replay when available. Report source gaps and untested paths literally.

Do not import legacy team fusion, pose filtering, advisory safety heuristics or
experimental sensor stubs into WORLD as validated capabilities. See the audit
release blockers. Do not download models, open devices or launch acquisition merely
to inspect a recording. A package import or successful build is not a device test.
