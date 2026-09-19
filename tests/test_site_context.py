import pandas as pd

from scripts.build_predictions import current_season_player_context


def test_current_season_context_excludes_prior_seasons_and_future_weeks():
    rows = [
        {
            "player_id": "p1",
            "season": 2025,
            "week": 18,
            "carries": 99,
            "targets": 99,
            "rushing_yards": 999,
            "receiving_yards": 999,
            "rushing_tds": 9,
            "receiving_tds": 9,
        },
        {
            "player_id": "p1",
            "season": 2026,
            "week": 1,
            "carries": 10,
            "targets": 3,
            "rushing_yards": 50,
            "receiving_yards": 20,
            "rushing_tds": 1,
            "receiving_tds": 0,
        },
        {
            "player_id": "p1",
            "season": 2026,
            "week": 2,
            "carries": 20,
            "targets": 5,
            "rushing_yards": 100,
            "receiving_yards": 40,
            "rushing_tds": 0,
            "receiving_tds": 1,
        },
        {
            "player_id": "p1",
            "season": 2026,
            "week": 3,
            "carries": 30,
            "targets": 8,
            "rushing_yards": 150,
            "receiving_yards": 60,
            "rushing_tds": 2,
            "receiving_tds": 0,
        },
    ]
    context = current_season_player_context(pd.DataFrame(rows), 2026, 2)["p1"]

    assert context["season"] == 2026
    assert context["games_played"] == 2
    assert context["season_rushing_avg"] == 75.0
    assert [game["week"] for game in context["recent_games"]] == [1, 2]
