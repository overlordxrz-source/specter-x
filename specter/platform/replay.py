"""Read-only CSI adaptation and deterministic observation capture/replay."""

from __future__ import annotations
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
from specter.sensors.esp32.dispatcher import CsiParser
from .observation import Observation, SCHEMA, ContractError


class TickEpoch:
    """Conservative unwrap. Epochs are inferred; no hardware boot ID is claimed."""

    def __init__(self):
        self.last = None
        self.offset = 0
        self.epoch = 0

    def push(self, tick):
        flags = []
        if self.last is not None and tick < self.last:
            if self.last > 2**32 - 2_000_000 and tick < 2_000_000:
                self.offset += 2**32
                flags.append("counter_wrap")
            else:
                self.epoch += 1
                self.offset = 0
                flags.append("clock_discontinuity")
        self.last = tick
        return tick + self.offset, f"unrecorded-epoch-{self.epoch}", flags


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class CsiReplay:
    """Source bytes only. Does not open devices, discover cameras or infer motion."""

    def __init__(self, path):
        self.path = Path(path)
        self.digest = sha256_file(path)
        self.counts = Counter()
        known = json.loads(Path(__file__).with_name("sources.json").read_text())
        self.known_source = known.get(self.digest)
        self.origin = "hardware" if self.known_source else "unknown"

    def __iter__(self):
        self.counts.clear()
        parser = CsiParser()
        clock = TickEpoch()
        last_seq = None
        with self.path.open("rb") as f:
            line_no = 0
            while True:
                raw = f.readline(16385)
                if not raw:
                    break
                line_no += 1
                if len(raw) > 16384:
                    raise ContractError(
                        f"line {line_no} exceeds 16 KiB; replay stopped"
                    )
                text = raw.decode("utf-8", "strict").strip()
                if not text.startswith("CSI_DATA,"):
                    self.counts["non_csi"] += 1
                    continue
                outcome = parser.feed_resilient(text)
                if outcome.malformed:
                    self.counts["malformed"] += 1
                if outcome.spliced:
                    self.counts["spliced_lines"] += 1
                if outcome.records:
                    self.counts["recovered_records"] += len(outcome.records)
                for record_index, rec in enumerate(outcome.records):
                    if rec is None:
                        self.counts["malformed"] += 1
                        continue
                    if len(rec.iq) != 128:
                        self.counts["unsupported_layout"] += 1
                        continue
                    if last_seq is not None and rec.seq <= last_seq:
                        self.counts["nonmonotonic_sequence"] += 1
                        raise ContractError(
                            "sequence reset/out-of-order: explicit session split required"
                        )
                    dropped = 0 if last_seq is None else rec.seq - last_seq - 1
                    last_seq = rec.seq
                    self.counts["sequence_missing"] += dropped
                    ts, epoch, flags = clock.push(rec.local_timestamp)
                    flags += [
                        "uncalibrated",
                        "clock_unsynced",
                        "signal_domain",
                        "not_spatial",
                        "receive_time_unrecorded",
                    ]
                    if outcome.spliced:
                        flags.append("spliced_line")
                    if outcome.malformed:
                        flags.append("torn_line")
                    amps = [math.hypot(im, re) for im, re in zip(rec.iq[::2], rec.iq[1::2])]
                    if rec.first_word_invalid:
                        amps[:2] = [None, None]
                        flags.append("first_word_invalid")
                    if not self.known_source:
                        flags.append("source_origin_unverified")
                    self.counts["observations"] += 1
                    record_suffix = (f":{record_index}"
                                     if len(outcome.records) > 1 else "")
                    yield Observation(
                        dict(
                            schema=SCHEMA,
                            id=f"{self.digest[:16]}:{line_no}{record_suffix}",
                            node_id="bench",
                            sensor_id="bench/esp32-s3/csi",
                            seq=rec.seq,
                            kind="csi_lltf_amplitude",
                            value=dict(
                                amplitudes=amps,
                                rssi_dbm=rec.rssi,
                                phy_rate_code=rec.rate,
                                sig_len_bytes=rec.sig_len,
                                noise_floor_dbm=rec.noise_floor,
                                csi_bytes=len(rec.iq),
                            ),
                            units="gain_compensated_csi_counts",
                            frame_id="esp32/lltf-frequency",
                            origin=self.origin,
                            classification="measured" if self.known_source else "unknown",
                            acquisition=dict(
                                domain="esp32.rx_ctrl.timestamp_us",
                                epoch=epoch,
                                ticks=rec.local_timestamp,
                                unwrapped_ticks=ts,
                                tick_hz=1_000_000,
                                wrap_bits=32,
                            ),
                            received=dict(domain="unrecorded", time_ns=None),
                            calibration=dict(
                                status="uncalibrated", id=None, reference=None
                            ),
                            uncertainty=dict(kind="unknown", variables=[], covariance=None),
                            evidence=dict(
                                level="recorded_hardware"
                                if self.known_source
                                else "unverified",
                                raw=dict(
                                    artifact=self.path.name,
                                    sha256=self.digest,
                                    line=line_no,
                                ),
                                parents=[],
                                algorithm="esp-csi-amplitude-replay",
                                revision="frontier001-adapter-v1",
                            ),
                            validity=dict(state="degraded", flags=flags),
                            dropped_before=dropped,
                        )
                    )


def write_capture(path, observations):
    """Exclusive create; no timestamp/UUID added, and input observations unchanged."""
    if Path(str(path) + ".manifest.json").exists():
        raise FileExistsError("capture manifest already exists")
    n = 0
    with Path(path).open("x", encoding="utf-8") as f:
        for obs in observations:
            if not isinstance(obs, Observation):
                raise ContractError("capture requires validated observations")
            f.write(obs.to_json() + "\n")
            n += 1
    manifest = dict(schema="specter.capture/1.0.0", count=n, sha256=sha256_file(path))
    with Path(str(path) + ".manifest.json").open("x", encoding="utf-8") as f:
        json.dump(manifest, f, sort_keys=True)
    return n


def read_capture(path):
    manifest_path = Path(str(path) + ".manifest.json")
    if not manifest_path.is_file():
        raise ContractError("capture manifest missing; completeness is unknown")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "specter.capture/1.0.0" or manifest.get(
        "sha256"
    ) != sha256_file(path):
        raise ContractError("capture integrity failure")
    n = 0
    with Path(path).open("rb") as f:
        while True:
            line = f.readline(262145)
            if not line:
                break
            if len(line) > 262144:
                raise ContractError("observation exceeds 256 KiB")
            n += 1
            yield Observation.from_json(line)
    if n != manifest.get("count"):
        raise ContractError("capture count mismatch")


def load_source(path, limit=4096):
    if type(limit) is not int or not 1 <= limit <= 50000:
        raise ValueError("limit must be 1..50000")
    path = Path(path)
    # Explicit, validated envelope capture detection, not a legacy auto-upgrade.
    with path.open("rb") as f:
        first = f.readline(262145)
    if first.lstrip().startswith(b"{"):
        iterator = read_capture(path)
        stats = {}
        source = None
    else:
        source = CsiReplay(path)
        iterator = iter(source)
        stats = source.counts
    observations = []
    truncated = False
    for obs in iterator:
        if len(observations) == limit:
            truncated = True
            break
        observations.append(obs)
    if not observations:
        raise ContractError("no usable observations in source")
    return observations, dict(stats, loaded=len(observations), truncated=truncated)
