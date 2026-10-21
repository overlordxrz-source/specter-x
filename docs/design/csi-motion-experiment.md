# Offline, consent-based Wi-Fi CSI motion experiment

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the harness is built and validated; the **null control** has been
measured. The human trials need a subject and have not been run.

---

## 1. What the hardware actually offers

The ESP32-S3 is associated with an access point and captures that access
point's **downlink** CSI, streaming it over USB. From the device's own boot
log (checkpoint 004 and the captures below):

```
I (3333) wifi:connected with Kent State Guest, aid = 1, channel 11, BW20, bssid = b8:62:1f:e5:ac:62
I (3333) wifi:security: Open Auth, phy: bgn, rssi: -69
I (4336) esp_netif_handlers: example_netif_sta ip: 10.7.82.237, mask: 255.255.240.0, gw: 10.7.95.254
I (5241) csi_recv_router: ================ CSI RECV ================
id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,aggregation,stbc,fec_coding,sgi,
noise_floor,ampdu_cnt,channel,secondary_channel,local_timestamp,ant,sig_len,rx_format,len,first_word,data
```

**The AP is "Kent State Guest"**, BSSID `b8:62:1f:e5:ac:62`, channel 11, 20 MHz,
open auth, bgn. The board holds an ordinary client address on it.

**A constraint that changes the design:** the Mac is **on a different
network** (10.12.182.214/20, gateway 10.12.183.254) from the ESP32's AP
(10.7.80.0/20). The classic two-node Wi-Fi sensing setup — a *client* on the
same AP whose traffic perturbs the channel the receiver senses — is therefore
**not available as-is**: the Mac cannot be the stimulus for the ESP32's
downlink CSI.

What *is* available, with the firmware that is already on the board:

* the access point's own downlink traffic (beacons and data to the ESP32)
  continuously perturbs the path;
* a person moving near that access point changes the radio path, and therefore
  the CSI amplitude, phase and RSSI.

So the supported experiment is **"ESP32 alone, sensing motion near its own
AP"**, with the Mac as the recorder and analyst. The ESP32 needs no firmware
change for this, and adds no traffic to the network beyond the association it
already has.

---

## 2. The experiment

### Trials

Labelled, fixed-length, run in a single port session (opening and closing the
CDC port repeatedly is itself a stall trigger — see checkpoint 007):

| Label | What the subject does |
|---|---|
| `stationary` | sits still at a marked spot, arms down |
| `hand` | waves one arm / moves hands at a steady rate, body still |
| `walk` | walks a fixed 3 m path and back, twice |
| `stationary` (repeat) | returns to the marked spot — repeated for the drift control |

Interleave the conditions rather than blocking them (all stationary, then all
hand, then all walk) so that slow ambient drift — the RSSI moved over a
**30 dB range** during today's session — cannot masquerade as a condition
effect. Repeat each condition **at least three times**, and put a
`stationary` trial at the start, the middle and the end.

### Duration

20 s per trial is enough (≈2 800 packets at the observed ~145 packets/s) and
short enough to repeat. A full session of 12 trials is about 4 minutes.

### Statistics per trial

* the total CSI amplitude (sum over the 64 subcarriers) — mean, std, min, max;
* the RSSI — mean, std, min, max;
* the per-carrier mean and std (the spectral signature);
* the packet count and the sequence-gap count (data quality per trial).

### Separability

For each subcarrier, the variance of that carrier's mean **across** trials
versus the average **within**-trial variance gives an F-like ratio. The
verdict is "separable" when the largest F is clearly above the control's.

### The null control (measured today)

Three identical `stationary` trials, no person moving, one port session:

| Trial | Packets | Total amplitude mean | std | RSSI mean | RSSI std |
|---|---|---|---|---|---|
| 1 | 2 841 | 622.26 | 91.74 | −64.73 dBm | 1.11 |
| 2 | 2 946 | 615.96 | 91.59 | −64.98 dBm | 1.05 |
| 3 | 2 838 | 614.66 | 81.90 | −64.82 dBm | 1.12 |

