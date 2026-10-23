# Hardware readiness and incoming-device acceptance dossiers

[Platform hub](README.md) · [Machine-readable tracker](readiness.json) · [Current inventory](readiness.json)

**Source:** owner's current FRONTIER request, 22 October 2026, reconciled with repository inventory and hardware checkpoints 001/018/019/021. Receipt is user-reported, not physically re-inspected here. Confirmed/accepted/reported-shipping is deliberately one unresolved logistics category: no delivery or carrier movement is inferred. No private contacts, shipment IDs or addresses are retained. No live device, motor, battery, laser, optics, camera or firmware operation occurred in this task.

## Current tracker

| Item | Logistics | Readiness / scope | Next gate |
|---|---|---|---|
| ESP32-S3 development board | RECEIVED | Recorded CSI acquisition; motion not validated | Preserve Alpha ownership; platform replay only |
| DATAQ DI-188 | RECEIVED | Prior USB streaming; analog calibration pending | Safe reference/ground and driver-specific approved session |
| Newhaven NHD-7.0-HDMI-N-RSXV-CTU + adapter | RECEIVED | User reports powered; HDMI/touch untested; cables missing | Identify revision/adapter; obtain HDMI and USB-HID cables |
| Carbon-fiber PLA spools | RECEIVED | Printing unverified | Identify formulation; printer/nozzle/process suitability |
| Unistellar eVscope 1 | RECEIVED | Functional testing outstanding | Identify serial/revision/charger and supported data access |
| Innov8tive BadAss 2814 980KV motor | RECEIVED | Unintegrated; not operated | Motor/ESC compatibility review only; no exposed-prop operation |
| Innov8tive Rebel V2 50A ESC | RECEIVED | Unintegrated; not operated | Exact revision, control/power/arming manual |
| APC 8x6E propellers (two) | RECEIVED | Unintegrated; not operated | Inspect identity/fit; no assembly or spin in this task |
| Northwest Blue: LightWare LW20/HA | CONFIRMED_OR_REPORTED_SHIPPING | Not received/validated here; single-point range, not scanning 3D LiDAR | Receipt, exact variant, electrical/protocol/manual review |
| Northwest Blue: Here4 RTK GNSS | CONFIRMED_OR_REPORTED_SHIPPING | Delivery not assumed; RTK accuracy not established | Receipt/antenna/correction path and reference survey |
| Northwest Blue: RFD900x telemetry pair | CONFIRMED_OR_REPORTED_SHIPPING | Delivery not assumed; link untested | Exact regional variants/antennas/power/authorization |
| Northwest Blue: Power Brick Mini | CONFIRMED_OR_REPORTED_SHIPPING | Delivery not assumed | Connector polarity, input/output/current ratings |
| Seengreat Raspberry Pi 5 | CONFIRMED_OR_REPORTED_SHIPPING | RAM/configuration unverified | Read actual board/RAM; PSU/cooling/storage/cables |
| Camemake OX05B1S RGB-IR MIPI camera | CONFIRMED_OR_REPORTED_SHIPPING | Driver and host compatibility unverified | Exact module/FPC, overlay, tuning and IR optics |
| Camemake GC4023 MIPI camera | CONFIRMED_OR_REPORTED_SHIPPING | Driver and host compatibility unverified | Exact module/FPC, supported host and kernel |
| Supertek USB low-light camera | CONFIRMED_OR_REPORTED_SHIPPING | Exact model unconfirmed; not a validated feed | Model/UVC modes, USB cable, lens, exposure |
| Nooploop LinkTrack UWB units | CONFIRMED_OR_REPORTED_SHIPPING | Quantity/revision/anchor access unverified | Receipt/topology/power/NLink protocol |
| Nooploop TOFSense-M S multizone ToF | CONFIRMED_OR_REPORTED_SHIPPING | Not a scanning LiDAR; range output unvalidated | Revision/protocol/grid/FOV/reference targets |
| ComNav K901 GNSS evaluation kit | CONFIRMED_OR_REPORTED_SHIPPING | Delivery and correction configuration unverified | Board variant/antenna/cables/reference corrections |
| Heltec WiFi LoRa 32 V4 / ESP32-S3 | CONFIRMED_OR_REPORTED_SHIPPING | Not a received dedicated CSI peer | Regional radio, board pinout/power/software support |
| Bioenno LiFePO4 battery + charger | CONFIRMED_OR_REPORTED_SHIPPING | Exact pack/charger ratings unconfirmed | Matched chemistry/voltage/polarity/BMS; no operation here |
| Mini-Circuits RF front-end samples | CONFIRMED_OR_REPORTED_SHIPPING | Exact part numbers/roles unconfirmed | Frequency, bias, impedance, limits and intended observable |
| Appcon LoRa modules | CONFIRMED_OR_REPORTED_SHIPPING | Exact module/region unconfirmed | Electrical/protocol/regional compatibility |
| TEKTELIC LoRaWAN gateway/sensors | CONFIRMED_OR_REPORTED_SHIPPING | Not equivalent to LoRa peer-to-peer | Region/backhaul/network-server and sensor profiles |
| Lansitec tracker | CONFIRMED_OR_REPORTED_SHIPPING | Exact model/network unconfirmed | Protocol, location observable and privacy review |
| Vicharak Shrike Lite FPGA | CONFIRMED_OR_REPORTED_SHIPPING | Toolchain/host and device revision unconfirmed | Pinout/programming/recovery path before development |
| EKB E4500 DLP module | CONFIRMED_OR_REPORTED_SHIPPING | Not a validated HUD | Exact module/light source/driver/electrical/optical review |
| OPCO collimator/mirrors | CONFIRMED_OR_REPORTED_SHIPPING | Prescription and compatibility unverified | Optical prescription, coatings, mounts and safe beam plan |
| XR Depot nonbooting HoloLens 2 for parts | CONFIRMED_OR_REPORTED_SHIPPING | Explicitly nonbooting; not a working AR platform | Receipt/condition/repair permissions and parts evaluation |
| BigRedBee GPS telemetry/tracker | CONFIRMED_OR_REPORTED_SHIPPING | Possible loan/return terms unresolved | Terms first; exact regional transmitter/receiver |
| CORVON H743v2 flight controller | CONFIRMED_OR_REPORTED_SHIPPING | Not an integrated aircraft | Exact board/firmware/connectors and bench plan |
| Lemon Rx radio components | CONFIRMED_OR_REPORTED_SHIPPING | Exact components/protocol unconfirmed | Model, matched receiver/transmitter and failsafe review |
| TI IWR6843AOP / DCA1000 | PENDING_OR_NEEDED | Not confirmed/received | Exact EVM/capture-card role and source |
| Radiometric thermal module | PENDING_OR_NEEDED | No validated thermal stream | Select exact model/raw radiometry and reference |
| Scanning 3D LiDAR | PENDING_OR_NEEDED | LW20 does not fill this requirement | Select aperture/scan/calibration and safety requirements |
| Dedicated second ESP32 CSI node | PENDING_OR_NEEDED | Not confirmed received | Receipt/pinned target and controlled-link plan |
| North Star HUD optics/components | PENDING_OR_NEEDED | System integration unverified | Prescription, optical safety and mechanical budget |
| RK3588 / advanced edge AI hardware | PENDING_OR_NEEDED | No integration or performance claim | Workload/power/toolchain evidence before acquisition |
| Additional IMUs / optics / power accessories | PENDING_OR_NEEDED | Exact selections unconfirmed | Prioritize calibrated rig dependencies |

