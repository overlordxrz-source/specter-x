# SPECTER-X hardware checkpoint 001 — DI-188 USB DAQ

**Date:** 2026-10-21
**Branch:** `feature/di188-usb-daq`
**Hardware connected:** DATAQ DI-188 (open-source DI-188 firmware) on a Seeed
XIAO M0 / SAMD21, over USB CDC-ACM.
**Analog inputs:** none connected — all four channels are floating.

## Checkpoint verdict

| Capability | State | Evidence |
|---|---|---|
| USB enumeration & identification | **VERIFIED** | `Seeed XIAO M0` 0x2846:0x8037, CDC-ACM, `/dev/cu.usbmodem101`; `info 0`→`DATAQ`, `info 1`→`188`, `info 6`→`022D9B0B` |
| Protocol | **VERIFIED** | documented ASCII protocol: CR-terminated commands, idle echo, `slist`/`srate`/`start`/`stop`/`read`, read-only `readflash` calibration |
| Streaming | **VERIFIED** | 30-min soak, 500 Hz × 4 ch: 901 080 frames, **0 lost, 0 malformed, 0 errors, 0 disconnects** (§1.7) |
| Analog measurement | **PENDING** | no source connected; all four inputs floating and reading ADC noise. Needs a known low-voltage source **and** a ground reference |
| Calibration (counts→volts) | **PENDING** | no reference source available; the instrument carries no DATAQ calibration (firmware defaults). Nominal datasheet mapping only, labelled `UNCALIBRATED` |

**Overall: USB / protocol / streaming VERIFIED. Analog measurement and
calibration PENDING.**

Nothing in this checkpoint is a measurement of an external signal. Every
value the software has produced so far is ADC noise from a floating input.

---

## 1. What was established

### 1.1 Detection

`system_profiler SPUSBDataType` returns nothing useful in this environment;
`ioreg -p IOUSB` is the reliable path.

```bash
ioreg -p IOUSB -w 0
#   +-o Seeed XIAO M0@00100000  <class IOUSBHostDevice ...>
```

Exactly **one** USB device is on the bus. There is no separate "DI-188" USB
product string — the DI-188 is built on Seeeduino XIAO hardware and reuses the
XIAO's USB descriptor.

| Property | Value |
|---|---|
| USB product | `Seeed XIAO M0` |
| VID / PID | `0x2846` / `0x8037` (10374 / 32815) |
| `bcdUSB` | 0x0200 (USB 2.00) |
| `bcdDevice` | 0x0104 |
| Interface class | **CDC-ACM** (`AppleUSBACMControl`) → virtual COM port |
| Serial | `022581D650555233362E3120FF081935` (SAMD21 128-bit unique ID) |
| Node | `/dev/cu.usbmodem101` (+ `/dev/tty.usbmodem101`) |

### 1.2 Model identification (protocol level)

The device answers the DI-188 information commands:

```
info 0 -> DATAQ          info 1 -> 188          info 2 -> 0
info 3 -> 0              info 6 -> 022D9B0B     rchn  -> 4
ggrp  -> 21845 (0x5555)  rgain -> 1 1 1 1       slist -> 1 0
```

