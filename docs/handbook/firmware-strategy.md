# First-party firmware strategy built on ESP-IDF

[Hub](../README.md) · **PROPOSED strategy; documentation only.**

## Recommendation

Own a small modular SPECTER device application on ESP-IDF, starting with the known Espressif CSI example and preserving its provenance. Own device identity, telemetry, configuration, capture policy, recovery and a documented transport. Keep the vendor radio stack and proven low-level drivers until a measured requirement justifies replacement.

[ESP-IDF](https://www.espressif.com/en/products/sdks/esp-idf) is Espressif's development framework; most components are available as source under Apache 2.0. Some [Wi-Fi libraries are binary components](https://github.com/espressif/esp32-wifi-lib/blob/master/README.rst). First-party application firmware does not imply ownership or source availability for the complete radio stack. Ferret is a separate effort; no Ferret code, licensing or hardware compatibility is assumed here.

## Proposed component boundaries

| Component | Responsibility | Acceptance evidence |
|---|---|---|
| board support | Pin/USB identity and board revision, safe boot defaults | Exact schematic and target manifest |
| capture | CSI callback copies bounded data with sequence/time and returns promptly | Callback latency and overflow counts under load |
| record queue | Bounded whole-record transfer to one writer | Stress, peak packet size and measured memory use |
| transport | One serialized output path; distinguish data from logs/control | No torn records; counted loss; recovery after backpressure |
| supervisor | HELLO, uptime/boot, health, queue and radio diagnostics | Real telemetry, liveness during CSI absence |
| radio session | Owned network configuration, association/BSSID/channel changes and traffic lifecycle | Controlled-link test and recovery record |
| configuration | Versioned local settings, bounded traffic rate, credential separation | Invalid config fails visibly, secrets excluded from logs |
| diagnostics | Reset reason, callback age, heap trend, drop counters | Attributable faults in hostile-host tests |
| update/recovery | Reproducible builds and reviewed recovery path | Build hashes, approved bench acceptance and later rollback validation |

The [earlier firmware proposal](../design/esp32-firmware-integration.md) contains contradictory overflow priorities and a `STAT` shape beyond the current parser. Resolve those before implementing against it. A task calling a print function once per second is not sufficient assurance against interleaving or blocking.

## Build versus reuse

Reuse ESP-IDF/FreeRTOS, supported USB/UART APIs, vendor drivers and maintained sensor SDKs. Wrap them behind SENSE contracts. Build first-party code when it supplies missing observability, reproducibility, control or integration. Rewrite a driver only when its defect is reproduced, the hardware protocol is documented, licensing permits the work and a reference comparison exists. “Proprietary” is a distribution/licensing choice, not a performance property.

## Migration gates

1. Preserve current image metadata and private backup provenance; recover exact source/dependency versions where possible. The dirty delta is still unknown.
2. Create a reproducible source/build manifest: target, IDF and compiler versions, dependency lock, configuration hash, partition layout and component licenses. Start compatibility work against v5.2.2; evaluate upgrades separately.
3. Freeze the legacy wire fixtures and [ICD](interfaces.md); decide additive versus new-version telemetry explicitly.
4. Build and inspect a candidate in the coding agent's engineering branch. A successful build only proves compilation.
5. Separately review source and authorize a hardware-write session. This docs task performs no flash or deployment.
6. After an authorized installation, compare capture and integrated workload before/after, including hostile-host tests, radio outages, resets and timing wrap.
7. Roll out to additional units only after repeatable device-specific acceptance and recovery evidence.

## Performance targets are conditional

Retain the existing proposal's ≥99% matched-baseline CSI throughput as a candidate criterion on an owned controlled link; avoid using the campus link's average rate as a universal target. Require zero malformed lines and no unexpected gaps under nominal continuous drain. Under overload permit counted drops while preserving device liveness and whole records. Compare observed gaps against producer/drop counters with explicit measurement windows; they need not match instantaneously because data and telemetry have different delays.

Size queues for the maximum valid record, not the first observed 128-byte CSI payload. Measure processing time, memory high-water marks and end-to-end age with UI load. A fixed delay per output record can limit throughput and must be benchmarked. Define whether health/control records have reserved capacity; document that tradeoff once.

OTA, secure boot and flash encryption are later design work, not automatic improvements to enable now. Some security provisioning is irreversible. [ESP-IDF OTA documentation](https://docs.espressif.com/projects/esp-idf/en/v5.2.2/esp32s3/api-reference/system/ota.html) provides mechanisms; SPECTER still needs its own reviewed key, recovery and update policy.
