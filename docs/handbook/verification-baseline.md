# Software and real-hardware verification baseline

[Hub](../README.md) · **Evidence review of `77abdd0`; no hardware or application tests rerun in this documentation task.**

> **Current Alpha gates (23 October 2026):** this baseline is the `933e856`
> snapshot. For the later Alpha 002-C exploratory result and Alpha 003
> planning, use the [experiment ledger](experiment-ledger.md). Alpha 002-C is
> exploratory positive and replication-pending; Alpha 003 is planned/offline.
> Neither upgrades this baseline's acquisition-only scope.

> **Edition 3 reconciliation:** Project intent follows the [canonical charter](north-star.md). Code links below target the Alpha snapshot `933e856`; the `95eae17` [review](alpha-95eae17-review.md) remains the dated record of that earlier state. The Alpha firmware has since been flashed to real hardware and passed a CSI acquisition preflight — see the [verification baseline](verification-baseline.md). *Hardware-validated* there means the acquisition preflight passed. It does not establish motion sensing, sustained unattended reliability, or performance superiority over any alternative.

## Capability ledger

| Capability | What exists / source | Evidence scope and remaining gate |
|---|---|---|
| Optical capture and pose | [camera adapter](../../specter/sensors/nightvision/camera.py), [pose backend](../../specter/ml/pose/estimator.py) | Code and synthetic demonstration; no inspected calibrated IMX462 hardware run |
| HUD and provenance | [renderer](../../specter/hud/renderer.py), [Measurement](../../specter/fusion/measurement.py), JSONL event path | Implemented pipeline; sample fields are not a complete validity guarantee |
| DI-188 identification/streaming | Checkpoints [001](../checkpoints/001-hardware-di188.md), [002](../checkpoints/002-alpha001-daq-end-to-end.md) | Recorded hardware integration; analog inputs unconnected |
| CSI acquisition and HUD | Checkpoints [006](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/006-alpha002b-csi-integration.md), [010](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/010-csi-view-rebuild.md), [011](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/011-csi-scientific-validation.md) | Recorded real CSI; display reports RF-path change, not human detection |
| ESP32 supervisor | [protocol](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/specter/sensors/esp32/protocol.py) and simulator | Host support implemented; original image does not emit proposed telemetry at baseline |
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

Checkpoint [008](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/008-usb-cdc-root-cause-host-drain.md) separates loss under inadequate host draining from much longer silences. A slow-reader arm received 47.8% of produced IDs with 777 gaps and 481 malformed lines; a continuous-reader control received 100% with zero reported errors. Other 50-ms arms were clean, so “50 ms always fails” is unsupported. Continuous draining is the design requirement; hostile-host firmware resilience remains unproven.

Checkpoint 011 records dual capture for 2,400.2 seconds: 184,132 USB CSI lines versus 184,104 UART CSI lines. Synchronized silences and association logs show that the long outages cannot be explained by native-USB delivery alone. The UART log requires **921600 baud**, not 115200. These findings do not erase the separate host-drain loss/wedge behavior.

The upstream router example generates 100 ICMP requests/s to the gateway. **The immediate RF transmitter observed by CSI is the wireless AP/frame source; an IP gateway need not be that physical radio.** About 178 received CSI records/s must not be equated mechanically with 100 successful pings or a particular ACK/echo count without packet-level evidence.

Association transitions and roaming are recorded. The exact campus policy, why CSI can remain absent for roughly 320 seconds after a short reassociation, and whether stale BSSID filtering or ping state is responsible remain unresolved. “AP policy proven” and “device failure excluded in general” overstate the evidence. Move to an owned, controlled traffic source and instrument firmware state in a separate reviewed engineering task.

## Human-motion experiment and statistics

Checkpoint [009](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/009-motion-experiment-first-run.md) records the first real experiment; checkpoint 011 reanalyzes it. Nine trials, three per condition, do not establish detection. For `roughness_used` the reported F is 0.909, permutation p 0.532 and held-out accuracy 0.444. Some pairwise estimated effects were large, but these estimates are noisy and selected from a small experiment.

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

## Newer Alpha reconciliation — 95eae17

The later [Alpha review](alpha-95eae17-review.md) supersedes the first edition's “agent work not inspected” status. Committed candidate source, sweep evidence and contract tests were inspected read-only at the full pinned commit. Station/SoftAP builds are reported in checkpoint 012; 261 passing tests are reported by the owner from OpenCode. Neither was reproduced here. Firmware remains **not flashed or hardware-validated**. The new candidate does not emit legacy supervisor telemetry. Local code and historical links above remain at `77abdd0`; this docs branch does not contain the newer firmware or tests.

**Superseded on hardware status only.** The section below records what happened at `933e856`, where the firmware was actually written to a board and the preflight was run. The `95eae17` review remains accurate as a record of that earlier snapshot; no statement in it is retroactively edited.

The first edition's 251-test figure referred to the older reported snapshot; it is not the newer Alpha count. Static source checks and a hand-authored parser fixture cannot establish runtime serialization, slow-host survival, SoftAP callback support or physical sensing. The review records qualifications without rewriting Alpha's historical checkpoint or changing engineering source.

## Alpha 002 hardware validation — through `933e856`

**This section supersedes the “not flashed or hardware-validated” status above for
the acquisition path only.** It records a real write to a real board and a real
preflight run. It does not advance the sensing claim, the reliability claim or
any performance comparison. The Alpha work lives on
`feature/alpha002-esp32-supervisor` at `933e856`; it is **not merged into
`main`**, and the evidence links below are pinned to that commit.

