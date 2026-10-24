# Architectural decision record

[Hub](../README.md) · **Decision log · started 23 October 2026.**

This is the lightweight ADR index for choices that affect SPECTER-X's
architecture, evidence claims or agent continuity. It records **why** a
boundary exists; detailed contracts remain in [architecture](architecture.md),
[data contracts](data-contracts.md) and [interfaces](interfaces.md).

Statuses: **proposed**, **accepted**, **superseded**. A superseded decision
stays in the record with a link to its replacement.

---

## ADR-001 — Canonical memory is in the repository

**Status:** accepted · 23 October 2026
**Context:** Agents and long sessions lose context; chat history is not a
reliable project record.
**Decision:** The repository is canonical. Maintain five memory surfaces:
North Star, research-ideas log, this ADR log, experiment ledger and current
agent handoff. Update them at checkpoints, before context compaction and
when an idea/decision/evidence gate changes.
**Consequences:** A future agent can reconstruct the project state from
versioned files. Memory entries are not evidence; they must link to
artifacts. Routine chat is not logged.
**Links:** [research ideas](research-ideas.md), [experiment ledger](experiment-ledger.md),
[agent handoff](agent-handoff.md).

## ADR-002 — Fusion preserves provenance, uncertainty and shared evidence

**Status:** accepted · 23 October 2026
**Context:** Multimodal fusion can improve coverage, but it can also hide
blind spots or double-count correlated observations.
**Decision:** Every fused value retains contributing observation IDs,
source, acquisition clock, coordinate frame, calibration validity, age,
uncertainty and alternatives. WORLD may retain conflicting hypotheses.
Fusion must not convert a weak or missing observation into a measured one.
**Consequences:** Fusion is a consumer of validated observations, not a
shortcut around them. Peer reports of the same raw observation are not
independent evidence. Unknown space remains unknown.
**Links:** [architecture — evidence plane](architecture.md#evidence-plane-and-control-plane),
[data contracts](data-contracts.md).

## ADR-003 — Confidence is not new spatial information

**Status:** accepted · 23 October 2026
**Context:** The symbolic complementary-observation example can be
misread as “confidence fills gaps.” A confident CSI channel-change result is
still not a 3-D location.
**Decision:** A confidence score is only a calibrated score over the task
the sensor/model measured. It does not add range, bearing, depth, identity
or occupancy. Cross-modal complementarity requires independent observables,
calibration, time alignment and association. Correlated sensors require a
shared-evidence model, not naive Bayesian multiplication. Missing values
stay unknown; no forced completion of the illustrative `1..10` row.
**Consequences:** A high-confidence single-link CSI detection cannot be
reported as a localized person. Radar range, thermal radiance and CSI
channel change remain distinct observables until a validated association
model exists.
**Links:** [research ideas — complementary observations](research-ideas.md#complementary-partial-observations).

## ADR-004 — Learned fusion must beat calibrated baselines

**Status:** accepted research policy · 23 October 2026
**Context:** Cross-attention and learned world models are attractive but can
overfit, leak adjacent windows or hide missing-modality failures.
**Decision:** Learned fusion is **RESEARCH**, not a default architecture. It
must be compared with calibrated Bayesian/factor-graph/late-fusion and
single-sensor baselines, use held-out sessions/people/sites, include
missing/stale/degraded channels and report abstention and wrong-high-confidence
cases. Attention is an architecture family, not evidence.
**Consequences:** A fusion project starts with two validated modalities and
a modest defined task. A learned model that does not beat a simple calibrated
baseline is a negative result, not a capability.
**Links:** [research program — fusion sequence](research-program.md#fusion-sequence),
[validation](validation.md).

## ADR-005 — Capability promotion requires frozen evidence

**Status:** accepted · 23 October 2026
**Context:** A single exploratory session or a software demo can be
mistaken for a validated capability.
**Decision:** A claim moves toward **VALIDATED** only with a frozen protocol,
recorded raw evidence, honest exclusions, independent replication where the
claim generalises, and a stated boundary. Exploratory, simulated and
acquisition-only results keep their labels. Historical results are amended
by dated notes, never rewritten.
**Consequences:** Alpha 002-C remains **IN PROGRESS — exploratory positive,
replication pending**. Alpha 003 is **PLANNED**. No presence, occupancy,
respiration or localization claim follows from the offline Alpha 003 code.
**Links:** [experiment ledger](experiment-ledger.md),
[Alpha 002-C forensic record](https://github.com/overlordxrz-source/specter-x/blob/a3c540d/docs/checkpoints/023-alpha002c-forensic-validation.md).

## ADR-006 — Agent startup and update ritual

**Status:** accepted · 23 October 2026
**Context:** Parallel worktrees and long-running experiments make stale
handoffs dangerous.
**Decision:** Every future agent reads, in order: North Star → relevant
research ideas → relevant ADRs → latest experiment ledger entry → current
agent handoff. Then inspect actual `git status` and worktrees before acting.
Update memory at checkpoints and before compaction. Do not merge, flash or
start human experiments without explicit authorization.
**Consequences:** Handoffs are short and link to evidence. A memory entry
that conflicts with a raw artifact is corrected by a dated note.
**Links:** [agent handoff](agent-handoff.md), [North Star](north-star.md).


## ADR-007 — Wearable AR interface with centralized and distributed compute

**Status:** accepted · 24 October 2026 · owner-directed design intent; implementation draft under review
**Owner directive:** The 24 October 2026 task requires the AR-headset/central-command/distributed-node architecture and rejects the assumption that all AI compute must fit in the wearable. This ADR records that accepted design intent; it does not claim deployment.
**Context:** Earlier architecture and roadmap language allowed the wearable to
be read as a complete self-contained compute system. That conflicts with the
intended AR-headset experience, high-performance central AI, and distributed
nodes with local safety.
**Decision:** **SPECTER-X is an AR headset-style interface, not a complete
self-contained compute system.** Primary high-performance compute may reside
in centralized command infrastructure, including workstation/server GPUs or
Jetson AGX Thor-class hardware. Central compute supports cross-platform AI,
persistent spatial intelligence, coordination and historical analysis.
SPECTER-X, SPECTER-AIR and SPECTER-GROUND are distributed participants in the
wider ecosystem; the headset is also the user-interface tier, not the central
compute tier. Distributed nodes retain the low-latency processing and
independent safety functions needed when central links are absent, degraded or
unauthorized.
**Consequences:** Architecture and procurement must not require all AI compute
to fit in the headset. Headset power, thermal, display, sensor and local-safety
constraints remain separate from central training/inference capacity. A network
outage cannot remove a local safety function. This is accepted design intent,
not evidence that central command, the headset or distributed nodes are built.
**Links:** [North Star](north-star.md), [architecture](architecture.md),
[roadmap](roadmap.md), [Hark procurement context](../procurement/HARK_CONTEXT.md).

## ADR-008 — Persistent Context Protocol

**Status:** accepted · 24 October 2026 · owner-directed design intent; implementation draft under review
**Owner directive:** The 24 October 2026 task requires a task-specific context preflight, repository-recoverable brief, receipt, protected-document checks, decision-change process and branch-safe handoffs. This ADR records the accepted governance intent; implementation remains a draft under review.
**Context:** ChatGPT, OpenCode, Work, Hark and future agents can drift when
chat history, stale handoffs or partial repository reads become the effective
source of truth.
**Decision:** Every material task starts from a task-specific context preflight
and produces a Context Receipt naming the authoritative commit, sources,
active ADRs, contradictions and unknowns. A generated Context Brief provides a
compact recovery surface. Protected architectural documents are hash-checked.
Proposals contradicting an accepted ADR must use the decision-change process
and obtain owner approval before adoption. Feature agents use branch-safe
handoffs and do not routinely edit the canonical main handoff.
**Consequences:** The repository remains canonical; the Brief and Receipt are
indexes, not new evidence. Automation checks references, hashes, decision IDs
and stale generated context; it cannot detect semantic contradictions. Human
or independent-agent review remains required for meaning, scope and owner
intent.
**Links:** [Context Protocol](../context/README.md),
[Context Brief](../context/CONTEXT_BRIEF.md),
[automation limits](../context/AUTOMATION_LIMITS.md).

## ADR-009 — OS/WORLD ownership and capability-label separation

**Status:** accepted · 24 October 2026 · owner-directed design intent; implementation draft under review
**Owner directive:** The 24 October 2026 task requires WORLD to be an evidence-grounded persistent spatial-intelligence system, OS to coordinate the ecosystem, and capability labels to remain distinct. This ADR records that accepted design intent; it does not claim a shipped OS or persistent world model.
**Context:** The ecosystem can be misread as a visualization product with a
miscellaneous collection of sensors, or as an operating system that already
exists.
**Decision:** **SPECTER-OS coordinates the software/device ecosystem** without
claiming a complete kernel or shipped OS. **SPECTER-WORLD is an evidence-grounded
persistent spatial-intelligence system**, not merely a visualization
application; VIEW is a client of WORLD, not a substitute for it. CORE, NODE,
SENSE, LINK, FUSION and VIEW retain their documented responsibilities.
Measured, inferred, predicted, simulated, unverified and unknown states are
independent and must never be conflated. SPECTER-ORBIT, SPECTER-BIO, advanced
AI and future sensing research remain in the long-term roadmap as VISION or
RESEARCH until evidenced.
**Consequences:** A track list, rendered scene or demo does not establish a
persistent world model. An OS-shaped document does not establish a kernel. A
high-confidence inference does not become a measurement. Capability promotion
remains governed by ADR-002/ADR-005 and the experiment ledger.
**Links:** [North Star](north-star.md), [architecture](architecture.md),
[research ideas](research-ideas.md), [experiment ledger](experiment-ledger.md).

---

## Adding a decision

Use the next ADR number. Include status, date, context, decision,
consequences and links. If a decision is reversed, mark it **superseded**
and add the replacement; do not delete the old entry.
