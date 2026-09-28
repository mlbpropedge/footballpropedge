import json
from datetime import date

import pandas as pd

from scripts.build_predictions import archive_prediction, preserve_played_games, scheduled_game_dates


def test_team_dates_follow_actual_schedule():
    schedule = pd.DataFrame([
        {"season": 2026, "week": 3, "game_type": "REG", "gameday": "2026-09-24", "home_team": "SEA", "away_team": "LA"},
        {"season": 2026, "week": 3, "game_type": "REG", "gameday": "2026-09-27", "home_team": "BAL", "away_team": "DAL"},
        {"season": 2026, "week": 4, "game_type": "REG", "gameday": "2026-10-04", "home_team": "BAL", "away_team": "SEA"},
    ])
    assert scheduled_game_dates(schedule, 2026, 3) == {
        "SEA": "2026-09-24", "LA": "2026-09-24",
        "BAL": "2026-09-27", "DAL": "2026-09-27",
    }


def test_grading_snapshot_freezes_on_first_game_date(tmp_path):
    path = tmp_path / "week.json"
    original = {"players": [{"game_date": "2026-09-24"}], "version": 1}
    revised = {"players": [{"game_date": "2026-09-24"}], "version": 2}
    assert archive_prediction(original, path, date(2026, 9, 23))
    assert not archive_prediction(revised, path, date(2026, 9, 24))
    assert json.loads(path.read_text())["version"] == 1


def test_in_week_refresh_keeps_pregame_numbers_for_finished_game(tmp_path):
    path = tmp_path / "week.json"
    path.write_text(json.dumps({"season": 2026, "week": 3, "players": [
        {"player_id": "a", "team": "SEA", "rushing_yards": 55},
        {"player_id": "b", "team": "LA", "rushing_yards": 48},
    ]}))
    fresh = [
        {"player_id": "a", "team": "SEA", "game_date": "2026-09-24", "rushing_yards": 99},
        {"player_id": "b", "team": "LA", "game_date": "2026-09-24", "rushing_yards": 99},
        {"player_id": "c", "team": "BAL", "game_date": "2026-09-27", "rushing_yards": 60},
    ]
    result = preserve_played_games(fresh, 2026, 3, path, date(2026, 9, 27))
    assert {r["player_id"]: r["rushing_yards"] for r in result} == {"a": 55, "b": 48, "c": 60}
    assert all(r.get("game_date") for r in result)
