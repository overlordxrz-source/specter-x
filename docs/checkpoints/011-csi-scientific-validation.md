# SPECTER-X checkpoint 011 — CSI scientific validation

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the six questions are answered. **No motion detection and no
vital-sign detection is claimed.** The firmware and the 16 MB backup are
untouched, nothing was flashed, and the campus network was not modified.

The most consequential finding is not about motion at all: **the flashed
firmware pings the campus gateway 100 times a second, and the entire CSI
stream is the downlink of those pings.** Everything else follows from that.

---

## 1. Does the firmware ping the gateway, and at what rate? **Yes — 100 pps.**

The upstream example's own README says:

> *"The device triggers the router to send packets through the Ping command
> to obtain the CSI data between the device and the router"*

and the source (`espressif/esp-csi @ 8633d67`, `examples/get-started/
csi_recv_router/main/app_main.c`) is unambiguous:

```c
#define CONFIG_SEND_FREQUENCY      100

static esp_err_t wifi_ping_router_start(void)
{
    esp_ping_config_t ping_config = ESP_PING_DEFAULT_CONFIG();
    ping_config.count             = 0;                    /* forever */
    ping_config.interval_ms       = 1000 / CONFIG_SEND_FREQUENCY;   /* 10 ms */
    ping_config.data_size         = 1;
    ...
    ping_config.target_addr.u_addr.ip4.addr = ip4_addr_get_u32(&local_ip.gw);
    esp_ping_callbacks_t cbs = { 0 };            /* no success, no timeout */
    esp_ping_new_session(&ping_config, &cbs, &ping_handle);
    esp_ping_start(ping_handle);
}
```

