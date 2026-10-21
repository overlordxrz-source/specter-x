# DI-188 — analog input wiring, safe first measurement, verification

> **Status: nothing is connected.** All four inputs are floating. Any number
> the software shows today is ADC noise, not a measurement.

---

## 1. What is connected to the Mac

| Property | Value |
|---|---|
| USB device | `Seeed XIAO M0` — the only USB device on the bus |
| VID / PID | `0x2846` / `0x8037` |
| USB version | 2.00 (`bcdUSB` 0x0200) |
| Interface | **CDC-ACM** → virtual COM port, no driver/kext/libusb needed |
| Node | `/dev/cu.usbmodem101` |
| USB serial | `022581D650555233362E3120FF081935` |
| Protocol model | **DI-188, model `188`** (`info 1` → `188`, `info 0` → `DATAQ`) |
| Instrument serial | `022D9B0B` (`info 6`) |
| Firmware / hardware rev | `0` / `0` |

The DI-188 is built on Seeeduino XIAO (SAMD21) hardware and DataQ ships its
firmware as an **open-source project**
([dataq-instruments/Arduino_WinDaq](https://github.com/dataq-instruments/Arduino_WinDaq),
sketch `xiao_windaq`). The constants observed on the wire match that source
exactly, so this unit is running the DI-188 protocol firmware.

**Identity caveat (resolved by a physical check, not by USB):** the instrument's
flash still holds the open-source defaults — calibration key
`0123456789ABCDEF` and calibration date `6214F19E` (the firmware's literal
default). A factory DATAQ unit would carry a real calibration date and key.
The USB descriptor is the stock XIAO M0 one. So this is *either* a factory
DI-188 board running open-source firmware *or* a bare XIAO M0 flashed with it.
**Look for the blue 8-position screw terminal block** — its presence confirms a
DI-188 PCB (and therefore the ±10 V front end); its absence means the inputs
are the XIAO's own 0–3.3 V ADC pads and the ±10 V specs below do not apply.

### Instrument's own digital calibration (read-only, via `readflash`)

| Channel | 0 | 1 | 2 | 3 | 4–7 |
|---|---|---|---|---|---|
| `adc_scale` | 18850 | 18850 | 18850 | 18850 | 18850 |
| `adc_offset` | −78 | −64 | −72 | −84 | 0 |

The firmware applies scale and offset before the counts reach us, so the counts
we receive are already device-calibrated. What is **not** known is how many
volts one count represents — that needs a reference source (§5).

---

## 2. Official electrical specifications

From the DI-188 datasheet and hardware manual.

| Parameter | Value |
|---|---|
| Analog channels | 4, **differential** |
| Full-scale range | **±10 V, fixed** |
| Input impedance | **1 MΩ** |
| Isolation | none |
| Absolute max input | ±30 V peak, continuous (protected) |
| Max common-mode + differential | ±10 V |
| Resolution | 12-bit (2047 counts above zero, 2048 below) |
| System noise | 7.8 mV rms |
| Typical accuracy | ±50 mV @ 25 °C, excluding common-mode error |
| CMRR | 40 dB (dc–60 Hz) |
| Crosstalk | −80 dB |
| Max sample rate | 8 kHz (1 ch), 4 kHz (2 ch), 2 kHz (4 ch) |
| Min sample rate | 0.02 Hz |
| Input connections | one 8-position screw terminal strip |
| Front end (schematic) | AD8554 quad precision op-amp, one differential stage per channel: 1 MΩ series input resistor per leg, 143 KΩ feedback, 100 pF filters, reference from an AD8571 buffer with a 10 Ω trim (`U3`) |
| Input DC path to ground | **none** — only 100 pF capacitors, so a floating input drifts (§5.3) |
| Supply | USB-C, <0.2 W; analog section on `5V_AVCC`, single common GND with the XIAO |

---

## 3. Terminal block map (authoritative)

The 8-position screw terminal block is silkscreened on the board. From the
official hardware manual (page 9, "connect Analog Input Channel 1"):

**Landscape orientation** (terminal strip along the bottom edge, USB-C at the
top — as in the manual's photograph), left → right:

```
   ┌────┬────┬────┬────┬────┬────┬────┬────┐
   │+CH1│−CH1│+CH2│−CH2│+CH3│−CH3│+CH4│−CH4│
   └────┴────┴────┴────┴────┴────┴────┴────┘
     J1  1    2    3    4    5    6    7    8      (J1 = CON8, schematic pin no.)
```

**Portrait orientation** (the strip runs vertically down the left edge, as in
the manual's 4–20 mA figure) — the **same linear order**, running downwards,
with `+CH1` at the top:

```
   ┌────┐
   │+CH1│  ← top
   │−CH1│
   │+CH2│
   │−CH2│
   │+CH3│
   │−CH3│
   │+CH4│
   │−CH4│  ← bottom
   └────┘
```

The block is physically two 4-position screw strips side by side, so it reads
`+CH1 −CH1 +CH2 −CH2 | +CH3 −CH3 +CH4 −CH4` across the bottom edge of the
board. **The silkscreen is printed on the board — trust the board, not this
document, if they ever disagree.**

Cross-reference to the schematic (internal nets, four differential pairs, one
AD8554 stage each):

| Channel | Terminal pair | Internal nets | ADC pin |
|---|---|---|---|
| CH1 | `+CH1` / `−CH1` | AIN1 / AIN0 | AN0 |
| CH2 | `+CH2` / `−CH2` | AIN2 / AIN3 | AN1 |
| CH3 | `+CH3` / `−CH3` | AIN5 / AIN4 | AN2 |
| CH4 | `+CH4` / `−CH4` | AIN6 / AIN7 | AN3 |

Firmware channel numbers are **0-based**: `slist 0 0` = CH1, `slist 1 1` = CH2,
`slist 2 2` = CH3, `slist 3 3` = CH4. The manual's "channel 1" is the
firmware's channel 0.

**There is no GND terminal on the 8-position strip** — it carries four
differential pairs and nothing else. A ground reference has to come from
elsewhere on the board (a Grove/GND pin, the XIAO GND pad, or the USB
shield). This matters: see §5.

---

## 4. How to talk to it on macOS

CDC mode, always. Commands are ASCII, **terminated with CR (0x0D)**, arguments
space-separated. The instrument **echoes what you type while idle**, and stops
echoing while scanning.

```bash
python3 tools/di188.py probe        # identity + instrument calibration
python3 tools/di188.py monitor      # live stats in the terminal
python3 tools/di188.py dashboard    # real-time dashboard in a browser
```

Protocol cheat sheet:

| Command | Effect |
|---|---|
| `info 0` / `info 1` / `info 2` / `info 3` / `info 6` | vendor / model / fw / hw / serial |
| `rchn` | number of channels (4) |
| `slist <pos> <ch>` | scan-list position (sequential from 0) → channel (0-based) |
| `slist` | number of scan-list positions |
| `srate <n>` / `srate` | set sample rate / read the realised rate |
| `eol 0\|1\|2` | terminator CR / LF / CRLF |
| `encode 1` / `encode 0` | ASCII / binary output mode |
| `start` / `stop` | begin / end scanning |
| `read` | one-shot snapshot, comma separated |

---

## 5. Safe first measurement with a known low-voltage source

### 5.1 What you need

| Item | Notes |
|---|---|
| Reference source | **1.5 V alkaline cell** (cheap, ±5 % — good enough to *prove* the channel works, not to calibrate it) or a bench supply set to **1.000 V** |
| Meter | a DMM to read the source to better than 1 % (needed for calibration, not for a smoke test) |
| Two leads | the 8-position strip has no GND terminal (§5.3) |
| Ground reference | *optional for the smoke test, required for a quantitative reading*: a Grove connector (GND on pin 4 of J2/J3/J4) or the XIAO GND pad (pin 13) |

### 5.2 Why this is safe

* The source is ~1.5 V against a ±10 V range — a factor of ~7 below full scale.
* The datasheet states the input is protected to **±30 V peak, continuous**.
  The schematic shows no external clamp network at the terminals, so that
  protection comes from the **1 MΩ series input resistors** (R2/R3, R7/R8,
  R22/R23, R25/R26) plus the amplifier's own clamp diodes — i.e. a fault
  voltage is limited to a few tens of µA before it reaches the front end.
  Either way, 1.5 V is far inside that.
* Input impedance is 1 MΩ (datasheet) and the schematic confirms a 1 MΩ
  resistor in series with each input leg. An alkaline cell's internal
  resistance is a few ohms, so loading is negligible.
* **Common mode is the one thing to get right.** The datasheet states
  *"Maximum common mode + differential voltage: ±10 V"*. A two-terminal
  source that floats relative to the instrument has an **undefined** common
  mode, and the schematic shows the input nodes have **no DC path to ground**
  (only 100 pF capacitors — no resistor ties them to GND). A floating input
  therefore drifts, which is exactly why all four channels currently read
  noise. See §5.3.

### 5.3 Grounding: what the schematic actually provides

Verified against the DATAQ schematic (`DI-188 Schematic.pdf`):

| Ground point on the board | Where | Accessible today? |
|---|---|---|
| XIAO **GND, pin 13** | tied to the board ground through **R21 = 10 Ω** | **No** — the SAMD21 module is a castellated part soldered to the PCB, so its pads are on the underside |
| **Grove connectors** J2 (I2C), J3 (I2C), J4 (UART) | each is a 4-pin CON4 with **GND on pin 4** | **No** — the manual states *"To use these ports, order and install the connector yourself"* (Grove connector, $4.99) |
| USB-C shell | not a signal-ground point in this schematic | **Do not use** |

All the ground symbols in the analog section are the **same net** as the
XIAO's GND, so the ±10 V front end is referenced to that single ground.

**Consequences for the first measurement:**

1. DATAQ's own guidance for a single-ended source (product FAQ) is: *"the best
   practice is to connect the ground wire to the negative input of the
   channel."* So the primary connection is **source − → −CH1**, and nothing
   else is strictly required to make the channel respond.
2. A reference to the instrument's own ground is **only** available with extra
   hardware (a Grove connector, or soldering the XIAO GND pad). Until then the
   common mode is undefined.
3. Therefore the first hookup is a **channel-response smoke test** — it
   proves the channel responds and roughly how it scales — **not** a
   calibrated measurement. Do not calibrate from it.

### 5.4 Wiring diagram — first measurement on CH1

```
   ┌────────────────┐                    ┌──────────────────────────┐
   │  reference     │                    │        DI-188            │
   │  1.5 V cell    │                    │                          │
   │  (or 1.000 V   │   RED  ──────────► │ +CH1                     │
   │   bench supply)│   lead             │  ┌───┬───┬───┬───┐        │
   │                │                    │  │+C1│−C1│+C2│−C2│        │
   │         ┌──────┤                    │  │+C3│−C3│+C4│−C4│        │
   │   BLACK ─┤      │                   │  └───┴───┴───┴───┘        │
   │   lead   │      │                   │                          │
   └──────────┴──────┘                   └──────────────────────────┘

   Measured quantity: V(+CH1) − V(−CH1)  →  CH1 (firmware channel 0)

   No ground connection is made in this first hookup:
     • the 8-position strip has no GND terminal;
     • the board's only ground points are the XIAO GND pad (underside,
       needs soldering) and the Grove connectors' pin 4 (needs a connector);
     • the USB-C shell is not a signal ground.
   Common mode is therefore UNDEFINED for this test - see §5.3.
```

Optional second stage, once a ground point is available: tie the source
negative to the board ground as well (Grove GND on pin 4, or the XIAO GND
pad). That fixes the common mode and makes the reading quantitative. Do not
use the USB-C shell for this.

Rules for this first hookup:

1. **One channel only.** Leave CH2/CH3/CH4 completely unconnected — they stay
   floating and must keep reporting noise.
2. **Positive to `+CH1`, negative to `−CH1`.** Swapping them only inverts the
   reading, it cannot damage anything.
3. **Power the DI-188 over USB first**, then attach the source.
4. **Screw the terminals properly**: strip only the conductor, no insulation
   under the pressure flap, snug but not crushed, then tug gently.

### 5.5 Then verify, in this order

```bash
# 1. before touching anything: all four channels float
python3 tools/di188.py monitor --rate 200
#    expect: CH1..CH4 all UNDECLARED/FLOATING, means ~0, std ~5-10 counts

# 2. attach the source as per the diagram above

# 3. CH1 must move; CH2-CH4 must not
python3 tools/di188.py monitor --rate 200 --connected 0 --source 0=1.5V_cell
#    expect: CH1 CONNECTED, mean ≈ 10 mV if the board is a bare XIAO (0-3.3 V)
#            CH1 CONNECTED, mean ≈ +1.5 V if the board has the DI-188 ±10 V front end
#    expect: CH2-CH4 still FLOATING/NOISE
#    NOTE: without a ground reference this is a SMOKE TEST - the common mode
#          is undefined, so the value is indicative only.

# 3b. add the ground reference (Grove GND pin 4, or the XIAO GND pad) and
#     repeat step 3. The reading should now be stable and quantitative.

# 4. promote it to a calibration (needs the DMM reading AND the ground ref)
python3 tools/di188.py calibrate --channel 0 --reference "1.500 V cell, DMM 1.487 V"
#    then repeat at 0.000 V for a second point, and save
```

The step-3 expectation is itself the physical identity test: a bare XIAO M0
reads ~1.5 V on a 0–3.3 V ADC, a DI-188 with the ±10 V front end reads the
same 1.5 V. The *counts* differ by ~3.3×, which is what tells them apart.

---

## 6. Verification checklist

### A. Software — can be done now, no hardware required

- [ ] `ioreg -p IOUSB -w 0` lists exactly one USB device: `Seeed XIAO M0`,
      `idVendor 10374`, `idProduct 32815`.
- [ ] `/dev/cu.usbmodem101` exists and `/dev/tty.usbmodem101` too.
- [ ] `python3 tools/di188.py probe` prints model `188`, vendor `DATAQ`,
      instrument serial `022D9B0B`, profile `di188_pm10v`.
- [ ] Instrument offsets read back as `[-78, -64, -72, -84]` for CH1–CH4.
- [ ] `python3 tools/di188.py monitor --rate 200` shows 4 channels, all
      `UNDECLARED`, means ≈ 0 and std ≈ 5–10 counts.
- [ ] `python3 tools/di188.py dashboard` shows the amber banner
      **"ALL INPUTS FLOATING / NOISE — values are ADC noise, NOT measurements"**.
- [ ] `python3 tools/di188.py stability --minutes 30` completes and writes a
      JSON report with `frames_received`, `frames_shortfall`, `stall_events`,
      `malformed_lines`, `serial_errors`, `disconnects`.
- [ ] `python3 tools/di188.py record --out /tmp/x.csv` writes a CSV whose header
      contains `# calibration_basis: UNCALIBRATED (nominal)` and a
      `# channel_state ch0 ...: UNDECLARED` line per channel.

### B. Physical — needs the board in hand

- [ ] Board has a **blue 8-position screw terminal block** → it is a DI-188 PCB
      with the ±10 V front end. (No block → bare XIAO M0; the ±10 V specs do
      not apply and the profile must be switched to `xiao_0_3v3`.)
- [ ] Silkscreen reads `+CH1 −CH1 +CH2 −CH2 +CH3 −CH3 +CH4 −CH4` (or the
      same linear order running down the block in the portrait orientation).
- [ ] A ground point is obtainable — **Grove connector pin 4** (J2/J3/J4) or
      the **XIAO GND pad (pin 13)**. The USB-C shell is **not** a signal
      ground. Until one of these is available, treat the reading as a smoke
      test only.
- [ ] Reference source measured with a DMM to better than 1 %.
- [ ] Wiring per §5.4: `+CH1` ← source+, `−CH1` ← source−. CH2–CH4 left
      completely alone.
- [ ] Terminals tight, no insulation under the pressure flap, leads tug-tested.
- [ ] CH1 moves off zero by roughly the expected amount; CH2–CH4 do not.
- [ ] Reversing the source inverts CH1's sign and changes nothing else.
- [ ] **Ground reference added** (Grove GND or XIAO GND pad) before any
      reading is treated as quantitative.
- [ ] Two-point calibration saved to `specter/calibration/di188.json`.
- [ ] Dashboard badge changes to **CALIBRATED** and CH1's volts match the DMM
      reading within the stated uncertainty.
- [ ] A recording taken with the source attached carries a
      `# channel_state ch0 ...: CONNECTED source=...` header.

---

## 7. Known unknowns / blockers

| Blocker | Impact | Status |
|---|---|---|
| No jumper wires, meter, breadboard or test source | no physical verification possible yet | **open** — software-side checks only |
| **No accessible ground point on the board** | the 8-position strip has no GND; the only grounds are the XIAO pad (underside) and the Grove connectors' pin 4 (needs a connector). The USB-C shell is not a signal ground | **open** — until resolved, a reading is a smoke test, not a measurement |
| Board may be a bare XIAO M0 rather than a DI-188 PCB | the ±10 V volts mapping may be wrong by ~3.3× | **open** — resolved by §5.5 step 3 or §6-B first item |
| Instrument has no DATAQ calibration (key/date are firmware defaults) | counts are device-calibrated but volt scale is uncertified | **open** — needs §5.5 step 4 |
| No official Python package for the DI-188 | driver written from the published protocol | resolved in-repo (`specter/sensors/di188/`) |
| ASCII mode has no frame sequence number | dropped frames cannot be counted exactly, and with host-side batching the arrival timestamps cannot resolve frame timing | mitigated — see `stability.py`; binary mode + sync bits would be needed for exact accounting |

---

## 8. References

* DI-188 Protocol — <https://www.dataq.com/resources/pdfs/misc/di-188-protocol.pdf>
* DI-188 Hardware Manual — <https://www.dataq.com/resources/pdfs/manuals/di-188-usb-daq-manual.pdf>
* DI-188 Datasheet — <https://www.dataq.com/resources/pdfs/datasheets/di-188-usb-data-acquisition.pdf>
* DI-188 Schematic — <https://www.dataq.com/resources/pdfs/DI-188%20Schematic.pdf>
* Open-source DI-188 firmware — <https://github.com/dataq-instruments/Arduino_WinDaq>
* MATLAB/macOS CDC examples — <https://github.com/dataq-instruments/Matlab-Example>
* Browser-based WinDaq for macOS — <https://www.dataq.com/products/windaq/indexwwb.html>
