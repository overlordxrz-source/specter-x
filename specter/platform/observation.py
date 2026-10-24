"""Strict, immutable observation boundary; legacy Measurement is not changed."""

from __future__ import annotations
import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
import numpy as np

SCHEMA = "specter.observation/1.0.0"


class ContractError(ValueError):
    pass


def exact(obj, keys, where):
    if not isinstance(obj, dict) or set(obj) != set(keys.split()):
        raise ContractError(f"{where}: expected exactly {keys}")


def number(v, where, minimum=None, integer=False):
    if type(v) not in ((int,) if integer else (int, float)) or not math.isfinite(v):
        raise ContractError(
            f"{where}: finite {'integer' if integer else 'number'} required"
        )
    if minimum is not None and v < minimum:
        raise ContractError(f"{where}: below {minimum}")


def text(v, where):
    if not isinstance(v, str) or not v or len(v) > 512:
        raise ContractError(f"{where}: nonempty text <=512 chars required")


def finite_json(v):
    if isinstance(v, dict):
        if any(not isinstance(k, str) for k in v):
            raise ContractError("JSON keys must be strings")
        for x in v.values():
            finite_json(x)
    elif isinstance(v, list):
        for x in v:
            finite_json(x)
    elif v is None or type(v) in (bool, str, int):
        pass
    elif type(v) is float and math.isfinite(v):
        pass
    else:
        raise ContractError("payload contains nonfinite or non-JSON value")


def validate(d):
    exact(
        d,
        "schema id node_id sensor_id seq kind value units frame_id origin classification acquisition received calibration uncertainty evidence validity dropped_before",
        "observation",
    )
    if d["schema"] != SCHEMA:
        raise ContractError(
            "unsupported observation schema; explicit migration required"
        )
    for k in ("id", "node_id", "sensor_id", "kind", "units", "frame_id"):
        text(d[k], k)
    for k in ("seq", "dropped_before"):
        number(d[k], k, 0, True)
    if d["origin"] not in ("hardware", "simulated", "unknown"):
        raise ContractError("invalid origin")
    if d["classification"] not in (
        "measured",
        "inferred",
        "predicted",
        "simulated",
        "unknown",
    ):
        raise ContractError("invalid classification")
    if (d["origin"] == "simulated") != (d["classification"] == "simulated"):
        raise ContractError("simulated origin/classification must agree")
    ac = d["acquisition"]
    exact(ac, "domain epoch ticks tick_hz wrap_bits unwrapped_ticks", "acquisition")
    text(ac["domain"], "clock domain")
    text(ac["epoch"], "epoch")
    number(ac["tick_hz"], "tick_hz", 1)
    for k in ("ticks", "unwrapped_ticks"):
        if ac[k] is not None:
            number(ac[k], k, 0)
    if (ac["ticks"] is None) != (ac["unwrapped_ticks"] is None):
        raise ContractError("clock ticks must both be known or unknown")
    if ac["wrap_bits"] is not None:
        number(ac["wrap_bits"], "wrap_bits", 1, True)
        if (
            ac["wrap_bits"] > 64
            or ac["ticks"] is None
            or ac["ticks"] >= 2 ** ac["wrap_bits"]
        ):
            raise ContractError("native tick out of bounds")
    rx = d["received"]
    exact(rx, "domain time_ns", "received")
    text(rx["domain"], "receive domain")
    if rx["time_ns"] is not None:
        number(rx["time_ns"], "receive time", 0, True)
    c = d["calibration"]
    exact(c, "status id reference", "calibration")
    if c["status"] not in ("unknown", "uncalibrated", "calibrated"):
        raise ContractError("invalid calibration status")
    if c["status"] == "calibrated" and (not c["id"] or not c["reference"]):
        raise ContractError("calibration needs ID and reference")
    for k in ("id", "reference"):
        if c[k] is not None:
            text(c[k], k)
    u = d["uncertainty"]
    exact(u, "kind variables covariance", "uncertainty")
    if u["kind"] == "unknown":
        if u["variables"] != [] or u["covariance"] is not None:
            raise ContractError("unknown uncertainty is not zero covariance")
    elif u["kind"] == "covariance":
        if not isinstance(u["variables"], list) or not 1 <= len(u["variables"]) <= 64:
            raise ContractError("covariance variable count")
        for v in u["variables"]:
            text(v, "variable with units")
        if len(set(u["variables"])) != len(u["variables"]):
            raise ContractError("duplicate covariance variables")
        finite_json(u["covariance"])
        if not isinstance(u["covariance"], list) or any(
            not isinstance(row, list) for row in u["covariance"]
        ):
            raise ContractError("covariance must be numeric rows")
        for row in u["covariance"]:
            for v in row:
                number(v, "covariance entry")
        try:
            cov = np.asarray(u["covariance"], dtype=float)
        except (ValueError, TypeError) as e:
            raise ContractError("invalid covariance") from e
        n = len(u["variables"])
        if (
            cov.shape != (n, n)
            or not np.isfinite(cov).all()
            or not np.allclose(cov, cov.T, rtol=0, atol=1e-10)
        ):
            raise ContractError("covariance shape/finite/symmetry")
        if np.linalg.eigvalsh(cov).min() < -1e-10:
            raise ContractError("covariance must be positive semidefinite")
    else:
        raise ContractError("invalid uncertainty kind")
    e = d["evidence"]
    exact(e, "level raw parents algorithm revision", "evidence")
    if e["level"] not in ("recorded_hardware", "simulated", "unverified"):
        raise ContractError("invalid evidence level")
    if e["level"] == "recorded_hardware" and (
        d["origin"] != "hardware" or e["raw"] is None
    ):
        raise ContractError(
            "hardware evidence requires hardware origin and raw reference"
        )
    if e["level"] == "simulated" and d["origin"] != "simulated":
        raise ContractError("simulation evidence/origin mismatch")
    if d["origin"] == "simulated" and e["level"] != "simulated":
        raise ContractError("simulation cannot be promoted")
    for k in ("algorithm", "revision"):
        text(e[k], k)
    if d["classification"] in ("inferred", "predicted") and not e["parents"]:
        raise ContractError("derived observations need parent evidence")
    if not isinstance(e["parents"], list):
        raise ContractError("parents must be list")
    for p in e["parents"]:
        text(p, "parent")
    if e["raw"] is not None:
        rr = e["raw"]
        exact(rr, "artifact sha256 line", "raw evidence")
        text(rr["artifact"], "artifact")
        if not isinstance(rr["sha256"], str) or not re.fullmatch(
            "[a-f0-9]{64}", rr["sha256"]
        ):
            raise ContractError("raw sha256 required")
        number(rr["line"], "raw line", 1, True)
    v = d["validity"]
    exact(v, "state flags", "validity")
    if v["state"] not in ("usable", "degraded", "invalid", "unknown"):
        raise ContractError("invalid validity")
    if not isinstance(v["flags"], list) or len(set(v["flags"])) != len(v["flags"]):
        raise ContractError("flags must be unique list")
    for flag in v["flags"]:
        text(flag, "validity flag")
    if v["state"] != "usable" and not v["flags"]:
        raise ContractError("nonusable state needs reason")
    finite_json(d)


