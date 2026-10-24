# SPECTER-WORLD desktop command center

[Master hub](../README.md) · [Architecture decision](architecture.md) · [Verification](verification.md) · [FRONTIER contracts](../frontier001/README.md)

WORLD is the Mac desktop research application; VIEW remains the compact Newhaven/HUD interface. WORLD reuses FRONTIER's Observation, Registry and replay adapter. It runs a local Python service and opens the default browser; no internet connection is needed for ordinary operation. There is no Electron bundle or separately installed native `.app` yet.

## Launch on this Mac

Double-click `SPECTER-WORLD.command` in this worktree, or run:

```sh
cd "$SPECTER_X_WORLD_WORKTREE"
./SPECTER-WORLD.command
```

Set `SPECTER_X_WORLD_WORKTREE`, `SPECTER_X_PYTHON` and `SPECTER_WORLD_CAPTURE` if the local paths differ. If macOS refuses double-click execution, use the Terminal command above. The launcher uses the existing project Python environment and the preserved Phase 0 source when it exists. It opens a free loopback port, avoiding conflicts with other applications. Close with **Shut down service** in the sidebar, or Ctrl-C in Terminal; closing the browser tab alone does not terminate the service.

Explicit command with approved recording/evidence roots:

```sh
PYTHONDONTWRITEBYTECODE=1 "$SPECTER_X_PYTHON" -m specter.world --replay "$SPECTER_WORLD_CAPTURE" --root docs/checkpoints
```

Portable setup: install the repository's normal Python dependencies, then `python -m specter.world --root /path/to/approved/recordings`. The installed `specter-world` command is equivalent. Add repeatable `--root` directories to browse reports and recordings. `--replay FILE` loads that one initial source but does **not** approve its parent; pass an explicit `--root` to browse evidence. The source is read-only. Only `.raw.csi` and `.observations.jsonl` files are replayable; manifests accompany the latter. Report `.json` and `.md` files are inspected as evidence text. No file upload or arbitrary-path API is exposed. Use `--no-browser` for automation; the printed URL is the real local endpoint.

## Operate

- **Overview:** selected-source rate/gaps/calibration, recorded signal and RSSI, shared source availability, observation inspection and actual session events.
- **Sensing:** select a recorded source or an offline modality, filter sequence/source, inspect an original envelope by clicking a row. Filtering limits the latest 80 matching rows through the current replay position; it does not change the underlying evidence or the selected timeline record.
- **Spatial:** inspect why current CSI amplitudes cannot be plotted as spatial coordinates; no fabricated map or scene.
- **Research:** open actual local recordings, read reports/checkpoints as original text and inspect raw-versus-derived semantics. The tool does not promote report assertions into experimental proof.
- **Nodes:** real local service uptime and replay-source identity; hardware uptime/authenticated identity and remote nodes remain unverified.
- **Evidence:** complete envelope, raw artifact SHA-256/line, algorithm/revision, parser counters and structured session errors.

The bottom transport provides play/pause, record stepping, keyboard/mouse scrubbing and 0.25×–8× inspection speed. Playback is 25 records/s at 1×, explicitly distinct from acquisition rate. **Detach** stops replay; reopen the session to reconnect replay. Source parsing and index construction run in a worker. LOADING, READY, ERROR, limit-reached and DISCONNECTED are visible. No physical transport is opened.

## Feature status and source gaps

| Capability | Status | Boundary |
|---|---|---|
| Local service, navigation, scalable SVG/native text, responsive desktop layout | WORKING | Browser application; native `.app` packaging not supplied |
| Real ESP32 preserved data, replay/filter/inspection/timeline | REPLAY-ONLY | Validates software ingestion of preserved evidence, not new hardware |
| Provenance, invalid flags, calibration and uncertainty display | WORKING | Unknown stays unknown; evidence follows FRONTIER |
| Multiple desktop resolutions / Retina render | WORKING | Automated Chromium on Mac; Safari and physical MacBook ergonomics unverified |
| DI-188 | OFFLINE | Prior physical test; no current connection opened |
| Radiometric thermal | OFFLINE / UNAVAILABLE | Module not received; no substitute feed |
| Simulated canonical recordings | WORKING / SIMULATED | Origin displayed explicitly; never LIVE |
| Bounded ingestion/test queue and stale/disconnect behavior | WORKING / SOFTWARE-TESTED | Integration seam only; no serial acquisition transport |
| Physical live CSI connection | UNVERIFIED | Requires explicit permission, uncontested port and acceptance evidence |
| Live device freshness/uptime/clock synchronization | UNVERIFIED | Raw file lacks those live guarantees |
| Spatial rendering/fusion, maps, tracks, skeletons | PLANNED | No calibrated spatial observations supplied |
| Remote AIR/GROUND nodes, LINK, fleet coordination | PLANNED | No remote nodes or actuation commands |
| Scientific motion/physiology detection | UNVERIFIED | No new detection result or Alpha statistics recomputation |

OpenCode can use the store/query/API and explicit ingress seam later without changing Alpha's frozen feature pipeline. Actual live integration needs a transport worker, exclusive device ownership, raw framing and clock evidence, user permission and hardware acceptance. Do not point WORLD at an active serial port or infer authorization from this code.