Every one of those values matches the open-source DI-188 firmware constants in
[`dataq-instruments/Arduino_WinDaq`](https://github.com/dataq-instruments/Arduino_WinDaq)
(`xiao_windaq/dqwindaq.h`: `MODELNUMBER 188`, `SOFTWARE_REV 0`,
`HARDWARE_REV 0`, `dqGainGroup 0x5555`, `dqGain {1,1,1,1}`,
`dqTotalChannel 4`). The device is running the DI-188 protocol firmware.

### 1.3 macOS communication path

The DI-188 is **always in CDC mode** (the DI-2008/2108/4108 family must be
switched from LibUSB/WinDaq mode; the DI-188 never is). macOS's built-in
CDC-ACM driver therefore exposes it as a plain serial device — **no driver, no
kernel extension, no libusb, no `system_profiler` gymnastics.**

* Baud rate is irrelevant on CDC-ACM; 115200 is a placeholder.
* Commands are ASCII, **terminated with CR (0x0D)**, arguments space-separated.
* The instrument **echoes every character typed while idle** and stops echoing
  while scanning. Responses are therefore prefixed by the echoed command; the
  driver strips it.
* `start` never echoes; `stop` always echoes.
* The command buffer is small — never pipeline commands.

### 1.4 Live acquisition verified

```
srate 500      -> device true rate 500.000000
achieved       -> 470.1 sample groups/s over 2.57 s
ch0: n=1210 mean=2.09 std=7.74     (ch1..ch3 equivalent)
```

ASCII stream format confirmed against the official protocol document:
space-separated channel values in scan-list order, CR-terminated.

### 1.5 Link behaviour: the host receives data in ~1 s bursts

The instrument streams on a hardware timer, so it produces frames at a fixed
rate regardless of the host. macOS's CDC-ACM path delivers that data in
**bursts**: the host typically sees a quiet moment of up to ~1 s, then a batch
of frames arrives. Consequences, all of which the stability harness now
separates explicitly:

* **the frame count is exact** — no frames are lost, so a clock-based
  shortfall is the authoritative loss metric;
* **arrival gaps are not stalls** — a gap of a few hundred milliseconds is
  normal batching, not a dropped frame;
* a genuine stall is a gap longer than 5 s during which nothing arrived.

An early version of the harness conflated the two and reported ~1 "stall" per
second on a link that was in fact losing nothing. The metric now reports
`frames_shortfall` (real loss), `burst_gaps` (host-side batching) and
`stall_events` (a real pause) separately.

### 1.6 Bugs found and fixed while building this

| Bug | Symptom | Fix |
|---|---|---|
| `start` echo leaked into the first frame | first line parsed as `start` → counted as a malformed frame | the driver's `start()` records the expected echo and strips it from the head of the stream |
| Echo stripping never matched | responses came back as `info 1 188` instead of `188` | the echoed LF arrives *after* the response, so the prefix to strip is the bare command, not `cmd + "\n"` |
| `ioreg -a` without `-l` omits properties | USB VID/PID read as `null` | use `ioreg -p IOUSB -a -l` |
| `ioreg -a` returns a dict, not a list | USB lookup crashed on `data[0]` | walk the root dict directly |
| Stall metric conflated batching with loss | 124 false "stalls" on a lossless link | see §1.5 |

---

### 1.7 30-minute stability soak — final result

Run: 2026-10-21 17:52:51 → 18:23:02 UTC, 500 Hz, channels 0–3, USB CDC-ACM.
Raw report committed alongside this file as
[`001-hardware-di188-stability.json`](001-hardware-di188-stability.json).

| Metric | Value |
|---|---|
| Duration | 1801.3 s (30.0 min) |
| Requested / realised rate | 500 / 500 Hz |
| **Achieved rate** | **500.2413 Hz (+0.048 %)** |
| Frames received | **901 080** |
| Frames expected | 900 645 |
| **Frame shortfall** | **0 (0.0000 %)** |
| Stalls (> 5 s) | 0 (worst 0.000 s) |
| Arrival bursts (> 10x median) | 4 752, worst 1.099 s — host-side batching, no loss |
| Arrival interval | median 0.002 ms, p95 0.004 ms, max 1099.043 ms |
| Malformed lines | 0 |
| Serial errors / disconnects | 0 / 0 |
| **Verdict** | **NO FRAME LOSS — PASS** |

Two things this settles:

* **The link is sound.** 901 080 frames with not one lost, malformed or
  dropped in half an hour, at four channels and 500 Hz.
* **The "~1 % shortfall" seen in short runs was the device's clock, not
  loss.** Early in a run the cumulative rate read 496 Hz; over the full
  30 minutes it settled at 500.24 Hz — slightly *above* nominal. The
  instrument derives its advertised rate from a nominal timer constant
  (8000 burst/s) while the SAMD21 paces the ADC from its internal 48 MHz RC
  oscillator, which drifts. The effect is a slowly varying rate, not a
  constant loss fraction — which is exactly what the per-window rate spread
  (0.745 %) is there to distinguish.

### 1.8 Grounding instructions re-verified against the schematic

`docs/di188-wiring.md` was corrected after reading `DI-188 Schematic.pdf`
directly:

* The **8-position strip carries no GND** — J1's eight pins map to
  AIN0…AIN7 only. This was already stated; it is now backed by the schematic.
* The board's only ground points are the **XIAO GND pin 13** (tied to the
  board ground through **R21 = 10 Ω**) and **pin 4 of each Grove connector**
  (J2 I2C, J3 I2C, J4 UART). Both need extra hardware: the XIAO is a
  castellated module whose pads are on the underside, and the manual states
  the Grove connectors must be *"order and install the connector yourself"*.
* **The USB-C shell was removed** from the grounding guidance — it is not a
  signal-ground point in this schematic.
* The input nodes have **no DC path to ground** (only 100 pF capacitors), so
  a floating input drifts. That is the physical reason all four channels
  currently read noise rather than a stable zero.
* The ±30 V input protection comes from the **1 MΩ series resistors** plus the
  amplifier's own clamp diodes — no external clamp network is drawn.

Consequence: the first hookup is now explicitly documented as a
**channel-response smoke test, not a measurement**, because with no ground
reference the common mode is undefined.

## 2. What was built

| Path | What |
|---|---|
| `specter/sensors/di188/driver.py` | protocol driver, identity, instrument flash calibration (`readflash`) |
| `specter/sensors/di188/calibration.py` | counts→volts models: nominal (datasheet) and measured (fitted) |
| `specter/sensors/di188/stats.py` | running statistics + input-state labelling |
| `specter/sensors/di188/recorder.py` | CSV recorder with a provenance header |
| `specter/sensors/di188/stability.py` | long-run stability harness (dropped frames, stalls, errors) |
| `specter/sensors/di188/dashboard.py` | real-time monitoring dashboard (stdlib HTTP, no deps) |
| `tools/di188.py` | CLI: `probe` `monitor` `dashboard` `record` `stability` `calibrate` |
| `docs/di188-wiring.md` | terminal map, specs, safe first measurement, checklist |

