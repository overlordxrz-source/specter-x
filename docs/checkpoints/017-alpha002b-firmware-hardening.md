# Checkpoint 017 — Alpha 002-B: firmware hardening

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **All five items are implemented, regression-tested and built for
both roles. Nothing has been flashed, reset or merged, and the device is
still running the Alpha 002 image.** The work is ready for one authorised
hardware session; the plan is in §7.

Builds: `77313e00af7c5b57` (SoftAP app), `9fe9cdfc03256639` (station app),
bootloaders `36c01f506c2916da` / `4af240ba3deb5789`. Tests: **306 passed, 1
skipped** (was 287).

---

## 1. WPA2 for SPECTER-LAB, with the credential outside Git

The lab network was **open**. A Kconfig option held the passphrase, and a
Kconfig value lives in a tracked `sdkconfig.defaults` — a published
passphrase. That option is gone.

The credential now comes from the build environment, and the build
**generates the header into the build directory**, which is gitignored, so the
secret never enters the source tree:

| | |
|---|---|
| `tools/lab_credentials.py init` | writes `firmware/esp32-csi/softap_csi/lab.env` — gitignored, mode 600, a random 20-character passphrase |
| the build | reads `SPECTER_LAB_PSK` from the environment, validates it (8–63 characters, an alphabet that needs no C escaping), and writes `lab_credentials.h` into `<build>/esp-idf/main/` |
| the firmware | uses `WIFI_AUTH_WPA2_PSK` when the credential is present, and `WIFI_AUTH_OPEN` with a loud boot warning when it is not |

Two properties are enforced rather than documented:

* **The build fails closed.** With no credential it refuses to build, with a
  message that says where to put one. An accidentally open lab AP is a
  silent failure, and it is now impossible by accident. An open build has to
  be asked for: `-DSPECTER_LAB_ALLOW_OPEN=ON`. *Verified:* the build was run
  without a credential and stopped with exactly that error.
* **The secret is never printed.** `lab_credentials.py init` prints the
  *path*, not the passphrase; `show` prints the length and not the value;
  `env` prints an export line and says first that it is a secret. The tool
  also refuses to write the credential anywhere git does not ignore.

**What this costs, stated plainly:** the passphrase is compiled into the app
image, so **the image and any flash backup taken from it are secrets** — an
image holder can associate with the lab network. The backups taken before
this change contain no credential and stay safe. A runtime provisioning path
(entering the credential over the console, stored in NVS) would keep the
image non-secret; it is deliberately **not** in this pass, because a
plaintext credential setter on a serial console is a security decision that
deserves its own review.

## 2. The 16 MB flash configuration

The symptom was a boot warning: *"Detected size(16384k) larger than the size
in the binary image header(2048k)"*, and the runtime falling back to 2 MB.
The cause was **not** the app image.

Reading the headers out of the verified 16 MB backup settled it:

| region | declared flash size |
|---|---|
| bootloader at `0x0` | **2 MB** |
| app at `0x10000` (the image that was running) | **2 MB** |
| app at `0x10000` (our build, before this pass) | 16 MB |
| bootloader (our build, before this pass) | 16 MB |

The size the ROM gives the driver comes from the **bootloader's** header, not
the app's: `esp_flash_init()` compares the physical chip against
`g_rom_flashchip`, which the ROM bootloader fills from the image it loaded
first. The device's bootloader says 2 MB, so the device ran with 2 MB — and
our app-only write could not change that, because it deliberately left
`0x0`–`0x9000` untouched to keep the rollback path intact.

So the app image was already correct and the fix is the **bootloader**. Both
roles now build a bootloader whose header declares 16 MB (verified in the
artefacts: `spi_size=16MB` for app and bootloader, both roles), and the
proposed flash command writes `0x0`, `0x8000` and `0x10000` with
`--flash_size 16MB`.

The device now also **reports what it actually has**, so the mismatch is
visible instead of being a warning in a log:

