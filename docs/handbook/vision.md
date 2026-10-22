# Vision, scope and principles

[Documentation hub](../README.md) · **Owner-adopted project intent; capabilities remain evidence-gated.**

> **Edition 3 reconciliation:** Project intent follows the [canonical charter](north-star.md). Code links below target the Alpha snapshot `933e856`; the `95eae17` [review](alpha-95eae17-review.md) remains the dated record of that earlier state. The Alpha firmware has since been flashed to real hardware and passed a CSI acquisition preflight — see the [verification baseline](verification-baseline.md). *Hardware-validated* there means the acquisition preflight passed. It does not establish motion sensing, sustained unattended reliability, or performance superiority over any alternative.

## Executive vision

The [canonical charter](north-star.md) fixes the central vision: SPECTER-X is the first interface to a vertically integrated spatial-intelligence ecosystem, with multispectral wearable/AR ambitions, SPECTER-OS, WORLD, AIR/GROUND/ORBIT and BIO.

Build one coherent family of sensing tools: a portable unit, distributed sensor nodes and eventually mobile platforms sharing compatible measurements, clocks, calibration records and health information. A user should be able to ask what changed, where it happened, what observed it and how uncertain the answer is. The system should answer with evidence or explicitly say it does not know.

The useful first product of the research is a dependable instrument for experiments. A polished display comes after trustworthy acquisition. Long-term value comes from predictable interfaces and measured performance across price tiers, not from rewriting every dependency or adding the largest number of sensors.

The user's “family home” analogy maps to stable shared contracts with a purpose-built room for each component. First-party applications and device firmware can share naming, logging, configuration and diagnostics while retaining vendor drivers, documented interfaces and replaceable hardware.

## Scope by horizon

| Horizon | Intended outcome | Claim boundary |
|---|---|---|
| Bench instrument | Capture DI-188 and CSI data with provenance, loss counters and replay | Streaming is not calibrated sensing or human detection |
| Integrated local rig | Calibrated optical, thermal, range and inertial observations in common frames | Requires each delivered sensor and measured alignment |
| Cooperative platform | Multiple consenting units share bounded, authenticated observations | Simulated networking does not establish field reliability |
| Portable research unit | Power, thermal, mechanical and RF budgets verified on a defined enclosure | No certification inferred from component ratings |
| AIR / GROUND / geospatial context | Mobile nodes and satellite layers using the same contracts | Longer-term platform work, separate operational reviews |
| Advanced laboratory sensing | Controlled obstruction, respiration and magnetic research | Experiments may fail; no promised operational capability |

## Intended uses and explicit non-goals

Priority uses are university instrumentation, multimodal perception research, controlled environmental mapping and consent-based cooperative experiments. Rescue-oriented research is an aspiration that needs its own partners, evidence and safety process before deployment.

This baseline does not support covert person identification, arbitrary building interiors reconstructed from a handheld sensor, dependable life detection behind debris, medical monitoring, or autonomous safety-critical decisions. Lack of a detection means lack of sufficient evidence; it does not establish an empty room or absence of life.

## Design principles

1. Every displayed claim links to observations, algorithm versions and validity conditions.
2. A working device and a useful signal have different health states. Floating DAQ inputs illustrate the distinction.
3. Confidence, covariance, detection probability and sensor availability are different quantities.
4. Time and geometry are measured inputs to fusion, not decorative metadata.
5. Failure handling is visible: stale observations expire, uncertainties grow and disconnected nodes remain disconnected.
6. Keep raw data when consent and storage policy permit, so a result can be replayed and disputed.
7. Add a modality only when it improves a measured task relative to a simpler baseline.
8. Buy or reuse mature infrastructure; own the contracts, integration, diagnostics and research algorithms that make the system distinctive.

## Success measures

Near-term success is reproducible acquisition with attributable loss, honest labels and a calibrated reference experiment. Later success is a held-out improvement over the best single sensor at a stated false-alarm rate, timing tolerance and power budget. A visually compelling demo, a simulator score or a passing parser test alone earns neither milestone.

Ownership, staffing, budget and exact supplier commitments are unresolved. The [roadmap](roadmap.md) sets gates and dependencies instead of guaranteed delivery dates.
