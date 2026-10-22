# Gated roadmap

[Hub](../README.md) · **Planning windows start 22 October 2026; dates are targets, not commitments.**

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

Conditional directions: richer optical/depth/thermal/radar fusion, distributed geometry, purpose-built carrier/enclosure, robust multi-node networking, and limited GROUND experiments. Add AIR only after navigation, vibration, link and operational constraints are addressed. Through-obstruction research stays material-specific, with opaque-wall controls and held-out layouts. Investigate whether affordable hardware tiers can share the same contracts while exposing different uncertainty and coverage.

**Exit:** task-specific repeatability across unseen rooms/subjects/platform motion; quantified failure envelope and support burden. Commercial pilot planning requires independent privacy, security, safety, ownership and regulatory review appropriate to the intended product.

## Years 3–5 and beyond

SPECULATIVE: cooperative AIR/GROUND sensing, geospatial/satellite context, remote scientific deployments and low-bandwidth fallback communications. Laboratory quantum magnetometry may become a university collaboration if access, sensitivity and environmental interference justify it. It remains separate from portable cardiac sensing promises.

Do not plan a custom satellite as a dependency of the local platform. Begin with existing licensed/public datasets or an approved communications service. Custom space hardware would be a distinct program with its own budget, spectrum, launch and operations constraints.

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
