# Persistent Context Protocol

**Status: accepted governance process, 24 October 2026.**
This directory makes repository-only recovery and cross-agent continuity
explicit. It does **not** become a new source of evidence, capability or
authority. Canonical intent and evidence remain the linked handbook documents.

## Why

ChatGPT, OpenCode, Work, Hark and future agents do not share conversation
history. A stale handoff, an older README or a plausible summary can silently
replace an accepted architecture. This protocol requires every material task to
name the authoritative revisions it used and to surface contradictions before
changing direction.

## Canonical order

0. Generated [Context Brief](CONTEXT_BRIEF.md) — compact recovery index. Read it
   first, then open the sources relevant to the task.
1. [North Star charter](../handbook/north-star.md) — identity, compute topology,
   doctrine and long-term scope.
2. Relevant [research ideas](../handbook/research-ideas.md).
3. Relevant accepted/proposed [ADRs](../handbook/decisions.md).
4. Current [experiment ledger](../handbook/experiment-ledger.md) and
   [verification baseline](../handbook/verification-baseline.md).
5. Current [agent handoff](../handbook/agent-handoff.md), interpreted with the
   branch-safe rule below.
6. Relevant [architecture](../handbook/architecture.md),
   [engineering contract](../architecture/ENGINEERING_CONTRACT.md),
   [hardware inventory](../handbook/hardware-inventory.md),
   [roadmap](../handbook/roadmap.md) and
   [Hark procurement context](../procurement/HARK_CONTEXT.md).

The generated [Context Brief](CONTEXT_BRIEF.md) is a compact recovery index over
these sources; it comes first for recovery but is not a replacement for them.

## Task preflight

Before materially changing architecture, research direction, procurement,
capability status or a protected document:

1. Run `python tools/check_context.py`; it must pass, or report why not.
2. Read the [Context Brief](CONTEXT_BRIEF.md) and the canonical sources relevant
   to the task. Verify the source commit and hashes; fetch the repository if the
   commit differs.
3. Fill in a [Context Receipt](CONTEXT_RECEIPT.md) in the task/PR/commit
   description: commit, sources, active ADRs, contradictions, unknowns,
   authorization and scope.
4. If a proposal contradicts an accepted ADR, stop and use the
   [decision-change process](DECISION_CHANGE.md). Owner approval is required
   before adoption.
5. Use the [branch-safe handoff template](BRANCH_HANDOFF_TEMPLATE.md). Feature
   agents do not routinely edit the canonical main handoff.
6. Report tests, gaps and protected-document changes literally.

A Context Receipt is a report, not a permission grant.

## Context Brief

Generate/check the brief from the repository root:

```sh
python tools/context_brief.py --write
python tools/context_brief.py --print
python tools/check_context.py
```

`--write` regenerates `docs/context/CONTEXT_BRIEF.md`; do not hand-edit it.
The generated brief records the source commit, protocol version, active accepted
ADRs, milestone, unresolved questions and SHA-256 hashes of every source. The
checker ignores the generation-time commit for staleness but verifies source
hashes, references, ADR IDs, protected-document hashes and Markdown links.

When a protected document intentionally changes, the owner/reviewer must approve
the semantic change and then update the protected hash manifest:

```sh
python tools/context_brief.py --update-protected
python tools/context_brief.py --write
python tools/check_context.py
```

The manifest update makes the change visible; it does not prove the change was
wise or authorized.

## Decision change

See [decision change](DECISION_CHANGE.md). No accepted ADR is silently
overridden by code, a PR, a vendor claim, a newer chat message or a generated
brief. A superseding decision must identify the old ADR, justify supersession,
record evidence/alternatives and obtain owner approval.

## Branch-safe handoff

See [branch handoff](BRANCH_HANDOFF_TEMPLATE.md). Feature branches may write a
branch-local handoff under `docs/context/handoffs/<branch-name-with-slashes-replaced-by-dashes>.md` or in the PR
description. Only an integration/owner process updates
`docs/handbook/agent-handoff.md`, so parallel agents do not create competing
canonical edits.

## Hark and procurement

[The Hark procurement context](../procurement/HARK_CONTEXT.md) separates central
command compute, the AR headset interface, distributed nodes and future sensors.
It is a question/compatibility checklist, not a bill of materials, budget,
quote, receipt or purchase authorization.

## ChatGPT / no-repository recovery

See [ChatGPT recovery](CHATGPT_RECOVERY.md). A model without repository access
must request the current Context Brief and source commit from the owner, label
unverifiable details, and avoid inventing files, hashes or capability status.

## What automation cannot do

See [automation limits](AUTOMATION_LIMITS.md). The checker catches missing
references, stale generated context, malformed/missing ADR IDs, protected-file
hash changes and broken local links. It cannot establish that a summary is
semantically faithful, that an owner approved a supersession, that a sensor is
calibrated, or that an apparently current file was not maliciously edited. A
Context Receipt and independent review remain necessary for meaning.
