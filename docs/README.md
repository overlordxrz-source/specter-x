# SPECTER-X documentation hub

**Baseline: 22 October 2026 · repository snapshot `77abdd0` · documentation edition 1.**

SPECTER-X is a modular multisensor research platform working toward a shared, evidence-backed picture of an environment. The “God’s Eye” aspiration means combining complementary observations while showing blind spots, uncertainty and age. It does not mean universal visibility, identification through walls, medical diagnosis or certified rescue capability.

**What exists:** a Python application, provenance-bearing measurements, HUD and simulated team pipeline; recorded DI-188 streaming and real ESP32-S3 CSI host integration. **What remains unverified:** calibrated analog signals, integrated field hardware, reliable controlled CSI human detection, through-obstruction inference and vital signs. Code presence, simulated output and a physical measurement are separate milestones.

## Start here

| Reader / question | Document |
|---|---|
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

## Read the evidence labels literally

- **RECORDED HARDWARE:** a repository artifact or checkpoint reports a real-device run. This documentation task did not rerun hardware.
- **IMPLEMENTED:** source exists at the baseline; this is not a statement that hardware works or that every code path was audited.
- **SIMULATED:** synthetic inputs or fixtures; validates a model or pipeline under specified assumptions.
- **REPORTED:** a person or prior agent asserted it; independent evidence may be missing.
- **PROPOSED:** an engineering design, acceptance requirement or planned experiment.
- **SPECULATIVE:** a research direction without demonstrated SPECTER-X capability.
- **UNKNOWN / BLOCKED:** source, physical access or evidence is missing. Unknown is never silently converted to “shipped” or “working.”

The handbook is the reconciled entry point. Existing [checkpoint records](handbook/verification-baseline.md) and [earlier design notes](design/esp32-firmware-integration.md) remain historical evidence; disagreements and overstated claims are called out rather than erased. The repository root README is older and contains capability language that should be read with these qualifications.

## Working rules

Keep raw observations, derived features and inferred world state distinguishable. Preserve source IDs through fusion. Show offline, stale, floating, simulated and uncalibrated states. Record failures and exclusions. Change hardware status only with a dated source. Review firmware separately from documentation; this edition authorizes no flashing, deployment, merge, purchases or external contact.

See [maintenance and handoff](handbook/handoff.md) for the exact files, snapshot and update procedure.
