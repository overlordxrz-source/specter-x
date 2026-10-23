# Gated roadmap

[Hub](../README.md) · **Planning windows start 22 October 2026; dates are targets, not commitments.**

> **Edition 3 reconciliation:** Project intent follows the [canonical charter](north-star.md). Code links below target the Alpha snapshot `933e856`; the `95eae17` [review](alpha-95eae17-review.md) remains the dated record of that earlier state. The Alpha firmware has since been flashed to real hardware and passed a CSI acquisition preflight — see the [verification baseline](verification-baseline.md). *Hardware-validated* there means the acquisition preflight passed. It does not establish motion sensing, sustained unattended reliability, or performance superiority over any alternative.

> **Edition 4 memory note (23 October 2026):** the status table below is the
> 22 October snapshot and is retained as history. Current gates:
> Alpha 002-C is **IN PROGRESS — exploratory positive, replication pending**;
> Alpha 003 is **PLANNED — offline/protocol only, no human session**;
> FRONTIER-001 is Work-owned. See the
> [experiment ledger](experiment-ledger.md) and
> [agent handoff](agent-handoff.md). No code or experiment was merged.

## Current program status (22 October 2026)

| Program | Status | Evidence / boundary |
|---|---|---|
| Alpha 002-C controlled CSI motion | **IN PROGRESS — frozen, not run** | Preregistration v2 frozen; no session or geometry record. No human trial without owner authorization. |
| FRONTIER-001 observation/replay slice | **PLANNED — preparatory** | Additive observation-contract fields only; registry, pipeline and adapters not implemented. |
| SPECTER-CORE mission coordination | **VISION** | Architecture boundary only; no hub service. |
| SPECTER-AIR fleet / SPECTER-LINK / Ferettux | **VISION / RESEARCH** | Documents only; no hardware, flight or kernel adoption. |

## First 30 days — through 21 November 2026

Goal: reproducible bench acquisition and one honest physical reference experiment.

- Reconcile actual parts status and sponsor terms; assign owners and budget.
- Review concurrent sweep/firmware work, freeze manifests and resolve interface conflicts.
- Verify DAQ analog front end, safe reference and calibration; retain floating/noise negative control.
- Establish an owned CSI traffic link with recorded geometry, mode, channel and rates.
- Quantify synthetic null behavior, sensitivity and model limitations; define real motion endpoints.
- Specify clock/record contracts and a raw-data/session manifest.

**Exit:** replayable evidence with known reference values or controlled stimulus, documented failures and clear hardware state. If key hardware or authorization is absent, complete offline work and report the blocked gate; do not substitute a simulated success.

## Days 31–90 — through 20 January 2027

Goal: a calibrated small rig and a defensible first fusion comparison.

Bring up delivered optical/thermal/range devices one at a time. Measure intrinsics/extrinsics and timing. Compare single modalities and paired fusion on held-out sessions. Run controlled CSI motion with randomized trials and useful power planning. Demonstrate degraded modes, clock steps, sensor disconnects and replay. Measure power, temperature, capture latency and logging load on the actual compute platform.

**Exit:** at least one task where fusion improves a prespecified metric over the best single sensor without hiding abstentions or missing data; otherwise publish an internal negative result and revise the model. Portability requires separate battery/mechanical evidence.

## Months 4–12 — through 22 October 2027

Goal: a repeatable research platform across units, sessions and environments.

Develop calibrated portable nodes if budgets permit. Evaluate GNSS/UWB/IMU pose with ground truth and NLOS failures; complete secure peer transport before sensitive shared experiments. Build WORLD history and uncertainty-aware maps. Compare camera/depth skeleton estimation to independently referenced metric geometry. Benchmark acceleration on the real workload, including power and accuracy. Add controlled respiration only after reference instrumentation, motion phantoms and review gates pass.

**Exit:** multiple independently repeated datasets, reproducible assembly/calibration, a release manifest, documented license state and a university research report or publication candidate with honest negative results. No guaranteed paper acceptance, sponsor funding or product certification is implied.

## Years 2–3

Conditional directions: richer optical/depth/thermal/radar fusion, distributed geometry, purpose-built carrier/enclosure, robust multi-node networking, and limited GROUND experiments. Add AIR fleet roles (fixed-wing scout, multirotor, thermal overwatch, mapping, relay) only after navigation, vibration, link and operational constraints are addressed; see [platforms](platforms.md). Through-obstruction research stays material-specific, with opaque-wall controls and held-out layouts. Investigate whether affordable hardware tiers can share the same contracts while exposing different uncertainty and coverage.

**Exit:** task-specific repeatability across unseen rooms/subjects/platform motion; quantified failure envelope and support burden. Commercial pilot planning requires independent privacy, security, safety, ownership and regulatory review appropriate to the intended product.

## Years 3–5 and beyond — ecosystem horizon

SPECULATIVE: cooperative AIR/GROUND sensing, geospatial/satellite context, remote scientific deployments and low-bandwidth fallback communications. Laboratory quantum magnetometry may become a university collaboration if access, sensitivity and environmental interference justify it. It remains separate from portable cardiac sensing promises.

Do not plan a custom satellite as a dependency of the local platform. Begin with existing licensed/public datasets or an approved communications service. Custom space hardware would be a distinct program with its own budget, spectrum, launch and operations constraints.

## Year 5+ — 2031 onward, research ambition

Pursue the complete ecosystem in the [charter](north-star.md): a multispectral X wearable with skeletal/AR interaction; SPECTER-OS coordinating heterogeneous hardware and optimized data/health/calibration services; persistent semantic WORLD models with observation histories; AIR/GROUND nodes and ORBIT data/resilient communications; and BIO supported by university laboratory methods. None has a guaranteed completion date. Each capability graduates independently through reproducible verification.

Proposed additions include NIR-compatible optics and, where appropriate, controlled illumination; stereo/depth; LiDAR; controlled CSI peers; positioning anchors; and optical/thermal/range reference fixtures. Advanced BIO adds appropriate physiological references and later calibrated magnetic instrumentation. Choose exact parts only after compatibility, optical/RF safety, power, compute and calibration review; see the inventory.

University methods/results may support a later narrow startup application, subject to evidence, demand, IP/licensing, manufacturability and support. The horizon preserves ambition without treating procurement, grants, partnerships or research success as scheduled facts.

## Decision and stop gates

| Gate | Continue when | Pause or redesign when |
|---|---|---|
| New modality | It adds a needed observable and can be calibrated | It adds UI complexity without independent information |
| New firmware | Provenance, source review and physical acceptance are ready | Dirty/unrecovered build inputs or compatibility gaps are unbounded |
| Fusion | Alignment and shared-parent dependencies are known | Apparent improvement disappears under held-out or timing controls |
| Vitals | Phantom/reference sensitivity and artifact rejection work | Empty-scene or mechanical controls produce similar rates |
| Obstruction | Material-specific signal survives nuisance controls and held-out sessions | Only training-room signatures remain |
| Productization | Demand and repeatable performance justify support/compliance cost | A prototype demo is the only evidence |

Re-estimate dates monthly from actual receipts, person-hours and gate outcomes. Preserve missed milestones and negative results as useful evidence; do not rewrite them into completed achievements.
