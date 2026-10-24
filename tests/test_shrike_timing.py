"""Software-only controls for SPECTER-SYNC event-log analysis."""

import pytest

from tools.shrike_timing import analyze


def row(count, ticks):
    return {"event_count": count, "fpga_ticks": ticks}


def test_duplicate_snapshots_do_not_create_events():
    result = analyze(
        [row(1, 100), row(1, 100), row(2, 200), row(2, 200)],
        tick_hz=1_000_000.0,
    )
    assert result["unique_events"] == 2
    assert result["duplicate_samples_ignored"] == 2
    assert result["missing_events"] == 0
    assert result["intervals_ticks"] == [100]


def test_missing_event_is_reported():
    result = analyze([row(1, 10), row(3, 30)])
    assert result["missing_events"] == 1
    assert result["intervals_ticks"] == [20]


def test_counter_wrap_uses_declared_width():
    result = analyze(
        [row(1, 0xFFFFFFFE), row(2, 0x00000002)],
        counter_bits=32,
        tick_hz=50_000_000.0,
    )
    assert result["wrap_deltas"] == 1
    assert result["intervals_ticks"] == [4]


def test_nominal_period_errors_are_reported_not_claimed_accurate():
    result = analyze(
        [row(1, 0), row(2, 50_000_010)],
        tick_hz=50_000_000.0,
        expected_period_s=1.0,
    )
    assert result["expected_ticks"] == 50_000_000.0
    assert result["error_ns_mean"] == pytest.approx(200.0)
    assert result["nominal_period_estimate_s"] == pytest.approx(1.0000002)


def test_backwards_event_count_is_rejected():
    with pytest.raises(ValueError, match="backwards"):
        analyze([row(2, 100), row(1, 200)])


def test_nonfinite_tick_rate_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        analyze([row(1, 0)], tick_hz=float("nan"))
