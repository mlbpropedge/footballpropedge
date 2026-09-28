import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.build_predictions import archive_prediction, preserve_played_games, scheduled_game_dates, scheduled_game_starts

ET = ZoneInfo("America/New_York")


def test_team_dates_follow_actual_schedule():
    schedule = pd.DataFrame([
        {"season": 2026, "week": 3, "game_type": "REG", "gameday": "2026-09-24", "gametime": "20:15", "home_team": "SEA", "away_team": "LA"},
        {"season": 2026, "week": 3, "game_type": "REG", "gameday": "2026-09-27", "gametime": "13:00", "home_team": "BAL", "away_team": "DAL"},
        {"season": 2026, "week": 4, "game_type": "REG", "gameday": "2026-10-04", "gametime": "13:00", "home_team": "BAL", "away_team": "SEA"},
    ])
    assert scheduled_game_dates(schedule, 2026, 3) == {
        "SEA": "2026-09-24", "LA": "2026-09-24",
        "BAL": "2026-09-27", "DAL": "2026-09-27",
    }
    assert scheduled_game_starts(schedule, 2026, 3)["SEA"] == "2026-09-24T20:15:00-04:00"


def test_grading_snapshot_freezes_at_kickoff(tmp_path):
    path = tmp_path / "week.json"
    original = {"players": [{"game_start": "2026-09-24T20:15:00-04:00"}], "version": 1}
    revised = {"players": [{"game_start": "2026-09-24T20:15:00-04:00"}], "version": 2}
    assert archive_prediction(original, path, datetime(2026, 9, 24, 19, tzinfo=ET))
    assert not archive_prediction(revised, path, datetime(2026, 9, 24, 21, tzinfo=ET))
    assert json.loads(path.read_text())["version"] == 1


def test_in_week_refresh_keeps_pregame_numbers_for_finished_game(tmp_path):
    path = tmp_path / "week.json"
    path.write_text(json.dumps({"season": 2026, "week": 3, "players": [
        {"player_id": "a", "team": "SEA", "rushing_yards": 55},
        {"player_id": "b", "team": "LA", "rushing_yards": 48},
    ]}))
    fresh = [
        {"player_id": "a", "team": "SEA", "game_date": "2026-09-24", "game_start": "2026-09-24T20:15:00-04:00", "rushing_yards": 99},
        {"player_id": "b", "team": "LA", "game_date": "2026-09-24", "game_start": "2026-09-24T20:15:00-04:00", "rushing_yards": 99},
        {"player_id": "c", "team": "BAL", "game_date": "2026-09-27", "game_start": "2026-09-27T13:00:00-04:00", "rushing_yards": 60},
    ]
    result = preserve_played_games(fresh, 2026, 3, path, datetime(2026, 9, 27, 12, tzinfo=ET))
    assert {r["player_id"]: r["rushing_yards"] for r in result} == {"a": 55, "b": 48, "c": 60}
    assert all(r.get("game_date") for r in result)
    assert all(r.get("game_start") for r in result)
