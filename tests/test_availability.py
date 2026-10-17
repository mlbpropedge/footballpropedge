from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.availability import games_missed, player_availability, snap_share_context


def injury_rows():
    return pd.DataFrame([
        {"season": 2026, "game_type": "REG", "week": 6, "gsis_id": "out", "report_status": "Out", "report_primary_injury": "Ankle"},
        {"season": 2026, "game_type": "REG", "week": 6, "gsis_id": "q", "report_status": "Questionable", "report_primary_injury": "Knee"},
        {"season": 2026, "game_type": "REG", "week": 6, "gsis_id": "practice", "report_status": None, "report_primary_injury": None},
        # Last week's designation must not carry into this week.
        {"season": 2026, "game_type": "REG", "week": 5, "gsis_id": "old", "report_status": "Out", "report_primary_injury": "Hamstring"},
    ])


def roster_rows():
    return pd.DataFrame([
        {"season": 2026, "game_type": "REG", "week": 6, "gsis_id": "ir", "team": "KC", "status": "RES"},
        {"season": 2026, "game_type": "REG", "week": 6, "gsis_id": "traded", "team": "LAC", "status": "ACT"},
        {"season": 2026, "game_type": "REG", "week": 6, "gsis_id": "q", "team": "BUF", "status": "ACT"},
    ])


def test_only_this_weeks_report_rules_players_out():
    result = player_availability(injury_rows(), roster_rows(), 2026, 6)
    status = result["availability"]
    assert status["out"]["unavailable"] and status["out"]["detail"] == "Ankle"
    assert status["q"]["status"] == "Questionable" and not status["q"]["unavailable"]
    assert "old" not in status and "practice" not in status
    assert status["ir"]["unavailable"] and status["ir"]["status"] == "Reserve list"
    assert result["teams"]["traded"] == "LAC"
    assert result["info"]["injury_report_week"] == 6


def test_missing_feeds_never_break_the_build():
    result = player_availability(pd.DataFrame(), pd.DataFrame(), 2026, 6)
    assert result["availability"] == {} and result["teams"] == {}
    assert snap_share_context(pd.DataFrame(), pd.DataFrame(), 2026, 6) == {}


def test_previous_week_inactive_is_ignored():
    roster = pd.DataFrame([{"season": 2026, "week": 5, "gsis_id": "p", "team": "KC", "status": "INA"}])
    assert "p" not in player_availability(pd.DataFrame(), roster, 2026, 6)["availability"]


def test_snap_share_maps_pfr_ids_to_gsis_ids():
    snaps = pd.DataFrame([
        {"season": 2026, "game_type": "REG", "week": w, "pfr_player_id": "PfrA", "offense_pct": pct}
        for w, pct in [(1, 0.5), (2, 0.6), (3, 0.7), (4, 0.8)]
    ])
    players = pd.DataFrame([{"gsis_id": "00-1", "pfr_id": "PfrA"}])
    context = snap_share_context(snaps, players, 2026, 4)["00-1"]
    assert context["snap_share_3"] == 70.0
    assert context["snap_share_season"] == 65.0
    assert context["by_week"][4] == 80.0


def test_bye_weeks_are_not_counted_as_missed_games():
    rows = []
    for week in (1, 2, 3, 5, 6):  # team bye in week 4
        rows.append({"player_id": "starter", "recent_team": "KC", "season": 2026, "week": week})
    for week in (1, 2):
        rows.append({"player_id": "hurt", "recent_team": "KC", "season": 2026, "week": week})
    out = games_missed(pd.DataFrame(rows), 2026, 6)
    assert out["starter"]["games_missed"] == 0
    assert out["hurt"] == {"last_played_week": 2, "games_missed": 3}
