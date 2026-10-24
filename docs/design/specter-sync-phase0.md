# SPECTER-SYNC Phase 0 — Shrike Lite hardware timing module

**Status: PLANNED / UNVALIDATED.** The owner reports that a Vicharak Shrike Lite
board has been physically received. It has not been powered, inspected,
connected to external signals, flashed or measured. No timing accuracy claim
exists.

This is an offline design and software-only preparation branch. It is not a
validated sensor, clock, calibration or field capability.

## 1. Manufacturer facts and unresolved identity

The manufacturer identifies **Shrike Lite** as an RP2040 microcontroller plus a
Renesas ForgeFPGA SLG47910 board. The board family also includes Shrike
(RP2350) and Shrike-fi (ESP32-S3); this document concerns only Shrike Lite.

### Exact identities still UNKNOWN

- **Received board revision: UNKNOWN.** Vicharak’s public hardware tree
  contains Shrike-Lite design revisions `v1_r0.4` and `v1_r0.5`. The public
  demo bitstreams are under `test/bitstreams/v1_4`. These labels are not enough
  to identify the physical board. Read the board silkscreen and photograph the
  received unit before selecting any firmware or bitstream.
- **Board serial/asset ID: UNKNOWN.**
- **Installed FPGA/RP2040 revisions, oscillator tolerance and regulator
  markings: UNKNOWN.**
- **J3 population: UNKNOWN.** The KiCad v1_r0.4 and v1_r0.5 PCB sources label
  the 2×6 J3 footprint value `DNP` while routing it as a PMOD-style header.
  Confirm whether the received unit has J3 populated before using it.
- **Per-pin current limits, absolute maximum external loads and protection
  topology: UNKNOWN from the Shrike documentation.** Do not attach external
  loads until the schematic, regulator and FPGA I/O constraints are reviewed.

### Manufacturer specifications (as published)

| Property | Published value | Status |
|---|---|---|
| MCU | RP2040, dual Arm Cortex-M0+, up to 133 MHz, 264 KB SRAM | manufacturer docs |
| Board flash | 4 MB QSPI, W25Q32JV | manufacturer docs |
| FPGA | Renesas SLG47910 ForgeFPGA | manufacturer docs |
| Logic | 1120 LUTs; board docs say “5-input”, Renesas product page says “6-input, 2-output” | vendor wording discrepancy; resolve against exact part data |
| FPGA memory | 1120 DFFs, 5 kb distributed memory, 32 kb BRAM | Renesas product page |
| FPGA clock | 50 MHz internal oscillator, PLL | Renesas product page |
| FPGA supplies | VDDIO 1.71–3.465 V, VDDC 1.1 V ±5% | Renesas datasheet |
| Board logic I/O | 3.3 V compatible | manufacturer docs |
| Board power | USB-C 5 V or 5 V header; never both simultaneously | manufacturer docs |
| Headers | 23 MCU GPIO, 14 FPGA GPIO, 6-bit FPGA–MCU link, PMOD-style connector, 2 LEDs | manufacturer docs |
| User LEDs | RP2040 GPIO4; FPGA GPIO16 | manufacturer docs |
| Programming | RP2040 via Arduino/MicroPython/CircuitPython/C SDK; FPGA via Renesas Go Configure | manufacturer docs |

Sources (retrieved 24 October 2026):

