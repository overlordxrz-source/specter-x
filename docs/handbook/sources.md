# Evidence register and external sources

[Hub](../README.md) · **Reviewed 22 October 2026.**

> **Edition 3 reconciliation:** Project intent follows the [canonical charter](north-star.md). Code links below target the Alpha snapshot `933e856`; the `95eae17` [review](alpha-95eae17-review.md) remains the dated record of that earlier state. The Alpha firmware has since been flashed to real hardware and passed a CSI acquisition preflight — see the [verification baseline](verification-baseline.md). *Hardware-validated* there means the acquisition preflight passed. It does not establish motion sensing, sustained unattended reliability, or performance superiority over any alternative.

## Source hierarchy

A saved raw artifact supports what its capture and instrument actually measure. A checkpoint is an account of a run; source code establishes implementation, not physical success. User/agent reports are attributed statements. A manufacturer's specification establishes a part specification, not this assembled system's performance. Research papers establish results under their own apparatus and protocol, not SPECTER validation.

The handbook distinguishes RECORDED HARDWARE / IMPLEMENTED / SIMULATED / REPORTED / PROPOSED / SPECULATIVE / UNKNOWN. Historical numerical results remain recorded claims, not new MEASURED results from this documentation session. Proposed experiments cannot be cited as successful experiments.

## Repository evidence map

Repository artifacts on `main` are linked relatively. Artifacts that exist only
on the Alpha branch are linked as immutable GitHub permalinks pinned to
`933e856fa578a1f923d53016a3aa942cc20ecbab`; that branch is pushed to the
remote, so those links resolve, and the pin means they cannot change under the
reader. The Alpha work is deliberately **not** merged into `main`.

