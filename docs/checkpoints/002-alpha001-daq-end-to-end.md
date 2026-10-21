# SPECTER-X checkpoint 002 — Alpha 001, DI-188 end to end

**Date:** 2026-10-21
**Branch:** `feature/alpha001-daq-end-to-end`
**Status:** the DI-188 is now a first-class SPECTER-X sensor — instrument →
`Measurement` → HUD → JSONL. It streams real data. **No analog measurement
has been made yet**: nothing is connected to the inputs, so every channel is
reported as floating noise.

**Alpha 001 goal:** prove the pipeline with a *real* sensor, using only
hardware in hand. The previous session logs in this repo were all synthetic.

---

## 1. What Alpha 001 adds

| Piece | Where |
|---|---|
| `AnalogSource` — background acquisition, bounded snapshots, `Measurement` factory | `specter/sensors/di188/measure.py` |
| `"analog": "ANALOG"` in the sensor-label table | `specter/fusion/measurement.py` |
| `ANALOG` HUD mode: four channel cards, state badges, sparklines, calibration banner | `specter/hud/renderer.py` |
| `--daq {off,di188}`, `--daq-port`, `--daq-rate`, `--daq-channels`, `--daq-log-hz`, `--min-seconds` | `specter/app.py` |
| 15 fake-driver tests + 1 real-device acceptance test | `tests/test_alpha001_daq.py`, `tests/test_alpha001_acceptance_real.py` |

`pyserial` is already a dependency of the DI-188 package; **no new
dependencies were added**. The CI workflow (numpy + opencv-headless + pytest)
is unaffected: the driver imports pyserial lazily and the acceptance test
skips when it is missing.

### The pipeline, end to end

```
DI-188 (USB CDC-ACM)
  └─> AnalogSource thread            asynchronous, bounded
        └─> Measurement(sensor="analog", kind="analog4", frame_id="daq")
              ├─> HUD  : ANALOG mode, FLOATING / NOISE badges
              └─> JSONL: "analog_sample" at ~1 Hz
```

---

## 2. Honesty rules, enforced in code

1. **A floating channel is never a measurement.** `ChannelState` is
   `CONNECTED` / `FLOATING` / `UNDECLARED`; only `CONNECTED` counts as a
   measurement, and software cannot promote `UNDECLARED` on its own.
2. **A floating channel carries no volt value at all.** The stats layer now
   withholds volts unless the channel is `CONNECTED`, so noise cannot be
   dressed up as a measurement by a caller that forgot to check.
3. **Device connectivity is separate from measurement validity.** The health
   row reads `ANALOG DI-188  OK` because the instrument is healthy; the
   channel badges say `FLOATING / NOISE` because nothing is plugged in. A
   healthy device with floating inputs is **not** a fault.
4. **The calibration basis travels with the value**: every measurement
   carries `calibration_basis: "UNCALIBRATED (nominal)"` and the HUD shows
   `CAL: UNCALIBRATED (nominal)` in amber.
5. **No fake confidence.** `Measurement.confidence` is `None`, never a
   number, because nothing here is calibrated.
6. **The event log is rate limited**, ~1 Hz, never one record per ADC sample.

---

## 3. Evidence

Committed under [`docs/alpha001/`](../alpha001/):

| File | What |
|---|---|
| `alpha001_app.png` | the HUD in `ANALOG` mode during a live app run |
| `alpha001_app_session.jsonl` | a full session log: 1284 frames, 12 s, 11 `analog_sample` records (~0.9 Hz) |
| `alpha001_hud.png` | the frame written by the acceptance test |
| `alpha001_acceptance_session.jsonl` | the acceptance test's own session log |

From the app session log:

```
analog_state  {'state': 'CONNECTING', 'detail': '/dev/cu.usbmodem101: identifying'}
analog_online {'state': 'CONNECTED',  'detail': 'DI-188 streaming'}
analog_sample provenance:
  sensor_id  di188-022D9B0B
  source     analog
  algorithm  di188-ascii
  frame_index 78
  notes      floating inputs are noise, not measurements
  confidence None
  value.calibration_basis  UNCALIBRATED (nominal)
  CH1 +CH1 / -CH1 | UNDECLARED | is_measurement=False | counts=-11.0 | volts=None
  CH2 +CH2 / -CH2 | UNDECLARED | is_measurement=False | counts= 6.0 | volts=None
  CH3 +CH3 / -CH3 | UNDECLARED | is_measurement=False | counts= 2.0 | volts=None
  CH4 +CH4 / -CH4 | UNDECLARED | is_measurement=False | counts=16.0 | volts=None
```

Note `volts=None` on every channel: nothing is connected, so there is no
volt value to show. `session_start` records `analog: DEGRADED` (connecting);
`analog_online` follows when the link is up.

---

## 4. Bugs found while building this

