# Immediate engineering backlog

[Hub](../README.md) · **Proposed work orders; no engineering changes authorized by this document.**

> **Edition 2 reconciliation:** Project intent follows the [canonical charter](north-star.md). Local code links below still target `77abdd0`; newer Alpha `95eae17` source/build/simulation status is recorded in the [separate review](alpha-95eae17-review.md), without a merge. Reported builds and 261 tests do not establish flashed or hardware-validated firmware.

Priority 0 blocks an honest next measurement; priority 1 enables integration; priority 2 expands scope. Owners are roles to assign, not promises that another agent is doing the work.

| ID / priority | Work / owner role | Dependency | Concrete acceptance / evidence |
|---|---|---|---|
| DOC-01 / P0 | Reconcile original parts-status CSV / owner | Missing upload | Exact source hash, dated logistics per row; sponsors and receipt proof separate |
| ENG-01 / P0 | Complete candidate runtime/source acceptance review after the docs reconciliation / reviewer | Alpha `95eae17` reviewed read-only | Obtain reproducible build/test evidence; resolve framing/output/counter gates; no automatic merge |
| SCI-01 / P0 | Freeze synthetic sweep and null protocol / experiment lead | Baseline analysis inspection | Seeded effect curve, null trial denominator and interval, positive control, held-out seeds, finite checks |
| CSI-01 / P0 | Verify owned controlled-link feasibility / RF engineer | Controllable peer; SoftAP CSI support question | Pin device/IDF/mode; record received qualifying frames and fixed geometry; source/traffic known |
| DAQ-01 / P0 | Inspect analog board and obtain safe reference equipment / instrumentation | Leads, DMM/reference, grounding | Board photos/identity, common-mode review, first known voltage with reference reading |
| ICD-01 / P0 | Ratify SPECTER_STAT consumption, output atomicity and drop semantics / firmware+host | Alpha separate tag vs older STAT proposal | Preserve legacy parser; one agreed diagnostics/version/priority policy with runtime evidence |
| FW-01 / P1 | Reproducible ESP-IDF candidate and provenance manifest / firmware | Agent work review, dependency locks | Clean target build, licenses, configuration and artifact hashes; candidate only until reviewed |
| USB-01 / P1 | Hostile-host and radio-outage validation / integration | Later authorized firmware test | Continuous / slow / stopped reader, bounded counted loss, no torn lines or silent wedge, independent liveness |
| TIME-01 / P1 | Clock-map and wrap/reset design / runtime | Data contract review | Reboot and wrap injections, wall-clock step test, measured residual and uncertainty |
| DAQ-02 / P1 | Analog calibration and uncertainty / instrumentation | DAQ-01 | Two-point fit plus independent check points, reference uncertainty, drift and residual report |
| CSI-02 / P1 | Controlled blinded motion experiment / experiment lead | SCI-01, CSI-01, stable capture | Preregistered endpoint, randomized trials, marked geometry, independent labels, held-out evaluation |
| RIG-01 / P1 | Receipt-driven optical/thermal/radar bring-up / sensing | Actual deliveries and fixtures | Per-device identity, calibration, raw examples and failure controls; no wholesale “integrated” label |
| FUS-01 / P1 | Time/frame-aware paired-sensor baseline / estimation | RIG-01, TIME-01 | Compare best single sensor against fused result; wrong-calibration/time-offset controls |
| LINK-01 / P1 | Peer threat model and privacy design / communications | Intended multi-node experiment | Encryption/identity/freshness design, partition behavior, data-retention policy; v1 gaps documented |
| PWR-01 / P1 | Power/thermal/cable budget / hardware | Delivered compute and sensors | Measured startup, peak and steady watts, temperature, brownout/recovery and cable retention |
| REPLAY-01 / P1 | Manifest-based replay / runtime | Raw logging contract | Frozen session replay, missing-artifact failure, deterministic comparisons and synthetic labels |
| WORLD-01 / P2 | Persistent environment model / estimation+VIEW | Validated fusion | Unknown space, source/time/uncertainty per object, expiry, no identity inference by default |
| VITAL-01 / P2 | Respiration feasibility with references / lab lead | Stable phase-capable rig and institutional review | Known-motion phantom first; reference respiration, abstention and motion-artifact results |
| FUT-01 / P2 | AIR/GROUND/satellite feasibility / systems | Core unit gates and budget | Separate measured link/power/pose plans; no procurement or flight implied |
| IP-01 / P1 | License and contribution inventory / owner+university office | Exact dependencies and sponsor terms | Third-party/model/data licenses, contributor ownership, disclosure history and private/public plan |

## First useful sequence

Review the concurrent agent's completed artifacts without modifying them. Reconcile the inventory when its source is available. Run the frozen offline null/sensitivity analysis before recruiting participants. In parallel, prepare safe analog reference equipment and verify controlled-link feasibility. Resolve the interface mismatch before any firmware acceptance session. Then perform calibration and controlled sensing, retaining failures.

Do not schedule a broad fusion demonstration until time, transforms and at least two physical modalities are validated. Do not expand to cardiac or through-obstruction claims because a software metric moved. The [validation plan](validation.md) supplies concrete controls and stopping rules.