Sources: [checkpoint 013](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/013-firmware-preflight.md) (preflight design), [checkpoint 014](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/014-first-hardware-validation.md) (flash and boot), [checkpoint 015](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/015-phone-station-csi-validation.md) (station validation) and [checkpoint 016](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/016-alpha002-hardware-checkpoint.md) (consolidated verdict).

### What was written, and what it proves

| Claim | Evidence | Boundary |
|---|---|---|
| An app-only write at `0x10000` is sufficient | Write plus independent read-back verification; bootloader and partition table byte-identical before and after | The rollback path was verified but never exercised |
| The firmware boots and runs | Boot log from `0x10000`, no abort or watchdog reset | One board, one image, one session |
| SoftAP mode comes up with its own DHCP | `SPECTER-LAB` on channel 6, gateway `192.168.4.1` | The AP is currently **open** (no WPA2) |
| **CSI callbacks fire in SoftAP mode** | Callback counter rises with no station attached, and with a station attached | Callbacks are not calibrated sensing |
| A station associates and is identified | Peer MAC stable across the capture; channel constant, no silent roam | One phone, one AP, one room |

### The acquisition preflight that passed

A 60-second capture with a phone associated and generating a 10 Hz ICMP load against the board's own gateway, scored by `tools/esp32_lab_preflight.py` under scoring v2:

| Metric | Measured | Criterion | Result |
|---|---|---|---|
| CSI frames | 2364 (39.0/s) | — | — |
| Longest inter-packet gap | 0.079 s device-side, 0.224 s host-side | ≤ 1.0 s | **PASS** |
| Gaps > 0.5 s | 0 | — | — |
| Required null subcarriers zero | 2364 / 2364 frames | every frame | **PASS** |
| Active subcarrier coverage | 52 / 52 slots | ≥ 99% | **PASS** |
| Malformed lines | 0 | 0 | **PASS** |
| Sequence gaps | 0 | 0 | **PASS** |
| Device queue drops | 0 | 0 | **PASS** |
| USB vs console byte drift | 0.25% | ≤ 0.5% | **PASS** |
| RSSI / noise floor / channel | −40 dBm / −96 dBm / 6 | in range, one channel | **PASS** |
| Continuity against the offered rate | 394% of 10/s | ≥ 95% | **PASS** |

Two readings of that score, and the difference matters. The continuity metric
compares **all** callbacks to the offered rate, so the station's 28-byte
null-data frames inflate it to 394%. The loss figure that actually matters comes
from the data frames alone: **600 received against 596 expected** at 10 Hz over
59.6 s, i.e. **≤ 0.7%**. The metric passes, but it is not a loss measurement;
splitting it by frame length is an open item.

Cadence is **bimodal, not uniform**: median inter-frame interval 26.9 ms, p95
61.8 ms, and only 50.3% of intervals are under 28.6 ms. The stream is gap-free
but it is not a steady 35 Hz feed, so a 35 FPS HUD cannot be assumed from this
result.

### A defect in the measurement, found and fixed

The first scored run failed its subcarrier check at 79.7% on a healthy link.
The cause was in the **tool**, not the hardware: the check required the set of
non-zero subcarrier slots to equal the 52 used slots exactly, but I and Q are
int8, so a faint active subcarrier truncates to `(0, 0)`. The v2 rule asserts
the structural property instead — every required null slot is zero in every
frame, plus aggregate coverage of all 52 active slots across the capture — and
reports `UNKNOWN` rather than guessing when there are too few frames or when a
v1 capture is replayed. The v1 score was preserved unchanged and is not
comparable to a v2 score. Regression tests use real captured records (one
exact, two with truncated active slots) plus synthetic edge cases. The
repository test suite stands at **287 passing, 1 skipped**.

Two harness defects were found and fixed in the same pass: a parse error raised
out of the CSI parser and killed the reader thread (the run reported 0 packets
while the console path had already captured 102 KB), and bytes that arrived
before the measurement window were being counted as data.

### The station, not the board, caused the silences

The same link, the same firmware and the same offered load produced two very
different results depending only on the state of the phone:

| Station state | Frames in 60 s | Data frames | Longest gap |
|---|---|---|---|
| Awake, traffic app in the foreground | 2364 | 600 | 0.079 s |
| Idle or backgrounded | 17 | 1 | 35.1 s |

The device's own counters show no firmware-side loss in either case
(`drop_old=0`, `drop_new=0`, `q=0`). The mechanism is **not** separated: 802.11
power save with a DTIM schedule and an application being suspended by the
operating system would both produce this shape, and no 802.11 frame capture, no
power-save state readout and no control condition were taken. The silence is
demonstrably phone-side; the reason for it is a **hypothesis**.

### Still unproven at `933e856`

| Question | Status |
|---|---|
| **Motion or vital-sign detection** | **Nothing measured.** No human-subject run, no detection claim, no sensitivity figure |
| **Sustained unattended reliability** | **No.** The one passing run is 60 s with an awake station; the station sleeps when it chooses to |
| **Performance superiority** | **No comparison exists.** No baseline was measured against, so "better" is unsupported |
| A uniform 35 Hz feed | **No.** Cadence is bimodal, median 26.9 ms, p95 61.8 ms |
| SoftAP under WPA2 | **No.** The lab AP is currently open |
| Correct 16 MB flash-size declaration | **No.** The runtime falls back to 2 MB and warns |
| Multi-station behaviour, long soak | **No** |
| Behaviour on a shared campus network | Deliberately not tested; an owned controlled link was used instead |
| Calibrated analog sensing | **No.** The DI-188 inputs were floating throughout the earlier work |
