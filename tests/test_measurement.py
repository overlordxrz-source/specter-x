import json

import numpy as np
import pytest

from specter.fusion.measurement import Measurement, Provenance


def make(**kw):
    base = dict(
        sensor="nightvision", kind="pose2d", t_host=1760000000.123, t_sensor=12.5,
        frame_id="imx462-0/image",
        value={"keypoints_xy": np.array([[1.5, 2.5], [3.0, 4.0]]), "score": np.float32(0.5)},
        confidence=0.87, covariance=np.eye(2) * 4.0,
        provenance=Provenance("imx462-0", "nightvision", "yolo11n-pose", "yolo11n-pose.pt", 42),
    )
    base.update(kw)
    return Measurement(**base)


def test_json_roundtrip():
    m = make()
    s = m.to_json()
    d = json.loads(s)  # valid JSON, numpy converted
    assert d["provenance"]["algorithm"] == "yolo11n-pose"
    assert d["value"]["keypoints_xy"] == [[1.5, 2.5], [3.0, 4.0]]
    m2 = Measurement.from_json(s)
    assert m2.to_dict() == m.to_dict()
    assert m2.provenance.frame_index == 42
    assert m2.id == m.id


def test_hud_tag():
    assert make().hud_tag == "SRC: OPTICAL conf 0.87"
    assert make(confidence=None).hud_tag == "SRC: OPTICAL conf n/a"
    syn = make(sensor="synthetic", provenance=Provenance("synthetic-0", "synthetic", "gt"))
    assert syn.hud_tag.startswith("SRC: SYNTHETIC")


def test_parents_survive_roundtrip():
    m = make(provenance=Provenance("imx462-0", "nightvision", "x", parents=("a1", "b2")))
    assert Measurement.from_json(m.to_json()).provenance.parents == ("a1", "b2")


@pytest.mark.parametrize("bad", [
    dict(confidence=1.5),
    dict(covariance=[[1, 0, 0], [0, 1, 0]]),
    dict(covariance=[[1, 2], [0, 1]]),
    dict(frame_id=""),
    dict(sensor="thermal"),  # mismatches provenance.source
])
def test_validation(bad):
    with pytest.raises(ValueError):
        make(**bad)


def test_contract_fields_default_without_changing_old_call_sites():
    m = make()
    assert m.schema_version == "specter.observation.v1"
    assert m.valid is True
    assert m.validity_flags == ()
    assert m.evidence_level == "software_verified"
    assert m.seq is None
    assert m.dropped_before == 0
    assert m.measurement_type is None
    assert m.units is None


def test_contract_fields_survive_roundtrip():
    m = make(
        measurement_type="csi_lltf_amplitude",
        units="adc_counts",
        calibration_version="uncalibrated/csi-signal-v1",
        evidence_level="hardware_measured",
        validity_flags=("signal_domain", "not_spatial"),
        raw_ref={"uri": "run.raw", "sha256": "ab", "format": "esp32-csi-text"},
        uncertainty={"kind": "none", "value": None, "units": "n/a"},
        seq=7,
        dropped_before=2,
    )
    m2 = Measurement.from_json(m.to_json())
    assert m2.to_dict() == m.to_dict()
    assert m2.validity_flags == ("signal_domain", "not_spatial")
    assert m2.evidence_level == "hardware_measured"
    assert m2.seq == 7 and m2.dropped_before == 2


@pytest.mark.parametrize("bad", [
    dict(evidence_level="certified"),
    dict(validity_flags=("made_up",)),
    dict(seq=-1),
    dict(dropped_before=-1),
    dict(schema_version=""),
])
def test_contract_fields_reject_invalid_values(bad):
    with pytest.raises(ValueError):
        make(**bad)