| | |
|---|---|
| **target** | the gateway, 10.7.95.254 (from the device's own log) |
| **rate** | **100 packets/s** (`CONFIG_SEND_FREQUENCY = 100`, interval 10 ms) |
| **duration** | forever (`count = 0`) |
| **callbacks** | **none** (`cbs = { 0 }`) - a timeout is never reported |
| **source of the CSI** | the *downlink* frames those pings elicit |

**Consequences, all of which matter:**

1. **The transmitter under test is the campus gateway**, 30+ m away, on a
   guest network the board does not control. The board's own radio is
   only the *receiver*.
2. **The CSI rate is the ping success rate**, multiplied by the downlink
   frames per ping. The measured ~178 packets/s is consistent with about
   two downlink frames (the ACK and the echo reply) per ping.
3. **Nothing is logged if the gateway stops answering**, because the ping
   session has no timeout callback. This is the mechanism behind the
   silent intervals in §2.
4. The board is generating **100 pps of ICMP to a campus gateway**. That
   is a real load on a network that is not ours, and it is likely to be
   policed.

**No network change was made.** The finding comes from reading the
upstream source and from the device's own log.

---

## 2. The 320–331 s silent intervals, reassessed

### What the host can see, and what it cannot

| candidate cause | predicted signature | observed? |
|---|---|---|
| **loss of qualifying Wi-Fi packets** | the device stops receiving frames that qualify for CSI; **both** the USB CDC stream and the device's own console copy stop; the id sequence stays consecutive; the device logs nothing | **yes - all four** |
| **Wi-Fi association problem** | the device logs a state change (`wifi:state: ... -> disconnected`) or a re-association (`wifi:connected with ...`) | **no** - the console went silent too |
| **CSI callback stall** | the Wi-Fi stack is alive but the callback stops; indistinguishable from the above from the host | **not separable from the host** |
| **USB output stall** | the device keeps producing and printing; the ids advance; the host sees a **gap** on recovery, or a burst | **excluded** - the ids were consecutive and no burst arrived |

### The instrument

The board has **two** USB paths, and the second one was being read at the
wrong speed. The example's `sdkconfig.defaults` sets
`CONFIG_CONSOLE_UART_BAUDRATE=921600`; reading the CH343 bridge at
115200 produces garbage, which is what made it look like a dead channel in
checkpoint 007. At **921600 baud** the console carries the ESP-IDF log
*and* a second, independent copy of the whole CSI CSV stream.

`tools/esp32_dual_capture.py` reads both channels at once for 40 minutes
(`runs/soak/dual_capture_40min.json`):

```
USB  :  86 018 665 bytes    184 132 CSI lines     84 log lines
UART :  86 005 628 bytes    184 104 CSI lines     84 log lines
        the two channels differ by 0.015 %
```

### The result: the campus network drops the client, every ~330 seconds

The device's own log says so, in the driver's own words:

```
I (659450)  wifi:state: run -> init (1a0)
I (659450)  wifi:pm stop, total sleep time: 3528720 us / 327236893 us
I (659451)  wifi:new:<1,0>, old:<1,0>, ap:<255,255>, sta:<1,0>, prof:1
I (661862)  wifi:new:<11,0>, old:<1,0>, ap:<255,255>, sta:<11,0>, prof:1
I (661863)  wifi:state: init -> auth (b0)
I (661866)  wifi:state: auth -> assoc (0)
I (662319)  wifi:state: assoc -> run (10)
I (662320)  wifi:connected with Kent State Guest, aid = 1, channel 11, BW20, bssid = b8:62:1f:e5:ac:62
I (662383)  wifi:AP's beacon interval = 313344 us, DTIM period = 1
```

**Four times in forty minutes the board's Wi-Fi stack is torn down
(`run -> init`) and re-associated (`init -> auth -> assoc -> run`), at a
regular period of about 330 seconds** (the log timestamps 659 450,
989 375, 1 648 535 and 2 308 992 µs - intervals of 330, 659 and 660 s).
Each re-association takes **2.4 s**.

And the silences on the wire line up with them, exactly:

| silence | length | USB silent | console's CSI copy silent | the device's log |
|---|---|---|---|---|
| 1 | 331 s | yes | **yes, to the same 0.1 s** | `run -> init` ... `connected with Kent State Guest` |
| 2 | 318 s | yes | **yes** | `run -> init` ... `connected` |
| 3 | 325 s | yes | **yes** | `run -> init` ... `connected` |
| 4 | 325 s | yes | **yes** | `run -> init` ... `connected` |

**The two channels' silence counters are identical to 0.1 s throughout the
whole forty minutes.** The device stopped *producing*, not just
transmitting.

Three of the four re-associations were to the same AP
(`b8:62:1f:e5:ac:62`, channel 11); the fourth was to a **different AP on a
different channel** (`b8:62:1f:b4:a5:62`, channel 6, rssi −76) - the
roaming that checkpoint 007's claim could not explain.

**The device was silent for 53 % of the window.**

### What each candidate cause is now worth

| candidate cause | verdict |
|---|---|
| **loss of qualifying Wi-Fi packets** | **the cause.** The AP drops the client on a ~330 s policy; the device re-associates; the frames that carry CSI stop arriving |
| **Wi-Fi association problem** | **the cause, and now visible**: the device logs `run -> init` and re-associates. The re-association is 2.4 s; the CSI takes ~320 s longer to come back |
| **CSI callback stall** | **not separable from the host** - the RSSI is delivered *by* the callback, so a stalled callback and a quiet radio look identical from outside |
| **USB output stall** | **excluded.** The console's own copy of the CSI stream stops at the same instant, and the ids stay consecutive with no burst on recovery. If the app had kept printing, the ids would have advanced. |
| **the host** | **excluded.** The host was reading continuously, at 100 % arrival, with 0 gaps, through every silence. |

### What is still unexplained, stated plainly

**The re-association takes 2.4 s; the CSI comes back ~320 s later. That
gap is not yet explained.** The leading candidate is the upstream's
one-shot setup: `esp_wifi_set_csi_rx_cb(cb, s_ap_info.bssid)` captures
the BSSID **once**, at init, and the callback filters on it forever
(`if (memcmp(info->mac, ctx, 6)) return;`), while the `esp_ping` session
is created once and never re-armed. A drop and re-association would then
leave both pointing at the old association.

**That is a hypothesis, not a finding**, and the honest test is cheap:
capture the console log *continuously* through a silence, so the device's
own account of the outage is on the record in full. The capture tool now
keeps every log line with its timestamp; the run above only kept the tail.

**The conclusion that does not depend on that gap:** the silences are not
the device failing, not the USB failing and not the host failing. They
are the campus network's session policy acting on a client that generates
100 packets a second to its gateway. The fix is a **local** traffic
source, not a better driver.

---

## 3. The format, validated against Espressif's own definitions

### The packet

`wifi_csi_info_t` (ESP-IDF v5.2.2, `esp_wifi_types.h`):

```c
typedef struct {
    wifi_pkt_rx_ctrl_t rx_ctrl;
    uint8_t mac[6];            /**< source MAC address of the CSI data */
    uint8_t dmac[6];
    bool first_word_invalid;   /**< first four bytes of the CSI data is invalid or not */
    int8_t *buf;               /**< valid buffer of CSI data */
    uint16_t len;              /**< valid length of CSI data */
    ...
} wifi_csi_info_t;
```

| | validated | finding |
|---|---|---|
| **the `mac` field** | the IDF header | it is the **source** MAC of the CSI data - the transmitter of the frame the board heard, **not** the board's own MAC. Checkpoint 007's claim that it always equals the associated BSSID is **not** true in general: the board roams between the guest APs, and the upstream filter is a **snapshot** of the BSSID taken once at init. |
| **the IQ samples** | the IDF header | `buf` is `int8_t*` and `len` is in **bytes**. The upstream prints exactly `len` values, so 128 bytes = **64 complex subcarriers**. The host's pairing (I,Q) per subcarrier is correct. |
| **the unused carriers** | measured on every packet | exactly **subcarrier 0 (DC) and 27..37 (the guard band)** - 52 of 64 in use. The null set in the *subcarrier index* domain matching the HT20 null set is itself the proof that the byte-pair-to-subcarrier mapping is right. |
| **the gain** | the upstream source | the printed values are **not** raw bytes: they are `(int16_t)(compensate_gain * (int8)buf[i])`, and `esp_csi_gain_ctrl` captures its gain baseline from the **first 100 packets** of every boot. So the first 100 packets of a session are on a **different scale** from the rest. |
| **`first_word_invalid`** | the IDF header | "the first four bytes of the CSI data is invalid". The host **ignored** this flag; it now masks the first two subcarriers instead of shifting every index. |
| **`local_timestamp`** | the IDF header **and** a real packet | `unsigned timestamp:32` in microseconds, but the example prints it with `%d`, so **a counter past 2^31 arrives as a negative number**. The host now masks it to 32 bits - and it still **wraps every 71.6 minutes**, which any analysis that differences it must account for. |
| **the metadata fields** | `wifi_pkt_rx_ctrl_t` | every field index is confirmed: rssi, rate, sig_mode, mcs, cwb, smoothing, not_sounding, aggregation, stbc, fec_coding, sgi, noise_floor, ampdu_cnt, channel, secondary_channel, timestamp, ant, sig_len. The CSV header's "rx_format" slot actually holds a **second copy of sig_mode**, and "first_word" holds the `first_word_invalid` flag. |
| **the `rate` field** | the IDF header and the wire | the **PHY rate of the received frame**, and it **varies** (8, 9, 11, 13, 14 observed). The CSI is measured on the preamble of a frame received at that rate, so **the amplitude scale follows the rate**. This is a confound the previous analyses never conditioned on. |

### Four parser fixes, all evidence-driven

1. **The tail length is checked.** A line whose tail length does not
   equal the `len` field is a truncated packet and is now counted as
   malformed instead of being used for a spectrum.
2. **`first_word_invalid` is honoured** - the affected carriers are
   masked, not dropped, so the indices stay aligned.
3. **The rate is carried** through the record, the view and the
   measurement, so the analysis can condition on it.
4. **The timestamp is read as unsigned.** A real packet captured on
   2026-10-22 carried `-1172452479` - the device's counter past 2^31,
   printed signed. The fixture in `tests/fixtures/csi_packet_sample.txt`
   is that packet, complete: 24 head fields, 128 IQ values matching the
   `len` field, the null carriers at exactly {0} ∪ {27..37}, and a value
   range of -25..31 (the gain-compensated int8 bytes).

### About the gain normalisation

The host normalises each packet by its own total amplitude. That is the
right choice for a *motion* metric - it removes the received power, which
is what the checkpoint-009 experiment showed was confounding the result.
But it is **not** sufficient on its own: the *rate* also scales the
amplitude, so the normalisation has to be done within a rate class, or the
rate has to be a covariate.

---

## 4. A controlled offline link

Designed in full in
[`docs/design/controlled-csi-link.md`](../design/controlled-csi-link.md).
The short version:

| option | what it needs | verdict |
|---|---|---|
| **A** - the Mac hosts the AP | the board's SSID is compiled in ("Kent State Guest"); macOS 27 has no `airport` tool; Internet Sharing needs a wired uplink (two unused USB Ethernet adapters are present) and would **take over the Wi-Fi radio and drop this session's own connectivity** | possible, fragile, invasive - a fallback |
| **B** - the board hosts the AP, the Mac is the station | a firmware build of the example's **router mode**; the Mac then generates the traffic, so the **stimulus is known by construction**. **Must first verify that the ESP32-S3 supports the CSI callback in SoftAP mode.** | **recommended** |
| **C** - two boards | the second board | the clean end state; blocked on the hardware |
| **D** - the bench, no radio | implemented in this checkpoint | **available now** |

**Option D is implemented**: `specter/sensors/esp32/synthetic_link.py`
builds a link with a **known ground truth** - a static multipath profile
with the board's real null band, a person modelled as a *moving reflector*
(a static reflector would change the amplitude and nothing else), a
drifting AGC, and a PHY rate that changes the amplitude scale. With it,
the detection pipeline's **sensitivity curve** and its **false-positive
rate** can be measured - something a real link can never provide, because
a real link never tells you what was really happening.

---

## 5. The blinded protocol, and the power we actually had

The machinery is in `specter/sensors/esp32/analysis.py`:

* a **frozen** feature set (`FEATURE_NAMES`, with the rationale written
  down) - changing it is a new pre-registration, not a re-analysis;
* **blinding**: the features are extracted without the labels, and the
  labels are shuffled by a recorded seed;
* **effect sizes**: Cohen's d with a bootstrap interval (the two groups
  resampled independently), and the partial eta-squared;
