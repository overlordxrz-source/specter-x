# Software and real-hardware verification baseline

[Hub](../README.md) · **Evidence review of `77abdd0`; no hardware or application tests rerun in this documentation task.**

## Capability ledger

| Capability | What exists / source | Evidence scope and remaining gate |
|---|---|---|
| Optical capture and pose | [camera adapter](../../specter/sensors/nightvision/camera.py), [pose backend](../../specter/ml/pose/estimator.py) | Code and synthetic demonstration; no inspected calibrated IMX462 hardware run |
| HUD and provenance | [renderer](../../specter/hud/renderer.py), [Measurement](../../specter/fusion/measurement.py), JSONL event path | Implemented pipeline; sample fields are not a complete validity guarantee |
| DI-188 identification/streaming | Checkpoints [001](../checkpoints/001-hardware-di188.md), [002](../checkpoints/002-alpha001-daq-end-to-end.md) | Recorded hardware integration; analog inputs unconnected |
| CSI acquisition and HUD | Checkpoints [006](../checkpoints/006-alpha002b-csi-integration.md), [010](../checkpoints/010-csi-view-rebuild.md), [011](../checkpoints/011-csi-scientific-validation.md) | Recorded real CSI; display reports RF-path change, not human detection |
| ESP32 supervisor | [protocol](../../specter/sensors/esp32/protocol.py) and simulator | Host support implemented; original image does not emit proposed telemetry at baseline |
| Thermal | [TC001](../../specter/sensors/thermal/tc001.py), [SenXor](../../specter/sensors/thermal/senxor.py) | Helpers / unverified driver; SenXor explicitly `VERIFIED = False` |
| Radar | [TLV parser](../../specter/sensors/radar/tlv.py) | Parser is specific to message/SDK shape; no inspected radar bench acquisition |
| GNSS / IMU / UWB | [NEO-M9N](../../specter/sensors/gnss/neom9n.py), [IMU layer](../../specter/sensors/imu/__init__.py), [DW1000](../../specter/sensors/uwb/dw1000.py) | Source, protocol/math and simulation; real integrated sensor validation not established |
| Team link / localization / association | [messages](../../specter/net/messages.py), [security](../../specter/net/security.py), [EKF](../../specter/localization/ekf.py), [team fusion](../../specter/fusion/team.py) | Implemented prototype and simulated team paths; no field reliability claim |
| Experimental event/acoustic/vitals/gas/VLM/LoRa | [experimental modules](../../specter/sensors/experimental/__init__.py) and neighboring sources | Stubs/templates/simulation; no operational modality validation |
| Depth / LiDAR / full WORLD / AIR / GROUND / satellite | Requested architecture and research tracks | Proposed; no implementation or ownership inferred |

## DI-188: acquisition works; calibrated physical sensing remains open

Checkpoint 001 reports a 1,801.3-second four-channel soak at nominal 500 sample groups/s: 901,080 received groups, 0 malformed, 0 serial errors/disconnects and no measured frame shortfall. The [summary artifact](../checkpoints/001-hardware-di188-stability.json) accompanies that claim. Arrival batching reached roughly 1.1 seconds.

The record supports a clean observed stream with no measured shortfall under that metric. An above-nominal aggregate count alone is not an independent sample-by-sample proof of zero loss. Preserve the exact metric and the original logs when improving the test.

All four inputs were floating. The instrument's stored calibration was firmware defaults; counts-to-volts was nominal, not independently calibrated. A healthy serial link does not establish a valid voltage input. Physical PCB identity, ground reference, common-mode limits and first known signal are still acceptance gates. Follow the existing [wiring note](../di188-wiring.md), then verify the exact assembled board before any connection.

## ESP32-S3: identity and firmware provenance

