# SPECTER-X checkpoint 007 — USB stall diagnosis, baselines, AP identity

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the repeated USB CDC stalls are now **diagnosed as device-side**,
with reproducible evidence. Six clean baselines quantify the link. The
transmitting access point is identified from the device's own log. The
16 MB firmware backup is untouched.

---

## 1. The USB CDC stalls

### Symptom

The ESP32-S3 keeps enumerating with the correct VID/PID and serial, but its
CDC data path stops delivering bytes in either direction. No command is
answered, no CSI packet arrives. It has now happened at least four times
today, and it also happened to the DI-188 (checkpoint 003) in the identical
way — two unrelated devices, the same family of SAMD/ESP32 USB-CDC failure.

### Evidence collected (read-only, no resets in the diagnostic path)

At the moment of a stall:

| Probe | Result | What it means |
|---|---|---|
| USB enumeration (`ioreg`) | **still present** — `USB JTAG_serial debug unit`, Espressif 0x303A:0x1001, serial `14:C1:9F:26:52:EC` | the host's USB stack still sees the device; the bus is not dead |
| The board's *other* USB path (the CH343 UART0 bridge) | **still opens and reads fine** | the host's USB stack is healthy for another device on the same board — **this is not a host-wide USB failure** |
| macOS kernel USB log | **no entries** | the host's USB stack logged no error, reset or stall |
| UART0 console during the stall | readable, **0 bytes** | *inconclusive* — the app's stdout goes to the USB CDC, so UART0 is normally silent. It is not evidence that the MCU has halted. |
| Application's own log on the CDC path | **nothing at all**, not even the `I (169) esp_image:` boot line it prints at startup | the CDC write path is dead, not just the CSI generator |
| Recovery | **a device-side hard reset** (over the UART bridge) always restores the stream | only an action on the device clears it |

### Diagnosis

**Device-side, not host-side.** The host keeps the device visible, keeps
another device on the same board working, and logs nothing; and the only
action that clears the fault is a reset of the device itself.

The finer question — *what* inside the device is dead — is narrowed but not
settled. Two candidates remain:

* the ESP32-S3's ROM USB stack does not re-establish its TX endpoint after
  the host closes the port, so the application's `ets_printf` (which writes
  through the ROM path) keeps writing into a dead endpoint. The application
  itself would still be running, which matches "the device enumerates but
  says nothing".
* the application has blocked or halted.

The evidence slightly favours the first: a host-side close of the port is
the only *reproducible* trigger we have found — **every** wedge we have
watched happened after the host released the port (a killed HUD process, a
finished baseline run, the end of a flash-backup session). The board's own
firmware never sees that the port was reopened, because the ROM's USB path
is not re-armed.

Supporting observation, from a controlled test:

```
after recovery                    : 1126 CSI packets
session A (open, stream, close)    : 1058 CSI packets
session B (reopen, no reset)      :    0 CSI packets   <-- the port was reopened
```

and, with a reset before each cycle, three consecutive reopen cycles were
healthy (876–970 packets each). So the failure after a close is
**intermittent but real**, and a reset is the only reliable cure.

### What this changes

* The **host** must not treat "the port opened" as "the device is talking".
  The reader already distinguishes a warm-up from a stall; it now also needs
  to distinguish "no bytes since the port was opened" from "no bytes after a
  period of traffic" — the first means the device needs a reset, the second
  means the link dropped.
* The **firmware** fix (Alpha 002-C, proposed in
  `docs/design/esp32-firmware-integration.md`) is the same diagnosis seen
  from the other side: routing the output through the IDF's VFS/`printf`
  instead of the ROM's `ets_printf` gives a CDC path that *does* recover
  from a host-side disconnect.
* The **host software** should keep one reader alive for the life of the
  process and close the port as gracefully as it can, rather than
  open/close per session. The motion recorder was changed for exactly this
  reason.

### Not done, deliberately

No automatic reset was added, no bootloader was entered, and the firmware was
not touched. The recovery remains a deliberate human action over the UART
bridge.

---

## 2. Baseline campaign — six 60-second acquisitions

| Run | Packets | Rate (pkt/s) | Gaps | Missing | Malformed | Dropped | Outages | RSSI | Channel |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 8 679 | 144.64 | 0 | 0 | 1 | 0 | 0 | −72…−56 | 11 |
| 2 | 8 748 | 145.79 | 0 | 0 | 0 | 0 | 0 | −72…−61 | 11 |
| 3 | 8 243 | 137.37 | 0 | 0 | 0 | 0 | 0 | −67…−57 | 11 |
| 4 | 9 264 | 154.40 | 0 | 0 | 0 | 0 | 0 | −61…−58 | 11 |
| 5 | 8 283 | 138.04 | 0 | 0 | 0 | 0 | 0 | −82…−57 | 11 |
| 6 | 9 345 | 155.74 | 0 | 0 | 0 | 0 | 0 | −86…−58 | 11 |

