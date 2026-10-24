# Research ideas and hypotheses

[Hub](../README.md) · **Living research log · started 23 October 2026.**

This is the dated idea register. It records **VISION** and **RESEARCH**
directions before they become experiments; it does not promote them. The
sensor-by-sensor observability analysis and programme boundaries remain in
the [research program](research-program.md). Architectural commitments are in
the [decision record](decisions.md). Evidence is in the
[experiment ledger](experiment-ledger.md).

**Rule:** an idea is not a capability. Only a frozen protocol, recorded
evidence and an explicit boundary can move an entry to **VALIDATED**.

## Status vocabulary

| Label | Use here |
|---|---|
| **VISION** | Long-term direction; no implementation or experiment exists. |
| **RESEARCH** | An open question or feasibility track; a negative result is valid. |
| **PLANNED** | A specified experiment or integration that has not started. |
| **IN PROGRESS** | Work exists and is partially evidenced; not yet validated. |
| **VALIDATED** | A recorded result supports the specific claim, with an artifact and stated boundary. |

## Complementary partial observations

The following is a **symbolic illustration**, retained because it captures the
intended fusion idea. It is not a measurement, a coordinate system or a
prediction that every gap can be filled.

```text
CSI:      1  ·  ·  ·  ·  6  ·  ·  ·  10
Radar:    ·  2  3  ·  5  ·  ·  8  9  ·
Thermal:  1  ·  ·  4  ·  ·  7  ·  9  ·
Combined: 1  2  3  4  5  6  7  8  9  10
```

What the example is allowed to mean:

- different sensors may constrain different **partial** properties of an
  event (a radio-channel change, a radar range/velocity, a thermal region);
- a joint model may produce a more useful hypothesis **if** the observations
  are time-aligned, spatially calibrated, associated to the same event and
  not merely restatements of one another;
- missing entries remain unknown. The `Combined` row is a hypothesis, not an
  observation.

What it does **not** mean:

- **High confidence is not new spatial information.** A CSI classifier can
  be very confident that the channel changed and still have no independent
  measurement of range, bearing, depth, identity or occupancy. Confidence is
  a calibrated score over a task; it does not create degrees of freedom the
  sensor did not observe.
- A confident radar range and a confident thermal blob do not by themselves
  prove they are the same object. Association, calibration, clock alignment
  and shared-parent dependence must be established.
- Sensors observing the same person are correlated. Treating their outputs
  as independent evidence can double-count one physical cause and produce
  unjustified certainty. Fusion must model shared evidence and preserve
  alternative hypotheses.
- Attention, a Transformer or a learned world model is an architecture
  family, not an evidence guarantee. It must be compared with calibrated
  Bayesian/factor-graph/late-fusion baselines and with missing modalities.

## Active log

| ID | Concept | Status | What would make it real / boundary |
|---|---|---|---|
| **RI-001** | **Uncertainty-aware multimodal fusion**: combine calibrated observations with explicit uncertainty, source dependencies and abstention rather than a single confidence score. | **RESEARCH** | Two validated modalities with clocks/transforms; compare calibrated late fusion and a factor graph against naive concatenation; report calibration and false alarms. See [research program](research-program.md#fusion-sequence). |
| **RI-002** | **CSI / radar / thermal complementarity**: use the different physical observables (RF multipath, range/Doppler, surface radiance) as partial constraints on one event. | **RESEARCH** | Independent references and association for each modality; test whether fusion improves a prespecified task over each sensor and a non-learning baseline. The example above is illustrative only. |
| **RI-003** | **Cross-attention / learned fusion**: a compact cross-attention or Perceiver-style model that lets one modality reinterpret another's features. | **RESEARCH** | Frozen splits by session/person/site; comparison with calibrated baselines; ablation of attention; report missing-modality and wrong-high-confidence cases. |
| **RI-004** | **Adaptive modality reliability**: reliability conditioned on scene, contrast, occlusion, multipath, motion and calibration state, not a fixed per-sensor weight. | **RESEARCH** | Reliability diagrams, context-stratified error, drift/failure tests; confidence is not automatically a covariance. |
| **RI-005** | **Missing-modality training**: train and test with dropped, stale, degraded and conflicting channels; report coverage and abstention. | **RESEARCH** | Deliberate dropout matrix, stale-data injection, sensor disconnect replay; report hallucination and wrong-high-confidence rates. |
| **RI-006** | **Temporal / persistent state**: aging, propagation uncertainty, track hypotheses, temporal consistency and event history. | **RESEARCH** | State schema with age/uncertainty/provenance; predict/measure separation; clock-step and replay tests. |
| **RI-007** | **Evidence provenance and lineage**: every track/event links to contributing raw/source observations, calibration, age, uncertainty and alternatives. | **IN PROGRESS** | Observation/provenance fields and contracts exist; multimodal lineage and WORLD history are not implemented. Preserve raw references and clock domains. |
| **RI-008** | **Information-gain-driven active perception**: choose the next observation (viewpoint, longer window, different modality) that most reduces uncertainty. | **RESEARCH** | Start with recommendations, not actuation; human authorization and local safety for any moving platform; measure decision benefit and cost. |
| **RI-009** | **Learned world models**: a persistent, uncertainty-aware spatial state learned from multimodal history. | **VISION** | Requires validated fusion, provenance, time alignment and independent evaluation; a track list or rendered scene is not a world model. |
| **RI-010** | **Confidence versus spatial information**: a high-confidence channel-change label must not be presented as a 3-D detection. | **RESEARCH** constraint | Enforced by [ADR-003](decisions.md); test with a CSI-only high-confidence condition and no range/bearing evidence. |
| **RI-011** | **SPECTER-SYNC / Shrike Lite FPGA timing**: use the RP2040 + Renesas SLG47910 board for deterministic event counters, timestamp capture and a minimal sensor-interface bridge. | **PLANNED** | Identify the physical board revision; verify stable power and 3.3 V I/O; measure the nominal 50 MHz oscillator against an external reference; characterize input latency, jitter, counter wrap and RP2040 readout. Any CORE/WORLD record must use the existing Observation v1 contract, not a new schema. No timing-accuracy claim before calibration. See [Phase 0 design](../design/specter-sync-phase0.md). |

## Adding an idea

Use the next ID and include: date, status, one-paragraph concept, mechanism,
prerequisites, risks, evidence link and the smallest experiment that could
change the status. Keep programme-level detail in
[research-program.md](research-program.md); keep evidence in the
[experiment ledger](experiment-ledger.md). Do not rewrite an old entry to
make a later result look expected; add a dated update instead.