| ID | Artifact | Use and scope |
|---|---|---|
| L01 | [Root README](../../README.md), [LICENSE](../../LICENSE) | Named BOM, software layout, coordinate conventions, MIT baseline and historical claims requiring qualification |
| L02 | [Checkpoint 001](../checkpoints/001-hardware-di188.md), [stability summary](../checkpoints/001-hardware-di188-stability.json) | DAQ identity, recorded streaming metrics, floating inputs, calibration/PCB limitations |
| L03 | [Checkpoint 002](../checkpoints/002-alpha001-daq-end-to-end.md), [acceptance JSONL](../alpha001/alpha001_acceptance_session.jsonl) | DAQ-to-Measurement/HUD/log evidence; not a calibrated analog signal |
| L04 | [Checkpoint 003](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/003-alpha002a-esp32-supervisor.md) | Host supervisor support and real-device telemetry gap |
| L05 | [Checkpoint 004](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/004-esp32s3-hardware-identification.md) | Recorded ESP32 identity/app descriptor and historical backup integrity |
| L06 | [Checkpoint 005](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/005-esp32s3-dispatcher-and-firmware-plan.md), [firmware proposal](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/esp32-firmware-integration.md) | Proposed supervisor firmware; design conflicts retained as open work |
| L07 | [Checkpoint 006](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/006-alpha002b-csi-integration.md) | Short real CSI baseline/integrated comparison |
| L08 | [Checkpoint 007](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/007-usb-stall-diagnosis-and-baselines.md), [008](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/008-usb-cdc-root-cause-host-drain.md) | Evolving USB diagnosis; later controls supersede single-cause interpretation |
| L09 | [Slow poll](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/evidence/expA_slow_poll.json), [continuous control](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/evidence/expB_continuous.json), [poll sweep](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/evidence/poll_sweep_180s.json) | Acquisition controls; not universal host timing guarantees |
| L10 | [Checkpoint 009](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/009-motion-experiment-first-run.md), [motion summary](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/evidence/motion_trial_20261021.json) | First real movement experiment, no verified detection |
| L11 | [Checkpoint 010](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/010-csi-view-rebuild.md) | CSI visualization iteration, not sensing accuracy |
| L12 | [Checkpoint 011](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/011-csi-scientific-validation.md), [dual-capture summary](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/evidence/dual_capture_40min.json) | Association events, synchronized silences, format/statistical analysis; qualifications in new baseline |
| L13 | [Controlled-link design](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/controlled-csi-link.md), [motion design](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/csi-motion-experiment.md), [vitals scope](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/vital-signs-scope.md) | Earlier proposals; physical/statistical statements require the new baseline's qualifications |
| L14 | [Measurement](../../specter/fusion/measurement.py), [messages](../../specter/net/messages.py), [supervisor parser](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/specter/sensors/esp32/protocol.py) | Existing fields and exact compatibility behavior inspected |
| L15 | [Pinmap](../../specter/hw/pinmap.yaml), [rig calibration](../../specter/calibration/rig.json), [frames](../../specter/fusion/coordinate_frames.py) | Design assignments and placeholder/coordinate state; not verified wiring/calibration |
| L16 | [DAQ wiring](../di188-wiring.md) | Existing grounding/common-mode guidance with physical-board questions still open |
| L17 | [Checkpoint 013](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/013-firmware-preflight.md), [flash and rollback design](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/design/flash-preflight-and-rollback.md) | Preflight design, thresholds and the app-only write/rollback plan the hardware session followed |
| L18 | [Checkpoint 014](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/014-first-hardware-validation.md) | The write itself: pre/post hashes, byte-identical bootloader and partition table, boot log |
| L19 | [Checkpoint 015](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/015-phone-station-csi-validation.md) | Phone-as-station validation, the defective subcarrier check, and the measured-versus-hypothesised cadence split |
| L20 | [Checkpoint 016](https://github.com/overlordxrz-source/specter-x/blob/933e856fa578a1f923d53016a3aa942cc20ecbab/docs/checkpoints/016-alpha002-hardware-checkpoint.md) | Consolidated Alpha 002 verdict: what is verified, what is not, and the separately versioned v1/v2 scores |

## Edition 2 primary local sources

The owner’s 22 October 2026 charter instruction establishes canonical intent, not measured capability. Full Alpha commit `95eae1787bfa5a3f09d46bd19ad917874cb80029` was inspected through local Git without merging it. [Alpha reconciliation](alpha-95eae17-review.md) enumerates the exact checkpoint, firmware, dependency, tests and simulated artifacts, plus the 261-test report and its missing independent transcript. This supersedes the first edition’s “recent agent work unreviewed” limitation; physical tests and build reproduction remain outside this handoff.

## Edition 3 primary local sources

Full Alpha commit `933e856fa578a1f923d53016a3aa942cc20ecbab` on
`feature/alpha002-esp32-supervisor` was inspected for this edition and is
pinned by the permalinks above. It supersedes the “not flashed or
hardware-validated” limitation **for the acquisition path only**: the firmware
was written to a real board and passed a 60-second CSI acquisition preflight.
The [verification baseline](verification-baseline.md) records the measured
numbers and, just as importantly, the questions that remain open — motion and
vital-sign detection, sustained unattended reliability and performance
superiority. The test suite stands at 287 passing, 1 skipped.

## Context and inaccessible inputs

- Referenced chat: `6ad7b780-ba94-83e9-a031-4c013ecfe2ac`, “Specter X Project Baseline.” `read_thread` returned six user/assistant turns and no attachments. Assistant replies were opaque content-reference markers, not usable substantive messages. The user-pasted coding-agent result was treated as a report and checked against repository checkpoints where possible.
- SPECTER-X OpenCode session: `ses_ea09a99f5ffe2XZs5SEOSq4vSU`. Read-only recent-message/status check observed post-baseline sweep and firmware work. No instruction was sent and no permissions were answered. Recent agent assertions were not adopted as validated results.
- Supplier CSV: row count and SHA-256 in the [supplier register](suppliers.md); imported as lead data only. The source file's local path is deliberately not published.
- Uploaded parts-status CSV, sponsor correspondence, shipment records and carrier tracking events: unavailable in the accessible sources. Missing inputs remain missing.
- Backup binary, live hardware state, current firmware deployment and latest full-suite outcome: the Alpha branch flashed a board and ran the preflight itself; this documentation edition did not access the device, restore the backup, or re-run the suite. The 287-passing figure is reported by that branch, and its checkpoints carry the raw hashes.

## External factual references

Links below were retrieved or surfaced from primary-source search during this handoff. Manufacturer pages and policies can change; pin versions and save the relevant evidence when an engineering decision depends on them. Brief factual paraphrases are used; no article or paper is reproduced.

| ID | Primary source | Supported use / access note |
|---|---|---|
| E01 | [Espressif esp-csi repository](https://github.com/espressif/esp-csi) | Upstream example family; page retrieved. The pinned `8633d67` tree URL could not be retrieved through the browser tool; exact revision behavior is attributed to local checkpoints, not a new byte-for-byte upstream audit |
| E02 | [ESP-IDF v5.2.2 ESP32-S3 Wi-Fi guide](https://docs.espressif.com/projects/esp-idf/en/v5.2.2/esp32s3/api-guides/wifi.html) | Device-specific modes/CSI API guidance; retrieved. Generic mode support is not a measured SoftAP CSI demonstration |
| E03 | [ESP-IDF framework overview](https://www.espressif.com/en/products/sdks/esp-idf), [Espressif Wi-Fi binary library README](https://github.com/espressif/esp32-wifi-lib/blob/master/README.rst) | Framework/source-license overview and binary radio dependency; surfaced from official sources |
| E04 | [ESP-IDF v5.2.2 OTA](https://docs.espressif.com/projects/esp-idf/en/v5.2.2/esp32s3/api-reference/system/ota.html) | Vendor update mechanisms; retrieved; no SPECTER OTA claim |
| E05 | [DATAQ DI-188 protocol](https://www.dataq.com/resources/pdfs/misc/di-188-protocol.pdf), [DATAQ example repository](https://github.com/dataq-instruments/Matlab-Example) | Manufacturer protocol lead. PDF returned HTTP 403 in this task; specifications/protocol details are attributed to local recorded evidence pending direct access |
| E06 | [TI IWR6843AOP product](https://www.ti.com/product/IWR6843AOP) | 60–64-GHz part identity; retrieved; no penetration/range guarantee for assembled rig |
| E07 | [TI vital-sign demonstration](https://www.ti.com/video/5428037798001), [TI IWR6843 tracking/vitals guide](https://dev.ti.com/tirex/explore/content/radar_toolbox_4_00_00_05/source/ti/examples/Industrial_and_Personal_Electronics/Vital_Signs/Vital_Signs_With_People_Tracking/docs/vital_signs_with_people_tracking_user_guide.html) | Vendor laboratory feasibility and firmware/output context; surfaced from official sources; not SPECTER validation |
| E08 | [FLIR thermal visibility explanation](https://www.flir.com/en-gb/discover/home-outdoor/can-thermal-imaging-see-through-walls/) | Surface imaging / walls / glass limitations; official source surfaced |
| E09 | [NIST UWB location](https://www.nist.gov/ctl/wireless-networks-division/ultra-wideband-location) | Material/building/multipath context; official source surfaced |
| E10 | [NIST microfabricated magnetic gradiometer](https://www.nist.gov/publications/microfabricated-optically-pumped-magnetic-gradiometer) | Concrete atomic magnetic instrument reference; retrieved |
| E11 | [Ambient magnetocardiography preprint, arXiv:2602.14264](https://arxiv.org/abs/2602.14264) | Research lead only; full methodology not audited here; no military or portable remote capability verified |
| E12 | [ESA Sentinel-2 overview](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2?app=true) | Nominal resolution/revisit context; official source surfaced |
| E13 | [OHRP informed-consent FAQs](https://www.hhs.gov/ohrp/regulations-and-policy/guidance/faq/informed-consent/index.html) | Human-subject consent process reference; not study approval |
| E14 | [Ultralytics licensing](https://www.ultralytics.com/license) | Optional dependency/model license review gate; official source surfaced; exact project obligations unresolved |
| E15 | [USPTO provisional application guidance](https://www.uspto.gov/patents/basics/apply/provisional-application) | Disclosure/IP planning reference; not case-specific legal advice |
| E16 | [FAA Part 107 overview](https://www.faa.gov/newsroom/small-unmanned-aircraft-systems-uas-regulations-part-107) | Future US flight-planning reference; no operational permission established |

## Citation maintenance

When updating a measured claim, preserve the old run and link the replacement artifact with its commit, protocol, timestamp and calibration. Resolve contradictions explicitly. Capture exact external versions and access dates when used in a build, experiment or legal decision. A URL's existence does not prove the proposition attached to it. Supplier proof URLs remain unverified lead sources until individually checked.
