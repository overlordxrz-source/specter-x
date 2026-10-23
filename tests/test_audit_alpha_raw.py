"""Synthetic controls for the independent raw checker, never human evidence."""

import csv
import io
import json
import math
import pytest
from tools.audit_alpha_raw import check


def make_capture(tmp_path, inject):
    raw, trials = io.StringIO(), []
    writer = csv.writer(raw)
    for block in range(10):
        for label in ("stationary", "hand"):
            samples = []
            for j in range(5):
                seq = len(trials) * 5 + j
                iq = [1, 0] * 64
                if inject and label == "hand" and j % 2:
                    iq[10] = block + 3
                fields = [
                    "CSI_DATA",
                    seq,
                    "synthetic",
                    -50,
                    11,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -96,
                    0,
                    6,
                    0,
                    seq * 100000,
                    0,
                    138,
                    0,
                    128,
                    0,
                    json.dumps(iq),
                ]
                writer.writerow(fields)
                samples.append(
                    dict(
                        id=seq,
                        local_timestamp=seq * 100000,
                        amplitudes=[
                            round(math.hypot(iq[k], iq[k + 1]), 2)
                            for k in range(0, 128, 2)
                        ],
                        rssi=-50,
                        rate=11,
                        channel=6,
                        sig_len=138,
                        first_word_invalid=False,
                    )
                )
            trials.append(
                dict(
                    block=block,
                    label=label,
                    index=len(trials) + 1,
                    samples=samples,
                    active_s=0.4,
                    sensor_span_s=0.4,
                    sample_span_s=0.4,
                    valid=True,
                )
            )
    r, s = tmp_path / "synthetic.raw", tmp_path / "session.json"
    r.write_text(raw.getvalue())
    s.write_text(json.dumps({"trials": trials}))
    return r, s


@pytest.mark.parametrize("inject", [False, True])
def test_injection_detected_and_null_remains_negative(tmp_path, inject):
    raw, session = make_capture(tmp_path, inject)
    result = check(raw, session)
    assert result["matched_samples"] == result["selected_samples"] == 100
    assert result["mismatches"] == []
    assert result["primary_p"] == (1 / 1024 if inject else 1.0)


def test_altered_sample_is_not_accepted_as_matching_raw(tmp_path):
    raw, session = make_capture(tmp_path, True)
    data = json.loads(session.read_text())
    data["trials"][0]["samples"][0]["amplitudes"][5] += 10
    session.write_text(json.dumps(data))
    result = check(raw, session)
    assert len(result["mismatches"]) == 1 and result["matched_samples"] == 99
