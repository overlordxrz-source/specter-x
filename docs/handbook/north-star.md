# SPECTER-X — Canonical Vision and Long-Term Project Charter

[Documentation hub](../README.md) · **Canonical project intent · adopted 22 October 2026 · charter v1.**

This document is the authoritative reference for SPECTER-X's identity, ambitions and engineering doctrine. Detailed handbook chapters implement it; evidence records establish current capability. The owner’s explicit project decisions govern changes to this charter. An older README, checkpoint, prototype or agent summary does not silently redefine the project.

## Central vision

**SPECTER-X is the first interface to a vertically integrated, multimodal spatial-intelligence ecosystem.** Its initial wearable experience combines sensing, skeletal perception and AR with a shared software/device foundation and a persistent understanding of space. Its identity extends beyond a helmet or any single enclosure.

Our long-term **God’s Eye** concept is a coherent, shared, historical picture assembled from complementary observations. Real physics, measurable performance, missing coverage and explicit uncertainty govern every representation. More sensors or more convincing graphics cannot substitute for evidence.

## The ecosystem we intend to build

| Name | Foundational ambition | Boundary |
|---|---|---|
| **SPECTER-X** | Multispectral wearable and AR interface: optical/NIR, thermal, radar, Wi-Fi CSI, LiDAR, positioning and skeletal perception | These are target modalities and capabilities; not all are acquired, integrated or validated |
| **SPECTER-OS** | Unified software/device ecosystem: firmware, drivers, protocols, scheduling, health, calibration, logging and optimized communication | An ecosystem architecture; no standalone kernel or complete operating system is claimed |
| **SPECTER-WORLD** | Persistent 3D spatial intelligence: semantic maps, fusion, uncertainty, observation history and shared world models | A track list or rendered scene alone is not this persistent model |
| **SPECTER-AIR / GROUND / ORBIT** | Future aerial and terrestrial nodes, satellite-data integration and resilient communications | ORBIT begins with existing data/services; a custom satellite is a separate possible program |
| **SPECTER-BIO** | Experimental non-contact physiology, radar vital signs and eventual university-level quantum-sensing research | Laboratory research with independent references; no medical or remote life-detection capability established |

**Compute topology clarification (owner-directed, 24 October 2026).**
SPECTER-X's wearable form factor is an **AR headset-style interface**, not a
complete self-contained compute system. Primary high-performance compute may
reside in centralized command infrastructure, including workstation/server
GPUs or Jetson AGX Thor-class hardware. Central computing supports
cross-platform AI, persistent spatial intelligence, coordination and
historical analysis. SPECTER-X, SPECTER-AIR and SPECTER-GROUND are distributed
participants in the wider ecosystem. The headset is the user-interface tier and
also a distributed participant for local safety; other distributed nodes retain
the necessary low-latency processing and independent safety functions. This is accepted
design intent, not a claim that every subsystem exists. See
[ADR-007](decisions.md), [architecture](architecture.md) and the
[Hark procurement context](../procurement/HARK_CONTEXT.md).

CORE, NODE, SENSE, LINK, FUSION and VIEW remain the [technical architecture](architecture.md) boundaries that serve this ecosystem. SPECTER-OS coordinates the software/device foundation; WORLD owns spatial state and history; X is the wearable experience, with future platforms consuming the same evidence contracts. CORE is the runtime and, PLANNED, the edge-AI and mission-coordination hub that assembles validated observations into WORLD, publishes evidence summaries to wearables and issues only authorized, auditable task updates to autonomous platforms. A task update is never inferred automatically from a single sensor observation, and onboard safety remains local.

## Engineering doctrine

