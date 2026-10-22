# Hardware inventory and readiness

[Hub](../README.md) · **As-of: repository `77abdd0`, 22 October 2026.**

> **Edition 2 reconciliation:** Project intent follows the [canonical charter](north-star.md). Local code links below still target `77abdd0`; newer Alpha `95eae17` source/build/simulation status is recorded in the [separate review](alpha-95eae17-review.md), without a merge. Reported builds and 261 tests do not establish flashed or hardware-validated firmware.

## Status vocabulary and missing source

Use two independent axes: **logistics** (have / shipped / confirmed-trackable / awaiting / needed / unknown) and **verification** (uninspected / identified / streaming / referenced / calibrated / integrated / field-validated). “Have” means historical possession is evidenced, not that a device is attached today. “Shipped” requires a dated dispatch record. “Confirmed-trackable” additionally requires an accessible carrier acceptance or movement event, not merely a label number. “Awaiting” requires an actual order or supplier commitment. “Needed” is a proposed acquisition dependency, not an order.

**The uploaded parts-status CSV was not accessible in the referenced chat response, repository, or the searched Downloads/Documents/Desktop CSV locations.** Its filename and rows are unknown. The accessible `SPECTER-X_outreach_targets.csv` is a supplier prospect list, not shipment evidence. No shipping or sponsorship status has been inferred from it. This ledger covers every named repository component and requested research modality; it cannot claim to enumerate unknown uploaded rows.

## Have: historical hardware evidence

| Item | Logistics evidence | Readiness | Next evidence needed |
|---|---|---|---|
| DI-188-protocol DAQ, connected via Seeed XIAO M0 CDC interface | **Have**, checkpoints [001](../checkpoints/001-hardware-di188.md) and [002](../checkpoints/002-alpha001-daq-end-to-end.md) | Identified and streaming; analog inputs floating, nominal conversion only | Inspect PCB/terminal block; connect safe reference and ground; independent meter readings; residual calibration errors |
| ESP32-S3 board: 16 MB flash / 8 MB PSRAM per recorded identification | **Have**, checkpoint [004](../checkpoints/004-esp32s3-hardware-identification.md) | Original CSI image identified; real CSI host path; supervisor firmware not established at baseline | Controlled radio link, source/build manifest, approved firmware validation later |
| Native USB and CH343/UART paths for that board | **Have**, checkpoints [004](../checkpoints/004-esp32s3-hardware-identification.md), [011](../checkpoints/011-csi-scientific-validation.md) | Both captured in recorded dual-channel run; UART console at 921600 | Stable device identifiers, cable/port mapping, explicit port ownership |
| Mac development host | **Have**, repository and recorded macOS runs | Host application and bench tools exist | Document reproducible dependency environment and storage budget |
| Two USB Ethernet adapters | **Reported have**, [controlled-link design](../design/controlled-csi-link.md) | Not validated in this task; unnecessary for offline synthetic bench | Physical identity if chosen for a controlled AP setup |

The DAQ speaks DATAQ's protocol; USB enumeration alone does not establish that the complete analog front end is a factory DI-188. The physical PCB question remains open in checkpoint 001. Sponsor/donor identity is unverified for all items above.

## Shipment and commitment queues

| Queue | Evidence available | Current ledger action |
|---|---|---|
| Shipped | No verified dispatch rows accessible | No items assigned |
| Confirmed-trackable | No carrier events accessible | No items assigned; do not publish tracking IDs |
| Awaiting | README anticipates SenXor arrival, but no dated commitment accessible | Record SenXor as unknown logistics pending owner CSV; do not invent an order |

## Planned bill of materials: possession unknown

Names and interfaces below are repository design selections, not purchasing confirmations. Source: [root hardware table](../../README.md), [pinmap](../../specter/hw/pinmap.yaml), and source paths in [baseline](verification-baseline.md).

