# Alpha 95eae17 — documentation reconciliation

[Hub](../README.md) · [Canonical charter](north-star.md) · **Read-only source review, 22 October 2026.**

## Snapshot and scope

Reviewed local Git commit **`95eae1787bfa5a3f09d46bd19ad917874cb80029`** on `feature/alpha002-esp32-supervisor`. It changes 19 files relative to `77abdd0`, including controlled-link firmware, synthetic sweep evidence, a console tool and firmware contract tests. The source checkout was clean at inspection. The separate docs branch remains based on `77abdd0`; no code, test, firmware or Alpha history was copied or merged into it.

For offline inspection, use `git show 95eae17:<path>` in either linked checkout. The immutable source links below use the configured GitHub remote; local Git objects were inspected, and remote availability of this commit was not tested. No push was performed.

## What the newer milestone establishes

| Item | Evidence and status | What it does not establish |
|---|---|---|
| Controlled-link candidate exists | **IMPLEMENTED source:** `firmware/esp32-csi/softap_csi/`, station and SoftAP configuration paths | Successful boot, association, capture or sensing on either candidate image |
| Station and SoftAP images built | **REPORTED BUILD:** checkpoint 012 lists IDF v5.2.2, binary sizes and truncated hashes | Reproduced build, full artifact verification or deployed firmware |
| 261 passing tests | **REPORTED TEST RESULT:** owner’s update attributes this count to OpenCode | A fresh test run or a committed complete test transcript inspected here |
| Contract checks added | **IMPLEMENTED tests:** `tests/test_firmware_contract.py`, ten test functions; source-pattern assertions plus a host-parser example | Execution of compiled C, real serial output, concurrency/overload safety or complete protocol compatibility |
| Synthetic sweep saved | **SIMULATED recorded artifacts:** seeded JSON/CSV, seven effect settings, twelve runs each | A physical sensitivity threshold, real-link FPR or human detection |
| Hardware installation | **NOT FLASHED / NOT HARDWARE-VALIDATED**, as reported by checkpoint and owner | No claim of a new working device image; no hardware access performed here |
| SoftAP CSI | **UNKNOWN:** candidate callback counter is a proposed diagnostic | Compile success does not establish mode-specific callback functionality |
| Supervisor telemetry | Candidate uses `SPECTER_STAT`; it does not emit legacy `HELLO` / `STAT` / `HB` | The original host-supervisor integration milestone is not completed by this candidate |

## Source-supported changes versus remaining validation

The candidate copies CSI data/metadata into a bounded FreeRTOS queue and moves formatting out of the callback. Queue code attempts drop-oldest and counts old/new drops. These are implemented design choices, not demonstrated cures for the earlier USB wedge. Queue pop counters are not independently verified physical delivery counts.

The older plan to extend five-field `STAT` remains incompatible with the existing parser. Alpha avoids that particular collision by emitting a separate `SPECTER_STAT` diagnostic tag. This does not make those diagnostics parsed supervisor measurements; a future interface review must specify how they are consumed and versioned.

The checkpoint describes one serialized writer, but inspected `app_main.c` contains both `writer_task` and `status_task` writing to stdout; the contract test explicitly permits both. Whole-record atomicity across task output and terminators therefore remains a runtime/source-review gate, not a proven property. Verify emitted framing against the actual parser before declaring byte-identical wire compatibility.

The dependency manifest permits `esp_csi_gain_ctrl >=0.1.4`; it does not pin exact equivalence to the original image's unknown dependency or dirty delta. Reproducibility and gain behavior remain checks. Keeping a station-role fallback is sensible, but this newly built station image has not itself been demonstrated on hardware.

A zero SoftAP callback count is an unsuccessful observation under one configuration. Check association, peer filtering, qualifying traffic, CSI enablement and counters before drawing a platform-support conclusion. A callback count above zero establishes callbacks under tested conditions; it does not establish calibrated sensing.

## Synthetic evidence and its limits

The committed CSV records zero detected effects in twelve null experiments, mean held-out accuracy 0.5208 at the null, and detection rate 0.9167 at the simulator's effect parameter 0.2. These are reported simulated outcomes from the saved artifact, not newly reproduced measurements. Zero of twelve is not evidence of a universally zero FPR; the effect parameter is not a calibrated human displacement or real RF sensitivity.

The newer checkpoint retracts the older interpretation that large-looking pairwise effect estimates establish a real effect. Preserve the narrower conclusion: the first real motion experiment has **no verified detection**. Its data and estimates still exist; “measured nothing” is too broad. A synthetic null band cannot be transferred as the exact null distribution of a different real link/statistic/design without validation. Trial counts and power remain protocol-specific planning questions.

## Immediate gates

1. Review candidate framing, output concurrency, counters and dependency manifest against the [ICD](interfaces.md); preserve tests as source/fixture checks, not runtime proof.
2. Preserve private backup provenance and reproducible build artifacts; no hardware write is authorized by this review.
3. In a separately authorized hardware session, establish boot, controlled association/traffic, callback behavior, emitted record validity and outage/slow-host recovery before a sensing experiment.
4. Then perform randomized, independently referenced motion experiments with held-out sessions and explicit missingness. Respiration, cardiac sensing and through-obstruction tasks remain separate later research gates.

## Exact sources inspected

- [Checkpoint 012](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/docs/checkpoints/012-alpha002-controlled-rf-research.md): reported build/status and interpretation.
- [Firmware README](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/firmware/esp32-csi/softap_csi/README.md): roles, unflashed state and separate diagnostic protocol.
- [Firmware contract tests](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/tests/test_firmware_contract.py): scope of source assertions and host fixture.
- [app_main.c](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/firmware/esp32-csi/softap_csi/main/app_main.c), [queue](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/firmware/esp32-csi/softap_csi/main/dq_ring.c), [formatter](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/firmware/esp32-csi/softap_csi/main/csi_output.c), [dependency manifest](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/firmware/esp32-csi/softap_csi/main/idf_component.yml): implementation details and remaining acceptance gates.
- [Synthetic CSV](https://github.com/overlordxrz-source/specter-x/blob/95eae1787bfa5a3f09d46bd19ad917874cb80029/docs/checkpoints/evidence/synthetic_sweep.csv) and companion JSON in the same directory: saved simulated results.
- Owner's current charter request: canonical intent, latest reported commit, 261-test report and not-flashed/not-hardware-validated boundary. No independent test transcript supplied with that request.
