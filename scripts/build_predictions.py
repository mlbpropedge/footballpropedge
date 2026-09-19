from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import CURRENT_SEASON, TRAINING_SEASONS, MODELS_DIR, SITE_DATA_DIR
from src.data import load_player_stats, load_schedules
from src.features import make_training_frame, latest_player_features
from src.modeling import fit_models, predict


def next_week_context(schedules: pd.DataFrame, season: int, completed_week: int) -> tuple[int, dict]:
    season_games = schedules[schedules["season"] == season].copy()
    next_week = completed_week + 1
    if next_week > int(pd.to_numeric(season_games["week"], errors="coerce").max()):
        next_week = completed_week
    games = season_games[season_games["week"] == next_week]
    opponent = {}
    for _, g in games.iterrows():
        away, home = g.get("away_team"), g.get("home_team")
        if pd.notna(away) and pd.notna(home):
            opponent[str(away)] = str(home)
            opponent[str(home)] = str(away)
    return next_week, opponent


def main():
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    stats = load_player_stats(TRAINING_SEASONS, refresh=True)
    stats = stats[stats["season"].isin(TRAINING_SEASONS)].copy()
    current = stats[stats["season"] == CURRENT_SEASON]
    if current.empty:
        raise RuntimeError(f"No {CURRENT_SEASON} player stats found upstream.")

    completed_week = int(pd.to_numeric(current["week"], errors="coerce").max())
    training = make_training_frame(stats)
    bundle = fit_models(training)

    features = latest_player_features(stats)
    latest_current = features[features["season"] == CURRENT_SEASON].copy()

    schedules = load_schedules(refresh=True)
    projection_week, opponents = next_week_context(schedules, CURRENT_SEASON, completed_week)

    latest_current["opponent"] = latest_current["recent_team"].map(opponents).fillna("TBD")
    latest_current["projection_week"] = projection_week
    preds = predict(bundle, latest_current)

    role = (
        (preds["carries_avg_3"] >= 2)
        | (preds["targets_avg_3"] >= 2)
        | (preds["projected_rushing_yards"] >= 8)
        | (preds["projected_receiving_yards"] >= 8)
    )
    preds = preds[role].copy()

    rows = []
    for _, r in preds.sort_values(
        ["projected_rushing_yards", "projected_receiving_yards"], ascending=False
    ).iterrows():
        rows.append({
            "player_id": str(r["player_id"]),
            "player": str(r["player_display_name"]),
            "team": str(r["recent_team"]),
            "opponent": str(r["opponent"]),
            "position": str(r["position"]),
            "week": int(r["projection_week"]),
            "rushing_yards": round(float(r["projected_rushing_yards"]), 1),
            "receiving_yards": round(float(r["projected_receiving_yards"]), 1),
            "td_probability": round(float(r["touchdown_probability"]) * 100, 1),
            "recent_carries": round(float(r.get("carries_avg_3", 0)), 1),
            "recent_targets": round(float(r.get("targets_avg_3", 0)), 1),
            "recent_rush_yards": round(float(r.get("rushing_yards_avg_3", 0)), 1),
            "recent_rec_yards": round(float(r.get("receiving_yards_avg_3", 0)), 1),
        })

    payload = {
        "season": CURRENT_SEASON,
        "week": projection_week,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "nflverse",
        "players": rows,
    }
    (SITE_DATA_DIR / "predictions.json").write_text(json.dumps(payload, indent=2))
    (SITE_DATA_DIR / "model_metrics.json").write_text(json.dumps(bundle.metrics, indent=2))
    joblib.dump(bundle, MODELS_DIR / "model_bundle.joblib")
    print(f"Wrote {len(rows)} player projections for {CURRENT_SEASON} week {projection_week}.")


if __name__ == "__main__":
    main()