## Common acceptance process

RECEIVED → INSPECTED → ELECTRICALLY VERIFIED → DRIVER WORKING → CALIBRATED → INTEGRATED → EXPERIMENTALLY VALIDATED. Inapplicable steps are marked with rationale, not silently skipped. Keep a private asset/terms registry and public redacted evidence references. Record model/revision, schematic/manual revision, rated supply/polarity/logic level, connector orientation, driver/OS/version, raw/config hash, clock domain, reference uncertainty, failures and reviewer. Before any connection obtain missing cables and compatible supply information; connector appearance is not a pinout. The steps below are **future acceptance procedures**, not permission to operate unfamiliar equipment now.

## D1 — Newhaven display (priority 0, received)

Exact owner-supplied model `NHD-7.0-HDMI-N-RSXV-CTU`, with its own adapter, user reports powered. Video and touch are untested; HDMI and USB touch cables are missing. Verify label/board/adapter revision and connector mapping against the [manufacturer specification](https://newhavendisplay.com/content/specs/NHD-7.0-HDMI-N-RSXV-CTU.pdf), especially mechanical drawing, supply table and USB-HID/HDMI interfaces. The sheet identifies an 800x480 panel; do not carry forward the old generic 1280x800/DisplayPort assumption. Use the supplied adapter only after its label/polarity are matched by the responsible hardware reviewer; do not infer that USB supplies the panel.

Host path: existing Linux/macOS HDMI output and USB HID touch, contingent on actual board/host behavior. Required accessories: host-appropriate HDMI cable/adapter and correct USB data cable, cable retention and later mount. Initial approved test: static 800x480 color/text pattern, then enumerate HID and check all touch corners/rotation; no camera needed. Record EDID/resolution, touch coordinates, latency, readability, power and thermal observations. Calibration is touch alignment/orientation and brightness/ergonomics, not sensor radiometry. Integration: run existing `specter.app --console --console-size 800x480`; accept only when no clipping, missed touch regions or unreadable required states are observed. The current screenshots establish rendering only.

## D2 — Pi 5 compute (priority 1, incoming)

Verify Seengreat-supplied board model, RAM, revision, headers and storage. Obtain the exact [Pi 5 documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) for power/ports and match supply, cooling, storage and display adapters before energizing. The agreed envelope is CPU/OS independent, but current Python/OpenCV runtime must be exercised on the actual OS image. Initial approved acceptance: boot/version/storage identity, sustained offline replay/test suite, rail and thermal monitoring; no camera auto-discovery or model download. Success: loss/accounting and canonical replay equal desktop reference under a documented workload without brownouts/throttling. Power or speed superiority remains unmeasured. Adapter: CORE host/node identity and health only; no invented sensing observations.

## D3 — low-light / RGB-IR / MIPI cameras (priority 1–2, incoming)

Supertek: exact SKU, USB speed, UVC/raw formats, lens, IR-cut configuration and connector must be verified. Candidate Linux V4L2/OpenCV path can reuse `sensors/nightvision/camera.py`; it is not proof the incoming device is supported. Obtain USB data cable and a safe fixed mount. Camemake OX05B1S RGB-IR and GC4023: inspect exact module, FPC pin count/pitch/orientation, voltages, supported host/kernel/overlay and vendor tuning. A MIPI connector does not guarantee Pi 5 compatibility; do not use a guessed ribbon adapter or overlay.

Future authorized acceptance: enumerate without recording people; test a non-person calibration target only after camera approval; verify exposure, pixel format, dropped frames, acquisition timestamp semantics and spectral channel meaning. Calibrate intrinsics/distortion, exposure/latency and rig extrinsics independently. RGB-IR separation needs actual raw format and filter/illumination evidence; no generic NIR sensitivity guarantee. Schema: image/frame observation with optical frame and pixel units, native time/raw hash; inferred skeleton joints cite parent image/model/depth/calibration. No camera activated here.

## D4 — TOFSense-M S and LinkTrack UWB (priority 2, incoming)

Verify Nooploop exact variants, counts, connector/power/logic levels, antenna arrangement and firmware protocol. Official [ToF downloads](https://support.nooploop.com/tofsense/download/) distinguish multizone M-series; [LinkTrack documentation](https://support.nooploop.com/linktrack/) provides the ranging/positioning system references. Pin NLink protocol/library revision after receipt; inspect native example fixtures before porting. Required accessories: matching cables/interface adapter, reference targets, mounts, and enough anchors/tags for the chosen observable. Do not treat an anchor-dependent position report as standalone calibrated ranging.

Future acceptance: decode known protocol fixtures first; then static measured LOS distances and controlled NLOS/distractor scenes with independent tape/survey uncertainty. ToF needs per-zone validity/grid/FOV mapping; UWB needs antenna delay, anchor geometry, clock behavior and NLOS error characterization. Success: reproduce reference ranges with documented error/coverage rather than borrow a vendor accuracy number. Typed adapters: `range` in meters in a sensor frame; `range_grid` with geometry/invalid mask; externally solved position must identify anchor frame/calibration and uncertainty. Existing DW1000 code is a math/protocol reference, not a LinkTrack electrical driver.

## D5 — LW20/HA single-point range (priority 2, incoming)

Verify exact LightWare revision and optical classification before selecting supply or serial/I2C adapter; use the matching [LightWare manual](https://www.documents.lightware.co.za/LW20%20-%20LiDAR%20Manual%20-%20Rev%2012.pdf). Older LW20/SF20 revisions are not automatically the HA pinout. Check cable harness, connector polarity, logic levels, target reflectivity/range limits and safe beam termination. No laser operated here.

Future approved acceptance: fixture/protocol decoding, static matte reference target at several surveyed distances/angles, invalid-return and timeout handling; log range units, native sampling and latency. Set tolerances from the delivered specification plus reference uncertainty before measuring. Schema: single `range` with axis/extrinsic calibration and uncertainty. This is **not** a scanning 3D point cloud; obtain a separate scanning sensor or rigorously validated scan mechanism for that capability. No mechanism is built here.

## D6 — Here4 / ComNav K901 GNSS and telemetry (priority 2–3, incoming)

Verify receiver/EVK revisions, antenna/bias requirements, supplied harness, electrical levels, supported protocol and host access. Obtain exact supplier/manufacturer manuals for Here4 and K901 after identity checks; no pinout is asserted here. Needed accessories include appropriate antenna/mount/ground plane, cables, compatible receiver/USB interface and a documented correction source for any RTK test. Proposed host adapter reuses existing GNSS parsing conventions only when the actual output format matches.

Future acceptance: replay vendor/raw protocol fixtures, then authorized outdoor reception with clear validity/fix flags and an independently referenced static location/route. Distinguish standalone, float and fixed solutions, receiver reported precision and measured accuracy. GNSS UTC/PPS is not automatic exposure/CSI synchronization. Observation: geodetic position with datum/altitude convention, fix state, acquisition time and covariance/unknown uncertainty; create local ENU only with an explicit anchor. RFD900x is a telemetry link, not GNSS; verify exact regional pair, antennas, supply/current, connector/pinout and lawful configuration before RF operation. Test wired framing first, later authorized link loss/reorder/recovery. Log LINK health/delivery, not fake tracks. Power Brick Mini requires exact input/output/polarity/current review and separate power acceptance.

## D7 — LoRa / LoRaWAN / trackers (priority 3, incoming)

Heltec WiFi LoRa 32 V4, Appcon modules, TEKTELIC gateway/sensors and Lansitec tracker need exact model, region, power/logic-level and protocol identification. Obtain manufacturer board schematics and regional radio manuals before a wiring plan. LoRaWAN involves gateway/network-server/profile credentials and is not the same protocol as peer-to-peer LoRa. Never put credentials in public docs. Do not assume the incoming Heltec board is a received/validated second CSI station.

Required accessories depend on actual regional antennas, data/power cables, compatible host interface and network/backhaul provision. Start with offline protocol/codec fixtures; later approved low-rate heartbeat transfer and intentional disconnect/restart/duplicate tests. Measure airtime, latency, delivery, bandwidth and power. Observations: health, environmental readings or tracker location with native validity/frame/time and source uncertainty; transport does not raise evidence level. LINK's existing HMAC prototype is not confidentiality or per-node secure identity.

## D8 — battery / power / RF samples (deferred until exact identity)

Bioenno pack and charger: verify model, chemistry, capacity, output, polarity, connectors, charger compatibility, BMS and current limits. Obtain the exact manual and suitable fused harness/enclosure plan; no charging/discharging test here. Future authorized acceptance uses responsible lab supervision, rated loads and documented cutoff/temperature/current observations before powering a sensor rig. Runtime estimates need measured simultaneous load and usable energy. Adapter: node power/health telemetry when a calibrated current/voltage source exists.

Mini-Circuits samples: exact part numbers, band, impedance, bias, maximum input and connector type must be known. They do not themselves provide a sensing result. First propose a testable RF role and simulator/measurement plan with appropriate reference instruments. No transmission, bias supply or powered bench operation performed.

## D9 — optical/HUD/FPGA and repair-only equipment

EKB E4500 DLP and OPCO optics require exact module/light engine, supply/controller/driver, prescription/coating/FOV/eye-relief and optical safety review. Obtain mating cables and mounts only after pinout/prescription checks. Initial non-destructive work is documentation/inspection; later controlled projection/beam checks require a safe laboratory setup, not a wearable pointed at eyes. Schema: VIEW configuration/calibration, not invented sensor observations.

Vicharak Shrike Lite: identify FPGA/board/toolchain license, power/logic and programming/recovery interfaces. Needed programmer/cables follow that board's manual. Start with offline build/simulation and protocol fixtures; no FPGA flash here. Do not assume acceleration improves latency/power without measurement.

The XR Depot HoloLens 2 is explicitly nonbooting and for parts. Receipt, condition, any loan/return/repair restrictions and safe disassembly documentation precede work. No working AR, video or eye-safe optical system is inferred. Unistellar eVscope 1 is received, not tested: identify exact revision, charger, supported app/API/data rights and mounting before any approved functional session. Neither is currently a SPECTER driver or proof of platform compatibility.

## D10 — RC / rocketry shelf equipment (not integrated AIR hardware)

Received motor, ESC and two propellers remain unoperated. CORVON H743v2 and Lemon Rx components have no assumed receipt or validated compatibility. BigRedBee may be a loan: establish ownership/return terms before modifications. Obtain exact electrical, control, arming/failsafe and regional RF documentation and compatible connectors before any design. Do not connect propulsion, expose spinning props or run batteries/radios during this task. A future aircraft program needs separate mechanical/electrical/flight-safety review, onboard stabilization/failsafes and qualified operators. This UI must not become flight-critical actuation.

## Missing evidence and what not to build yet

The original full procurement/status CSV is still unavailable here; this user-provided snapshot supersedes earlier “unknown receipt” rows only for the specifically named items. Commercial acceptance/shipment confirmations do not establish delivery. Radar/DCA1000, radiometric thermal, scanning LiDAR, dedicated CSI peer, North Star optical pieces and advanced compute remain pending/needed, not placeholder feeds. Do not write a live integration against an assumed pinout or give a future device a healthy tile. Keep display, compute, one low-light camera and ToF/range acceptance ahead of speculative fleet/HUD/quantum work.
