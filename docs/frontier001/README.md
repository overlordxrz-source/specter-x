# FRONTIER-001 — platform foundation and SPECTER-VIEW

[Master hub](../README.md) · [Architecture decision](architecture-review.md) · [Hardware dossiers](hardware-readiness.md) · [Roadmap / handoff](roadmap.md) · [Reproducibility and limitations](reproducibility.md)

Implemented: immutable strict observation v1, registry, real CSI replay adapter, deterministic JSONL capture with integrity manifest, bounded diagnostic history, explicit source gaps and retention evictions, and a diagnostic mode in the existing OpenCV application. No spatial fusion, detection or new live hardware driver is claimed.

## Run, without opening any device or camera

From this worktree, use its configured Python environment (`python` below must have numpy, OpenCV and pytest):

```sh
python -m specter.app --console --windowed
python -m specter.app --console --replay /absolute/path/to/phase0-short.raw.csi --windowed
python -m specter.app --console --replay /absolute/path/to/phase0-short.raw.csi --console-size 800x480 --windowed
python -m specter.app --console --replay /absolute/path/to/phase0-short.raw.csi --at 255 --headless --console-size 800x480 --save-frame preview.png
```

The real preserved capture used in local verification is a private, gitignored `phase0-short.raw.csi` under the owner's Alpha run directory; it is not copied into this branch. Point `--replay` at the local capture. All CSI records are shown as acquired radio-channel data, not human observations or localized points. Default empty console shows OFFLINE sources, never generated feeds.

Space plays/pauses; A/D steps; click the bottom timeline to seek; E cycles provenance pages, N node readiness, S signal view, J the next session, Q exits. `--session-dir` browses at most 64 `.raw.csi` or `.observations.jsonl` files. `--replay-limit` defaults to 4096 (maximum 50000), and a visible “limited” marker exposes truncation. `--buffer-capacity` bounds the retained diagnostic history; evictions are not sensor losses. The per-source rate is computed from native acquisition ticks, not render FPS or replay wall time. Playback uses fixed record batches for inspection, not a real-time-rate simulator. Window controls remain offline; there is no network or hardware command path.

## Contract and compatibility

`Observation` accepts exactly `specter.observation/1.0.0`. All metadata fields are required: source/node, units/frame, acquisition domain/epoch/native ticks/tick rate, original receive-time availability, origin/classification, calibration, uncertainty, validity, evidence references and missing-record count. Unknown is explicit; optional absence does not create hardware or experimental assurance. No new fields were added to legacy Measurement. `from_legacy` is opt-in and marks origin/evidence/units unknown while preserving the original timestamps as legacy data.

The normative runtime validator is `specter/platform/observation.py`. Covariance must have ordered variable/unit labels, matching dimensions, finite numeric entries, symmetry and positive-semidefiniteness. No covariance means unknown, not zero. Confidence is not synthesized. Evidence origin (hardware/simulated/unknown) and epistemic classification (measured/inferred/predicted/simulated/unknown) are separate. This slice's CSI conversion is measured signal amplitude with unknown physical uncertainty and no spatial frame or motion inference.

The bundled `specter/platform/sources.json` binds two reviewed hardware-recording digests to their historical sources. An arbitrary CSI text file is **UNKNOWN**, not hardware-measured merely because its syntax parses. Adding a hardware source requires a reviewed hash/source entry; simulated envelopes stay simulated.

The CSI adapter uses the existing **resilient** parser, preserves uint32 microsecond ticks and LLTF ordering, masks hardware-invalid first pairs, retains PHY/signal-length/RSSI metadata, recovers lost-newline splices/torn prefixes, marks them with `spliced_line`/`torn_line` quality flags, and cites raw SHA-256 plus physical line number. A splice exactly at the metadata/IQ boundary remains undetectable without a checksum; this is a stated format limitation. It supports the captured 128-value LLTF layout; other layouts are counted unsupported. Reset/out-of-order sequence fails closed and requires an explicit source/session split. Wraps and inferred timing discontinuities carry flags and unrecorded epoch labels. No boot ID, receipt timestamp, calibration or synchronization is invented.

## Deterministic capture / replay

```sh
python -m specter.app --console --replay /absolute/path/to/phase0-short.raw.csi --headless --save-frame preview.png --capture-out session.observations.jsonl
python -m specter.app --console --replay session.observations.jsonl --windowed
```

The writer creates exclusively and cannot overwrite a capture. A companion `.manifest.json` records count and SHA-256; replay refuses missing/tampered manifests. Canonical observations contain no new wall clock or random ID, so the same preserved source generates byte-identical captures. Keep capture plus manifest together. These exports contain measurement data and must remain in the approved private research area. File hashes identify bytes, not whether an original participant label or experimental interpretation was correct.

## Honest scope

DI-188 has a registry contract and a truthful OFFLINE state; this mode does not open its serial port. Thermal remains unavailable. No unrelated signals are called fused. A future driver must supply its own acquisition semantics, calibration and references, then register the exact kind/units/frame. Multi-node display is a source/readiness list, not invented positions or authenticated live team transport. Ferret remains an optional future target; the envelope can be implemented independently in Rust/C without changing kernel or flight-controller requirements.

Headless previews were rendered on the Mac, not on the received Newhaven display. Keyboard/mouse controls work in the desktop window; physical HDMI and USB touch, touch-only ergonomics, operating-system DPI and enclosure integration remain untested. No camera or personal image acquisition is required or performed.
