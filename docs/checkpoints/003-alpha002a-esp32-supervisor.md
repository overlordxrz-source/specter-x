# SPECTER-X checkpoint 003 — Alpha 002-A, ESP32-S3 supervisor (host side)

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor` (stacked on
`fix/di188-acquisition-shutdown`; `main` is untouched)
**Status:** the **host side** of the ESP32-S3 supervisor is complete and
tested. The firmware that will produce these packets does not exist yet, and
nothing has been flashed.

---

## 1. Hardware: what is actually on the bus

The ESP32-S3 is plugged in and was identified **read-only** (USB descriptors
only; no `esptool`, no bootloader reset, no write):

| | |
|---|---|
| Native USB | `USB JTAG_serial debug unit`, **Espressif 0x303A:0x1001**, USB serial **`14:C1:9F:26:52:EC`** (the board MAC) → `/dev/cu.usbmodem1101` |
| UART bridge | `USB Single Serial`, **WCH 0x1A86:0x55D3** (CH343/CH9102 family), serial `5B90160228` → `/dev/cu.usbmodem5B901602281` |
| On-board hub | WCH 0x1A86:0x8091 |

Two facts matter for the design:

1. **The board already runs a Wi-Fi CSI streamer.** At 15:50 its native USB
   port was emitting the CSI line format at high rate:

   ```
   CSI_DATA,7182,b8:62:1f:b4:a5:62,-73,11,1,4,0,0,1,0,0,0,1,-95,0,6,0,85322850,0,67,1,128,0,"[0,0,-8,4,-8,5,...
   ```

   Note this is **not** the format `firmware/esp32-csi/README.md` documents
   (`CSI,<timer>,<mac>,...`) — the tag is `CSI_DATA` and the field layout
   differs. The README has been corrected.

2. **The board stopped streaming between 15:50 and 16:26.** Its native USB
   port now delivers zero bytes, while UART0 shows non-textual bytes at
   115200 consistent with the ROM bootloader. The board therefore looks like
   it has reset or halted. Confirming that needs `esptool chip-id`, which
   performs a bootloader reset - **not run**, per the instruction not to
   initiate bootloader resets. This is a blocker for physical integration
   (see §6).

### Toolchain correction

**The ESP32-S3 is a Xtensa LX7 part, not RISC-V.** My earlier note that
ESP-IDF's `riscv32-esp-elf` toolchain was "the ESP32-S3's RISC-V core" was
wrong: `riscv32-esp-elf` is for the RISC-V parts (ESP32-C3, C6, P4), while
the S2 and **S3 use the Xtensa LX7 core and the `xtensa-esp-elf` toolchain**.
ESP-IDF v5.2.2 is installed with both toolchains present, so nothing is
missing - but the S3 build must use `xtensa-esp-elf` and `idf.py set-target
esp32s3`. The USB descriptor alone (0x303A:0x1001) cannot tell an S2/S3 from
a C3/C6, which is why the chip id is worth reading once that is allowed.

---

## 2. What Alpha 002-A implements

**Host side only.** The firmware is a later milestone.

| Piece | Where |
|---|---|
| Wire protocol + parser | `specter/sensors/esp32/protocol.py` |
| Bounded acquisition, health model, Measurements | `specter/sensors/esp32/supervisor.py` |
| Simulator (drives the whole path without hardware) | `specter/sensors/esp32/simulator.py` |
| USB serial discovery by VID:PID | `specter/hw/usb.py` |
| HUD block | `specter/hud/renderer.py` (`draw_supervisor_block`) |
| App wiring + JSONL | `specter/app.py` (`--supervisor esp32`) |
| Tests | `tests/test_esp32_supervisor.py` (35) |

### The protocol

One CSV-with-a-type-tag packet per line, CR or LF terminated - the same
shape as the CSI streamer already on the board, so one host-side line reader
can serve both.

```
HELLO,<proto>,<board>,<chip>,<mac>,<fw_version>,<fw_build>
STAT,<uptime_s>,<heap_free>,<heap_min>,<health>
HB,<seq>,<uptime_s>
```

### Two heartbeats, deliberately apart

| | Device heartbeat | Network heartbeat |
|---|---|---|
| what | the board's own liveness counter, over USB | the unit's presence on the team link |
| where | `specter/sensors/esp32/` | `specter/net/messages.py` (`Heartbeat`) |
| how it appears | `Measurement(sensor="supervisor", kind="supervisor_status")` | a signed `Heartbeat` message |
| question | "is this board alive?" | "is this unit on the mesh, and where?" |

They are never merged, and `SENSOR_LABELS` gained a separate `"supervisor"`
key so the HUD can label them differently.

### Health is derived from two sources, and both are reported

* the **device's own** health word (`OK` / `WARN` / `DEGRADED` / `FAULT`);
* the **host's** view: is the heartbeat arriving, is the identity known, how
  many heartbeats were missed.

A board that claims to be fine but has stopped sending heartbeats is not
fine, and the host's view wins. A device that reports `WARN` degrades an
otherwise healthy link.

---

## 3. Honesty rules

* **The identity is never invented.** Until a `HELLO` packet arrives the
  provenance `sensor_id` is `"unknown"`, `model_version` is `None` and the
  note says *"identity not yet reported"*. The HUD draws *"identity not
  reported"*, not a guessed board name.
* **Malformed lines are counted, never fatal.** The real board is streaming
  CSI traffic, not supervisor packets; every one of those lines is counted
  as malformed and skipped.
* **A silent device is OFFLINE, not hung.** The acquisition has a stall
  timeout, the port is always released, and the state says so.
* **Confidence is `None`** - a supervisor status is not a measurement of the
  world.

---

## 4. Evidence

`docs/alpha002/`:

| File | What |
|---|---|
| `alpha002a_supervisor_hud.png` | the HUD with a healthy supervisor (simulator): identity, MAC, firmware, uptime, heartbeat, missed count, device health |
| `alpha002a_real_device_offline.png` | the HUD against the **real** board, which is enumerating but not streaming: `OFFLINE`, *"identity not reported"*, no invented identity |

The real-device run also proved the port selection: the supervisor picked
`/dev/cu.usbmodem1101` (Espressif native USB) and **not** the WCH UART
bridge, and it did so by USB VID:PID, not by guessing.

---

## 5. Test results

* `tests/test_esp32_supervisor.py` - **35 passed**: protocol parsing, 20
  malformed-packet cases, identity handling, missed heartbeats, a device
  restart not being counted as loss, late-heartbeat degradation, timeout to
  OFFLINE, recovery, the device-vs-host health split, rate-limited logging,
  the device/network heartbeat distinction, bounded acquisition, port
  release, and the status row.
* Full suite on this branch: **161 passed, 1 failed** - the failure is the
  DI-188 real-device acceptance test, which is fixed on the Task 1 branch
  (it now skips correctly when the instrument is disconnected). See §7.
* Without pyserial (the CI image): **161 passed, 1 skipped**.

---

## 6. Blockers before physical integration

1. **No supervisor firmware exists.** The protocol is specified and the host
   is tested against a simulator; nothing has been built or flashed. This is
   the main gap.
2. **The board is not streaming and looks reset.** Its native USB port is
   silent and UART0 shows ROM-level bytes. Before any firmware work, the
   board should be confirmed alive - which needs `esptool chip-id`, and that
   performs a bootloader reset.
3. **The chip family is not confirmed from the descriptors alone** (0x303A:0x1001
   covers S2/S3/C3/C6). `chip-id` settles it, and the S3 must be built with
   `xtensa-esp-elf`.
4. **Two serial nodes belong to the board.** The supervisor must use the
   native USB node; the WCH bridge is the UART0 console and is not a
   supervisor channel. The selection is by VID:PID, so this is handled, but it
   is worth stating.
5. **CSI and supervisor share one board and one USB CDC link.** When the
   firmware milestone comes, the two workloads must share the port or the
   supervisor must have its own. This is a firmware design decision, not a
   host one.
6. **The repo's CSI format documentation does not match the running board**
   (`CSI_DATA,` vs `CSI,`, and a different field layout). Corrected in the
   README, but the parser still has to be written.

---

## 7. Branch topology

```
main                    b5e1875  (unchanged)
  └─ fix/di188-acquisition-shutdown     25b2948   Task 1
       └─ feature/alpha002-esp32-supervisor          Task 2
```

The Alpha branch is stacked on the Task 1 branch because Task 1's fix is
required for a green suite here: the DI-188 is currently disconnected, and
only the fixed skip condition skips its acceptance test correctly. Both
branches are pushed and **neither is merged into main**.