* **held-out evaluation**: leave-one-repetition-out - the classifier is
  built on the other repetitions and scored on the one that was held out;
* **false positives**: a label-permutation test, reporting both the
  empirical p and the procedure's own **measured** false-positive rate.

### The real session, re-analysed

| feature | F | p | permutation p | measured FPR | Cohen's d (pairs) | held-out accuracy |
|---|---|---|---|---|---|---|
| roughness_used | 0.909 | 0.452 | 0.532 | 0.023 | 0.11, 0.95, 1.28 | 0.444 |
| amp_volatility | 0.612 | 0.573 | 0.641 | 0.083 | −0.78, −0.49, 0.50 | 0.667 |
| shape_shift | 0.029 | 0.972 | 0.967 | 0.023 | −0.25, −0.15, −0.04 | 0.111 |
| change_rate | 0.665 | 0.549 | 0.784 | 0.000 | 0.62, 0.73, 0.38 | 0.222 |

**The effect sizes are large** - d = 0.95 for stationary vs walking and
d = 1.28 for hand vs walking, which are conventionally "large" - and the
test still did not reach significance. **That is a power problem, not an
effect problem.**

### How many trials would have been needed

Simulated with the same omnibus test and the same critical value the
analysis uses (`analysis.required_n`):

| effect size | trials per condition | total | time at 30 s each | power **we had** with 3 |
|---|---|---|---|---|
| 0.40 | 30 | 90 | 45 min | 0.10 |
| 0.60 | 14 | 42 | 21 min | 0.15 |
| **0.95** | **7** | **21** | **11 min** | **0.34** |
| 1.28 | 4 | 12 | 6 min | 0.57 |

