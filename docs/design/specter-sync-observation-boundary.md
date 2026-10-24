# SPECTER-SYNC Observation boundary

**Status: design only.** No hardware data exists. This document defines how a
future Shrike Lite event counter must enter CORE/WORLD. It uses the existing
Observation v1 contract unchanged.

Canonical schema: `specter.platform.observation.SCHEMA`
(`specter.observation/1.0.0`). See
[engineering contract](../architecture/ENGINEERING_CONTRACT.md) and
[implementation](../../specter/platform/observation.py).

## No second envelope

The adapter must emit:

```json
{
  "schema": "specter.observation/1.0.0",
  "id": "string",
  "node_id": "string",
  "sensor_id": "string",
  "seq": 0,
  "kind": "fpga_event_timestamp",
  "value": {},
  "units": "string",
  "frame_id": "string",
  "origin": "hardware",
  "classification": "measured",
  "acquisition": {
    "domain": "string",
    "epoch": "string",
    "ticks": 0,
    "unwrapped_ticks": 0,
    "tick_hz": 1.0,
    "wrap_bits": 32
  },
  "received": {"domain": "string", "time_ns": null},
  "calibration": {"status": "uncalibrated", "id": null, "reference": null},
  "uncertainty": {"kind": "unknown", "variables": [], "covariance": null},
  "evidence": {
    "level": "recorded_hardware",
    "raw": {"artifact": "string", "sha256": "64-hex", "line": 1},
    "parents": [],
    "algorithm": "shrike-lite-event-counter",
    "revision": "specter-sync-phase0-v1"
  },
  "validity": {"state": "degraded", "flags": []},
  "dropped_before": 0
}
```

This is the shipped Observation shape, not a new JSON schema. Do not invent a
parallel FPGA-event record format for storage or transport.

## Field mapping

| Observation field | Shrike Lite source | Rule |
|---|---|---|
| `schema` | constant | Must equal `specter.observation/1.0.0`. |
| `id` | raw artifact prefix + physical line/index | Stable for the exact raw record. |
| `node_id` | assigned board/asset ID | `shrike-lite-unassigned` is allowed only for pre-identity bench work. |
| `sensor_id` | assigned logical counter source | Suggested `shrike-lite/fpga-event-counter`; stable per node/source. |
| `seq` | FPGA `event_count` or adapter sequence | Must be strictly increasing within an epoch; gaps become `dropped_before`. |
| `kind` | constant | `fpga_event_timestamp`. It is an event tick, not a position, range or human-detection claim. |
| `value` | raw event metadata | May include counter width, nominal clock, pulse source and readout status. Do not add a second measurement envelope. |
| `units` | `"fpga_ticks"` | The value is ticks, not seconds. |
| `frame_id` | `"shrike-lite/fpga-clock"` | Clock-domain label; not a spatial frame. |
| `origin` | `"hardware"` only after a real capture | `simulated` for testbench/offline fixtures; `unknown` for incomplete provenance. |
| `classification` | `"measured"` only for captured hardware ticks | Never promote a synthetic race-free simulation to calibrated time. |
| `acquisition.domain` | `"shrike.fpga.osc50m"` | Nominal 50 MHz oscillator domain. |
| `acquisition.epoch` | one bitstream load/power session | New epoch on reconfiguration, reset or counter discontinuity. |
| `acquisition.ticks` | latched event timestamp | Preserve receiver counter; do not overwrite with host time. |
| `acquisition.unwrapped_ticks` | adapter unwrap of the 32-bit counter | Explicit modulo reconstruction; preserve a reset boundary. |
| `acquisition.tick_hz` | nominal `50_000_000.0` until calibrated | Mark as nominal in validity flags. |
| `acquisition.wrap_bits` | `32` | Counter wraps at nominal ~85.9 s. |
| `received.domain` | `"rp2040.usb-readout"` | Readout time is separate from event time. |
| `received.time_ns` | host/RP2040 readout timestamp | Missing remains `null`; never infer event time from readout. |
| `calibration` | uncalibrated until reference measurement | No invented frequency correction. |
| `uncertainty` | unknown until repeated/reference measurements | No invented covariance or confidence. |
| `evidence` | raw capture/hash/line | The raw CSV/artifact remains primary; the Observation points to it. |
| `parents` | none for the raw tick | Derived event intervals may name parent observations later. |
| `validity` | degraded until clock/readout validation | Suggested flags: `oscillator_uncalibrated`, `readout_unverified`, `clock_unsynced` when applicable. |
| `dropped_before` | event-count delta − 1 | Never hide missed events. |

## Time meaning

- The FPGA counter is the acquisition clock. It is not a host timestamp and is
  not synchronized to UTC or PTP.
- The RP2040 readout time is **received** time, not event time.
- Absolute time requires an external reference/frequency calibration and an
  explicit mapping. Do not subtract unrelated device clocks.
- The nominal 50 MHz oscillator is not a calibrated frequency. A nominal
  `20 ns` tick is not a claimed timing accuracy.
- A counter wrap is not a new event. An epoch reset, reconfiguration or
  unexplained discontinuity must create a new `epoch`.

## WORLD gating

WORLD may consume only validated Observation records through the existing
platform registry/replay boundary. It must not import FPGA code or read the
bench CSV directly. Until calibration and repeatability are established, the
capability remains gated and labelled uncalibrated/degraded.

## Raw artifacts

The bench CSV is a raw artifact with its own SHA-256 and immutable line
references. It is not a replacement for Observation v1. The adapter export is a
projection of raw data into the canonical contract; it does not erase the raw
source.
