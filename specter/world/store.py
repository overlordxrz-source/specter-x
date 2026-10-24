"""Asynchronous, disk-indexed replay. No serial, camera or network acquisition."""

from __future__ import annotations
from collections import Counter, deque
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import threading
import time

from specter.platform.observation import ContractError
from specter.platform.registry import default_registry, SensorSpec
from specter.platform.replay import CsiReplay, read_capture, sha256_file


class WorldStore:
    MAX_BYTES = 512 * 1024 * 1024

    def __init__(self, max_records=250_000):
        if type(max_records) is not int or not 1 <= max_records <= 1_000_000:
            raise ValueError("max_records must be 1..1000000")
        self.limit = max_records
        self.lock = threading.RLock()
        self.lifecycle = threading.Lock()
        self.cancel = threading.Event()
        self.temp = tempfile.TemporaryDirectory(prefix="specter-world-")
        self.path = Path(self.temp.name) / "index.sqlite"
        self.worker = None
        self.closed = False
        self._reset()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA cache_size=-2048")
        return db

    def _reset(self):
        with self._connect() as db:
            db.execute("DROP TABLE IF EXISTS observations")
            db.execute(
                "CREATE TABLE observations (i INTEGER PRIMARY KEY, sensor TEXT, seq INTEGER, body TEXT, health TEXT)"
            )
            db.execute("CREATE INDEX source_index ON observations(sensor,i)")
        self.count = 0
        self.status = "OFFLINE"
        self.error = None
        self.filename = None
        self.counters = {}
        self.sources = []
        self.started = time.monotonic()
        self.elapsed = None
        self.limited = False
        self.position = 0
        self.playing = False
        self.speed = 1.0
        self.play_wall = time.monotonic()
        self.events = deque(maxlen=64)

    def _stop_worker(self):
        self.cancel.set()
        if self.worker:
            self.worker.join(timeout=10)
            if self.worker.is_alive():
                raise RuntimeError("loader did not stop; source switch rejected")
        self.worker = None

    def load(self, path):
        with self.lifecycle:
            self._replace_source(path)

    def _replace_source(self, path):
        if self.closed:
            raise RuntimeError("store closed")
        path = Path(path)
        if not path.is_file() or path.stat().st_size > self.MAX_BYTES:
            raise ValueError("source absent or exceeds 512 MiB")
        self._stop_worker()
        with self.lock:
            self._reset()
            self.cancel.clear()
            self.filename = path.name
            self.status = "LOADING"
            self.events.append({"code": "LOAD_STARTED", "message": path.name})
        self.worker = threading.Thread(
            target=self._load, args=(path,), name="world-index", daemon=True
        )
        self.worker.start()

    def _load(self, path):
        registry = default_registry(256)
        adapter = None
        counts = Counter()
        try:
            if path.name.endswith(".observations.jsonl"):
                initial_digest = sha256_file(path)
                records = read_capture(path)
            else:
                adapter = CsiReplay(path)
                initial_digest = adapter.digest
                records = iter(adapter)
            with self._connect() as db:
                for i, obs in enumerate(records):
                    if self.cancel.is_set():
                        return
                    if i >= self.limit or self.path.stat().st_size >= self.MAX_BYTES:
                        self.limited = True
                        break
                    d = obs.to_dict()
                    if d["kind"] == "csi_lltf_amplitude":
                        value = d["value"]
                        amps = (
                            value.get("amplitudes") if isinstance(value, dict) else None
                        )
                        if (
                            not isinstance(amps, list)
                            or len(amps) != 64
                            or any(
                                v is not None
                                and (
                                    type(v) not in (int, float)
                                    or not math.isfinite(v)
                                    or v < 0
                                )
                                for v in amps
                            )
                        ):
                            raise ContractError(
                                "CSI amplitude payload must contain 64 finite/nonnegative or masked slots"
                            )
                        for key in (
                            "rssi_dbm",
                            "noise_floor_dbm",
                            "phy_rate_code",
                            "sig_len_bytes",
                        ):
                            v = value.get(key)
                            if type(v) not in (int, float) or not math.isfinite(v):
                                raise ContractError(
                                    "CSI numeric metadata missing: " + key
                                )
                    sid = d["sensor_id"]
                    if sid not in registry.streams:
                        registry.register(
                            SensorSpec(
                                sid,
                                d["node_id"],
                                sid,
                                d["kind"],
                                d["units"],
                                d["frame_id"],
                            )
                        )
                    registry.ingest(obs, i * 1_000_000)
                    st = registry.streams[sid]
                    val = d["value"]
                    if isinstance(val, dict) and "sig_len_bytes" in val:
                        counts[f"sig_len_{val['sig_len_bytes']}"] += 1
                    health = dict(
                        received=st.received,
                        source_missing=st.source_missing,
                        rate_hz=st.rate_hz,
                        buffer_evictions=st.buffer_evictions,
                        retained=min(i + 1, 256),
                        state=st.state,
                    )
                    db.execute(
                        "INSERT INTO observations VALUES (?,?,?,?,?)",
                        (i, sid, d["seq"], obs.to_json(), json.dumps(health)),
                    )
                    if (i + 1) % 128 == 0:
                        db.commit()
                        with self.lock:
                            self.count = i + 1
                db.commit()
                n = db.execute("SELECT count(*) FROM observations").fetchone()[0]
                sources = [
                    dict(sensor_id=s, count=c)
                    for s, c in db.execute(
                        "SELECT sensor,count(*) FROM observations GROUP BY sensor"
                    )
                ]
            if sha256_file(path) != initial_digest:
                raise ContractError("source changed while indexing; integrity rejected")
            with self.lock:
                if self.cancel.is_set():
                    return
                self.count = n
                self.sources = sources
                self.counters = dict(counts)
                if adapter:
                    self.counters.update(
                        {
                            k: adapter.counts[k]
                            for k in (
                                "observations",
                                "sequence_missing",
                                "malformed",
                                "unsupported_layout",
                                "non_csi",
                            )
                        }
                    )
                self.status = "READY" if n else "ERROR"
                self.error = (
                    None
                    if n
                    else {"code": "EMPTY_SOURCE", "message": "No usable observations"}
                )
                self.elapsed = time.monotonic() - self.started
                self.events.append(
                    {"code": "LOAD_FINISHED", "message": f"{n} indexed observations"}
                )
        except Exception as exc:
            with self.lock:
                if self.cancel.is_set():
                    return
                self.status = "ERROR"
                self.error = {"code": type(exc).__name__, "message": str(exc)[:1024]}
                self.playing = False
                self.events.append(self.error)
                if adapter:
                    self.counters = dict(adapter.counts)

    def control(self, action, value=None):
        with self.lock:
            if action == "seek":
                if type(value) is not int or not 0 <= value < self.count:
                    raise ValueError("seek outside indexed recording")
                self.position = value
            elif action == "play":
                if type(value) is not bool:
                    raise ValueError("play requires boolean state")
                if self.status != "READY" or not self.count:
                    raise ValueError("a ready source is required")
                self.playing = bool(value)
            elif action == "speed":
                if type(value) not in (int, float) or value not in (
                    0.25,
                    0.5,
                    1,
                    2,
                    4,
                    8,
                ):
                    raise ValueError("unsupported playback speed")
                self.speed = value
            elif action == "disconnect":
                self.cancel.set()
                self.playing = False
                self.status = "DISCONNECTED"
                self.events.append(
                    {
                        "code": "DISCONNECTED",
                        "message": "Replay detached; cached evidence retained",
                    }
                )
            else:
                raise ValueError("unknown control")
            self.play_wall = time.monotonic()

    def snapshot(self, index=None, source=None, query=""):
        with self.lock:
            if self.playing and self.count:
                elapsed = time.monotonic() - self.play_wall
                advance = int(elapsed * 25 * self.speed)
                if advance:
                    self.position = min(self.count - 1, self.position + advance)
                    self.play_wall += advance / (25 * self.speed)
                    if self.position == self.count - 1:
                        self.playing = False
            pos = self.position if index is None else index
            result = dict(
                status=self.status,
                error=self.error,
                file=self.filename,
                count=self.count,
                position=pos,
                playing=self.playing,
                speed=self.speed,
                limited=self.limited,
                max_records=self.limit,
                counters=self.counters,
                sources=self.sources,
                load_seconds=self.elapsed,
                events=list(self.events),
                observation=None,
                rows=[],
                series=[],
                health=None,
                mode="REPLAY" if self.filename else "OFFLINE",
                live_verified=False,
                timing="25 records/s × speed; inspection playback, not acquisition time",
            )
            if not self.count:
                return result
            if type(pos) is not int or not 0 <= pos < self.count:
                raise ValueError("observation outside indexed recording")
            with self._connect() as db:
                row = db.execute(
                    "SELECT body,health FROM observations WHERE i=?", (pos,)
                ).fetchone()
                if not row:
                    return result
                result["observation"], result["health"] = map(json.loads, row)
                where = "i <= ?"
                params = [pos]
                if source:
                    where += " AND sensor=?"
                    params.append(source)
                if query:
                    where += " AND (CAST(seq AS TEXT) LIKE ? OR sensor LIKE ?)"
                    params += ["%" + query[:64] + "%"] * 2
                rows = db.execute(
                    "SELECT i,body FROM observations WHERE "
                    + where
                    + " ORDER BY i DESC LIMIT 80",
                    params,
                ).fetchall()
                for i, b in rows:
                    d = json.loads(b)
                    val = d["value"] if isinstance(d["value"], dict) else {}
                    result["rows"].append(
                        dict(
                            index=i,
                            seq=d["seq"],
                            sensor=d["sensor_id"],
                            origin=d["origin"],
                            state=d["validity"]["state"],
                            tick=d["acquisition"]["ticks"],
                            rssi=val.get("rssi_dbm"),
                            sig_len=val.get("sig_len_bytes"),
                        )
                    )
                sid = result["observation"]["sensor_id"]
                series = db.execute(
                    "SELECT i,body FROM observations WHERE sensor=? AND i<=? ORDER BY i DESC LIMIT 160",
                    (sid, pos),
                ).fetchall()
                for i, b in reversed(series):
                    d = json.loads(b)
                    v = d["value"] if isinstance(d["value"], dict) else {}
                    result["series"].append(
                        dict(
                            index=i,
                            tick=d["acquisition"]["ticks"],
                            rssi=v.get("rssi_dbm"),
                            amplitudes=(v.get("amplitudes") if d["kind"] == "csi_lltf_amplitude" else None),
                            sig_len=v.get("sig_len_bytes"),
                            phy_rate=v.get("phy_rate_code"),
                        )
                    )
            return result

    def close(self):
        with self.lifecycle:
            if not self.closed:
                self._stop_worker()
                self.closed = True
                self.temp.cleanup()