- [Shrike hardware overview](https://vicharak-in.github.io/shrike/hardware_overview.html)
- [Shrike pinouts](https://vicharak-in.github.io/shrike/shrike_pinouts.html)
- [Shrike tools setup](https://vicharak-in.github.io/shrike/tools_setup_guide.html)
- [Shrike bitstream generation](https://vicharak-in.github.io/shrike/generating_your_first_bitstream.html)
- [Shrike CLI guide](https://vicharak-in.github.io/shrike/shrike_cli_guide.html)
- [Shrike repository](https://github.com/vicharak-in/shrike)
- [Renesas SLG47910](https://www.renesas.com/en/products/slg47910)
- [Renesas Go Configure Software Hub](https://www.renesas.com/en/software-tool/go-configure-software-hub)

Local manufacturer reference checkout used for this design:
`vicharak-in/shrike` commit `2186d6b` (shallow clone). Hardware schematics:
`hardware/shrike-lite/kicad/v1_r0.4/` and `.../v1_r0.5/`.

## 2. Exposed headers and FPGA–MCU link

These maps are transcribed from the v1_r0.5 KiCad PCB. The v1_r0.4 maps are
identical for J2/J3/J4. **Verify against the physical board and its silkscreen
before making any connection.**

### J2 — 1×19 header

| Pin | Net | Pin | Net |
|---:|---|---:|---|
| 1 | VUSB/5 V | 11 | RP2040 GPIO14 |
| 2 | 3.3 V | 12 | RP2040 GPIO15 |
| 3 | RP2040 GPIO5 | 13 | GND |
| 4 | RP2040 GPIO6 | 14 | FPGA F17 |
| 5 | RP2040 GPIO7 | 15 | FPGA F18 |
| 6 | RP2040 GPIO8 | 16 | FPGA F0 |
| 7 | RP2040 GPIO9 | 17 | FPGA F1 |
| 8 | GND | 18 | FPGA F2 |
| 9 | RP2040 GPIO10 | 19 | FPGA F7 |
| 10 | RP2040 GPIO11 |  |  |

### J4 — 1×19 header

| Pin | Net | Pin | Net |
|---:|---|---:|---|
| 1 | VUSB/5 V | 11 | RP2040 GPIO22 |
| 2 | 3.3 V | 12 | RP2040 GPIO21 |
| 3 | RP2040 GPIO29 | 13 | GND |
| 4 | RP2040 GPIO28 | 14 | RP2040 GPIO20 |
| 5 | RP2040 GPIO27 | 15 | RP2040 GPIO19 |
| 6 | RP2040 GPIO26 | 16 | RP2040 GPIO18 |
| 7 | GND | 17 | RP2040 GPIO17 |
| 8 | RP2040 GPIO25 | 18 | RP2040 GPIO16 |
| 9 | RP2040 GPIO24 | 19 | GND |
| 10 | RP2040 GPIO23 |  |  |

### J3 — 2×6 PMOD-style header (population UNKNOWN)

| Pin | Net | Pin | Net |
|---:|---|---:|---|
| 1 | 3.3 V | 7 | FPGA F11 |
| 2 | 3.3 V | 8 | FPGA F10 |
| 3 | GND | 9 | FPGA F13 |
| 4 | GND | 10 | FPGA F12 |
| 5 | FPGA F9 | 11 | FPGA F15 |
| 6 | FPGA F8 | 12 | FPGA F14 |

The PCB value is `DNP`; do not assume J3 is populated. It is not used by the
first proof-of-life or timing design.

### FPGA–MCU interconnect

| FPGA package pin | RP2040 pin | Function |
|---:|---:|---|
| EN | GPIO13 | FPGA enable |
| PWR | GPIO12 | FPGA power/control |
| 3 | GPIO2 | configuration SPI clock |
| 4 | GPIO1 | configuration SPI chip-select |
| 5 | GPIO3 | configuration SPI SI/MOSI |
| 6 | GPIO0 | configuration SPI SO/MISO |
| 18 | GPIO14 | direct GPIO link (default 0 Ω populated) |
| 17 | GPIO15 | direct GPIO link (default 0 Ω populated) |

The SPI/control pins and the two direct GPIO links are used for configuration
and internal board communication. Do not attach external signals to J2 pins
11, 12, 14 or 15 or to the corresponding header positions.

## 3. Electrical and power boundaries

- **All GPIO and PMOD signals are 3.3 V logic, not 5 V tolerant.** A 5 V input
  may permanently damage the RP2040 or FPGA.
- Power from USB-C **or** the 5 V header, never both simultaneously.
- Do not source external loads from header 3.3 V/5 V rails until regulator,
  current and thermal limits are established.
- Floating FPGA inputs are not valid logic levels. Every future input must be
  driven or terminated intentionally.
- No external signal is to be connected in this phase. No board power-up,
  flashing or probing is authorized by this document.
- The RP2040/FPGA each have their own programming path; FPGA OTP programming is
  irreversible. Future work must use the SPI/MCU bitstream path and must not
  select an OTP option without a separate reviewed procedure.

## 4. Practical Apple Silicon macOS support

### RP2040 side — expected native macOS path

- Arduino IDE 2 with the Earle Philhower RP2040 core is the board’s documented
  path.
- The vendor MicroPython/CircuitPython UF2 images and Thonny/mpremote are also
  documented. These are macOS-usable; no Linux requirement is known.
- The board uses native USB CDC; no third-party serial driver is assumed.

### FPGA side — the practical uncertainty

- Bitstream generation requires **Renesas Go Configure Software Hub** and its
  ForgeFPGA Workshop. Renesas publishes a macOS 11+ installer and lists
  SLG47910 support.
- The public requirement page does not explicitly state native Apple Silicon
  support. **Native arm64 execution is UNVERIFIED.** If the macOS build fails
  or is Intel-only, options are Rosetta 2, a Linux/Windows VM with USB
  passthrough, or a separate x86 machine. That must be tested on the actual
  Mac before relying on this path.
- Go Configure requires a Renesas account/login. It is not a fully offline
  first-run tool.
- Verilog simulation can be done offline with Icarus Verilog/GTKWave (software
  only). It does not replace synthesis or board validation.
- The community `shrike-gen` CLI is not the official path and is not used here.
  It depends on binaries shipped inside Go Configure and carries its own
  compatibility risks.

### Official workflow summary (do not execute yet)

1. Identify board revision from the physical silkscreen; choose matching UF2
   and bitstream only after review.
2. RP2040 proof-of-life: install the matching Shrike MicroPython UF2, then
   `mpremote run firmware/shrike_lite/rp2040/heartbeat.py`.
3. FPGA proof-of-life: open a ForgeFPGA SLG47910 project in Go Configure, load
   `firmware/shrike_lite/fpga/proof_of_life/main.v`, synthesize, map the clock
   and GPIO16 in the IO Planner, then generate the bitstream.
4. The generated `FPGA_bitstream_MCU.bin` is copied to the RP2040 filesystem
   and loaded with the vendor `shrike.flash(...)` helper. Do not use OTP.
5. Only after the two independent proof-of-life checks pass should the event
   counter and readout be attempted.

## 5. Proof-of-life examples

- `firmware/shrike_lite/rp2040/heartbeat.py` — MicroPython GPIO4 heartbeat and
  UART/USB console message. This is the MCU-only check.
- `firmware/shrike_lite/fpga/proof_of_life/main.v` — minimal 50 MHz counter
  toggling the FPGA user LED on F16. It follows the manufacturer’s top-module
  and output-enable conventions.
- Neither example has been flashed or executed. No bitstream is committed.

## 6. First event-timestamp experiment

### Goal and non-claim

Measure whether a known pulse train produces consistent FPGA tick timestamps
and whether the RP2040 can read them reproducibly. This is **not** a claim of
absolute time accuracy, oscillator calibration, event-detection accuracy or
external synchronization.

### Design

- FPGA clock: internal 50 MHz oscillator. Nominal tick `20 ns`; frequency
  tolerance and drift are **UNKNOWN** until measured against a reference.
- 32-bit free-running counter. At nominal 50 MHz it wraps every ~85.9 s;
  trials stay below 60 s and the analyzer flags modulo deltas.
- Event input: one 3.3 V CMOS input on FPGA **F1** (J2 pin 17).
- Input conditioning: 3-stage synchronizer and rising-edge detector in the
  FPGA. The external pulse must have a high and low width of at least 1 µs
  (recommended for the first run; the synchronizer samples at 20 ns nominal,
  but the external source’s edge quality is unverified).
- On each event, latch the counter and increment a 32-bit event count.
- Readout: two internal wires already routed by the board:
  - FPGA **F18** input read clock ← RP2040 **GPIO14**;
  - FPGA **F17** output serial data → RP2040 **GPIO15**.
  `J2` pins 11/12/14/15 are not to be used for external wiring.
- Readout protocol: after ≥1 ms idle, the FPGA reloads a 64-bit snapshot
  `{event_count[31:0], last_timestamp[31:0]}`. The RP2040 toggles 64 read
  clocks and samples the data line while the clock is low, MSB first. No
  command path, FIFO or vendor-specific packet is invented.
- The snapshot is coherent because both event registers update on the same
  50 MHz edge and the shift register is loaded only while idle.

### Known pulse source

Two stages, both future and both requiring electrical review:

1. **Loopback characterization:** a jumper from RP2040 GPIO6 (J2 pin 4) to
   FPGA F1 (J2 pin 17), with the RP2040 generating a known low-rate pulse
   train. This checks wiring, edge capture, count and readout. It is not an
   independent timing reference.
2. **External reference:** a 3.3 V CMOS pulse generator or counter reference at
   F1. This is required before any absolute timing claim. The source must be
   reviewed for voltage, ground, drive and edge-rate compatibility.

### Measurement procedure (after authorization)

1. Use USB power only; never connect the 5 V header and USB together.
2. Verify the board revision and pin continuity before applying signals.
3. Load only the reviewed MCU/FPGA examples; do not use OTP.
4. Confirm the MCU heartbeat and FPGA LED separately.
5. Connect the internal F17/F18 readout only; no external signals first.
6. Confirm the 64-bit readout is stable and that event count increments.
7. Apply the reviewed pulse source at F1; capture the RP2040 CSV log.
8. Analyze with `tools/shrike_timing.py`.
9. Record board revision, bitstream hash, firmware hash, source settings,
   supply, temperature and all raw data. Preserve failures.

### Acceptance for prototype function (not accuracy)

- event count increments exactly once per observed pulse;
- timestamp is monotonic for increasing event counts (modulo 2^32);
- no duplicate or missing counts in the controlled run;
- readout is repeatable across repeated snapshots;
- analyzer reports deltas against the known pulse period;
- any reset/wrap is explicit, not hidden.

### Analysis command

```sh
python tools/shrike_timing.py capture.csv \
  --tick-hz 50000000 \
  --expected-period-s 1.0
```

The raw CSV is a bench artifact. It is not a new canonical sensor schema; only
the Observation mapping below can be exported to CORE/WORLD.

## 7. CORE/WORLD integration boundary

See [the Observation boundary design](specter-sync-observation-boundary.md).
It uses `specter.platform.observation.SCHEMA` unchanged and treats nominal
50 MHz, 32-bit wrap, host-read time, calibration and uncertainty explicitly.
No duplicate data schema is permitted.

## 8. Hardware bring-up checklist (short)

- [ ] Photograph board and record silkscreen revision; mark UNKNOWN fields.
- [ ] Compare physical board to v1_r0.4/v1_r0.5; record selected design source.
- [ ] Inspect for damage/shorts and confirm J3 population.
- [ ] Confirm no 5 V header supply is connected while USB is connected.
- [ ] Use USB-C data cable only; no external signal connections.
- [ ] Install matching RP2040 UF2; verify boot/disk/USB CDC behavior.
- [ ] Run `heartbeat.py`; record LED and console evidence.
- [ ] Build and load the FPGA proof-of-life bitstream through the MCU path.
- [ ] Confirm FPGA LED F16 behavior; record bitstream hash.
- [ ] Verify F17/F18 internal readout only; do not use J2 pins 11/12/14/15.
- [ ] Capture the event counter with no external pulses; confirm stable count.
- [ ] After review, add the F1 pulse source and capture timing data.
- [ ] Preserve raw logs, hashes and failures before any claim.

## 9. Open questions before hardware work

- Exact received board revision and matching vendor UF2/bitstream set.
- Apple Silicon behavior of the exact Go Configure version.
- Per-pin drive/current limits and protection topology.
- Actual FPGA oscillator frequency, tolerance, drift and temperature behavior.
- Whether F17/F18 post-configuration readout is supported by the selected
  bitstream/IO planner and whether any board resistor option affects it.
- Whether J3 is populated and usable as a PMOD connector.
- The minimum pulse width and edge-rate behavior of F1 with a real source.
- The exact behavior of the vendor FPGA bitstream loader with respect to
  configuration-pin reuse after load.
