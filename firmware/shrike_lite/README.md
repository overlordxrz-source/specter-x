# Shrike Lite examples and toolchain notes

**Status: design-only, not executed.** Do not flash, connect external signals,
or power the board from the 5 V header until the hardware review.

## Files

```text
rp2040/heartbeat.py              MicroPython proof-of-life (GPIO4)
rp2040/event_counter_readout.py  future 64-bit event readout (GPIO14/15)
rp2040/pulse_loopback.py         future non-independent RP2040 pulse source
fpga/proof_of_life/main.v        FPGA LED heartbeat (F16)
fpga/proof_of_life/shrike_50mhz.sdc  50 MHz timing constraint for the heartbeat
fpga/event_counter/main.v        event timestamp + 2-wire readout
fpga/event_counter/tb_event_counter.v
fpga/event_counter/tb_event_counter_hazards.v  CDC/idle reload hazard control
rp2040/event_counter_readout_bounded.py        bounded future readout
```

The design rationale, pin tables, electrical limits and experiment protocol are
in [`docs/design/specter-sync-phase0.md`](../../docs/design/specter-sync-phase0.md).

## Official workflows

Shrike Lite has two independent programming paths:

1. **RP2040:** MicroPython/CircuitPython UF2, Arduino with the Earle Philhower
   RP2040 core, or the Raspberry Pi Pico C SDK.
2. **FPGA:** Verilog in Renesas Go Configure Software Hub / ForgeFPGA Workshop;
   synthesize, map I/O, generate `FPGA_bitstream_MCU.bin`, copy it to the RP2040
   filesystem, and load it with the vendor `shrike.flash(...)` helper.

Do not use the FPGA OTP programming option. The MCU/SPI bitstream path is the
only intended path for this work. The exact FPGA image is not committed here;
it was generated from the reviewed Verilog on 24 October 2026 and its SHA-256
is recorded in `fpga/proof_of_life/verification.json`. One owner-authorized
volatile load produced the approx. 1 Hz F16 heartbeat; the staged image was
then removed and the factory `main.py`/`blink_all.bin` state restored. No
persistent custom image is present.

## macOS / Apple Silicon

- The vendor's RP2040 paths (MicroPython UF2, Thonny, `mpremote`, Arduino) are
  expected to work on macOS. No Linux dependency is known for the MCU side.
- Renesas publishes a macOS 11+ Go Configure installer and lists SLG47910
  support. **Verified 24 October 2026:** Go Configure Software Hub 6.56.01 is
  universal (arm64 + x86_64), ran natively as ARM64, selected `SLG47910V
  (Rev BB)`, and completed Yosys 0.59 synthesis plus eda-placer v23
  place-and-route and `FPGA_bitstream_MCU.bin` generation. No Rosetta or VM was
  needed.
- Go Configure requires a Renesas account. No cloud/LLM service is required by
  the examples.
- Verilog simulation is available with Icarus Verilog/GTKWave via Homebrew; it
  does not replace synthesis.

## Board/pin constraints

- All GPIO and PMOD pins are **3.3 V logic, not 5 V tolerant**.
- Power from USB-C **or** the 5 V header, never both at once.
- The FPGA/RP2040 link uses RP2040 GPIO13/12 for EN/PWR, GPIO2/1/3/0 for the
  configuration SPI, and GPIO14/15 ↔ FPGA F18/F17.
- Do not use J2 pins 11/12/14/15 for external wiring.
- J3 (2×6 PMOD-style) is marked DNP in the available v1_r0.5 PCB source; verify
  population on the physical unit.
- The received board revision is UNKNOWN until the silkscreen is read.

## First event-counter pin plan

| Signal | Device pin | Header | Use |
|---|---|---|---|
| Event input | FPGA F1 | J2 pin 17 | 3.3 V CMOS pulse, future only |
| Reference ground | GND | J2 pin 13 | Common reference, future only |
| Read clock | FPGA F18 ← RP2040 GPIO14 | J2 pin 15 / pin 11 | **Internal link only; no external wire** |
| Read data | FPGA F17 → RP2040 GPIO15 | J2 pin 14 / pin 12 | **Internal link only; no external wire** |
| FPGA LED | F16 | onboard | Proof-of-life output |
| RP2040 LED | GPIO4 | onboard | Proof-of-life output |

For the first loopback characterization, a future reviewed jumper may connect
RP2040 GPIO6 (J2 pin 4) to FPGA F1 (J2 pin 17). An external 3.3 V pulse source
is preferred for the timing experiment because it is independent of the MCU.

### ForgeFPGA IO Planner mapping (event counter)

| Verilog port | IO Planner selection | Direction |
|---|---|---|
| `clk` | `OSC_CLK` | FPGA internal oscillator |
| `clk_en` | `OSC_EN` | output-high enable |
| `event_in` | `GPIO1_IN` | input |
| `rd_clk` | `GPIO18_IN` | input |
| `rd_data` | `GPIO17_OUT` | output |
| `rd_data_en` | `GPIO17_OE` | output-high enable |

The proof-of-life blink maps `led` to `GPIO16_OUT` and `led_en` to
`GPIO16_OE`. These planner names must be checked in the installed tool version;
do not guess if the UI presents a different label.

## Readout protocol

The FPGA loads `{event_count[31:0], last_timestamp[31:0]}` after ≥1 ms of read
clock idle. The RP2040 samples data while holding clock low and raises the
clock 64 times, MSB first. The legacy code waits 3 ms between snapshots. The
event-counter hazard test shows that a host pause longer than the idle reload
interval can mix two snapshots; the bounded future readout aborts on an edge
gap above 250 µs. This is a minimal custom link; it is not a vendor sensor
protocol. See the [prepared event-counter gate](../../docs/design/shrike-lite-event-counter-experiment-20261024.md).

## Software-only checks

```sh
python -m pytest -q tests/test_shrike_timing.py
python tools/shrike_fpga_verify.py
iverilog -g2012 -o /tmp/shrike_blink.vvp \
  firmware/shrike_lite/fpga/proof_of_life/main.v
iverilog -g2012 -o /tmp/shrike_event.vvp \
  firmware/shrike_lite/fpga/event_counter/main.v \
  firmware/shrike_lite/fpga/event_counter/tb_event_counter.v
vvp /tmp/shrike_event.vvp
iverilog -g2012 -o /tmp/shrike_event_hazards.vvp \
  firmware/shrike_lite/fpga/event_counter/main.v \
  firmware/shrike_lite/fpga/event_counter/tb_event_counter_hazards.v
vvp /tmp/shrike_event_hazards.vvp
```

The verifier checks the frozen heartbeat source hash, top-level ports and
IO-planner mapping. The manifest records the reviewed MCU bitstream hash; pass
`--bitstream path/to/FPGA_bitstream_MCU.bin` to compare a generated image
without opening a serial port or writing to the board.

## Future command shapes (do not execute yet)

```sh
# After the matching UF2 is installed and the board is powered from USB only:
python -m mpremote connect port:/dev/tty.usbmodemXXXX \
  run firmware/shrike_lite/rp2040/heartbeat.py

# FPGA bitstream load is through the vendor MicroPython helper:
python -m mpremote connect port:/dev/tty.usbmodemXXXX \
  run firmware/shrike_lite/rp2040/event_counter_readout.py
```

The event readout assumes the reviewed FPGA bitstream is already loaded.
