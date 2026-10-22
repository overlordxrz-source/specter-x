# Documentation handoff — 22 October 2026

[Documentation hub](../README.md)

## Edition 2 — canonical charter and Alpha reconciliation

The owner adopted the [North Star charter](north-star.md) on 22 October 2026. It governs identity and doctrine; detailed chapters and dated evidence have separate roles. The handbook now explicitly includes SPECTER-OS, WORLD, AIR/GROUND/ORBIT and BIO, the multispectral wearable/skeletal/AR ambition, per-value epistemic states and a five-plus-year horizon.

Added `docs/handbook/north-star.md` and `docs/handbook/alpha-95eae17-review.md`. Updated the hub, vision, architecture, contracts, firmware strategy, ICD, backlog, inventory, roadmap, research/platforms, verification/source registers and this handoff. These are documentation changes only, on the existing `docs/specter-x-handbook-20261022` branch. The original edition's manifest below is retained as history; edition 2 brings the handbook to 20 Markdown files.

Inspected Alpha `95eae1787bfa5a3f09d46bd19ad917874cb80029` through local Git: checkpoint 012, candidate source, contract tests, dependency manifest and saved synthetic CSV. Builds and 261 tests remain reported, not reproduced. Firmware remains not flashed or hardware-validated. Static contract checks do not establish runtime output reliability or sensing; new diagnostics are distinct from the original supervisor protocol. The original checkout stayed on the same clean Alpha commit during this update. No software/test/firmware changes, merges, rebases, pushes, resets or hardware operations were performed.

The docs branch still inherits code at `77abdd0`; Alpha is reconciled in prose with immutable source identifiers, not merged. No newer checkpoint was overwritten. Remaining access gaps include the original parts-status CSV, sponsor/shipment evidence, independent complete 261-test transcript and reproduced build/hardware results. The earlier source/access notes below retain their edition-1 dates and scope; the new Alpha review supersedes its uninspected-agent limitation.

## Edition 1 historical record

### Produced repository state

- Existing source repository: `/Users/overlord/sideprojects/specter-x`.
- Isolated linked worktree: `/Users/overlord/sideprojects/specter-x-docs-20261022`.
- Documentation branch: `docs/specter-x-handbook-20261022`.
- Parent/source snapshot: `77abdd0` (full SHA available from this branch's parent commit).
- Scope: 18 new Markdown documents, all under `docs/`; no existing files modified.
- Delivery: local documentation commit on that branch; no merge, push, flash or deployment.

The docs branch deliberately starts from the coding agent's existing feature snapshot so its hardware evidence and source links are available. It is **not a branch based only on main**. Comparing this branch directly to main may include the inherited feature history; review the docs commit or compare to `77abdd0` for this handoff's exact changes.

The original checkout initially reported branch `feature/alpha002-esp32-supervisor` at `77abdd0` with untracked `tools/esp32_csi_sweep.py`. It was left untouched. A later read-only check saw that same feature branch at `95eae1787bfa5a3f09d46bd19ad917874cb80029` with a clean status, consistent with concurrent agent progress. That independently advancing history was neither reset nor copied into the docs baseline. This observation does not certify the newer commit or its experiments.

## Exact new-file manifest

- `docs/README.md`
- `docs/handbook/architecture.md`
- `docs/handbook/backlog.md`
- `docs/handbook/commercialization.md`
- `docs/handbook/constraints.md`
- `docs/handbook/data-contracts.md`
- `docs/handbook/firmware-strategy.md`
- `docs/handbook/handoff.md`
- `docs/handbook/hardware-inventory.md`
- `docs/handbook/interfaces.md`
- `docs/handbook/platforms.md`
- `docs/handbook/research-program.md`
- `docs/handbook/roadmap.md`
- `docs/handbook/sources.md`
- `docs/handbook/suppliers.md`
- `docs/handbook/validation.md`
- `docs/handbook/verification-baseline.md`
- `docs/handbook/vision.md`

## Evidence reviewed and access gaps

Reviewed the root overview/license, checkpoint/design records, key saved JSON/JSONL evidence, measurement and message schemas, supervisor parser, pinmap and selected sensor source. Read the referenced chat through the thread tool; its returned attachments list was empty and assistant replies were content-reference markers. Read recent SPECTER-X OpenCode messages/status without sending instructions, approving permissions or interrupting work.

Imported all 79 accessible supplier-lead rows into Markdown with source-file SHA-256. The source parts-status CSV, sponsor correspondence, confirmed receipts and tracking events were unavailable. No supplier or carrier account was accessed and no supplier was contacted. No physical hardware, current device firmware or backup binary was accessed.

External sources were checked through primary-source browsing where practical. DATAQ's protocol PDF returned HTTP 403; the pinned upstream `8633d67` tree URL could not be retrieved. The public esp-csi overview and versioned Espressif documentation were available. [Sources](sources.md) records supported uses and access limitations; supplier proof pages are carried as unverified leads.

The app exposed local tools and a Work sidebar context; no dedicated tool to toggle this chat's execution mode was available. The requested work was completed locally against the existing Mac repository through its linked docs worktree. No unrelated repository or new chat was created.

## Validation scope

Documentation checks cover relative file-link resolution, index coverage, source-only diff boundaries, Markdown table shape/fences and whitespace. A deliberately missing file target is used as a negative control for link validation. The final verification result is delivered in the accompanying output report.

No application test suite, physical experiment, firmware build, restore or deployment was run. Historical test counts, performance metrics and backup checks are explicitly attributed to their existing records. No success is claimed for the coding agent's newer sweep or firmware. These checks establish documentation consistency and isolation; they do not validate the physical platform.

## Update and review procedure

Open `docs/README.md` in the docs worktree. Review the docs-only commit against `77abdd0`. Preserve the original feature branch and its working files. Merge/cherry-pick/rebase only in a separately authorized integration step; none was performed here.

When the owner supplies the original status CSV, update the inventory using its dated evidence, keeping personal/shipping details private. When new engineering work completes, review its actual diff and artifacts, update the baseline commit/date and revise claims explicitly. Add new run records instead of erasing failed results. Recheck relative links and schema compatibility when files move.

Named CORE/NODE/SENSE/LINK/FUSION/WORLD/VIEW boundaries are proposed architecture. Backlog/roadmap items do not instruct another agent or authorize purchases, hardware writes, participant studies, external contact or publication.
