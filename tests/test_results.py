from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_predictions import (
    apply_change_markers,
    calibration_buckets,
    prior_td_rates,
    range_hit,
)


def test_range_hit_is_inclusive_and_tolerates_missing_ranges():
    assert range_hit(40, [40, 80]) is True
    assert range_hit(81, [40, 80]) is False
    assert range_hit(50, None) is None


def test_calibration_buckets_compare_prediction_to_outcome():
    probs = [5] * 20 + [45] * 20
    actual = [0] * 19 + [1] + [1] * 10 + [0] * 10
    buckets = {b["label"]: b for b in calibration_buckets(probs, actual)}
    assert buckets["0–10%"]["actual_rate"] == 5.0
    assert buckets["40–50%"]["actual_rate"] == 50.0
    assert "10–20%" not in buckets


def test_prior_td_rate_uses_only_earlier_games():
    stats = pd.DataFrame([
        {"player_id": "p", "season": 2026, "week": w, "rushing_tds": td, "receiving_tds": 0}
        for w, td in [(1, 1), (2, 0), (3, 1)]
    ])
    rates = prior_td_rates(stats)
    assert ("p", 2026, 1) not in rates
    assert rates[("p", 2026, 2)] == 1.0
    assert rates[("p", 2026, 3)] == 0.5


def test_change_markers_flag_meaningful_moves_only():
    previous = {"season": 2026, "week": 6, "players": [
        {"player_id": "a", "rushing_yards": 60, "receiving_yards": 10, "td_probability": 30},
        {"player_id": "b", "rushing_yards": 60, "receiving_yards": 10, "td_probability": 30},
    ]}
    rows = [
        {"player_id": "a", "rushing_yards": 70.5, "receiving_yards": 12, "td_probability": 30},
        {"player_id": "b", "rushing_yards": 62, "receiving_yards": 10, "td_probability": 30},
        {"player_id": "c", "rushing_yards": 50, "receiving_yards": 0, "td_probability": 20},
    ]
    assert apply_change_markers(rows, previous, 2026, 6)
    assert rows[0]["change"] == {"rushing_yards": 10.5}
    assert "change" not in rows[1]
    assert rows[2]["new_to_slate"] is True


def test_change_markers_reset_for_a_new_week():
    rows = [{"player_id": "a", "rushing_yards": 70, "change": {"rushing_yards": 9}}]
    assert not apply_change_markers(rows, {"season": 2026, "week": 5, "players": []}, 2026, 6)
    assert "change" not in rows[0]
