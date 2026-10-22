# SPECTER-X controlled-link firmware (`softap_csi`)

**Status: built, not flashed.** Neither image has been written to the board,
and the board has not been reset, erased or modified.

| | |
|---|---|
| Build | ESP-IDF **v5.2.2**, target `esp32s3`, Xtensa LX7 |
| App binary | **449 216 bytes** - 57 % of the 1 MB app partition free |
| Partition layout | **unchanged** from the running image: bootloader at 0x0, table at 0x8000, app at 0x10000 |
| Wire format | **unchanged** - Espressif's `csi_recv_router`, byte for byte |
| Artefact SHA-256 | recorded in `docs/checkpoints/012-*.md` |

---

## 1. What it is for

The CSI stream on the campus link is not an experiment. The board pings the
campus gateway 100 times a second and the CSI is the *downlink* of those
pings, so the transmitter is the campus gateway, the traffic is the board's
own, and the campus network's session policy periodically drops the client
for five minutes at a time (checkpoint 011).

This firmware is for a **local** link: one board, one local peer, a known
geometry, and a traffic pattern we control.

## 2. The two roles

One build, two roles, chosen at build time.

### `SPECTER_ROLE_STATION` (the default, and the known-good one)

The board joins a **local** access point and measures the **downlink** CSI
of the frames that point sends. This is the role the original image used,
so the behaviour is known and the data is comparable with the archive.

* The access point is the **Mac** (hosting a SoftAP) or a **second ESP32**.
* The Mac, as the access point, **generates the controlled traffic** - it
  pings the board at a fixed rate, and the board's ACKs are the downlink
  frames whose CSI is measured. The stimulus is therefore known by
  construction.
* The board does **not** ping anything. The traffic must be exactly what
  the Mac generates.

### `SPECTER_ROLE_SOFTAP` (the role this milestone asked for)

The board **is** the access point and the Mac is the station, so the board
would have to measure the **uplink** CSI of the station's frames.

> **This mode's CSI support is NOT established, and this build does not
> pretend otherwise.**
>
> * Espressif ships **no** SoftAP CSI example. All three of their documented
>   architectures - "get router CSI", "get CSI between devices", "get CSI
>   specific devices" - measure the CSI on a **station**, of a **downlink**.
>   Both `csi_recv` and `csi_send` run `WIFI_MODE_STA`.
> * The IDF does not document the mode either.
> * The ESP32-S3's Wi-Fi is a **precompiled library**
>   (`components/esp_wifi/lib/esp32s3/libpp.a`), so the source cannot
>   answer the question.
> * There are field reports of the S3's CSI callback never firing at all.
>
> **So the firmware answers it at runtime instead of by argument.** The
> `SPECTER_STAT` line carries `csi_cb`, the number of times the callback
> fired. Flash it, join the SoftAP from the Mac, have the Mac send traffic,
> and read one line a second: if `csi_cb` stays at zero, the answer is no.
> That is one minute on the bench, with no guesswork.

## 3. What is preserved, and what is fixed

**Preserved** (so the archive stays comparable and the host parser is
unchanged):

* the CSV header and every field, in the upstream's order, including the
  upstream's two quirks - the second copy of `sig_mode` in the `rx_format`
  slot, and `first_word` carrying the `first_word_invalid` flag;
* the CSI configuration: **LLTF only, channel filter on, manual scale**;
* the gain compensation, applied to the same bytes, so the amplitude values
  on the wire are the values the original image printed.

**Fixed:**

* **The callback no longer formats or prints.** The IDF is explicit:
  *"The CSI receiving callback function runs from Wi-Fi task. So, do not do
  lengthy operations in the callback function. Instead, post necessary data
  to a queue and handle it from a lower priority task."* The original image
  printed 128 formatted numbers inside that callback. Here the callback
  copies the raw bytes and the radio metadata into a record and pushes it.
* **One writer task does all the output**, so a line can never be torn by a
  concurrent write. The output is serialised by construction.
* **The queue is bounded and its losses are counted.** When the queue is
  full the *oldest* record is dropped - a live time series wants the newest
  data - and the drop is counted and reported in `SPECTER_STAT`
  (`drop_old`, `drop_new`). A slow host now costs **counted packet loss**
  instead of a corrupted stream.

`tests/test_firmware_contract.py` enforces the contract between this
firmware and the host parser: the header, the field count, the field order,
the quoted tail, the bounded queue, the callback's restraint, the single
writer, the unchanged CSI configuration and the gain compensation are all
checked, so the two cannot drift apart silently.

## 4. Building

```bash
cd firmware/esp32-csi/softap_csi
source ~/esp/esp-idf/export.sh

# the station role (the default)
idf.py set-target esp32s3
idf.py build

# the SoftAP role
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.softap.defaults" \
       -B build-softap build
```