Checkpoint 004 identifies an ESP32-S3, 16 MB flash and 8 MB PSRAM. Its app descriptor reports `csi_recv_router`, revision `8633d67-dirty`, ESP-IDF v5.2.2 and build date 2026-10-15. The matching public source family is [Espressif esp-csi](https://github.com/espressif/esp-csi). The dirty suffix and unpinned gain-control dependency mean the exact build inputs are not recovered by the revision string alone.

The checkpoint records a full 16,777,216-byte backup and read-back match, SHA-256 `51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0`. This documentation task did not access, restore or independently re-hash that binary. Do not redistribute flash images: embedded network credentials or other private data may be present.

## CSI throughput and reliability: two different failure classes

Checkpoint 006 records 176.37 packets/s integrated versus 178.15 packets/s baseline, approximately 99.0%, over 70 seconds with zero reported gaps/missing/malformed/queue drops. That is a short acquisition comparison on one setup, not a universal performance guarantee or sensing benchmark.

Checkpoint [008](../checkpoints/008-usb-cdc-root-cause-host-drain.md) separates loss under inadequate host draining from much longer silences. A slow-reader arm received 47.8% of produced IDs with 777 gaps and 481 malformed lines; a continuous-reader control received 100% with zero reported errors. Other 50-ms arms were clean, so “50 ms always fails” is unsupported. Continuous draining is the design requirement; hostile-host firmware resilience remains unproven.

Checkpoint 011 records dual capture for 2,400.2 seconds: 184,132 USB CSI lines versus 184,104 UART CSI lines. Synchronized silences and association logs show that the long outages cannot be explained by native-USB delivery alone. The UART log requires **921600 baud**, not 115200. These findings do not erase the separate host-drain loss/wedge behavior.

The upstream router example generates 100 ICMP requests/s to the gateway. **The immediate RF transmitter observed by CSI is the wireless AP/frame source; an IP gateway need not be that physical radio.** About 178 received CSI records/s must not be equated mechanically with 100 successful pings or a particular ACK/echo count without packet-level evidence.

Association transitions and roaming are recorded. The exact campus policy, why CSI can remain absent for roughly 320 seconds after a short reassociation, and whether stale BSSID filtering or ping state is responsible remain unresolved. “AP policy proven” and “device failure excluded in general” overstate the evidence. Move to an owned, controlled traffic source and instrument firmware state in a separate reviewed engineering task.

## Human-motion experiment and statistics

Checkpoint [009](../checkpoints/009-motion-experiment-first-run.md) records the first real experiment; checkpoint 011 reanalyzes it. Nine trials, three per condition, do not establish detection. For `roughness_used` the reported F is 0.909, permutation p 0.532 and held-out accuracy 0.444. Some pairwise estimated effects were large, but these estimates are noisy and selected from a small experiment.

Do not conclude “an effect exists, only power is missing.” A nonsignificant result permits multiple explanations. Planning power from the observed effect is exploratory and may overestimate the effect. Seven repetitions per condition is a planning suggestion, not a guaranteed 80% powered future study. Final sample size should be simulated against a prespecified scientifically useful effect with the actual design, missingness and endpoint selection.

## Historical assertions requiring qualification

| Prior language | Interpretation used in this handbook |
|---|---|
| 60-GHz radar and CSI provide through-wall presence/motion | Task/material/geometry-specific research; no SPECTER-X capability established |
| “Glare-proof” event camera | No optical system is universally immune to saturation/noise; measure the selected device |
| Adding telemetry cannot affect CSI | Shared CPU/output/heap scheduling can affect it; compare before/after |
| A long RF path makes submillimeter motion physically impossible to detect | No such impossibility follows from total path length alone; coupling, bistatic geometry, SNR and multipath matter |
| Respiration requires phase; amplitude cannot work | Amplitude can change with multipath; phase is also valuable but needs clock/offset treatment. Neither establishes feasibility here |
| Null subcarrier positions prove complete parser correctness | A useful consistency check; verify order, sign, scaling, metadata and captured fixtures independently |
| A real link can never have ground truth | Synchronized reference instruments and controlled labels can supply independent truth, with uncertainty |
| A finite synthetic sweep has zero FPR | Zero observed errors needs denominator and interval; simulator validity and held-out real validation remain separate |

No existing historical document was rewritten. The [validation plan](validation.md) defines the stronger evidence required next.

## Concurrent agent boundary

A read-only check of the SPECTER-X OpenCode session found recent activity on a synthetic sweep and a firmware project after the snapshot. A status query reported `running: false` at that instant, while recent messages described ongoing implementation. This is an observation, not a guarantee of completion or inactivity. Those changes are excluded from this baseline; no agent was interrupted or messaged. A later integration review must inspect its final diff and evidence.

The referenced chat reports 251 passing tests. They were **not rerun or independently confirmed here**. No current suite-passing, firmware-build, flashed-supervisor or controlled-link claim is made by this handoff.
