from scripts.add_prediction_ranges import reliability_adjusted_score, reliability_score


def test_reliability_rewards_narrower_empirical_range():
    narrow = reliability_score(60.0, [45.0, 75.0], 15.0, 15.0)
    wide = reliability_score(60.0, [20.0, 100.0], 15.0, 15.0)
    assert narrow > wide


def test_reliability_rewards_stable_workload():
    stable = reliability_score(60.0, [40.0, 80.0], 15.0, 15.0)
    volatile = reliability_score(60.0, [40.0, 80.0], 5.0, 15.0)
    assert stable > volatile


def test_adjusted_score_stays_bounded():
    assert reliability_adjusted_score(120.0, 120.0) == 100.0
    assert reliability_adjusted_score(-10.0, -10.0) == 0.0
