# Hark procurement context — SPECTER-X ecosystem

**Status: PLANNED / QUESTION SET. No purchase, receipt, sponsorship, delivery,
compatibility or performance claim.** 24 October 2026.

This profile gives Hark enough architectural context to evaluate procurement
without treating the current prototype or a single vendor as the whole system.
It implements [ADR-007](../handbook/decisions.md) and the
[North Star](../handbook/north-star.md). The hardware ledger remains
[the inventory](../handbook/hardware-inventory.md); nothing here changes a
logistics or readiness status.

## Compute topology first

| Tier | What it is for | What it is not |
|---|---|---|
| **Central command** | High-performance AI training/inference, cross-platform coordination, persistent WORLD history, large-scale replay and analysis; workstation/server GPUs or Jetson AGX Thor-class hardware | Not worn; not required to be portable; not an observation source by itself |
| **SPECTER-X headset** | AR display/optics, cameras and sensors, user interaction, local low-latency processing and independent safety; also a distributed participant | **Not a complete self-contained high-performance compute system**; not required to host all AI |
| **Distributed participants** | SPECTER-AIR / SPECTER-GROUND / other NODEs, plus the headset's local-safety role; local latency-critical processing, safety and bounded autonomy | Not dependent on central compute for local safety; not automatically authorized to act |

The central tier may be a local workstation/server or a remote facility. The
headset may be tethered or wireless. Distributed nodes may be disconnected;
their safety functions remain local and must fail safe.

## Central command compute

Procurement questions:

- GPU memory, sustained compute, interconnect, CPU/RAM/storage and expansion
  headroom for the intended models and multi-session WORLD history.
- Power, cooling, noise, UPS/backup, physical security, remote management,
  operating-system/driver support and update policy.
- Network path to headset/nodes: bandwidth, latency, jitter, loss, roaming,
  encryption, identity and offline behavior.
- Workstation/server GPU versus Jetson AGX Thor-class trade-off: throughput,
  power envelope, portability, availability, software stack and support.
- Data governance: raw evidence locality, retention, access control, backup,
  deletion, participant/location sensitivity and export constraints.
- Reproducibility: driver/CUDA/runtime pinning, benchmark protocol, acceptance
  workload and rollback.

Do not select a central tier from peak TOPS alone. Require measured workload
throughput, memory residency, sustained power/thermal behavior, compatibility
and support. A central tier is not a substitute for headset safety or a sensor.

## SPECTER-X AR headset interface

Procurement questions:

- Display/optics: field of view, resolution, luminance, contrast, distortion,
  eye relief, IPD, focus, latency, persistence and outdoor readability.
- Sensing: camera modules/lenses, NIR/thermal/radar/CSI/LiDAR/depth/IMU/GNSS/UWB
  candidates; interface, synchronization, calibration and raw-access support.
- Local compute: low-latency sensor ingest, safety monitoring and fallback;
  **not** a requirement to run all high-performance AI locally.
- Power/thermal: battery or tether, peak/continuous draw, heat path, skin
  contact, charging and brownout behavior.
- Ergonomics/safety: mass, center of gravity, mounting, cables, impact,
  occlusion, audio, eye safety, radio exposure and emergency removal.
- Connectivity: wired/wireless links to central command and nodes, handover,
  loss behavior, identity and authorization.
- Privacy: camera/microphone/physiology indicators, local raw retention, field
  of view and bystander considerations.

A headset that cannot meet local safety or thermal limits is not made acceptable
by adding central compute. A headset that requires central compute for every
function is not the intended architecture.

## Distributed compute and participants

- Local NODE/AIR/GROUND compute must handle acquisition, time-stamped evidence,
  latency-critical control and independent safety without central connectivity.
- Evaluate Jetson Orin-class or lower-power Thor variants, RP2040/ESP32-class and
  other controllers by role, not as one universal part. The central AGX
  Thor-class/server baseline is a separate tier.
- Require local time sources, health/heartbeat, bounded queues, fail-safe states,
  update/rollback, physical access and tamper/identity controls.
- Communications must preserve provenance and authorization; a relay does not
  create a new observation or independent evidence.
- Autonomy is bounded and auditable; central absence is never permission to act.

## Future sensor context

Target modalities remain **VISION / RESEARCH / PLANNED**, not a shopping list:
optical/NIR, thermal, 60 GHz radar, Wi-Fi CSI, LiDAR/depth, IMU, GNSS/UWB,
acoustic and eventual BIO laboratory instrumentation. For each candidate,
require:

- exact model/revision/interface and raw-data access;
- voltage/current/thermal and 3.3 V/5 V compatibility;
- clock, trigger, timestamp and calibration support;
- driver/SDK/licensing/security and update path;
- measurable task benefit over existing modalities and a negative control;
- physical safety, RF/optical exposure, privacy and regulatory review.

Clinical, rescue, through-wall, universal-surveillance and non-contact vital-sign
claims are not procurement criteria; they remain out of scope unless separately
evidenced and authorized.

## Compatibility and acceptance skeleton

| Area | Required evidence before commitment |
|---|---|
| Architecture | Fits central/headset/distributed roles; no hidden self-contained assumption; ADR-007 |
| Interfaces | Observation v1/provenance, time/clock, transport, identity, authorization and error semantics |
| Compute | Benchmarked target workload, memory, sustained power/thermal, driver/toolchain pinning |
| Sensors | Raw access, calibration, synchronization, negative controls and task-relevant accuracy |
| Mechanical/electrical | Mounting, connectors, power budget, cooling, serviceability, safety |
| RF/optical | Regulatory limits, coexistence, exposure, filtering and field validation |
| Security/privacy | Identity, encryption, update integrity, data retention/deletion and audit |
| Supply/support | Availability, lead time, warranty, repair, replacement, licensing and export |
| Cost | Total cost of ownership including spare units, calibration, power and support |

## Hark output expected

For each candidate, Hark should return a **dated compatibility note**, not an
order: exact SKU/revision, quoted capability, interfaces, evidence requested,
known incompatibilities, unresolved questions, estimated lifecycle/support, and
whether it belongs to central command, headset or a distributed node. Missing
data stays unknown. A quote, datasheet or vendor demonstration is not a
measured SPECTER-X capability.

## Do not infer

- That the headset must contain all AI compute.
- That central compute replaces local safety or makes a network reliable.
- That a GPU/TOPS number proves the SPECTER workload.
- That a sensor's presence proves calibration, synchronization or a task claim.
- That a procurement note is a purchase, receipt, sponsorship or deployment.
- That ORBIT, BIO or advanced AI has left the long-term roadmap.
