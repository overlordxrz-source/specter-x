# ADR-WORLD-001: local desktop research application

Accepted within the owner's implementation brief, 22 October 2026. Base: FRONTIER-001 `dc695c7`. Branch: `feature/specter-world-desktop`. SPECTER-VIEW remains the compact OpenCV console; SPECTER-WORLD is the desktop research application. Neither is a flight-control interface.

## Decision and alternatives

OpenCV is useful for pixel/HUD rendering but its manual text/layout/event handling is unsuitable for a document-heavy, accessible desktop research workspace. Extending it would duplicate scrolling, focus, high-DPI text and inspection behavior. Qt would supply native widgets but adds a substantial packaged runtime and platform-specific installation burden. A browser UI plus a loopback Python service supplies native high-DPI text, responsive layout, keyboard controls and SVG without adding a runtime dependency. It is the selected implementation; native app bundling remains future work.

The service binds only `127.0.0.1`, uses an ephemeral port by default and serves its own assets. No CDN, remote map, font, analytics, model download or internet connection is required. A Mac launcher opens the default browser. Host/origin checks and a per-process POST token prevent ordinary cross-origin commands and DNS-rebinding hosts; there is no CORS grant. This is not a multi-user authenticated server or a defense against other code running as the same local user. CSP restricts resources to the local origin.

## Boundaries

- `store.py`: one asynchronous source loader, temporary SQLite index, canonical Observation storage and registry validation. File I/O and parsing do not run in the browser. Random access, filtering and recent-window queries read the index. FRONTIER contracts, CsiReplay, source-hash evidence classification and Registry are reused; no competing measurement contract or classifier exists.
- `server.py`: approved-root catalog, structured JSON API and local lifecycle. Only catalog IDs can be opened. Files are read-only; the index is temporary and removed on clean shutdown. Reports are displayed as source text and do not become independently validated statistics.
- `web/`: presentation and controls. Graphs derive exclusively from indexed values. A source with no matching observation has no substituted signal. The inspector displays the canonical envelope, raw hash/line and clock/uncertainty semantics. Native times are never replaced by playback wall time.
- `ingress.py`: offline-tested bounded envelope queue and Registry seam for a future worker around existing acquisition infrastructure. It contains no hardware transport. Test connection/stale/disconnected/error states cannot become LIVE. A future transport owner must handle actual dispatcher framing, device ownership, authorization, raw recording, acquisition provenance and hardware acceptance.

A test seam is not a live driver. WORLD cannot claim a physical connection merely because envelopes were submitted. OpenCode's serial sessions, frozen Alpha protocols and firmware remain outside this change.

## Resource and timing contracts

The source-file limit is 512 MiB; default record limit is 250,000, configurable up to 1,000,000. The index checks its own 512 MiB size between records; SQLite transaction/journal overhead and one in-progress transaction can exceed that file threshold. This is a guardrail, not a hard process RSS quota. SQLite cache is configured to 2 MiB per connection. Registry history holds 256 records; queries return at most 80 rows and 160 RSSI points. HTTP request bodies are capped at 4 KiB and active request threads at twelve; client read timeout is five seconds. The catalog returns at most 512 approved items; evidence text is limited to 256 KiB. Source loading is cancelled/joined before replacement. Shutdown stops the server and loader and removes its temporary index.

Playback advances at an explicit **25 records/s × speed**, for inspection. It does not reproduce radio acquisition cadence. Rates use original native tick intervals over up to 128 records; the first record has no rate estimate. Old recording timestamps never imply current live freshness. `DISCONNECTED` means the replay was detached, not that a physical board was unplugged. Cached evidence remains inspectable. Live device age, uptime and clock alignment remain unknown.

## Scope and remaining risks

The spatial workspace is a truthful empty state with calibration/time/evidence gates, not a renderer containing invented points. Persistent WORLD mapping, calibrated spatial fusion, secure remote nodes, transport integration and native app packaging are planned. Read-only artifact inspection does not rerun Alpha statistics or determine preregistration compliance. Only reviewed raw-source hashes are classified as hardware by the CSI adapter; other syntactically valid captures remain UNKNOWN until provenance review.

This local service can index real private captures. Screenshots and exports require ordinary review before external sharing. No remote serving, camera acquisition, firmware operation, flights, autonomous commands, telemetry transmission or external publication is implemented here.