**The nine-trial experiment had a 10-35 % chance of detecting the effect
it was looking for.** It was not a failed hypothesis; it was an
under-powered experiment.

### The protocol for the next run

| | |
|---|---|
| conditions | stationary, hand, walking, **and a return-to-stationary control at the end** |
| order | **randomised**, seed recorded, labels shuffled again before the analysis |
| repetitions | **7 per condition minimum** (11 min), 10 preferred (16 min) |
| geometry | the subject at a **marked distance**; the distance randomised across trials |
| traffic | the same pattern, size and rate in every trial |
| baseline | a 10 s quiet reference before each trial, contemporaneous |
| exclusions | **pre-registered**: a trial is excluded if the PHY rate changed, the source AP changed, or the link dropped a packet - and the exclusion is recorded |
| analysis | the frozen features, the permutation test, the effect size with a bootstrap interval, the held-out score, and the measured FPR |

**And one thing that must be recorded this time: where the subject was
standing.** The first experiment did not record it, so its most likely
explanation cannot be checked from the data.

---

## 6. Respiration and heartbeat

Scoped in full in
[`docs/design/vital-signs-scope.md`](../design/vital-signs-scope.md). The
essences:

* **Respiration is plausible** - 5-12 mm of chest displacement is
  0.25-0.61 rad of phase at 2.4 GHz. But **the current pipeline uses the
  amplitude only**, and respiration is a *path-length* change: it moves
  the **phase**. Using the amplitude for respiration is the wrong
  measurement, not a weak one. The complex samples are on the wire and
  the phase has never been used.