| Role / named part | Logistics | Software readiness at baseline | Receipt / acceptance gate |
|---|---|---|---|
| Raspberry Pi 5 8 GB | Unknown | Setup guidance, Picamera2 path | Board revision, OS, power/cooling, actual sustained capture |
| Arducam IMX462 camera | Unknown | Picamera2/OpenCV adapters and pose backend | Exact module/lens/cable; image acquisition; intrinsics, distortion and exposure |
| 7-inch 1280×800 touchscreen | Unknown | HUD targets resolution | Exact model/interface; display and touch; latency and outdoor readability |
| TOPDON TC001 thermal | Unknown | Frame parsing / thermal helpers | Raw-mode format and unit validation; reference temperatures and emissivity |
| Meridian SenXor 160×120 EVK | Unknown; arrival anticipated in old note | Explicitly UNVERIFIED driver + simulation | Exact EVK/SDK and reference-target tests; claimed FOV is not calibrated |
| TI IWR6843AOPEVM | Unknown | UART TLV parser | Board/SDK/chirp identity; known-range and Doppler target; geometry calibration |
| BNO085 IMU | Unknown; “kept” in README is not receipt proof | Driver path | Chip identity; axis alignment; static/dynamic bias and drift |
| LSM9DS1 / MIKROE-1996 9DOF Click | Unknown | Driver and orientation layer | Address/pin checks, scale, temperature and magnetic interference |
| MIKROE-6423 Pi 5 Click Shield | Unknown | Proposed pinmap and checks | Actual revision, voltage compatibility and bus conflicts |
| MIKROE-4199 UWB Click / DW1000 | Unknown | DS-TWR math and simulator; real register integration requires verification | Two working endpoints, antenna delays, LOS/NLOS reference range |
| MIKROE-3922 GNSS 7 Click / NEO-M9N | Unknown | UBX/NMEA path | Outdoor reference track, antenna, fix quality, PPS/host timing |
| Hailo-8L accelerator / matching HAT | Unknown, optional | Roadmap integration | Supported model/toolchain and licensing; accuracy and sustained speed |
| Pi AI HAT+ 2 / Hailo-10H | Unknown, candidate named in README | VLM template + simulator | Exact hardware compatibility, model, power and citation reliability |
| Prophesee GenX320 event camera kit | Unknown, candidate | Stub + simulator | Actual SDK/host interface; contrast threshold and noise; no “glare-proof” claim |
| miniDSP UMA-16 v2 microphone array | Unknown, candidate | Acoustic stub + simulator | Channel order, geometry, synchronization, reverberation tests |
| LoRa / Meshtastic-compatible module | Unknown, candidate | Codec + simulation | Exact radio, region and airtime; lawful link and measured delivery |
| CO / CO2 gas sensors | Unknown, candidate | Advisory stub + simulator | Exact gas technology, calibration and cross-sensitivity; no safety certification |
| Vitals-capable radar configuration | Unknown; could reuse radar, not a separate receipt | Experimental stub + simulator | Approved reference protocol and motion-artifact rejection |

## Needed dependencies: proposals, not purchases

| Dependency | Why / readiness gate |
|---|---|
| Jumper leads, suitable DMM, safe low-voltage reference, verified grounding | Complete first DAQ measurement and calibration |
| Second CSI-capable board or dedicated controllable AP/traffic peer | Separate network behavior from sensing; SoftAP option needs feasibility check |
| Rigid mounts, fiducials, rulers, reference thermometer / suitable thermal target | Establish repeatable optical/thermal/range geometry |
| Optical/NIR capability and any compatible illumination (model undecided) | Spectral response, lens/filter and exposure verification; emitter safety/power review if active; no receipt or validated NIR capability implied |
| Depth camera or stereo pair; LiDAR (model undecided) | Metric depth and mapping research; no hardware or driver selection verified |
| Respiratory reference and approved ECG reference system | Later respiration/cardio experiments; avoid improvised body-connected electronics |
| Power supply, current/power logger, powered hub if required | Peak load and brownout characterization before a battery design |
| Battery/BMS, fusing, connectors, enclosure, cooling and strain relief | Portable integration after measured power and thermal budget |
| Laboratory magnetometer, field coils, quiet rig / shielding as needed | Long-term magnetometry; research partnership before acquisition |
| AIR/GROUND chassis, navigation/reference equipment, comms hardware | Separate future-platform feasibility, budget and operational review |

## Reconciliation procedure when the parts CSV becomes available

Preserve its original file and SHA-256 privately. Import each row with original wording, source date, quantity, exact SKU, sponsor/purchase basis, logistics status and evidence location. Keep carrier IDs, addresses, invoice data and contact history out of public Markdown. Add an asset ID and separate bench readiness. Conflicts become explicit rows with both sources until resolved; the later date alone does not prove delivery. A signed receipt or physical inspection can establish possession. A successful streaming log can establish streaming, not calibration.
