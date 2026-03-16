import numpy as np

from app.services.ml.inference import _reconstruct_levels


def test_reconstruct_open_equals_prev_close():
    close_t = 100.0
    comps = np.array([10.0, np.log(1.05), 0.0, 0.0, np.log1p(1000.0)], dtype=float)
    levels = _reconstruct_levels(close_t, comps)

    assert levels["open"] == close_t
    assert np.isfinite(levels["close"])
    assert levels["high"] >= max(levels["open"], levels["close"])
    assert levels["low"] <= min(levels["open"], levels["close"])
    assert levels["volume"] >= 0.0


def test_reconstruct_eliminates_gap_in_autoregressive_steps():
    close_t = 100.0
    prev_close = close_t
    for _ in range(3):
        comps = np.array([5.0, np.log(1.02), 0.1, 0.1, np.log1p(10.0)], dtype=float)
        levels = _reconstruct_levels(prev_close, comps)
        assert levels["open"] == prev_close
        prev_close = float(levels["close"])


def test_reconstruct_clamps_invalid_high_low():
    close_t = 100.0
    comps = np.array([0.0, np.log(1.2), -1.0, -1.0, np.log1p(1.0)], dtype=float)
    levels = _reconstruct_levels(close_t, comps)

    body_max = max(levels["open"], levels["close"])
    body_min = min(levels["open"], levels["close"])
    assert levels["high"] >= body_max
    assert levels["low"] <= body_min

