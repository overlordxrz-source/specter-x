# Shrike Lite physical bring-up log — 24 October 2026

**Status: RP2040 verified online; custom FPGA heartbeat built and hashed, NOT flashed.**
Host: Apple Silicon macOS. Connection: USB-C only. No external signals, no
alternate supply, no flash erase, no OTP, no custom FPGA bitstream loaded.

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
the physical revision remains **UNKNOWN**. A focused, high-resolution photo of
the `R0.4`/`R0.5` silkscreen, or the owner's explicit acceptance of the
electrically identical v1_r0.4/v1_r0.5 evidence, is required before flashing.

## Read-only heartbeat verifier

`tools/shrike_fpga_verify.py` checks the frozen `main.v` SHA-256, top-level
module/ports and IO-planner mapping. The manifest now records the reviewed MCU
bitstream size/hash; the custom image passes and the factory `blink_all.bin`
fails as a negative control. It never opens a serial port or writes to the
board.

## FPGA readiness gate

**Software build ready; programming still gated.** Completed:

1. Go Configure 6.56.01 installed and verified native ARM64.
2. `SLG47910V (Rev BB)` selected; synthesis, place-and-route and MCU bitstream
   generation succeeded.
3. Exact source and bitstream hashed; 50 MHz timing constraint added, WNS
   +8585 ps with 0 failing endpoints.
4. Factory `main.py` and `blink_all.bin` remain backed up and unchanged.

Still required before custom FPGA programming:

1. Establish the physical revision: capture a clear `R0.4`/`R0.5` silkscreen
   photo, or explicitly accept the electrically identical v1_r0.4/v1_r0.5
   evidence above.
2. Authorize suspending or replacing the factory `main.py`. It calls
   `shrike.flash("blink_all.bin")` at boot and drives GPIO14/15. For the F16
   heartbeat, GPIO14/15 do not conflict electrically, but the factory loop
   would overwrite the custom image; for the future F17/F18 readout it would
   contend directly.
3. Authorize loading exactly `FPGA_bitstream_MCU.bin` with SHA-256
   `6931f347e6fb521435efda5004a0300e9ccb4aa7fc4e5d71b229c327ce87e267`
   through the vendor `shrike.flash(...)` path, USB-C only, no OTP.
4. Observe the onboard FPGA LED (F16) for a ~1 Hz heartbeat, record the result,
   and restore or confirm the factory files afterward.

No custom FPGA bitstream has been flashed. No external signal or alternate
supply was used. No physical timing accuracy is claimed. The existing
Observation v1 boundary remains the only future CORE/WORLD record format.