The `esp_csi_gain_ctrl` component is fetched by the component manager.

## 5. The exact physical steps for the first controlled experiment

**Nothing below has been done.** These are the steps, in order, for the
first Mac ↔ ESP32 controlled link.

### 5.0 Before anything: take a second backup

The 16 MB backup is verified and untouched, but a second one costs nothing:

```bash
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 --after hard-reset \
         read-flash 0x0 0x1000000 /tmp/backup-before-lab.bin
shasum -a 256 /tmp/backup-before-lab.bin
```

### 5.1 Decide the role

* **Try `SPECTER_ROLE_SOFTAP` first.** It is the architecture this
  milestone asked for, and the build's runtime probe answers the open
  question in a minute.
* If `csi_cb` stays at zero, **fall back to `SPECTER_ROLE_STATION`**, which
  is known to work, with the Mac hosting the access point.

### 5.2 Put the Mac on the air

macOS 27 has no `airport` tool, so the SoftAP has to be **Internet
Sharing**:

1. Give one of the unused USB Ethernet adapters (`en2` or `en3`) an address.
   The Mac's only uplink is Wi-Fi, and Internet Sharing needs a wired one.
2. System Settings → General → Sharing → Internet Sharing → share **Wi-Fi**
   from that Ethernet adapter, and set the shared network's **name to the
   SSID the firmware is configured with** (`SPECTER-LAB` by default).
   *In the SoftAP role the board publishes this name; in the station role
   the board joins it.*
3. **This takes over the Wi-Fi radio and will drop this session's own
   connectivity.** Do it in a way that survives it - a local terminal, not
   over the network.

### 5.3 Flash the new image (over the UART bridge, not the native USB)

```bash
cd firmware/esp32-csi/softap_csi
# the native USB port is the fastest path, but the UART bridge is the one
# that is proven; pick one and use it consistently
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 \
         write-flash 0x0  build/bootloader/bootloader.bin \
                      0x8000 build/partition_table/partition-table.bin \
                      0x10000 build/specter_csi_lab.bin
```

### 5.4 Check it, in this order

1. **The console log** (UART0, **921600 baud** - the rate in
   `sdkconfig.defaults`, and the one that makes the log readable):

   ```bash
   python3 tools/esp32_console.py --seconds 20
   ```

   Look for `SPECTER-X controlled-link firmware ready` and, in the SoftAP
   role, `station <mac> joined`.

2. **The CSI stream** on the native USB port, and **the status line**:

   ```bash
   python3 tools/esp32_csi_baseline.py --seconds 30
   ```

   `SPECTER_STAT` must show `csi_cb` climbing and `drop_old=0`.

3. **The capability probe** (SoftAP role only): have the Mac send traffic
   and watch `csi_cb`. If it stays at zero while the Mac is pinging the
   board, the S3 does not do AP-side CSI, and the station role is the path.

### 5.5 The first controlled measurement

Once the link is up, the Mac pings the board at a **fixed rate** (say
20 packets/s) - those ACKs are the downlink frames - and the subject stands
at a **marked distance**. Then run the experiment exactly as checkpoint 011
specifies it: **7-10 repetitions per condition, randomised, blinded, with
the subject's position recorded and the PHY rate conditioned on.**

## 6. Known limitations of this build

1. **The SoftAP role's CSI is unverified** - that is the point of the
   probe, and the reason the station role exists.
2. **The `esp_csi_gain_ctrl` component is the one from the registry**, at
   whatever version the manager resolves (`>=0.1.4`). The original image
   used an unknown version of the same component, so the *absolute* gain
   compensation may differ slightly. The **normalised** features - the ones
   the analysis uses - are unaffected by a constant scale.
3. **The queue holds 32 records** - about 180 ms at 178 packets/s. A host
   that stops reading for longer than that will cost dropped records, which
   are counted. It will not corrupt the stream, and it will not wedge the
   device the way the original image's in-callback `printf` did.
4. **The writer task formats 128 numbers per packet.** At 178 packets/s
   that is ~23 000 numbers a second, which the S3 can do, but it is the
   heaviest part of the build. If the link ever drops frames, this is the
   first thing to look at.
5. **The `local_timestamp` still wraps** at 2^32 µs (71.6 minutes). The
   host now reads it as unsigned; an analysis that differences it must
   still handle the wrap.
6. **No supervisor telemetry is emitted by this build.** The `HELLO` /
   `STAT` / `HB` protocol (checkpoint 003) is a separate piece of work and
   is not in this image. The `SPECTER_STAT` line here is the firmware's own
   status, and it is **not** the supervisor protocol - the host will not
   mistake the two, because the tags differ.
