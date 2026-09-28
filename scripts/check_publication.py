"""Fail the refresh before committing malformed or mismatched public data."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(payload, performance, now=None):
    now = now or datetime.now(timezone.utc)
    generated = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    assert abs((now - generated).total_seconds()) < 4 * 3600, "Projection run is stale"
    players = payload["players"]
    assert len(players) >= 100, "Unexpectedly small player slate"
    assert len({row["player_id"] for row in players}) == len(players), "Duplicate players"
    opponents = {row["team"]: row["opponent"] for row in players}
    assert 20 <= len(opponents) <= 32 and len(opponents) % 2 == 0, "Invalid game slate"
    for row in players:
        assert row["week"] == payload["week"]
        assert row["game_date"] and row["opponent"] != row["team"]
        assert opponents[row["opponent"]] == row["team"], "Non-reciprocal matchup"
        assert 0 <= row["td_probability"] <= 100
        assert row["rushing_yards"] >= 0 and row["receiving_yards"] >= 0
        for key in ("rushing_range_80", "receiving_range_80"):
            low, high = row[key]
            assert 0 <= low <= high, f"Invalid {key}"
    assert performance["graded_weeks"] == len(performance["weekly_results"])


if __name__ == "__main__":
    data = ROOT / "data"
    check(json.loads((data / "predictions.json").read_text()),
          json.loads((data / "performance.json").read_text()))
    print("Published slate and results passed sanity checks.")
