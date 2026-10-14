"""EXPERIMENTAL modules: contracts, caps, and honesty labels."""
import numpy as np

from specter.sensors.experimental import (
    EXPERIMENTAL, LoRaFallback, SyntheticAcousticArray, SyntheticEventCamera,
    SyntheticGas, SyntheticVitals, summarize_tracks,
)
from specter.sensors.experimental import acoustic, event_camera, gas, lora, vitals, vlm
from specter.sensors.experimental.gas import danger_level, gas_measurement
from specter.sensors.experimental.lora import MTU, decode_packet
from specter.sensors.experimental.vlm import SENSOR as VLM_SENSOR


def test_all_flagged_experimental():
    assert EXPERIMENTAL is True
    for mod in (acoustic, event_camera, gas, lora, vitals, vlm):
        assert mod.EXPERIMENTAL is True


def test_event_camera_contract():
    m = SyntheticEventCamera().read()
    assert (m.sensor, m.kind) == ("event_camera", "event_motion")
    assert m.value["sim"] is True and "EXPERIMENTAL" in (m.provenance.notes or "")
    assert m.hud_tag.startswith("SRC: EVENT conf")


def test_acoustic_doa_contract():
    m = SyntheticAcousticArray().read()
    assert (m.sensor, m.kind) == ("acoustic", "sound_doa")
    assert -90 <= m.value["azimuth_deg"] <= 90 and m.value["sim"] is True


def test_vitals_range_and_validation():
    import pytest

    m = SyntheticVitals().read()
    assert (m.sensor, m.kind) == ("vitals_radar", "vitals")
    assert 4.0 <= m.value["breath_bpm"] <= 40.0
    with pytest.raises(ValueError):
        vitals.vitals_measurement(4.0, 300.0, 70.0)  # impossible breath rate


def test_vlm_summary_cites_measurement_ids():
    class T:
        def __init__(self, pos, units, mids):
            self.position, self.contributors = np.array(pos), units
            self.measurement_ids, self.label = mids, "person"

    tr = [T([10, 4, 0], [("unit-1", "thermal"), ("unit-2", "thermal")], ["m-a", "m-b"])]
    m = summarize_tracks(tr)
    assert m.sensor == VLM_SENSOR and m.kind == "ai_summary"
    assert "m-a" in m.value["text"] and "m-b" in m.value["text"]  # cites ids
    assert m.provenance.parents == ("m-a", "m-b")
    assert m.hud_tag.startswith("SRC: AI-SUMMARY conf")
    empty = summarize_tracks([])
    assert "no contacts" in empty.value["text"]  # honest emptiness


def test_lora_fits_mtu_and_roundtrips():
    link = LoRaFallback("unit-1")
    hb = link.heartbeat("GNSS", 1.2)
    md = link.mandown("no-motion")
    assert len(hb) < MTU and len(md) < MTU  # never video, fits mesh payload
    assert decode_packet(hb)["t"] == "hb" and decode_packet(md)["why"] == "no-motion"
    import pytest

    with pytest.raises(ValueError):
        decode_packet(b"\xff\xfe nope")


def test_gas_thresholds_and_honesty():
    assert danger_level(5, 450) == "OK"
    assert danger_level(50, 450) == "WARN" and danger_level(5, 2000) == "WARN"
    assert danger_level(250, 450) == "DANGER"
    m = SyntheticGas().read(co_ppm=250.0)
    assert m.value["danger"] == "DANGER" and "not certified" in (m.provenance.notes or "").lower()
    assert m.hud_tag.startswith("SRC: GAS conf")
