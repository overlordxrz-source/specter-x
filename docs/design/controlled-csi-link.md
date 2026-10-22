# A controlled, offline CSI link

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** a design. **Nothing is flashed, and the campus network is not
touched.**

---

## 1. Why the current link cannot be an experiment

The upstream example's own README says it:

> *"The device triggers the router to send packets through the Ping command
> to obtain the CSI data between the device and the router"*

and the source confirms it:

```c
static esp_err_t wifi_ping_router_start(void)
{
    esp_ping_config_t ping_config = ESP_PING_DEFAULT_CONFIG();
    ping_config.count             = 0;                       /* forever */
    ping_config.interval_ms       = 1000 / CONFIG_SEND_FREQUENCY;
    ...
    ping_config.target_addr.u_addr.ip4.addr = ip4_addr_get_u32(&local_ip.gw);
    esp_ping_new_session(&ping_config, &cbs, &ping_handle);
    esp_ping_start(ping_handle);
}
```

**`CONFIG_SEND_FREQUENCY` is 100, so the board sends 100 ICMP echo
requests per second to the campus gateway** (10.7.95.254), forever, with
`esp_ping_callbacks_t cbs = { 0 }` - no success callback, no timeout
callback, so *nothing is logged if the gateway stops answering*.

This is the single most important fact for the whole project, and it was
not known until the source was read:

1. **The CSI stream is not spontaneous.** It is the *downlink* of the
   board's own pings. The transmitter under test is the **campus
   gateway**, not the board, and the CSI rate is the ping success rate
   multiplied by the number of downlink frames each ping elicits.
2. **The transmitter is out of our control.** It is 30+ m away, behind
   unknown infrastructure, on a guest network with several access points.
3. **The link's traffic is polite but constant.** 100 packets/s of ICMP to
   a campus gateway is a lot, and it is likely to be policed.

### And that explains the silent intervals

The ~320-331 second silences are now explained without any speculation
about a device fault: **when the campus network stops answering the
board's ping flood, the ACK and echo-reply frames stop, the CSI callback
stops firing, and the board goes silent - in complete silence, because
the ping session has no callbacks to report a timeout with.**

The dual-channel capture confirms the mechanism: during a silence the
**USB CDC stream and the board's own console copy of the CSI stream both
stop at the same moment**, and the board's log stops with them. The
device was not failing; it had nothing to report.

---

## 2. What "controlled" has to mean

An experiment needs to control, at minimum:

| what | why |
|---|---|
| **the transmitter** | the CSI is the *downlink* of something; the something must be ours |
| **the traffic pattern** | the CSI rate is a function of the downlink traffic; it must be the same in every trial |
| **the geometry** | the subject's position relative to the radio path must be fixed and known |
| **the clock** | the subject's motion and the CSI must share a time base |
| **the environment** | no campus router, no cellular, no other traffic |

The current link controls **none** of these.

---

## 3. The options

### Option A - the Mac becomes the access point

The board stays in STA mode (no firmware change) and joins an AP hosted by
the Mac; the Mac's transmissions are then the thing under test.

*What the machine can actually do* (checked, not assumed):

* macOS 27.2 has **no `airport` tool** - it was removed - so there is no
  supported command line for creating an AP.
* `/usr/libexec/InternetSharing` exists and can create a SoftAP on
  `llw0`, but it **needs a wired upstream**. This Mac's only uplink is
  Wi-Fi (`en0` is the Wi-Fi port, on 10.12.182.214); there are two
  **unused USB Ethernet adapters** (`en2`, `en3`) with no address.
* Enabling it would **take over the Wi-Fi radio and drop this session's
  own connectivity**.

*Two further blockers, independent of the Mac:*

* the board's SSID is **compiled into the firmware** ("Kent State Guest"),
  so the Mac's AP would have to be given that exact name; and
* the campus is **open** while Internet Sharing is WPA2, so the
  credentials would have to match too.

**Verdict: possible, fragile, and invasive.** It changes the host's
networking and cannot be done while the session depends on the network. It
is a fallback, not a plan.

### Option B - the board becomes the access point and the Mac becomes the station (recommended)

The upstream example is literally named `csi_recv_router`, and the esp-csi
documentation has a "get_router_csi" figure for its other mode: the board
runs a SoftAP and measures the **uplink CSI of a connected station**. The
station is the Mac.

```
   Mac (STA)  --Wi-Fi-->  ESP32-S3 (SoftAP "SPECTER-LAB")
    generates the traffic        measures the Mac's uplink CSI
    on a known schedule          over USB, to the host
```

* **The transmitter is the Mac**, at a known position, sending traffic the
  Mac generates exactly.
* **The traffic pattern is ours**: the Mac can send a fixed-rate, fixed-
  size stream, or a shaped burst, and the *ground truth of the stimulus
  is then known by construction*.
* **No campus, no cellular, no second board.**
* The board's `esp_wifi_set_csi_rx_cb(cb, peer_bssid)` filter is set to
  the *station's* MAC in this mode, which is the same mechanism as today
  but pointing the other way.