**Summary**

* **Rate: 137.4 – 155.7 packets/s, mean 146.0, stdev 7.1, spread 12.6 %.**
* **Loss: 0 sequence gaps, 0 missing packets, 0 dropped, 1 malformed line**
  (a truncated final line) across six minutes of streaming.
* **Outages: 0.**
* **Channel: 11 in every packet of every run — perfectly stable.**
* **RSSI: −86 … −56 dBm across the session** — a 30 dB ambient range.
* The device's own cadence moves between **5 644 and 5 988 µs** per packet
  (167–177 packets/s produced).

**Where the rate variation comes from.** The host loses essentially nothing
(0 gaps, 0 missing, 0 dropped), and the device's own median interval varies
by 6 % between runs. So the 12.6 % spread in the *observed* rate is
**device-side** — how many CSI callbacks the ESP32's Wi-Fi stack delivers
and prints — not host-side USB loss.

**A metric bug found and fixed on the way.** The first campaign reported
rates of 115–159 packets/s with 27 402 "dropped" records. That was the
baseline tool's own bounded queue filling up because the tool never drained
it, so the tool was discarding real packets and then reporting the survivors
as the rate. The tool now drains every iteration, counts *arrivals*, and the
numbers above are the corrected ones.

---

## 3. The transmitting access point

Identified from the device's own ESP-IDF log (read-only, from its USB console):

| | |
|---|---|
| **SSID** | **`Kent State Guest`** |
| **BSSID** | `b8:62:1f:e5:ac:62` |
| Channel / bandwidth | 11 / 20 MHz |
| Security / PHY | open auth / bgn |
| Signal at boot | −69 dBm |
| Board address | 10.7.82.237/20, gateway 10.7.95.254 |

The BSSID in the log matches the `mac` field of every captured CSI packet,
so the board is reporting the CSI of the access point it is associated with.

**The Mac is on a different network** (10.12.182.214/20, gateway 10.12.183.254),
so the Mac cannot be the stimulus for this AP's CSI. This constrains the
motion experiment — see §4.

No network was scanned, and no device other than the one the board was
already associated with was identified or contacted.

---

## 4. The motion experiment

Designed, built and **null-controlled** in
[`docs/design/csi-motion-experiment.md`](../design/csi-motion-experiment.md);
the harness is `tools/esp32_csi_motion.py`.

**Null control** (three identical `stationary` trials, no person moving):

| Trial | Packets | Total amplitude mean | std | RSSI |
|---|---|---|---|---|
| 1 | 2 841 | 622.26 | 91.74 | −64.73 ± 1.11 dBm |
| 2 | 2 946 | 615.96 | 91.59 | −64.98 ± 1.05 dBm |
| 3 | 2 838 | 614.66 | 81.90 | −64.82 ± 1.12 dBm |

**max F = 0.012** — identical conditions give a between/within variance
ratio of ~0.01, which is the metric's noise floor and the bar any real
condition effect has to clear.

**Status: the positive control has not been run.** It needs a consenting
subject. The harness, the statistics, the consent gate and the control are
ready; what is missing is the human trial.

---

## 5. The firmware backup is untouched

```
~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin
  16 777 216 bytes
  sha256 51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0
  read-back MATCH
```

Not re-read, not written, not modified. No flash, no erase, no bootloader
entry beyond the deliberate manual resets used to recover the instrument
between experiments.

---

## 6. Limitations

1. **The stall's internal mechanism is not settled** — the evidence points at
   the ROM USB path rather than a halted application, but the two cannot be
   fully separated without a reset.
2. **The id counter is per printed packet**, so the device's *own* dropped
   CSI callbacks are invisible to us. We can prove the host loses nothing;
   we cannot prove the device prints everything it receives.
3. **The rate is not constant** (12.6 % spread) and the device's cadence
   drifts over the session.
4. **The ambient RSSI range is 30 dB**, so RSSI alone is a weak
   discriminator.
5. **The motion effect is unproven** — only the null control exists.
6. **The DI-188 is still disconnected**, so its acceptance test skips.

---

## 7. Branch integration — proposed sequence (not executed)

The tree is linear, so there is nothing to untangle:

```
main                                b5e1875
 └─ fix/di188-acquisition-shutdown  25b2948   small, self-contained reliability fix
     └─ feature/alpha002-esp32-supervisor  b924a6b   Alpha 002 A + B
```

Proposed sequence, in order:

1. **Merge `fix/di188-acquisition-shutdown` into `main`** on its own. It is
   five files and 10 tests, it is the precondition for the DI-188 acceptance
   test to skip correctly, and merging it alone keeps the history readable.
2. **Merge `feature/alpha002-esp32-supervisor` into `main`**. Because the
   Alpha branch already contains the fix, this merge then contributes only
   the Alpha work.
3. Only then open a pull request for `main`.

**Not done** — no merge has been performed, and `main` is still `b5e1875`.