@dataclass(frozen=True, init=False)
class Observation:
    _canonical: str

    def __init__(self, data):
        try:
            validate(data)
        except (TypeError, ValueError, OverflowError) as e:
            raise ContractError(str(e)) from e
        object.__setattr__(
            self,
            "_canonical",
            json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False),
        )

    @classmethod
    def from_json(cls, s):
        def unique(pairs):
            d = {}
            for k, v in pairs:
                if k in d:
                    raise ContractError("duplicate JSON key")
                d[k] = v
            return d

        try:
            return cls(json.loads(s, object_pairs_hook=unique))
        except (ValueError, TypeError) as e:
            raise ContractError(str(e)) from e

    def to_dict(self):
        return json.loads(self._canonical)

    def to_json(self):
        return self._canonical


def from_legacy(measurement):
    """Explicit migration: never infer hardware origin from a sensor name."""
    m = measurement.to_dict()
    ac = m.get("t_sensor")
    d = dict(
        schema=SCHEMA,
        id=m["id"],
        node_id="legacy-unknown",
        sensor_id=m["provenance"]["sensor_id"],
        seq=0,
        kind=m["kind"],
        value=copy.deepcopy(m["value"]),
        units="unknown",
        frame_id=m["frame_id"],
        origin="unknown",
        classification="unknown",
        acquisition=dict(
            domain="legacy.unspecified",
            epoch="unknown",
            ticks=ac,
            unwrapped_ticks=ac,
            tick_hz=1,
            wrap_bits=None,
        ),
        received=dict(domain="legacy.wall_seconds", time_ns=None),
        calibration=dict(status="unknown", id=None, reference=None),
        uncertainty=dict(kind="unknown", variables=[], covariance=None),
        evidence=dict(
            level="unverified",
            raw=None,
            parents=[m["id"]],
            algorithm=m["provenance"]["algorithm"],
            revision="unrecorded",
        ),
        validity=dict(
            state="unknown",
            flags=["legacy_unverified", "units_unknown", "clock_unsynced"],
        ),
        dropped_before=0,
    )
    # Preserve original times as data, without pretending they are synchronized.
    d["value"] = {
        "legacy_value": d["value"],
        "original_t_host": m["t_host"],
        "original_t_sensor": ac,
    }
    return Observation(d)