**What must be verified before building it:** whether the ESP32-S3
supports the CSI callback in **SoftAP** mode. On the original ESP32 the
AP-side CSI callback is supported; on the S3 it has to be confirmed
against the IDF documentation for the chip. **If the S3 cannot do it,
Option B is dead and Option C is the only route.**

**This needs a firmware build, and flashing is explicitly not authorised
yet.** The design is written so that the build can be reviewed on its own.

### Option C - two boards (the clean end state)

```
   ESP32 #1 (SoftAP + traffic)  --Wi-Fi-->  ESP32 #2 (STA, CSI)
        the transmitter                          the receiver
                    \                                /
                     \------ USB to the Mac -------/
                            the only thing that stores data
```

* Both boards are 30 cm apart on the same desk. The geometry is fixed and
  marked, so the subject's distance to the radio path is a controlled
  variable.
* Neither board touches the campus.
* The traffic generator can be either board or the Mac.

**Blocked on the second board.** Until it arrives, Option B is the route
and Option C is the destination.

### Option D - the bench link, with no radio at all (available now)

Two parts, both implemented in this checkpoint:

1. **A synthetic link with a known ground truth**
   (`specter/sensors/esp32/synthetic_link.py`). A single AP and a single
   station, 64 complex subcarriers with the board's real null band, a
   static multipath profile, a person who is a *moving reflector* (a
   static reflector would change the amplitude and nothing else), a
   drifting AGC, and a PHY rate that changes the amplitude scale. The
   ground truth is a label per trial plus a **known effect size**.
2. **A file-backed replay** so a recorded session can be pushed through
   the same dispatcher at the original rate.

**What the bench buys:** the detection pipeline can be validated against a
*known* answer, and - more importantly - the **false-positive rate of the
whole procedure can be measured** by running it on trials whose ground
truth says nobody is there. That number cannot be obtained from a real
link at all, because a real link never tells you what was really
happening.

---

## 4. The recommended next experiment

### On the bench first (no radio, no subject, today)

1. Fix the feature set (`specter/sensors/esp32/analysis.py` freezes it).
2. Run the pipeline on the synthetic link at a range of effect sizes and
   find the **sensitivity curve**: the effect size at which the held-out
   accuracy reaches 95 %.
3. Run it on null trials and confirm the false-positive rate.
4. Replay the real campus recording through the same code and measure the
   effect size it *actually* has.

### Then on the radio (once a build is approved)

5. Build the SoftAP/router-mode image, **on a branch, for review**.
6. The Mac joins "SPECTER-LAB" and sends a fixed traffic pattern.
7. The subject stands at a **marked distance** from the radio path, and
   the distance is a randomised factor.
8. Blinded, randomised, repeated trials - the numbers below.

### How many trials

The power calculation (`analysis.required_n`, simulated with the same
omnibus test and critical value the analysis uses):

| effect size (Cohen's d) | trials per condition | total | time at 30 s each |
|---|---|---|---|
| 0.40 | 30 | 90 | 45 min |
| 0.60 | 14 | 42 | 21 min |
| 0.95 | **7** | **21** | **11 min** |
| 1.28 | 4 | 12 | 6 min |

**The real session's measured effect size was d = 0.95 (stationary vs
walking) and d = 1.28 (hand vs walking) - and with 3 trials per condition
the power was 0.34 and 0.57.** The nine-trial experiment was not a
failure of the hypothesis; it was an experiment with a 10-35 % chance of
detecting the effect it was looking for. **Seven trials per condition is
the minimum for the effect size actually observed**, and it is cheap:
eleven minutes, not hours.

### The protocol

| | |
|---|---|
| conditions | stationary, hand, walking (and a **return-to-stationary** control at the end) |
| order | **randomised**, seed recorded, labels shuffled again before the analysis |
| repetitions | **7 per condition minimum**, 30 s each |
| geometry | the subject at a marked distance; the distance randomised across trials |
| traffic | the same pattern, size and rate in every trial |
| baseline | a 10 s quiet reference before each trial, contemporaneous |
| exclusions | **pre-registered**: a trial is excluded if the received PHY rate changed, the source AP changed, or the link dropped a packet - and the exclusion is recorded, not decided afterwards |
| analysis | the frozen features, the permutation test, the effect size with a bootstrap interval, and the held-out score |

---

## 5. What this does not solve

* The **campus** link remains a *monitoring* link, not an experimental
  one. It is fine for watching the link's health and for a first look at
  whether the room changes anything; it is not a controlled instrument.
* The board will keep pinging the campus gateway at 100 pps **until the
  firmware changes**. That traffic is the price of the current CSI
  method, and it is a real load on a network that is not ours. The
  SoftAP/router-mode build replaces it with a local peer.
* The ~324 s silences will keep happening on the campus link until the
  traffic source is local. The dual-channel capture shows the device is
  healthy throughout them.