---

## 3. Honesty constraints enforced

The repo rule is *provenance first*. Concretely, in this subsystem:

1. **Floating inputs are never presented as measurements.** Every channel
   carries a state — `CONNECTED` / `FLOATING` / `UNDECLARED`. The dashboard
   shows an amber banner *"ALL INPUTS FLOATING / NOISE — values are ADC noise,
   NOT measurements"*, and each card is badged `FLOATING / NOISE`.
2. **The volt scale is labelled by its basis.** `UNCALIBRATED (nominal)` means
   "datasheet estimate, no reference source"; `CALIBRATED` means "fitted
   against a named reference", and the reference is printed next to the value.
3. **Undeclared is never silently upgraded to connected.** Software cannot tell
   a 0 V source from a floating input, so `UNDECLARED` stays `UNDECLARED`.
4. **Every recording carries its own provenance header** — instrument model,
   serial, USB VID:PID, port, instrument offsets, calibration basis and
   per-channel connection state.
5. **The instrument's own calibration is distinguished from a real one.** Its
   flash still holds the firmware defaults (key `0123456789ABCDEF`, calibration
   date `6214F19E`), i.e. it was **not** calibrated by DATAQ.

---

## 4. Hardware facts and caveats

* **Terminal strip:** 8-position screw block, silkscreened
  `+CH1 −CH1 +CH2 −CH2 +CH3 −CH3 +CH4 −CH4` (landscape) or the same linear
  order running down the block (portrait). **No GND terminal** — the board's
  only grounds are the XIAO GND pad (underside) and the Grove connectors'
  pin 4, both needing extra hardware. See §1.8.
* **Specs:** 4 differential channels, ±10 V fixed full scale, 1 MΩ input
  impedance, protected to ±30 V, 12-bit (2047/2048 counts), 7.8 mV rms system
  noise, ±50 mV typical accuracy, 8/4/2 kHz max rate for 1/2/4 channels.
* **Firmware channel numbers are 0-based**; manual "channel 1" = firmware
  channel 0.
* **Unresolved:** the USB descriptor is the stock XIAO M0 one and the flash
  holds open-source defaults, so this unit may be a bare XIAO M0 flashed with
  the DI-188 firmware rather than a factory DI-188. A blue 8-way screw
  terminal block on the board settles it. Until then, treat the ±10 V volt
  mapping as unproven.

---

## 5. Open items and remaining limitations

| # | Item | Blocked by | Status |
|---|---|---|---|
| 1 | Physical wiring + first signal | no jumper wires, meter or test source | **open** — software-side checks only |
| 2 | Two-point calibration | needs a reference source with a DMM reading **and** a ground reference | **open** |
| 3 | 30-minute stability run | — | **done** — 901 080 frames, 0 lost, 0 malformed, 0 errors (§1.7) |
| 4 | Confirm DI-188 PCB vs bare XIAO | physical inspection (blue 8-way screw block) | **open** |
| 5 | Quantify the common-mode budget | needs a ground reference; the strip has no GND | **open** |

### Limitations that remain, stated plainly

* **Nothing has been measured yet.** Every number the software has produced
  comes from a floating input and is ADC noise. The instrument is detected,
  identified, streaming and stable — but it has not yet measured a *signal*.
* **The volt scale is unproven.** `UNCALIBRATED (nominal)` assumes the ±10 V
  datasheet mapping. It is right only if this board has the DI-188 front end.
* **The instrument carries no DATAQ calibration** — key `0123456789ABCDEF` and
  calibration date `6214F19E` are the open-source firmware's own defaults, so
  its counts are device-calibrated but its volt scale is uncorrected.
* **Frame accounting cannot be made exact in ASCII mode.** There are no
  sequence numbers, and because macOS delivers CDC-ACM data in ~1 s bursts the
  host timestamps cannot resolve frame timing either. The 30-minute run shows
  no loss, but proving "no loss" in general would need binary mode and the
  WinDaq sync bits.
* **The dashboard is a browser page, not the OpenCV HUD.** It is a macOS bench
  tool; integrating it into the Pi HUD is not done.
* **Only one instrument model is supported.** The DI-2008/2108/4108 family
  needs a LibUSB→CDC mode switch first and a different command set.

---

## 6. Quick reference

```bash
python3 tools/di188.py probe
python3 tools/di188.py monitor --rate 200
python3 tools/di188.py dashboard --rate 200        # http://127.0.0.1:8765/
python3 tools/di188.py record --out runs/di188.csv
python3 tools/di188.py stability --minutes 30
python3 tools/di188.py calibrate --channel 0 --reference "1.500 V cell"
```

Full wiring procedure, safe first-measurement diagram and verification
checklist: [`docs/di188-wiring.md`](../di188-wiring.md).
