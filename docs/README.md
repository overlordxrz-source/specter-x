# SPECTER-X documentation hub

**Edition 3 · 22 October 2026 · Alpha snapshot `933e856` · hardware preflight passed.**

**Start with the [Canonical Vision and Long-Term Project Charter](handbook/north-star.md).** It is the authoritative North Star for identity, goals and engineering doctrine; this hub and the detailed chapters support it. Read the [Alpha reconciliation](handbook/alpha-95eae17-review.md) for the `95eae17` engineering status, and the [verification baseline](handbook/verification-baseline.md) for what has since been measured on real hardware.

SPECTER-X is the first wearable/AR interface to a vertically integrated, multimodal spatial-intelligence ecosystem: SPECTER-OS, persistent SPECTER-WORLD, future AIR / GROUND / ORBIT integration and experimental SPECTER-BIO. The “God’s Eye” aspiration means combining complementary observations while showing blind spots, uncertainty and age. It does not mean universal visibility, identification through walls, medical diagnosis or certified rescue capability.

**What exists:** a Python application, provenance-bearing measurements, HUD and simulated team pipeline; recorded DI-188 streaming and real ESP32-S3 CSI host integration. **What has been measured on hardware:** the ESP32-S3 CSI firmware was written to a real board and passed a 60-second acquisition preflight — 2364 frames, 39.0/s, longest gap 79 ms, subcarrier nulls clean in 2364/2364 frames, zero malformed lines, zero sequence gaps, zero queue drops. **What remains unverified:** calibrated analog signals, integrated field hardware, motion or vital-sign detection, sustained unattended reliability, and any claim of performance superiority. Code presence, a passing preflight, simulated output and a physical measurement remain separate milestones, and a passing preflight is an acquisition result — not a sensing result.

## Start here

| Reader / question | Document |
|---|---|
| Canonical identity, doctrine and five-plus-year ambition | [North Star charter](handbook/north-star.md) |
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

The charter governs project intent; dated evidence governs capability claims. The handbook is the reconciled entry point. Existing [checkpoint records](handbook/verification-baseline.md) and [earlier design notes](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/esp32-firmware-integration.md) remain historical evidence; disagreements and overstated claims are called out rather than erased. The repository root README is older and contains capability language that should be read with these qualifications.

## Working rules

Keep raw observations, derived features and inferred world state distinguishable. Preserve source IDs through fusion. Show offline, stale, floating, simulated and uncalibrated states. Record failures and exclusions. Change hardware status only with a dated source. Review firmware separately from documentation; this edition authorizes no flashing, deployment, merge, purchases or external contact.

See [maintenance and handoff](handbook/handoff.md) for the exact files, snapshot and update procedure.