```
flash: 2048 kB available at runtime, 16384 kB on the chip
```

and on the status line, `flash_kb=2048,flash_phys_kb=16384`. The preflight
turns that into a check: the runtime size must be 16 MB, and it **FAILS**
until the bootloader is rewritten. It is UNKNOWN on the old firmware, which
does not report it. *Verified against the running device:* the v3 tool
reports `flash size: not reported by this firmware → UNKNOWN` and does not
crash.

**Not done, and it matters:** the app partition in the device's partition
table is 1 MB. The new app is 745 KB — 29% of the partition — so it fits,
but the headroom is small. The partition table is prepared for the next
session; growing it means writing `0x8000` as well.

## 3. Preflight accounting: three counts, kept apart

The v2 score compared the **CSI callback total** with the offered traffic
rate. A callback fires for every frame the radio hears, including the empty
ones a station sends to keep an association alive, so the passing capture
reported **394% continuity** — a number that meant nothing. The honest
figure, from the payload frames alone, was 600 received against 596 expected.

Scoring **v3** separates them:

| count | what it is | how it is obtained |
|---|---|---|
| callbacks | how often the CSI callback fired at all | the device's `csi_cb` |
| records | how many records reached the wire | the device's `printed` |
| rejected | how many callbacks produced nothing | the device's `rej` (new) |
| **data frames** | records whose frame carried a payload | classified from the signal length |
| **null-data frames** | records whose frame carried none | classified from the signal length |
| **ambiguous** | records whose length is too close to the boundary to classify | classified from the signal length |

Continuity is now computed from the **data frames** alone, and the frame mix
is reported. The device's own counters are compared against the host's — two
independent counts, so transport loss shows up as a *difference* rather than
as a silence. *Verified against the running device:* `30 host, 30 device
(0.00% apart)`.

**The classifier and its honest limit.** The Wi-Fi driver does not expose the
802.11 frame type, so the **signal length** is the only discriminator
available. A frame with no payload is exactly 28 bytes (24-byte MAC header +
4-byte FCS); every payload frame observed on this link was ≥ 66. The 29–32
band is counted **separately** rather than guessed into a class, because a
short QoS null frame would land there, and a wrong answer there would
corrupt the continuity figure rather than merely look untidy. The
signal-length histogram is recorded in every observation so the assumption
can be audited on each run instead of trusted once. Frames that cannot be
classified **fail** the check: an unclassifiable frame is a hole in the
accounting, not a detail.

**Scores remain versioned.** v3 is a new version; a v1 or v2 capture replays
as UNKNOWN for the v3 questions rather than inheriting a verdict. The
original v1 and v2 JSON and raw files are untouched, and the v3 run writes
new files.

## 4. USB line splicing

### What the evidence shows

The three preserved captures were analysed byte by byte. Three distinct
signatures appear, and none of them is a format change:

1. **A duplicated fragment inside a line.** From the crashed attempt's first
   bytes:
   ```
   6,csi_cb=4223,printed=3859,drop_i_cb=4223,printed=3859,drop_old=0,…
   ```
   The same text appears twice, with a truncated piece in front of it. This
   is what **two writers and a buffered stdio** produce: `fwrite()` of a
   500-byte line goes out in stdio-sized chunks, and the other task's output
   lands between two of them.

2. **A line cut and another record spliced into the gap.** The line that
   killed the CSI reader thread was a CSI record cut after 18 fields, with
   the *status* line's own fields in the place of the timestamp — the
   `SPECTER_STAT,` prefix itself was gone. Bytes were lost in the middle of
   the stream.

3. **A record truncated with binary garbage.** The first CSI line of
   `phone-station.raw`, cut at the timestamp field, followed by invalid
   UTF-8. This one is at **port open**: the reader arrived late and the
   backlog was already in flight. The tool's drain (0.25 s before the
   window) addresses it, and it is not a link fault.

