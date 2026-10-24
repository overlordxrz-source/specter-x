# Shrike Lite physical bring-up log — 24 October 2026

**Status: RP2040 verified online; first custom F16 heartbeat PASS (owner visual, ~1 Hz); volatile load; factory boot restored.**
Host: Apple Silicon macOS. Connection: USB-C only. No external signals, no
alternate supply, no flash erase, no OTP. The custom image was loaded once
into volatile FPGA configuration, observed, removed and rolled back; factory
files and hashes were restored.

## USB / MCU identity observed

- Product string: `SHRIKE` / `Board in Micropython Mode`
- VID: `0x2e8a` (11914)
- PID: `0x0005` (5)
- USB serial: `de621c3003395627`
- macOS device: `/dev/cu.usbmodem101`
- MicroPython: `1.26.0-preview` / `v1.26.0-preview.527.g599f545a3.dirty`
- `os.uname()`: `rp2`, machine `Vicharak Shrike FPGA with RP2040`
- `sys.implementation`: MicroPython `1.26.0-preview`, build `RPI_PICO`
- CPU frequency: `125000000` Hz
- `machine.unique_id()`: `de621c3003395627`
- `machine.reset_cause()`: `1`

## Factory filesystem and backup

Files present at `/`:

```text
.fseventsd/
blink_all.bin
main.py
```

No `boot.py` was present. Local backup:

`runs/shrike_lite_factory_backup_20261024/`

| File | Size | SHA-256 |
|---|---:|---|
| `main.py` | 463 B | `0e3b259a4f2387260823435a3a53e98dbc9f4164860cff95d84421a2f73f5b59` |
| `blink_all.bin` | 45 KiB | `cd40b215efa40f272fe788202417d7f312a4e8f772fb06c2f96beafaf4fb65fd` |

The local backup hashes match the on-board hashes read through MicroPython.

## Factory `main.py` behavior

The factory script:

1. configures RP2040 GPIO4–11 and 14–29 as outputs;
2. calls `shrike.reset()`;
3. calls `shrike.flash("blink_all.bin")`;
4. toggles all those MCU pins at approximately 1 Hz forever.

This means the factory loop drives MCU GPIO14/15, which are internally wired to
FPGA F18/F17. For the F16 heartbeat, that activity is independent of the FPGA
LED pin and does not create an electrical conflict. However, the factory script
calls `shrike.flash("blink_all.bin")` at every boot; if left in place it will
overwrite a custom FPGA image. It must be suspended/replaced before any custom
bitstream is loaded, and it must be stopped before the future F17/F18 readout
experiment. The factory loop was not modified.

## Factory bitstream provenance

The on-board `blink_all.bin` hash exactly matches the manufacturer’s published:

- `test/bitstreams/v1_4/blink_all.bin`
- `test/multi_hardware_test/blink_all.bin`

from `vicharak-in/shrike` commit `2186d6b`. This identifies the factory
bitstream bytes, but **does not identify the physical board revision**.

## RP2040 heartbeat test

A transient REPL-only script toggled only onboard RP2040 GPIO4 (MCU LED) 12
times at 250 ms intervals. It wrote no files. Log:

`runs/shrike_lite_factory_backup_20261024/rp2040_heartbeat.log`

The factory `main.py` was restored by a soft reset; its hash and the bitstream
hash remained unchanged.

## Go Configure / toolchain verification

### Installer and native execution

- Downloaded `go-configure-sw-hub-v6.56.001-mac.dmg`.
- SHA-256 `e455e9d7e88daf62f2953897898463553af4390e38c350e32e303b6a60cf92d6`;
  DMG integrity passed.
- Signed by Developer ID Application: Renesas Electronics Corporation
  (`RM4ZZ9ZAD4`); notarized and accepted by Gatekeeper.
- App bundle is universal **arm64 + x86_64**. Installed app is version
  `6.56.01` and runs natively as **ARM64**; no Rosetta or VM was used.
- One standard macOS first-launch approval was required; no security bypass.

### Target, source and mapping

- Selected **`SLG47910V (Rev BB)`**. `SLG47910C` is a different variant and was
  not used.
- Created a local project at
  `~/.cache/specter-sync-goconfig/specter_sync_blink/specter_sync_blink.ffpga`
  (not committed).
- Used the frozen source
  `firmware/shrike_lite/fpga/proof_of_life/main.v`, SHA-256
  `33d1f9b7e4c3cac7fd68e950a6b399f705c0d953633b3463fe16808c29fa9e6e`.
