# Shrike Lite physical bring-up log — 24 October 2026

**Status: RP2040 verified online; FPGA custom programming NOT attempted.**
Host: Apple Silicon macOS. Connection: USB-C only. No external signals, no
alternate supply, no flash erase, no OTP, no custom FPGA bitstream.

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
FPGA F18/F17. Any future custom FPGA readout must first stop this factory loop
and establish a reviewed pin-ownership plan. The factory loop was not modified.

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

## FPGA readiness gate

**Not ready for custom FPGA programming.** Required before proceeding:

1. Read and report the physical PCB revision/silkscreen. The manufacturer
   hardware tree contains Shrike-Lite `v1_r0.4` and `v1_r0.5`; the factory
   bitstream directory is `v1_4`. The physical revision is still UNKNOWN.
2. Confirm whether the J3 2×6 PMOD-style header is populated (published PCB
   sources mark it DNP).
3. Review the intended F1 input and F17/F18 internal readout against the actual
   board revision and schematic.
4. Install/verify Renesas Go Configure Software Hub on this Apple Silicon Mac
   and its native/Rosetta behavior. It is not installed in `/Applications` at
   this checkpoint.
5. Authorize replacing or temporarily suspending the factory `main.py` loop
   before a custom FPGA bitstream is loaded. The current factory loop drives
   GPIO14/15, which are reserved for the internal FPGA link.
6. Generate a reviewed custom bitstream from the Phase 0 Verilog and record its
   hash before any programming.

No custom FPGA bitstream was generated or flashed. No timing accuracy is
claimed. The existing Observation v1 boundary remains the only future
CORE/WORLD record format.
