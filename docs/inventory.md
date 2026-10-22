# Hardware inventory

**Last updated:** 2026-10-22

Status vocabulary, used strictly:

| status | meaning |
|---|---|
| **VALIDATED** | exercised on hardware, with a recorded result |
| **RECEIVED / NOT YET TESTED** | physically present, never powered or exercised by this project |
| **NOT RECEIVED** | planned, not in hand |

A component's status is about *this project's* use of it. "Received" is a
statement about the box on the shelf, not about the component working.

---

## Received, validated

| item | status | evidence |
|---|---|---|
| ESP32-S3 dev board (QFN56 v0.2, 8 MB PSRAM, 16 MB flash, MAC `14:c1:9f:26:52:ec`) | **VALIDATED** | checkpoint 014 (identification), 016 (alpha 002 acquisition), 018 (alpha 002-B: 16 MB runtime, WPA2, v3 preflight PASS) |
| iPhone as a SoftAP station | **VALIDATED, with caveats** | checkpoint 015, 018. Associates and produces 10 Hz payload traffic; the earlier cadence failure was confounded by a different traffic app (017 §5) and unattended behaviour is not established |
| Mac (bench host) | **VALIDATED** | host-side capture, scoring and tooling; stayed on the campus network throughout |
| DI188 sensor | **VALIDATED** | checkpoints 001–002 |

## Received, not yet tested

| item | status | notes |
|---|---|---|
| **Carbon-fibre PLA spools** | **RECEIVED / NOT YET TESTED** | Physically arrived. Never printed, dried, measured or mechanically tested. No claim about print quality, stiffness, dimensional accuracy or compatibility with any printer is made or implied. |
| **Newhaven 7-inch display** | **RECEIVED / NOT YET TESTED** | Physically arrived. **Exact model not yet identified.** It presents **Micro-USB** and **DisplayPort** connectors. **No cables are on hand**, so it has not been powered, and nothing has been attempted: no display integration, no driver work, no enclosure change. Its power requirements, input voltage, interface type and pinout are **unknown and must not be assumed** — Micro-USB and DisplayPort on the same unit do not by themselves establish how it is powered or driven. Next step is to read the label/silkscreen and establish the exact part number before any cable or supply is chosen. |
| **Unistellar eVscope** | **RECEIVED / NOT YET TESTED** | Physically arrived. Not powered, not aligned, not connected, no firmware or app interaction attempted. No claim about optical performance, tracking or data access. |

## Not received

| item | status | notes |
|---|---|---|
| Second ESP32-S3 board (control station) | **NOT RECEIVED** | Required for a controlled cadence experiment with a station whose power-save behaviour we control (017 §6, 018 §10.7) |

---

## Rules this file follows

1. **"Received" is not "works".** Nothing moves to VALIDATED without a
   recorded hardware result.
2. **No interface assumptions.** A connector is not a specification. A part
   stays unspecified until its exact model is identified from the unit
   itself, not from a product family or a photograph.
3. **No integration before identification.** The display will not be wired,
   powered or driven until its model and requirements are known.