- Synthesis: Yosys **0.59**. Place-and-route: eda-placer **v23**.
- I/O Planner mapping:
  `clk → OSC_CLK`, `clk_en → OSC_EN`, `led → GPIO16_OUT`,
  `led_en → GPIO16_OE`.
- Added the 50 MHz timing constraint
  `create_clock -name clk {clk} -period 20.000 -waveform {0 10.000}`.
- Final PNR at 20 ns: WNS **+8585 ps**, 0 failing endpoints; achievable period
  **11.414 ns (~87.6 MHz)**.
- PNR reported one warning:
  `Clock clk directly fed by port without CLKBUF`. This is consistent with the
  documented `(* clkbuf_inhibit *)` attribute and the OSC_CLK global clock-tree
  assignment; there were no PNR errors.

### Generated image

- Output: `ffpga/build/bitstream/FPGA_bitstream_MCU.bin`
- Size: **46,408 bytes**
- SHA-256:
  `6931f347e6fb521435efda5004a0300e9ccb4aa7fc4e5d71b229c327ce87e267`
- The size exactly matches the vendor factory `blink_all.bin` (46,408 bytes).
  Other `.bin` variants in the build tree are not the MCU image and must not be
  used.
- Icarus Verilog simulation of the exact source passed: the first LED transition
  occurred at **25,000,001 cycles**, i.e. 0.5 s at 50 MHz, consistent with a
  ~1 Hz heartbeat.
- Build artefacts are preserved locally under
  `runs/shrike_lite_custom_heartbeat_20261024/`; the binary is deliberately not
  committed.

## Board revision cross-check (v1_r0.4 vs v1_r0.5)

Owner photographs show both 19×1 GPIO headers populated, no populated 2×6 J3,
USB-C power and a red indicator; the revision silkscreen is not legible.

Cross-check against the official KiCad sources:

- Both revisions contain the same 57 component references. J2/J4 are the two
  19×1 headers; J3 is the 2×6 header marked **DNP** in both revisions.
- Pad/net comparison found **0 electrical differences** across all components;
  both have 71 named nets. The only placement change is C2 moving by 0.055 mm
  in v1_r0.5. Footprint-library names and some reference labels differ, but no
  connection differs.
- The only clear revision discriminator is the front silkscreen **`R0.4` vs
  `R0.5`** at approximately `(148.4, 123.0)`, immediately below `V1.0` and near
  the `Shrike-Lite`/J3/J5 area.

The photographic findings are therefore consistent with **both** revisions;
the physical revision remains **UNKNOWN**. The owner authorized this single
experiment within the v1_r0.4/v1_r0.5 candidate set; no published electrical
difference affects the F16 LED or OSC pins. A focused silkscreen photo remains
required before any later revision-specific work.

## First custom F16 heartbeat — PASS

**Date:** 24 October 2026. **Owner authorization:** one bounded volatile load
using exactly the reviewed image.

- Device: Vicharak Shrike Lite; MicroPython RP2040, USB serial
  `de621c3003395627`, `/dev/cu.usbmodem101`.
- Target: `SLG47910V (Rev BB)`.
- Image: `FPGA_bitstream_MCU.bin`, **46,408 bytes**, SHA-256
  `6931f347e6fb521435efda5004a0300e9ccb4aa7fc4e5d71b229c327ce87e267`.
- Method: `shrike.flash('specter_sync_blink.bin', 46408)` after staging the
  temporary image. No OTP, external wiring, firmware replacement or persistent
  startup change.

### Preflight and staging

- Host image hash and size matched the reviewed manifest.
- Device identity, MicroPython build (`1.26.0-preview`) and responsive REPL
  matched the prior bring-up record.
- Board factory `main.py` (463 B, `0e3b259a…`) and `blink_all.bin`
  (46,408 B, `cd40b215…`) matched the backups immediately before programming.
- Staged image readback matched the exact host SHA-256 and size; the only new
  filesystem entry was `specter_sync_blink.bin`.

### Programming and observation

- The single `shrike.flash` command reported `FPGA programming done` with no
  error markers; it was not repeated.
- Owner-visual observation (automated camera unavailable): the blue FPGA LED
  **D2** blinked on/off at approximately **1 Hz** for more than 10 seconds.