Signatures 1 and 2 are consistent with the firmware's own output path, which
had **two writers**: `writer_task` for the data lines and `status_task` for
the status line, both calling `fwrite()`/`fputs()`/`fflush()` on the same
`FILE*`. The handbook had recorded this as an open gate — *"inspected
app_main.c contains both writer_task and status_task writing to stdout"* —
and the contract test explicitly permitted it. It is now closed.

### The fixes

**Firmware — one writer, one write per line.** `stdout` is unbuffered
(`setvbuf(…, _IONBF, 0)`), every line — data, status **and** the IDF's own
log lines — goes out through one `console_emit()` that issues a **single
`write()`** for the whole line under a mutex. A line can no longer be split
by the stdio layer, and two tasks can no longer interleave inside one. The
contract test now *requires* this: no `fwrite`/`fputs` anywhere in the
firmware, one `write(fileno(stdout)…)`, and the IDF log routed through the
same path.

**Host — the stream survives a damaged record.** The parser gained
`feed_resilient()`, which splits a line at every record start it contains and
parses each piece separately:

* one piece that parses — an ordinary line;
* several pieces that all parse — a **lost newline** joined two records, no
  data was lost, and **both** are recovered;
* a piece that does not parse — real damage, counted as malformed, and a
  status line spliced into it is salvaged as text.

The preflight now counts malformed lines, spliced lines and rescued records
separately, and the capture continues. A lost record still shows up as a
**sequence gap**, so the loss is visible rather than closed.

**A limitation, stated rather than hidden:** a splice that lands exactly at
the boundary between a record's metadata and its IQ tail **cannot be
detected** by the current wire format, because the format carries no
checksum. Such a record would carry one frame's metadata and another's
spectrum. Detecting it needs a checksummed format — a wire-format change,
which is out of scope for a hardening pass and is left as a follow-up.

**An evidence gap, also closed:** `--raw-out` used to preserve only the
console path, so a record damaged on the native USB path was never saved.
Both paths are now preserved: `<raw-out>` is the console stream and
`<raw-out>.csi` is the native USB stream.

## 5. The experiment documentation, corrected

Checkpoint 016 stated the cadence difference as *"the station sleeping"* and
reported the two phone trials as *"idle / screen off"* versus *"awake, app in
foreground"*. **Both were over-claims.** The failing and the succeeding
iPhone trials used **different traffic apps**, so the two are confounded:
whether the app sends, at what rate, and whether the operating system
suspends it all changed at the same time as the phone's power-saving
behaviour.

What the device-side evidence actually establishes is narrower and still
useful: in the failing capture the phone put **one** payload frame on the
link in 60 seconds, and in the succeeding one it put **600**. The phone
transmitted almost nothing. The device's own counters show no firmware-side
loss in either case.

Checkpoints 015 and 016 are corrected in place: the mechanism is now listed
as **not separated** among at least three candidates (802.11 power save with
a DTIM schedule, the OS suspending the app, the app simply not sending), the
table labels name the *trial* rather than a measured phone state, and the
claim that the silence is phone-side is kept — because that much is
established by the device's counters.

## 6. What was NOT done

* **No flash, no reset, no merge.** The board is still running the Alpha 002
  image, with the phone associated. The working firmware and the verified
  backups are untouched.
* **No wire-format change.** The CSI record is still Espressif's
  `csi_recv_router`, byte for byte, and the host parser still reads it
  without change.
* **No runtime credential provisioning** (§1).
* **No partition-table change on the device** — the table is prepared, not
  written.
* **No unrelated redesign.** The flash-size work changes what is written, not
  what the firmware does.

## 7. The hardware validation plan

One authorised session, in this order. Each step has an acceptance
criterion, and each step can stop the session.

**Before anything is written**

1. Re-verify the flash: read `0x0`–`0x10000` and compare with
   `esp32s3-csi-flash-backup-20261022-verify.bin` (the known-good backup).
   **Acceptance:** byte-identical. **If not: stop** — the rollback base is
   not what we think it is.
