# Accepted context truths — derived digest

**Derived context, not evidence.** This page is a compact digest for recovery. **ADR-007 is normative for the
compute topology**; this digest is an index, not a second decision source.
Canonical intent remains the [North Star](../handbook/north-star.md), decisions
[ADR log](../handbook/decisions.md), evidence
[experiment ledger](../handbook/experiment-ledger.md) and current
[agent handoff](../handbook/agent-handoff.md). If this page and a canonical
source disagree, stop and produce a Context Receipt; do not silently choose one.

## Architecture

- **SPECTER-X is an AR headset-style interface, not a complete self-contained
  compute system.** High-performance AI training/inference, persistent WORLD
  history, cross-platform coordination and historical analysis may run on
  **central command infrastructure**: workstation/server GPUs or Jetson AGX
  Thor-class hardware. See [ADR-007](../handbook/decisions.md).
- **SPECTER-X, SPECTER-AIR and SPECTER-GROUND are distributed participants** in
  the wider ecosystem. The headset is also the user-interface tier, not the
  central compute tier. Local nodes retain low-latency processing and
  independent safety; central-link loss must not remove local safety.
- **SPECTER-WORLD is an evidence-grounded persistent spatial-intelligence
  system**, not merely a visualization application. Semantic state, uncertainty,
  history and provenance belong to WORLD; VIEW is a client of WORLD.
- **SPECTER-OS coordinates the software/device ecosystem** without claiming a
  complete kernel or shipped operating system. CORE, NODE, SENSE, LINK, FUSION
  and VIEW retain their documented responsibilities. See
  [ADR-009](../handbook/decisions.md) and [architecture](../handbook/architecture.md).
- **SPECTER-ORBIT, SPECTER-BIO, advanced AI and future sensing** remain
  long-term VISION/RESEARCH directions. They are not current capabilities.
- Procurement is context-bound: central command, headset and distributed nodes
  are distinct tiers; see [Hark procurement context](../procurement/HARK_CONTEXT.md).

## Capability status (source-bound; no promotion here)

- **ESP32-S3 CSI acquisition:** a recorded 60-second acquisition preflight
  passed at the Alpha snapshot. That is acquisition evidence only, not motion,
  presence, vital-sign or calibration validation. See the
  [verification baseline](../handbook/verification-baseline.md) and
  [experiment ledger](../handbook/experiment-ledger.md).
- **Alpha 002-C:** **IN PROGRESS — exploratory positive, independent replication
  pending.** Not confirmatory or general motion detection.
- **Alpha 003:** **PLANNED — offline protocol/code and software rehearsal
  complete; no human session.**
- **FRONTIER-001 / WORLD desktop:** offline observation/replay and inspection
  integrated; 7,290-record real-CSI replay recorded. Persistent live WORLD
  streaming, semantic mapping and calibrated spatial fusion are not validated.
- **SPECTER-OS / CORE mission hub:** architectural intent and partial software;
  no complete independent OS, mission hub or control service.
- **Central command, AR headset and distributed compute:** accepted design
  intent; procurement/implementation status is **PLANNED / VISION**, not
  possession or deployment.
- **AIR / GROUND / ORBIT / BIO:** long-term roadmap; no flight, satellite,
  medical or physiological capability established.
- **Hardware:** receipt and readiness are exactly what the
  [inventory](../handbook/hardware-inventory.md) says; a plan, price, datasheet
  or demo is not a receipt.

## Epistemic rules

Keep **measured, inferred, predicted, simulated, unverified and unknown**
independent. A measured image can support an inferred joint, but the joint is not
a measured 3D location. A high-confidence classifier does not create range,
bearing, depth or identity. A simulated result is not hardware validation. A
track list, rendered scene or UI demo is not a persistent world model. Missing
data stays unknown.

## Change control

- The repository is canonical; chat history, this digest and the generated
  Context Brief are indexes, not new evidence.
- A proposal contradicting an accepted ADR must identify the ADR, justify
  supersession, state evidence/alternatives and obtain owner approval before
  adoption. See [decision change](../context/DECISION_CHANGE.md).
- Feature branches use branch-safe handoffs and do not routinely edit the
  canonical main handoff. See [branch handoff template](../context/BRANCH_HANDOFF_TEMPLATE.md).
- Protected architectural documents are hash-checked; automation cannot detect
  semantic contradictions. See [automation limits](../context/AUTOMATION_LIMITS.md).
- Every material task starts with a **Context Receipt** naming the commit,
  sources, ADRs, contradictions and unknowns. See
  [Context Protocol](../context/README.md).

## Recovery

A new agent with no conversation history should read the generated
[Context Brief](../context/CONTEXT_BRIEF.md), verify its source commit/hashes,
then open the canonical links for the task. A ChatGPT session without repository
access must request the current Brief and commit from the owner and label its
knowledge unverified. See [ChatGPT recovery](../context/CHATGPT_RECOVERY.md).