| Bug | Symptom | Fix |
|---|---|---|
| **`Serial.read(n)` blocks for the whole port timeout** | every command took ~1 s; the instrument needed 11 s to connect | the driver now only reads what is already buffered (`in_waiting`), so reads never block. Connect time: 11 s → **0.3 s** (measured over 3 runs) |
| **A fixed read window made the identity read flaky** | `info 6` occasionally came back empty → the serial number was missing | replies are now read until they are *complete* (CR, or a few ms of silence) instead of for a fixed window, and the identity query retries |
| `readflash` drained a fixed 2.5 s | 2.5 s of dead time at startup | the drain stops as soon as the 196 bytes have arrived |
| `start` echo leaked into the first frame | the first line parsed as `start` → a false malformed frame | the driver skips the expected echo at the head of the stream |
| `info N` responses came back with the echo attached | `info 1 188` instead of `188` | the echoed LF arrives *after* the response, so the prefix to strip is the bare command |
| `ioreg -a` without `-l` omits properties | USB VID/PID read as `null` | use `ioreg -p IOUSB -a -l` |
| `ioreg -a` returns a dict, not a list | the USB lookup crashed | walk the root dict directly |
| The first `start` frame counted as malformed | a false "malformed line" in every run | skipped with the echo |
| Floating channels still produced a volt value | noise dressed up as a measurement | volts are withheld unless the channel is `CONNECTED` |

---

## 5. Remaining limitations

* **No analog measurement exists.** The instrument is connected and
  streaming, but the inputs are floating. The pipeline is proven; the
  *use* of it is not.
* **No calibration.** The volt scale is the datasheet nominal and is labelled
  `UNCALIBRATED`. A reference source and a ground reference are still needed.
* **The instrument identity is still ambiguous** — the USB descriptor is the
  stock XIAO M0 one, so whether this board has the DI-188 ±10 V front end is
  unproven. The nominal volts-per-count assume it does.
* **Startup latency**: the instrument needs ~0.3 s to connect (open,
  identify, read the flash, configure). The HUD shows `CONNECTING` for that
  window and never blocks on it.
* **One process can hold the serial port.** `tools/di188.py`, the dashboard
  and the app cannot run at the same time; the app reports `BUSY` when the
  port is contended.
* **Raspberry Pi 5 compatibility is untested, not impossible.** An earlier
  draft of this checkpoint claimed the Pi 5 "has no USB host" — that was
  wrong and has been corrected. The Pi 5 has **2x USB 3.0 and 2x USB 2.0
  host ports**, which is exactly what a CDC-ACM instrument needs, and the
  Python side is platform-neutral (pyserial + stdlib). What is genuinely
  unverified is: the `cdc_acm` kernel path and udev rules, the 600 mA
  default USB current limit with a 3 A supply (the DAQ draws well under
  100 mA, so this should be fine), and whether the instrument is practical
  to run from a battery-powered Pi. Until it is tried, the panel must
  degrade to `N/A` on a Pi — the same stub pattern as every other absent
  sensor — but that is a *missing test*, not a proven incompatibility.
* **The optical path is still synthetic** on this machine: the Mac's camera
  is blocked by macOS privacy settings.

---

## 6. Review record (pre-merge)

A review of Alpha 001 was carried out before merging. Findings, all fixed:

| Finding | Fix |
|---|---|
| **The checkpoint claimed "a Pi has no USB host" for the DAQ — false.** The Pi 5 has 2x USB 3.0 and 2x USB 2.0 host ports, which is exactly what a CDC-ACM instrument needs | the claim is corrected in §5 and now distinguishes *untested* from *proven incompatible* |
| Port discovery globbed only macOS node names (`/dev/cu.usbmodem*`) | Linux nodes (`/dev/ttyACM*`, `/dev/ttyUSB*`) and the stable `/dev/serial/by-id/*` names are included, so the Pi gap is hardware/kernel, not code |
| `AnalogSource.stop()` cleared the thread handle before joining, so a `start()` right after a `stop()` could leave two acquisition threads running | the handle is cleared only after the thread is down |
| `status()` took a second snapshot on every HUD refresh | it now accepts the snapshot the caller already has |
| The derived calibration was written from the acquisition thread without the lock | it is now written under the lock |
| The ANALOG view assumed exactly four channels and would overflow the grid with more | the grid draws the first four |
| No test covered the *connected* channel path in the HUD, nor the "volts are withheld from a floating channel" rule | 3 tests added: the connected card is drawn green with no floating styling, the floating card is drawn amber with no green, and volts appear only on the connected channel |

Net effect after the review: **127 tests pass with pyserial, 126 + 1 skip
without it**; the instrument connects in **0.3 s** (measured over three runs).

## 7. Reproducing it

```bash
# fake-driver tests (no hardware, runs in CI)
python -m pytest tests/test_alpha001_daq.py -q

# real-device acceptance test (writes docs/alpha001/)
python -m pytest tests/test_alpha001_acceptance_real.py -q -s

# the whole thing as an app run
python -m specter.app --source synthetic --pose synthetic \
    --daq di188 --mode ANALOG --frames 400 --min-seconds 12 --headless \
    --save-frame docs/alpha001/alpha001_app.png
```
