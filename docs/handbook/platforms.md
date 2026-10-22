# Future platforms: AIR, GROUND, satellite data and communications

[Hub](../README.md) · **SPECULATIVE architecture extensions; no platform procurement, flight or deployment.**

## Shared premise

A platform is a NODE carrying calibrated SENSE devices, a clock/pose solution and LINK policy. CORE/FUSION/WORLD/VIEW should consume its evidence without pretending that mobile geometry is the same as a fixed bench. Distinguish where a sensor was at acquisition from where the platform is when a packet arrives.

## SPECTER-GROUND

Begin with a manually moved cart or stationary remote node. Log wheel/IMU/other odometry only when independently validated; GNSS loss and wheel slip must increase uncertainty. Test vibration, clutter, dust, cable loads, field of view and link shadowing. A wheeled or tracked chassis can increase power/storage capacity but adds safety, navigation and mechanical complexity.

The first experiment should compare a stationary calibrated rig with the same rig moved along a reference path. Only after motion compensation works should remote operation or autonomous mapping be considered. Keep motor control/safety interlocks separate from research perception; no inference from this prototype authorizes unsafe motion.

## SPECTER-AIR

A future airborne NODE could provide a different vantage for optical/thermal mapping or communication relay. Payload mass, flight time, vibration, propeller acoustic interference, RF coexistence, rolling shutter, pose accuracy and ground-to-air time alignment are major constraints. Do not assume a chest-motion or CSI experiment tolerates a flying platform.

Start with recorded public/authorized aerial datasets or a static elevated rig. Any flight would require a separate reviewed operating plan, qualified operator, site/airspace permissions and local rules. The [FAA Part 107 overview](https://www.faa.gov/newsroom/small-unmanned-aircraft-systems-uas-regulations-part-107) is a US reference; educational status alone does not settle which rules apply. No flight authorization or legal determination is made here.

## Satellite data as contextual evidence

First integrate existing licensed/public imagery, terrain and environmental data as timestamped context. Every layer needs source, acquisition time, publication/processing time, resolution, georeference, cloud/quality mask, license and update cadence. Reproject into a declared coordinate reference system; do not silently equate orthometric and ellipsoidal heights.

For scale, [ESA's Sentinel-2 overview](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2?app=true) lists 10-m resolution and a nominal five-day revisit. Such imagery supports landscape context, not live indoor person tracking. Actual usable scenes depend on acquisition, band/product, cloud cover and processing/access latency. Historical data must render as historical even if fetched seconds ago.

Radar satellite products, commercial imagery and other geospatial layers would each need their own documented licensing, resolution and interpretation. A satellite observation of a surface change is not evidence of a specific person or indoor event.

## Communications hierarchy

| Link class | Proposed role | Limits to measure |
|---|---|---|
| Local USB/UART/SPI/I2C | Device observations within a NODE | Ownership, bandwidth, voltage, timestamp and backpressure |
| Local Wi-Fi / wired network | Richer peer reports, authorized file transfer | Contention, delay, loss, partitions, encryption and credentials |
| UWB | Ranging observations | Distinct from bulk-data transport; geometry and NLOS bias |
| LoRa-class link | Small heartbeats/status, possibly compact alerts | Low throughput, airtime/regional limits, latency and delivery; no video assumption |
| Cellular / approved satellite service | Backhaul in defined coverage | Cost, power, antenna view, latency, data policy and outages |
| Store-and-forward | Offline sessions and delayed reports | Preserve acquisition time, expiry and replay rejection |

Use message priorities and explicit expiry rather than silently queuing obsolete world state. Preserve enough local storage for disconnected acquisition. A relay repeats evidence references; it does not become another independent sensor observation. Satellite communication and satellite sensing are separate capabilities.

## Platform graduation gates

A new platform needs a measured payload/power budget, mounting/calibration procedure, time/pose uncertainty, interference characterization, communication-loss behavior, privacy scope and recovery procedure. Demonstrate benefit on a fixed task against the simpler stationary rig. Custom satellite hardware, launches or remote autonomous operations would be separate programs with separate resources and authorizations.