2. `tools/lab_credentials.py check` — the credential is present, sane and
   git-ignored. Read the passphrase off the machine for the phone; do not
   paste it anywhere.

**The write** (app-only is not enough this time — the bootloader is the
point)

3. Write all three regions with the built bootloader, partition table and
   app, `--flash_size 16MB`:
   `0x0 bootloader.bin`, `0x8000 partition-table.bin`, `0x10000 app.bin`.
   The app is at the same offset as before, so the rollback image stays valid
   for the app region.
4. Independent `verify_flash` read-back. **Acceptance:** digest matched.
5. Read back `0x0`–`0x9000` and confirm the bootloader header now declares
   16 MB.

**The boot**

6. **Acceptance:** the boot log contains
   `flash: 16384 kB available at runtime, 16384 kB on the chip`, **and no**
   "Detected size … larger than the size in the binary image header" warning.
   The SoftAP comes up on channel 6, the phone **joins with the WPA2
   passphrase** (this is the first test of the credential), and it gets
   `192.168.4.x`.
7. **Acceptance:** the status line shows the new counters —
   `rej=`, `data=`, `null=`, `amb=`, `flash_kb=16384`, `flash_phys_kb=16384`.

**The acquisition**

8. With the phone associated and generating 10 Hz of traffic against
   `192.168.4.1`, run the preflight for 60 s under scoring v3:
   ```
   .venv/bin/python tools/esp32_lab_preflight.py --seconds 60 --expect-rate 10 \
     --raw-out runs/alpha002_hw_validation_20261022/preflight-v3.raw \
     --out runs/alpha002_hw_validation_20261022/preflight-v3.json
   ```
   **Acceptance:** `subcarrier nulls` PASS, `active subcarrier coverage`
   PASS, `frame mix` PASS with **0 ambiguous**, `device vs host record count`
   PASS, `flash size` **PASS** (this is the check that was failing), and
   `packet continuity` computed from the data frames.
9. Confirm the splice behaviour directly: the run's two raw files must both
   exist, and any malformed line in them must be followed by intact records
   with no unexplained sequence gap.

**The fallback**

10. If the bootloader write does not bring the runtime up to 16 MB, the
    device is still bootable: the app region is unchanged and the original
    app image (`54ef5eeb…6c8a065`) is the rollback. Restore `0x0`–`0x9000`
    from the verified backup. **The 2 MB runtime was not a failure to
    operate** — it was a defect in the configuration, and the app works
    inside it.

## 8. Still unproven

| Question | Status |
|---|---|
| That the WPA2 build boots, associates and streams | **not yet** — built and tested at the source level, never flashed |
| That the 16 MB runtime is reachable | **not yet** — the bootloader is built with the right header; the write has not happened |
| Motion or vital-sign detection | **nothing measured** — unchanged by this pass |
| Sustained unattended reliability | **no** — and the phone's behaviour is now known to be confounded |
| Performance superiority | **no comparison exists** |
| A splice at the metadata/IQ boundary | **undetectable** with the current format; needs a checksum |
| A controlled cadence experiment | **no control condition** — still needs a station whose behaviour we control |

## 9. Evidence

| Artefact | SHA-256 (first 16) |
|---|---|
| `build-softap/specter_csi_lab.bin` (745 056 B) | `77313e00af7c5b57` |
| `build-softap/bootloader/bootloader.bin` | `36c01f506c2916da` |
| `build-station/specter_csi_lab.bin` (744 848 B) | `9fe9cdfc03256639` |
| `build-station/bootloader/bootloader.bin` | `4af240ba3deb5789` |
| `partition-table.bin` (both roles) | `7f00b6c042a89b15` |

Both apps and both bootloaders carry `spi_size=16MB` in their image headers.
The verified flash backup `esp32s3-csi-flash-backup-20261022-verify.bin`
(`51ae0968…602458f0`) was not modified, and no device was touched.