1. **Trace every claim.** Every observation, track, skeletal joint and rendered inference carries evidence lineage, source, acquisition time, coordinate frame, algorithm/model and calibration validity. Missing evidence stays explicit.
2. **Keep epistemic states distinct.** Measured, inferred, predicted, simulated and unknown remain distinguishable through fusion, networking, storage and display. A measured image can support an inferred joint; that joint is not a directly measured 3D location without the appropriate evidence.
3. **Verify reproducibly.** Every major capability requires a frozen task/protocol, independent reference, negative controls, raw-to-result provenance and repeatable evaluation. Compilation, tests, simulation and hardware validation are different milestones.
4. **Integrate vertically for measured benefit.** Own interfaces, diagnostics and integration. Reuse vendor primitives when justified; develop custom firmware, drivers, protocols or scheduling when comparative measurements warrant the cost and risk. First-party does not automatically mean closed-source, fully custom or faster.
5. **Expose uncertainty and failure.** Preserve timing/calibration uncertainty, shared evidence dependencies, stale predictions, blind spots and disagreement. Absence of detection is not proof of absence.
6. **Keep research consent-based and claims bounded.** Protect participant/location/physiology data, respect site/network permissions and separate research prototypes from medical or life-safety assurances.

## Current maturity and next priorities

The [evidence baseline](verification-baseline.md) records real DI-188 streaming and ESP32-S3 CSI host integration, with floating/uncalibrated analog inputs and unresolved acquisition limitations. The software includes a HUD, provenance structures and simulated paths. A complete wearable, calibrated multimodal world model, validated human detection and physiological sensing are not established.

The [Alpha `95eae17` reconciliation](alpha-95eae17-review.md) records committed synthetic sweep evidence and new controlled-link firmware source. Since that record, the Alpha firmware was written to a real board and passed a **60-second CSI acquisition preflight** at `933e856` — see the [verification baseline](verification-baseline.md). That is a hardware-validated **acquisition** result only. It does not establish motion or vital-sign detection, sustained unattended reliability, or performance superiority; the software test suite stands at 287 passing, 1 skipped. The Alpha work remains on `feature/alpha002-esp32-supervisor` and is not merged into `main`.

Immediate priorities: reconcile actual hardware receipts; review the Alpha candidate; establish safe analog references and an owned CSI link; validate clocks, calibration and record integrity; then compare a small calibrated fusion rig against single-sensor baselines. [Backlog](backlog.md), [validation](validation.md) and [inventory](hardware-inventory.md) define the work and dependencies.

## Five-plus-year ambition

Over successive verified stages, progress from a dependable bench instrument to calibrated portable sensing, multispectral skeletal/AR interaction, persistent semantic WORLD models and cooperative nodes. Explore AIR/GROUND mobility and ORBIT data/resilient links when pose, timing, power and communications support them. Develop BIO through phantoms, reference instruments and university laboratory collaboration before any physiological claim. Five-plus years is a research horizon, not a delivery guarantee or a ceiling on ambition.

Proposed additions include NIR-compatible optics/illumination, depth/stereo, LiDAR, additional controlled CSI endpoints, positioning anchors, calibration fixtures and eventually suitable physiological/magnetic laboratory instrumentation. Selection follows observability, safety, power, compute, mechanical and measurable task benefit; no purchase or receipt is implied.

University work can establish methods, datasets and reproducible results. A later startup can develop a narrow validated application when demand, ownership, licensing, manufacturing and support justify it. No partnership, patent, funding or commercialization outcome is assumed. See [roadmap](roadmap.md), [research](research-program.md), [constraints](constraints.md) and [commercialization](commercialization.md).

## Instructions for future engineering work

Read this charter, the hub, Alpha reconciliation, relevant ICD and evidence before changing behavior. Preserve feature branches and working files. Do not reduce the ecosystem vision to the current prototype or promote aspirations into achievements. Record a proposed design separately from a measured result. Change this charter only to reflect an explicit owner decision, with a dated rationale; routine implementation work cannot redefine it. This charter grants no permission to merge, push, flash, deploy or publish.

**Persistent memory (owner-directed, 23 October 2026).** After this charter,
read the [research ideas](research-ideas.md),
[decisions](decisions.md),
[experiment ledger](experiment-ledger.md) and
[current agent handoff](agent-handoff.md). This is the canonical startup
reference for every future agent, including ChatGPT, OpenCode, Work and other
coding agents. Update those files at checkpoints and before context
compaction. They index and constrain work; they do not replace raw evidence,
and a memory entry never promotes a capability by itself.
