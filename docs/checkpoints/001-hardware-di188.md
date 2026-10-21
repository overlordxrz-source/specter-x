# SPECTER-X hardware checkpoint 001 — DI-188 USB DAQ

**Date:** 2026-10-21
**Status:** device detected, protocol verified, live acquisition working.
**Hardware connected:** DATAQ DI-188 (open-source DI-188 firmware) on a Seeed
XIAO M0 / SAMD21, over USB CDC-ACM.
**Analog inputs:** none connected — all four channels are floating.

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
  `+CH1 −CH1 +CH2 −CH2 +CH3 −CH3 +CH4 −CH4` (landscape) or
  `+CH1 +CH2 +CH3 +CH4` / `−CH1 −CH2 −CH3 −CH4` (portrait). **No GND terminal**
  — a ground reference must come from elsewhere on the board.
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

## 5. Open items

| # | Item | Blocked by |
|---|---|---|
| 1 | Physical wiring + first signal | no jumper wires, meter or test source |
| 2 | Two-point calibration | needs a reference source with a DMM reading |
| 3 | 30-minute stability run | none — runnable now |
| 4 | Confirm DI-188 PCB vs bare XIAO | physical inspection |

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
