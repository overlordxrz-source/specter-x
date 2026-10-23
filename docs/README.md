# SPECTER-X documentation hub

**FRONTIER-001 and SPECTER-WORLD integration:** [FRONTIER-001](frontier001/README.md) and [SPECTER-WORLD desktop](world/README.md) · [integration and verification](world/integration.md). These are offline software/replay milestones, not new sensing claims. Canonical project memory below remains authoritative.

**Edition 3 · 22 October 2026 · Alpha snapshot `933e856` · hardware preflight passed.**

**Edition 4 memory note · 23 October 2026.** Persistent project memory now
lives in the repository. Start with the [North Star](handbook/north-star.md),
then the [research ideas](handbook/research-ideas.md),
[decisions](handbook/decisions.md),
[experiment ledger](handbook/experiment-ledger.md) and
[current agent handoff](handbook/agent-handoff.md). This is a
documentation-only update: no code, firmware or experiment was merged.

Since the Edition 3 snapshot, Alpha 002-C produced an **exploratory**
hand-motion vs stationary result (one 20-trial session, p = 1/1024,
d_z = 1.69, CI [1.34, 2.91]); it is **not confirmatory** and independent
replication is pending. Alpha 003 presence is **PLANNED / offline only**; no
human session exists. See the [experiment ledger](handbook/experiment-ledger.md)
and [checkpoint 023](https://github.com/overlordxrz-source/specter-x/blob/a3c540d/docs/checkpoints/023-alpha002c-forensic-validation.md).


**Start with the [Canonical Vision and Long-Term Project Charter](handbook/north-star.md).** It is the authoritative North Star for identity, goals and engineering doctrine; this hub and the detailed chapters support it. Read the [Alpha reconciliation](handbook/alpha-95eae17-review.md) for the `95eae17` engineering status, and the [verification baseline](handbook/verification-baseline.md) for what has since been measured on real hardware.

SPECTER-X is the first wearable/AR interface to a vertically integrated, multimodal spatial-intelligence ecosystem: SPECTER-OS, persistent SPECTER-WORLD, future AIR / GROUND / ORBIT integration and experimental SPECTER-BIO. The “God’s Eye” aspiration means combining complementary observations while showing blind spots, uncertainty and age. It does not mean universal visibility, identification through walls, medical diagnosis or certified rescue capability.

**What exists:** a Python application, provenance-bearing measurements, HUD and simulated team pipeline; recorded DI-188 streaming and real ESP32-S3 CSI host integration. **What has been measured on hardware:** the ESP32-S3 CSI firmware was written to a real board and passed a 60-second acquisition preflight — 2364 frames, 39.0/s, longest gap 79 ms, subcarrier nulls clean in 2364/2364 frames, zero malformed lines, zero sequence gaps, zero queue drops. **What remains unverified:** calibrated analog signals, integrated field hardware, motion or vital-sign detection, sustained unattended reliability, and any claim of performance superiority. Code presence, a passing preflight, simulated output and a physical measurement remain separate milestones, and a passing preflight is an acquisition result — not a sensing result.

## Persistent project memory

**This is the canonical startup reference for every future agent — ChatGPT,
OpenCode, Work and any other coding agent.** Read these before starting
major work; the repository is canonical, not chat history.

1. [North Star charter](handbook/north-star.md) — stable intent and doctrine.
2. [Research ideas](handbook/research-ideas.md) — dated VISION/RESEARCH log.
3. [Architectural decisions](handbook/decisions.md) — accepted/proposed ADRs.
4. [Experiment ledger](handbook/experiment-ledger.md) — current gates and evidence links.
5. [Current agent handoff](handbook/agent-handoff.md) — branch, owner, blockers, next task.

The [documentation handoff](handbook/handoff.md) remains the historical
record of how the handbook was built. Update memory when a distinctive idea,
decision or experiment finding appears, at checkpoints, and before context
compaction. Memory entries are not evidence; open the linked artifact.

## Start here

| Reader / question | Document |
|---|---|
| What should every new agent read first? | [Persistent memory](#persistent-project-memory) |
| Canonical identity, doctrine and five-plus-year ambition | [North Star charter](handbook/north-star.md) |
| Dated research ideas and their status | [Research ideas log](handbook/research-ideas.md) |
| Why an architectural/evidence boundary exists | [Decision record](handbook/decisions.md) |
| What is the latest experiment gate? | [Experiment ledger](handbook/experiment-ledger.md) |
| What is the current branch and next task? | [Agent handoff](handbook/agent-handoff.md) |
| What changed in Alpha `95eae17`? | [Evidence and compatibility reconciliation](handbook/alpha-95eae17-review.md) |
| What has been measured on real hardware? | [Verification baseline — Alpha 002 through `933e856`](handbook/verification-baseline.md) |
| What are we building and why? | [Vision, scope and principles](handbook/vision.md) |
| What hardware do we actually have? | [Inventory and readiness ledger](handbook/hardware-inventory.md) |
| Who might supply equipment? What was sponsored? | [Supplier leads and sponsorship evidence](handbook/suppliers.md) |
| How do CORE / NODE / SENSE / LINK / FUSION / WORLD / VIEW fit? | [Architecture and data flow](handbook/architecture.md) |
| What does an observation mean? | [Provenance, clocks, calibration and uncertainty](handbook/data-contracts.md) |
| What runs, and what was measured? | [Software and hardware evidence baseline](handbook/verification-baseline.md) |
| Should we write our own firmware? | [First-party ESP-IDF strategy](handbook/firmware-strategy.md) |
| What must a component implement? | [Interface control document](handbook/interfaces.md) |
| What should engineering do next? | [Prioritized backlog](handbook/backlog.md) |
| What happens in 30 days, 90 days, a year and beyond? | [Gated roadmap](handbook/roadmap.md) |
| How can each modality help, and where does it fail? | [Sensor and fusion research program](handbook/research-program.md) |
| How will we establish results? | [Experiments, benchmarks, simulation and replay](handbook/validation.md) |
| What about batteries, enclosures and safe research? | [Physical constraints, safety and privacy](handbook/constraints.md) |
| How do AIR / GROUND / satellite layers fit? | [Future platforms, data and communications](handbook/platforms.md) |
| University research, business and ownership? | [Research, commercialization and licensing](handbook/commercialization.md) |
| Which sources support which statements? | [Evidence register and external references](handbook/sources.md) |
| What was inspected and changed in this handoff? | [Documentation handoff and access gaps](handbook/handoff.md) |

## Evidence states through the whole pipeline

Measured, inferred, predicted, simulated and unknown describe what a value represents. These states apply per observation, joint, track and rendered inference, independently of implementation/build readiness. Preserve them across storage, fusion and communication; do not use a single confidence score as a substitute.

## Read the evidence labels literally

- **RECORDED HARDWARE:** a repository artifact or checkpoint reports a real-device run. This documentation task did not rerun hardware.
- **IMPLEMENTED:** source exists at the baseline; this is not a statement that hardware works or that every code path was audited.
- **SIMULATED:** synthetic inputs or fixtures; validates a model or pipeline under specified assumptions.
- **REPORTED:** a person or prior agent asserted it; independent evidence may be missing.
- **PROPOSED:** an engineering design, acceptance requirement or planned experiment.
- **SPECULATIVE:** a research direction without demonstrated SPECTER-X capability.
- **UNKNOWN / BLOCKED:** source, physical access or evidence is missing. Unknown is never silently converted to “shipped” or “working.”

## Status vocabulary for new and edited pages

New or edited statements use these five labels. Older pages keep their existing
labels; this table maps them.

| Label | Meaning in this repository |
|---|---|
| **VISION** | Long-term intent. No implementation, hardware or experiment exists for the claim. |
| **RESEARCH** | An open question or feasibility track. It may produce a negative result. |
| **PLANNED** | A specified design, experiment or integration that has not started. |
| **IN PROGRESS** | Work exists and is partially evidenced; it is not yet validated. |
| **VALIDATED** | A recorded hardware or experimental result supports the specific claim, with an artifact and a stated boundary. |

Mapping: RECORDED HARDWARE → VALIDATED for the measured scope only;
IMPLEMENTED → IN PROGRESS; PROPOSED → PLANNED; SPECULATIVE → VISION or
RESEARCH. SIMULATED is never a hardware or experimental validation.

The charter governs project intent; dated evidence governs capability claims. The handbook is the reconciled entry point. Existing [checkpoint records](handbook/verification-baseline.md) and [earlier design notes](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/esp32-firmware-integration.md) remain historical evidence; disagreements and overstated claims are called out rather than erased. The repository root README is older and contains capability language that should be read with these qualifications.

## Working rules

Keep raw observations, derived features and inferred world state distinguishable. Preserve source IDs through fusion. Show offline, stale, floating, simulated and uncalibrated states. Record failures and exclusions. Change hardware status only with a dated source. Review firmware separately from documentation; this edition authorizes no flashing, deployment, merge, purchases or external contact.

Use the five labels literally. Record distinctive ideas in the
[research log](handbook/research-ideas.md), architectural choices in the
[decision record](handbook/decisions.md), experiment gates in the
[ledger](handbook/experiment-ledger.md) and the current state in the
[agent handoff](handbook/agent-handoff.md). Do this at checkpoints and before
context compaction. A higher confidence score is not new spatial
information; missing observations remain unknown.

See [maintenance and handoff](handbook/handoff.md) for the exact files, snapshot and update procedure.
