# Implementation sequence and safe handoff

[Hub](README.md) · [Canonical vision](../handbook/north-star.md)

## Now: code plus preserved evidence

FRONTIER-001 provides strict observations, explicit historical migration, immutable raw references, source registry, deterministic replay/capture and diagnostic VIEW. Keep this package independent of Alpha's frozen features, motion recorder, statistical analysis, geometry and ESP32 firmware. OpenCode owns those areas. The initial interrupted optional-Measurement extension was inspected but not imported; reconcile it later by an explicit reviewed migration, not by silently merging defaults.

Next platform work: a schema implementation in another language, validated device identity/boot handling, timestamp maps with measured uncertainty, capture manifests bound to configuration/calibration and portable font/touch accessibility review. These are not completed by a source ID or a finite replay test.

## Next receipts and bench gates

1. Identify display revision and supplied adapter; obtain HDMI and USB-HID cables. Validate video and touch in a separately authorized session, then exercise 800x480 UI ergonomics. Desktop previews do not count as this gate.
2. On Pi 5 receipt, identify RAM/revision and compatible cooling/PSU/storage. Reproduce offline suite and replay before a camera is connected.
3. USB low-light camera is the simplest potential second live stream; identification, OS enumeration, exposure/latency and consent approval precede acquisition. MIPI cameras need exact board/connector/driver compatibility first.
4. Add Nooploop ToF/UWB, LW20 single range and GNSS/telemetry in priority order determined by actual delivery. Each needs its own electrical inspection, protocol fixtures, reference tests and typed adapter.
5. A second real modality can share the registry before it is spatially fused. Calibrated extrinsics, compatible acquisition-time uncertainty and a documented observation model must precede fusion claims. Measure benefit against single-sensor baselines with held-out sessions and failure controls.

Use RECEIVED → INSPECTED → ELECTRICALLY VERIFIED → DRIVER WORKING → CALIBRATED → INTEGRATED → EXPERIMENTALLY VALIDATED. Mark inapplicable stages explicitly. Every promotion requires a dated artifact and responsible reviewer; a shipment is never a receipt, and a receipt never implies electrical safety or sensor accuracy.

## Five-year systems outlook — conditional, not funded commitments

**Year 1:** dependable local CORE registry/capture/clock/calibration services, usable VIEW on desktop/display, receipt-driven sensors, small calibrated rig and an independent replayable fusion benchmark. Alpha remains separate active research with no detection claim inferred from acquisition success.

**Year 2:** portable X wearable/HUD ergonomics, optical/NIR/depth/thermal/range interoperability and uncertainty-aware WORLD history, measured power/thermal budgets and replaceable nodes. A field research rig is not certified PPE or medical equipment.

**Year 3:** authorized GROUND nodes and limited AIR sensor platforms; shared evidence with authentication, encryption, clock/anchor provenance, loss recovery and bandwidth budgets. Local operation survives loss of network or CORE. Dedicated flight controllers retain stabilization, failsafes and operator safety functions.

**Years 4–5+:** heterogeneous AIR fleet research: fixed-wing wide-area scouting, multirotor local mapping, thermal overwatch, environmental observation and relay, integrated with ground/wearable evidence. CORE can coordinate heavier inference and tasks; WORLD persists uncertain semantics and history; LINK supports degraded connectivity and ORBIT data/service backhaul. Fleet/swarm autonomy, regulatory operations and any custom satellite remain distinct research programs. Do not implement flight control or autonomous missions from this interface yet.

SPECTER-OS provides shared device/software contracts and lifecycle. Ferettux/Ferret is a separate project aiming to rewrite Linux kernel components in Rust, per owner; compatibility and maturity are not verified here. It may become a foundation on supported compute boards later. No replacement of current Linux, RTOS or bare-metal systems is required. BIO progresses only through reference-instrument/phantom and institutional laboratory gates.

## Differentiation and resources

Sensor fusion, robotics mapping, GNSS/UWB and distributed aircraft are established industries and open research fields; naming them is not a SPECTER invention. Our demonstrated contribution in this slice is validated software interoperability and truthful diagnostic replay. Potential differentiators to test: calibrated multimodal provenance/uncertainty, affordable replaceable nodes, failure visibility, degraded-network behavior and usable responder interfaces. Superiority, novel science, operational rescue benefit and commercial traction remain unverified.

Each stage needs people, budget, reference instruments, calibration time, storage, compute, electrical/mechanical engineering and authorized test sites. Prioritize two or three useful physical capabilities rather than every incoming item at once. Do not yet build autonomous fleet tasking, a custom satellite, unvalidated through-wall localization, medical diagnosis or life-safety actuation. RC/rocketry donations remain shelf equipment until separately reviewed integration.

## Research and commercialization constraints

Potential university collaborations can supply metrology, participant-review processes, RF/robotics expertise and physiological/magnetic reference instrumentation; no collaboration or endorsement is claimed. Any responder study needs specific partner/consent/safety validation before field claims. Civilian search-and-rescue, firefighting and disaster-response research guide the roadmap; weapon/combat development is outside this program.

F-1 status and project ownership do not themselves authorize employment or startup operations. Confirm the actual permitted work through the DSO and qualified immigration counsel before business activity; the [ICE employment guidance](https://www.ice.gov/sevis/employment) is a process reference, not individual permission. USCIS's official students/employment page returned 403 during this review; no mirror was used as authority. Export-control review is separate: [BIS deemed-export guidance](https://www.bis.gov/learn-support/deemed-exports/what-deemed-export) describes controlled-technology releases. Do not assume civilian purpose, public source or university affiliation resolves every hardware/technology/access restriction. Ownership, dependency/model licenses and sponsor loan/return/publication terms require review before commercialization or external disclosure.

## OpenCode handoff

Safe later use: import `specter.platform`, wrap a driver with an explicitly populated Observation, or run `specter.app --console` against preserved data. No need to change Alpha's frozen hypothesis, experiment code or firmware. Review the new contract instead of adopting interrupted default evidence fields. Software and hardware branches are not merged automatically. Requests for live cameras, device writes, personal recordings, flight/propulsion, deployment or publication require their own explicit authorization.
