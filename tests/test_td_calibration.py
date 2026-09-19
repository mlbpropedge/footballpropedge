import numpy as np

from src.modeling import apply_td_calibration


def test_td_calibration_keeps_probabilities_bounded():
    calibrated = apply_td_calibration(
        np.array([0.001, 0.50, 0.999]), base_rate=0.20, slope=1.5
    )
    assert np.all(calibrated >= 0.001)
    assert np.all(calibrated <= 0.999)


def test_td_calibration_slope_zero_returns_base_rate():
    calibrated = apply_td_calibration(
        np.array([0.05, 0.50, 0.90]), base_rate=0.25, slope=0.0
    )
    assert np.allclose(calibrated, 0.25)


def test_td_calibration_slope_one_preserves_probabilities():
    raw = np.array([0.05, 0.50, 0.90])
    calibrated = apply_td_calibration(raw, base_rate=0.25, slope=1.0)
    assert np.allclose(calibrated, raw)
