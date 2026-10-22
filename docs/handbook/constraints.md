# Power, mechanical, RF, optical, safety and privacy constraints

[Hub](../README.md) · **Requirements to measure and review; no certified capability.**

## Power and thermal engineering

Create a measured rail budget for compute, display/backlight, sensors, radios, accelerator and cooling. Record nominal/peak/startup current, regulator efficiency, connector/cable losses and brownout behavior. Avoid sizing a battery from idle consumption or adding component averages without simultaneous-load testing.

Use `usable energy (Wh) / measured average load (W)` only as a runtime estimate under stated load and temperature. Validate complete discharge behavior with the actual BMS/regulators and safe cutoffs. Budget logging and radio bursts, cold startup and future ports. Isolate and fuse appropriate branches, select rated connectors and provide strain relief. Battery chemistry, pack, charging/BMS design and enclosure details remain unselected; no unattended battery test is implied.

Measure internal and accessible-surface temperature with the final enclosure and sustained inference workload. Detect throttling and fan failures; retain data-integrity and visible degraded modes under thermal load. A component operating-temperature rating does not rate the assembled product for a fireground or hazardous atmosphere.

## Mechanical and wearable constraints

Start with a rigid bench geometry and documented mounting coordinates. Repeated removal/reassembly must either preserve calibration within measured tolerance or trigger recalibration. Protect camera/depth/thermal windows with materials appropriate to each wavelength; ordinary visible-transparent material may block LWIR. Keep radar/antenna apertures clear and test enclosure/body detuning.

Handheld center of mass, cable routing, connector accessibility, splash/dust protection, heat exhaust and drop protection need measured tests. Helmet/chest/goggle concepts add neck load, impact, snag, visibility and heat constraints. They remain design research; no PPE compatibility or protective rating is established.

## RF and optical limits

Operate only on authorized networks and locally permitted frequency/power/duty-cycle settings for the exact module/antenna. Record country/region configuration and avoid treating an evaluation board's certification as approval of a modified system. CSI traffic generation should be bounded and controlled; do not use campus infrastructure as an unconsented stimulus generator.

Map antenna geometry, polarization, bandwidth and nearby interference. Radio range, resolution and penetration vary with hardware, material, orientation and multipath. A single number from a product page is not the system's operating envelope. Optical depth/LiDAR choices require review of the exact product's laser safety and optical operating conditions; do not invent a laser class before selecting a model. Do not modify emitters as part of routine sensor integration.

Measure camera latency/exposure/rolling-shutter effects, lens focus, thermal drift and multi-sensor parallax. “Night vision” does not mean zero-photon imaging. Visible and thermal coverage differ, and a plausible overlay can be misregistered. VIEW should show coverage and stale data rather than fill unobserved regions with certainty.

## Analog and physiological experiments

The DAQ's differential input range is not a permission to connect arbitrary voltages or mains. Verify the actual analog board, grounding, input/common-mode and isolation limits before connecting a safe reference. USB ground and chassis paths matter. Follow the [wiring record](../di188-wiring.md) only after matching the actual assembly; its unresolved physical questions remain unresolved here.

Do not connect an improvised USB DAQ or homemade electrode arrangement to a person. Cardiac references must use equipment appropriate for body connection under laboratory supervision. Respiration/radar/optical research starts with phantoms and consenting participants under an approved protocol where applicable. No reading from this prototype should direct medical care, evacuation or a life-safety decision.

## Consent and data management

Use a marked research area with informed participants and permission from the site/network owner. Specify modalities, intended inferences, recording, recipients, retention and withdrawal handling before capture. Avoid collecting incidental bystander data. Skeletons, location, RF-derived activity and voice remain sensitive even when raw video is absent.

Use pseudonymous participant IDs; keep consent/contact records separately with restricted access. Restrict raw access to the approved team, set retention periods, protect storage and log exports. Derived datasets can retain sensitive information; apply the same review to them. Do not upload research recordings or flash backups to public repositories by default.

University human-subject determinations belong to the institution, not to a code comment or a statement that participants are volunteers. [HHS OHRP consent guidance](https://www.hhs.gov/ohrp/regulations-and-policy/guidance/faq/informed-consent/index.html) is a starting reference for the applicable institutional process, not a determination that a particular study is exempt or approved.

## Team communications and research displays

Current shared-key HMAC traffic is cleartext, permits team-key holders to impersonate peers and loses replay memory when the receiver restarts. These limits are documented in the [root README](../../README.md) and [ICD](interfaces.md). Limit current tests to non-sensitive authorized environments. Future confidential sharing requires a reviewed identity/encryption/key lifecycle, not just a “secure” label.

AI summaries must retain evidence references, age and uncertainty, and distinguish observation from inference. No VLM should invent a person, vital sign or hazard where the sensor did not establish it. Alerts and man-down messages in source code are prototype behaviors, not certified emergency functions.

## Risk register

| Risk | Early observable | Mitigation / gate |
|---|---|---|
| Silent acquisition failure | Callback age, sequence/drop counters, independent reference absent | Independent liveness; fail invalid, preserve logs |
| Misregistered confident overlay | Physical reprojection error, stale rig revision | Calibration validity and uncertainty; reject wrong frame |
| Power/thermal instability | Brownouts, resets, throttling, hot enclosure | Simultaneous-load tests and measured thermal/power design |
| Unconsented inference or disclosure | Unexpected recipients/data fields or bystanders | Scope/retention/access controls; no default public raw export |
| Unsupported rescue/medical interpretation | Display text implying life/absence or safety assurance | Explicit experimental states and task-specific evidence limits |
| Supplier/ownership confusion | Lead shown as sponsor or delivery | Dated receipt and terms before status promotion |

Each future test records an owner, stop condition and recovery procedure. This is a program-specific constraints register, not evidence of regulatory compliance.