- A controlled RP2040 GPIO4/MCU LED pulse was visible on the separate blue
  **D3** next to the red power LED; the flashing D2 continued unchanged. This
  distinguishes the FPGA heartbeat from the MCU loop.
- The blink rate is an owner estimate, not an instrumented measurement. No
  oscilloscope, photodiode or camera capture was used.

### Rollback

- Temporary `specter_sync_blink.bin` removed.
- Explicit soft reset executed.
- Postflight `main.py` and `blink_all.bin` hashes matched the factory backups;
  no extra file remained.
- The custom image was volatile and is not present after reset; factory
  `main.py` reloads `blink_all.bin` at boot.

### Evidence

Local logs and readbacks:
`runs/shrike_lite_custom_heartbeat_20261024/flash-20261024/` (preflight,
staging, programming, MCU control, observations, rollback, postflight and
manifest). The directory is gitignored; the committed manifest records the
result and hashes.

**Result: PASS**, with the remaining uncertainty limited to approximate visual
rate, unknown physical PCB revision, and the unresolved CLKBUF inference
warning. No motion, timing-accuracy or persistent-firmware claim follows.

## Read-only heartbeat verifier

`tools/shrike_fpga_verify.py` checks the frozen `main.v` SHA-256, top-level
module/ports and IO-planner mapping. The manifest now records the reviewed MCU
bitstream size/hash; the custom image passes and the factory `blink_all.bin`
fails as a negative control. It never opens a serial port or writes to the
board.

## FPGA readiness gate

**First F16 heartbeat complete; no persistent custom firmware.** Completed:

1. Go Configure 6.56.01 installed and verified native ARM64.
2. `SLG47910V (Rev BB)` selected; synthesis, place-and-route and MCU bitstream
   generation succeeded.
3. Exact source and bitstream hashed; 50 MHz timing constraint added, WNS
   +8585 ps with 0 failing endpoints.
4. One owner-authorized volatile load observed: blue D2 blinked at ~1 Hz;
   MCU D3 was separately controlled to distinguish it.
5. Temporary image removed, soft reset executed, factory `main.py` and
   `blink_all.bin` hashes restored; no persistent custom image remains.

Still open for later work:

1. Establish the physical revision from the `R0.4`/`R0.5` silkscreen; the
   published candidate layouts are electrically identical for this test.
2. For the future F1/F17/F18 event-counter experiment, stop or replace the
   factory `main.py` before loading a custom image. It calls
   `shrike.flash("blink_all.bin")` at boot and drives GPIO14/15; the F16
   heartbeat itself has no electrical conflict with those pins.
3. Instrument the actual blink rate if a timing claim is needed; the owner
   visual estimate is not a calibrated measurement.
4. Treat the CLKBUF inference warning as a watch item for higher-speed logic.

No custom FPGA bitstream is present after rollback. No external signal,
alternate supply or OTP operation was used. No physical timing accuracy is
claimed. The existing Observation v1 boundary remains the only future
CORE/WORLD record format.

## Next event-counter gate — PREPARED, NOT AUTHORIZED

The existing event-counter source was assessed offline on the isolated
`research/specter-sync-event-counter` branch. No event-counter bitstream was
generated, staged or programmed, and no external signal/jumper was connected.

- F17/F18 are the internal MCU–FPGA link. The factory `main.py` drives RP2040
  GPIO14/15 as outputs, so the factory loop must be interrupted and GPIO15 set
  to input before any future event-counter load. No external wires are
  permitted on J2 pins 11/12/14/15.
- The event count and timestamp are updated on the same 50 MHz edge and the
  snapshot shift register loads only after idle; nominal snapshot coherence is
  confirmed. An event during a read is excluded from the active snapshot.
- A host pause longer than the 1 ms idle reload can mix two snapshots. The new
  hazard test reproduces this, and the bounded future readout aborts on an edge
  gap above 250 µs.
- F1 has no bias resistor in the published PCB sources. Event-count claims
  require a separately authorized 3.3 V CMOS bias/pulse path; this preparation
  makes no count claim.
- Offline nominal and hazard simulations pass. Bundled Yosys 0.59 synthesis
  reports 596 cells and 0 problems; full Go Configure PNR, timing and bitstream
  generation are not run.
- Exact source/readout hashes, protocol phases, stop rules and rollback are in
  [the event-counter protocol](shrike-lite-event-counter-experiment-20261024.md).

No physical event-counter run is authorized by the F16 heartbeat result or by
this preparation.