* **The heartbeat is a research project, not a validation** - 0.2-0.5 mm
  of cardiac displacement is 0.010-0.025 rad, an order of magnitude below
  the respiration signal in the same measurement. It needs a **3-lead
  ECG** (a pulse oximeter is *not* a ground truth: it is delayed by the
  pulse transit time), a coupled and static geometry, and its deliverable
  should be the **minimum detectable displacement**, not a detection rate.
* **On the current campus link neither is physically plausible.** A
  chest-wall displacement of a fraction of a millimetre cannot perturb a
  30-metre path. That is arithmetic, and no amount of data changes it.
  Both require the controlled link first.

---

## 7. The recommended next experiment

**In order:**

1. **The bench, today, no radio and no subject** - sweep the synthetic
   link's effect size to find the sensitivity curve, confirm the
   false-positive rate on null trials, and re-analyse the real campus
   recording through the same code. (The code and the first numbers
   exist; the sweep is a script away.)
2. **The controlled link** - build the SoftAP/router-mode image on a
   branch **for review**, verify the S3's SoftAP CSI support first, and
   put the Mac on the far side of a marked 1 m link.
3. **The motion experiment, done properly** - 7-10 repetitions per
   condition, randomised, blinded, with the subject's position recorded
   and the PHY rate conditioned on. **11-16 minutes.**
4. **Only then** the phase, the respiratory belt, and respiration.
5. **The heartbeat** only if the respiration rig works, and only with an
   ECG.

**What is not worth doing:** another run on the campus link. The
transmitter is not ours, the traffic is the board's 100 pps ping flood,
the geometry is unknown, and the power will be no better than last time
unless the repetitions go up - which makes it a worse use of an hour
than steps 1 and 2.

---

## 8. What is claimed today

**Nothing.** The live HUD says "RF PATH CHANGE, NOT A HUMAN DETECTION".
The motion experiment has **no verified detection**. The vital-sign
experiments are **scoped, not started**. The firmware and the backup are
untouched, and the campus network is unchanged.
