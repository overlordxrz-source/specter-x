# Branch handoff — docs/persistent-context-protocol

- **Branch / worktree:** `docs/persistent-context-protocol` in
  `specter-x-context`.
- **Base commit:** `f2ef96b0cfe48e2e47c9d4ac02b3ac8e3376a2a2` (current main).
- **Head commit:** see the branch tip / draft PR; the source commit used for the
  generated Brief is recorded inside `docs/context/CONTEXT_BRIEF.md`.
- **Owner / task:** owner-directed Persistent Context Protocol implementation;
  no merge/hardware/purchase authorization.
- **Context receipt:** included below.
- **Scope completed:** ADR-007/008/009; central/headset/distributed compute
  clarification; generated Context Brief; Context Receipt; protected-document,
  source, ADR-ID, stale-brief and local-link checks; branch-safe handoff;
  decision-change process; Hark procurement context; context-free recovery test;
  CI context gate.
- **Canonical documents read:** AGENTS, North Star, decisions, research ideas,
  experiment ledger, hardware inventory, architecture, roadmap, engineering
  contract, agent handoff, docs hub, verification baseline, work-order template.
- **Accepted ADRs applied:** existing ADR-001..006; new accepted ADR-007
  (central/headset/distributed compute), ADR-008 (Persistent Context Protocol),
  ADR-009 (OS/WORLD ownership and capability labels).
- **Protected docs changed:** AGENTS, North Star, architecture, decisions,
  hardware inventory, roadmap, agent handoff, context truths, Hark profile.
  Their reviewed hashes are in `docs/context/protected-docs.json`.
- **Tests / controls:** full offline suite **251 passed, 1 deselected**;
  architecture **PASS**; context checks **PASS**; context protocol tests
  **6 passed**; context-free recovery test **PASS** (rejected “all AI inside the
  wearable” citing ADR-007).
- **Evidence artifacts:** `docs/context/RECOVERY_TEST.md`,
  `docs/context/CONTEXT_BRIEF.md`, protected/source manifests, CI output.
- **Known gaps / unknowns:** semantic contradictions cannot be fully checked
  automatically; no live Hark procurement evidence; no ChatGPT-without-repo
  session was run (procedure documented); independent review still pending;
  central/headset/distributed hardware remains PLANNED/VISION.
- **Rollback:** abandon this branch; main and all other branches/worktrees are
  untouched. No hardware, purchase, flash or deployment occurred.
- **Next smallest task:** independent review, then fix review findings and obtain
  owner acceptance before any merge.
- **Integration constraints:** do not merge without owner authorization; do not
  treat the Brief, this handoff or a passing hash check as capability evidence.

## Context Receipt

```text
Context Receipt
- Agent/session: OpenCode, current task
- Task / owner request: implement Persistent Context Protocol and draft PR
- Authorization limit: docs/tooling only; no merge/hardware/purchase
- Repository commit reviewed: f2ef96b (base); branch uncommitted until commit
- Context Brief generated commit / source hashes: generated on this branch
- Canonical sources read: AGENTS, North Star, architecture, engineering
  contract, decisions, research ideas, experiment ledger, verification baseline,
  hardware inventory, roadmap, agent handoff, docs hub, work order
- Active accepted ADRs applied: ADR-001..009
- Protected documents expected to change: AGENTS, North Star, architecture,
  decisions, hardware inventory, roadmap, agent handoff, context truths, Hark
- Branch / worktree ownership: docs/persistent-context-protocol; no other branch
- Contradictions found: no existing ADR contradicted by ADR-007/008/009; prior
  language was ambiguous about central compute and required explicit clarification
- Unknowns / unverifiable claims: central/headset hardware, Hark quotes,
  no-repo ChatGPT behavior, semantic completeness
- Tests / adversarial controls planned: full suite, architecture, context
  checker, ADR/protected/link tests, context-free adversarial recovery prompt
- Rollback or stop condition: abandon branch; stop on semantic contradiction or
  owner decision conflict
- Decision-change required? none (clarifying/additive ADRs; no supersession)
```