**max F = 0.012** — the between-trial variance is ~1 % of the within-trial
variance. That is the metric's **noise floor**: identical conditions give
F ≈ 0.01, so a real condition effect has to push F well above that to mean
anything. The trial means drift by ~1.2 % even with nobody moving, which is
why the conditions must be interleaved.

### Two other facts the statistics must respect

* **The within-trial amplitude noise is ~14 % of the mean** (std ≈ 90 on a
  mean of ≈ 620) even when nothing moves. Any detector has to separate a
  condition effect from that.
* **The ambient RSSI range is large** (−86 … −56 dBm across today's
  session). RSSI alone is therefore a poor discriminator; the *shape* of the
  subcarrier spectrum is the better signal.

---

## 3. Consent and scope

This experiment measures a person moving in a room. The rules it follows:

1. **The subject consents explicitly.** The recording stores a `--consent`
   note naming the subject and recording that they were informed and agreed.
   The tool refuses to record without one.
2. **Only the network the ESP32 is already on is touched.** No scanning, no
   probing, no identification of any other AP, client or device. The CSI
   packets carry only the access point's own BSSID — no other device's
   address is recorded or inferred.
3. **No added traffic.** The ESP32 keeps the association it already has; the
   experiment does not generate packets to the network, so it is not an
   active probe of a third party's service.
4. **Everything stays on this machine.** The recording is a local file; the
   analysis is local. Nothing is uploaded.
5. **Bounded and revocable.** The session has a fixed duration and a fixed
   trial count; the subject can ask for the file to be deleted, and it can be
   deleted in one command.
6. **No third-party inference.** The data is used to distinguish three
   movement conditions of the consenting subject. It is not used to infer
   anything about other people, and no attempt is made to extend it to them.

A note on the network itself: "Kent State Guest" is a guest network operated
by a third party. Rule 3 is deliberate — the experiment adds **no** traffic to
it beyond the association the board already maintains, so it does not
constitute active use of that service. If the operator's terms are ever in
question, the honest alternative is to point the board at a network the user
controls.

---

## 4. Running it

```bash
# record (all trials in one port session)
python3 tools/esp32_csi_motion.py record \
    --trial stationary:20 --trial hand:20 --trial walk:20 \
    --trial stationary:20 --trial hand:20 --trial walk:20 \
    --consent "subject: <name>, informed: yes, date: 2026-10-21" \
    -o runs/motion_001.json

# analyse offline, any time later
python3 tools/esp32_csi_motion.py analyse runs/motion_001.json
```

The recorder opens the port **once** and slices the trials out of that
session, because repeatedly closing the CDC port is a demonstrated trigger
for the ESP32's USB stall.

---

## 5. What is feasible, and what is not

| | |
|---|---|
| **Feasible today, no firmware change** | the ESP32 sensing motion near its own AP; the Mac recording and analysing it; per-carrier statistics; a null control and a separability metric |
| **Feasible today, needs a subject** | the hand and walking trials — the harness is ready, but the trials need a person |
| **Not feasible as-is** | the Mac as the *stimulus* for the ESP32's CSI — it is on a different network. A true two-node experiment would need the board moved onto the Mac's network, which means a firmware change (different SSID/credentials) and is not proposed here |
| **Not available** | any inference about other people or devices; the data does not support it and the scope excludes it |
| **Unproven** | that motion produces an effect above the control's F ≈ 0.01. The null control says the metric is calibrated, but the positive control has not been run. **This is the single measurement still missing** |

---

## 6. Next step

Run the positive control: one `stationary` trial and one `hand` trial, three
repeats each, with the subject present and consenting. If the F ratio
clears the control's 0.01 by a wide margin, the experiment design is
validated and the remaining work is a proper 12-trial session. If it does
not, the honest outcome is that the downlink CSI of this access point is not
sensitive enough to the movement tested, and the design needs a stronger
stimulus — which means a different network and a firmware change.
