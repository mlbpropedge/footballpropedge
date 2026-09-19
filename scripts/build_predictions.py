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
from src.features import (
    DEFENSE_FEATURES,
    latest_defense_features,
    latest_player_features,
    make_training_frame,
)
from src.modeling import fit_models, predict

def attach_schedule_context(stats: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Attach leakage-safe historical home/away context to player rows."""
    out = stats.copy()
    if "recent_team" not in out.columns:
        if "team" in out.columns:
            out["recent_team"] = out["team"]
        else:
            raise ValueError("Player stats are missing both recent_team and team columns.")
    season_games = schedules.copy()
    if "game_type" in season_games.columns:
        season_games = season_games[season_games["game_type"].astype(str).eq("REG")]

    home_rows = season_games[["season", "week", "home_team"]].rename(
        columns={"home_team": "recent_team"}
    )
    home_rows["home_game"] = 1.0
    away_rows = season_games[["season", "week", "away_team"]].rename(
        columns={"away_team": "recent_team"}
    )
    away_rows["home_game"] = 0.0
    context = pd.concat([home_rows, away_rows], ignore_index=True).drop_duplicates(
        ["season", "week", "recent_team"]
    )

    out = out.merge(
        context,
        on=["season", "week", "recent_team"],
        how="left",
        suffixes=("", "_schedule"),
    )
    if "home_game_schedule" in out.columns:
        out["home_game"] = out["home_game_schedule"].fillna(out.get("home_game", 0.0))
        out = out.drop(columns=["home_game_schedule"])
    else:
        out["home_game"] = out.get("home_game", 0.0)
    out["home_game"] = pd.to_numeric(out["home_game"], errors="coerce").fillna(0.0)
    return out



def next_week_context(
    schedules: pd.DataFrame, season: int, completed_week: int
) -> tuple[int, dict, dict]:
    """Return the next real regular-season slate based on scheduled game dates.

    Do not infer the upcoming week as completed_week + 1. Player-stat feeds can
    publish a week label before that week's games are complete, which can push
    projections one week too far into the future.
    """
    season_games = schedules[schedules["season"] == season].copy()
    if "game_type" in season_games.columns:
        season_games = season_games[season_games["game_type"].astype(str).eq("REG")]

    if "gameday" not in season_games.columns:
        raise ValueError("Schedule data is missing required gameday column.")

    season_games["gameday_dt"] = pd.to_datetime(
        season_games["gameday"], errors="coerce"
    ).dt.date
    today_utc = datetime.now(timezone.utc).date()

    future = season_games[
        season_games["gameday_dt"].notna()
        & (season_games["gameday_dt"] >= today_utc)
    ].copy()

    if future.empty:
        next_week = int(
            pd.to_numeric(season_games["week"], errors="coerce").dropna().max()
        )
    else:
        next_game_date = future["gameday_dt"].min()
        next_week = int(
            pd.to_numeric(
                future.loc[future["gameday_dt"] == next_game_date, "week"],
                errors="coerce",
            ).dropna().min()
        )

    games = season_games[season_games["week"] == next_week]
    opponent = {}
    home_game = {}
    for _, g in games.iterrows():
        away, home = g.get("away_team"), g.get("home_team")
        if pd.notna(away) and pd.notna(home):
            opponent[str(away)] = str(home)
            opponent[str(home)] = str(away)
            home_game[str(away)] = 0.0
            home_game[str(home)] = 1.0
    return next_week, opponent, home_game


def attach_matchup_features(
    features: pd.DataFrame, stats: pd.DataFrame, opponents: dict, home_games: dict
) -> pd.DataFrame:
    out = features.copy()
    out["opponent"] = out["recent_team"].map(opponents).fillna("TBD")
    out["home_game"] = out["recent_team"].map(home_games).fillna(0.0)

    defense = latest_defense_features(stats)
    if not defense.empty:
        lookup = defense.set_index(["def_team", "position"])
        keys = list(zip(out["opponent"].astype(str), out["position"].astype(str)))
        for col in DEFENSE_FEATURES:
            out[col] = [
                float(lookup.at[key, col]) if key in lookup.index else 0.0
                for key in keys
            ]

        ranked = defense.copy()
        ranked["rush_def_rank"] = ranked.groupby("position")[
            "opp_pos_rush_yards_allowed_avg_4"
        ].rank(method="min", ascending=True)
        ranked["rec_def_rank"] = ranked.groupby("position")[
            "opp_pos_rec_yards_allowed_avg_4"
        ].rank(method="min", ascending=True)
        rank_lookup = ranked.set_index(["def_team", "position"])
        out["opp_rush_def_rank"] = [
            int(rank_lookup.at[key, "rush_def_rank"])
            if key in rank_lookup.index
            else 0
            for key in keys
        ]
        out["opp_rec_def_rank"] = [
            int(rank_lookup.at[key, "rec_def_rank"])
            if key in rank_lookup.index
            else 0
            for key in keys
        ]
        out["opp_def_rank_total"] = [
            int((ranked["position"] == position).sum())
            for position in out["position"].astype(str)
        ]
    else:
        out["opp_rush_def_rank"] = 0
        out["opp_rec_def_rank"] = 0
        out["opp_def_rank_total"] = 0
    return out


def current_season_player_context(
    stats: pd.DataFrame, season: int, completed_week: int
) -> dict[str, dict]:
    """Return compact current-season-only trends for the player detail UI."""
    season_rows = stats[
        (pd.to_numeric(stats["season"], errors="coerce") == season)
        & (pd.to_numeric(stats["week"], errors="coerce") <= completed_week)
    ].copy()
    if season_rows.empty:
        return {}

    numeric = [
        "week",
        "carries",
        "targets",
        "rushing_yards",
        "receiving_yards",
        "rushing_tds",
        "receiving_tds",
    ]
    for col in numeric:
        season_rows[col] = pd.to_numeric(
            season_rows.get(col, 0), errors="coerce"
        ).fillna(0)

    context = {}
    for player_id, group in season_rows.groupby("player_id"):
        group = group.sort_values("week")
        games = []
        for _, game in group.tail(5).iterrows():
            games.append(
                {
                    "week": int(game["week"]),
                    "rushing_yards": round(float(game["rushing_yards"]), 1),
                    "receiving_yards": round(float(game["receiving_yards"]), 1),
                    "carries": round(float(game["carries"]), 1),
                    "targets": round(float(game["targets"]), 1),
                    "touchdowns": int(
                        float(game["rushing_tds"]) + float(game["receiving_tds"])
                    ),
                }
            )
        context[str(player_id)] = {
            "season": int(season),
            "games_played": int(len(group)),
            "season_rushing_avg": round(float(group["rushing_yards"].mean()), 1),
            "season_receiving_avg": round(float(group["receiving_yards"].mean()), 1),
            "season_carries_avg": round(float(group["carries"].mean()), 1),
            "season_targets_avg": round(float(group["targets"].mean()), 1),
            "recent_games": games,
        }
    return context


def add_edge_scores(preds: pd.DataFrame, metrics: dict) -> pd.DataFrame:
    """Create transparent 0-100 ranking scores for each projection market.

    The score is a ranking heuristic, not a probability. It blends projection
    strength, recent workload, workload stability, matchup quality, and the
    market model's walk-forward validation quality.
    """
    out = preds.copy()

    def pct(col: str) -> pd.Series:
        values = pd.to_numeric(out.get(col, 0.0), errors="coerce").fillna(0.0)
        if values.nunique() <= 1:
            return pd.Series(0.5, index=out.index)
        return values.rank(pct=True, method="average")

    def stability(short_col: str, medium_col: str) -> pd.Series:
        short = pd.to_numeric(out.get(short_col, 0.0), errors="coerce").fillna(0.0)
        medium = pd.to_numeric(out.get(medium_col, 0.0), errors="coerce").fillna(0.0)
        denom = medium.abs().clip(lower=1.0)
        return (1.0 - ((short - medium).abs() / denom)).clip(0.0, 1.0)

    rush_cv = metrics.get("rushing", {}).get("cv_mae")
    rec_cv = metrics.get("receiving", {}).get("cv_mae")
    td_brier = metrics.get("touchdown", {}).get("cv_brier")

    rush_reliability = max(0.2, min(1.0, 1.0 - float(rush_cv or 30.0) / 50.0))
    rec_reliability = max(0.2, min(1.0, 1.0 - float(rec_cv or 30.0) / 50.0))
    td_reliability = max(0.2, min(1.0, 1.0 - float(td_brier or 0.2) / 0.30))

    rush_projection = pct("projected_rushing_yards")
    rush_workload = pct("carries_avg_3")
    rush_stability = stability("carries_avg_3", "carries_avg_5")
    rush_matchup = pct("opp_rush_yards_allowed_avg_4")

    rec_projection = pct("projected_receiving_yards")
    rec_workload = pct("targets_avg_3")
    rec_stability = stability("targets_avg_3", "targets_avg_5")
    rec_matchup = pct("opp_rec_yards_allowed_avg_4")

    td_projection = pct("touchdown_probability")
    td_workload = pct("opportunities_avg_3")
    td_stability = stability("opportunities_avg_3", "opportunities_avg_5")
    td_matchup = pct("opp_td_allowed_avg_4")

    out["rush_edge_score"] = (
        100.0
        * (
            0.35 * rush_projection
            + 0.22 * rush_workload
            + 0.18 * rush_stability
            + 0.20 * rush_matchup
            + 0.05 * rush_reliability
        )
    ).clip(0, 100)

    out["receiving_edge_score"] = (
        100.0
        * (
            0.35 * rec_projection
            + 0.22 * rec_workload
            + 0.18 * rec_stability
            + 0.20 * rec_matchup
            + 0.05 * rec_reliability
        )
    ).clip(0, 100)

    out["td_edge_score"] = (
        100.0
        * (
            0.42 * td_projection
            + 0.20 * td_workload
            + 0.13 * td_stability
            + 0.20 * td_matchup
            + 0.05 * td_reliability
        )
    ).clip(0, 100)

    out["rush_matchup_score"] = (100.0 * rush_matchup).clip(0, 100)
    out["receiving_matchup_score"] = (100.0 * rec_matchup).clip(0, 100)
    out["td_matchup_score"] = (100.0 * td_matchup).clip(0, 100)
    return out


def evaluate_history(stats: pd.DataFrame, projection_week: int) -> dict:
    history_dir = SITE_DATA_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    evaluated = []

    for path in sorted(history_dir.glob("*.json")):
        try:
            saved = json.loads(path.read_text())
        except Exception:
            continue

        season = int(saved.get("season", 0))
        week = int(saved.get("week", 0))
        if season != CURRENT_SEASON or week >= projection_week:
            continue

        actual = stats[(stats["season"] == season) & (stats["week"] == week)].copy()
        if actual.empty:
            continue

        actual["actual_td"] = (
            pd.to_numeric(actual.get("rushing_tds", 0), errors="coerce").fillna(0)
            + pd.to_numeric(actual.get("receiving_tds", 0), errors="coerce").fillna(0)
            > 0
        ).astype(int)
        actual_by_player = actual.set_index("player_id")

        for row in saved.get("players", []):
            pid = row.get("player_id")
            if pid not in actual_by_player.index:
                continue

            a = actual_by_player.loc[pid]
            if isinstance(a, pd.DataFrame):
                a = a.iloc[0]

            projected_rush = float(row.get("rushing_yards", 0))
            projected_rec = float(row.get("receiving_yards", 0))
            actual_rush = float(a.get("rushing_yards", 0))
            actual_rec = float(a.get("receiving_yards", 0))
            td_prob = float(row.get("td_probability", 0)) / 100.0
            actual_td = int(a.get("actual_td", 0))

            evaluated.append(
                {
                    "season": season,
                    "week": week,
                    "player": row.get("player"),
                    "position": row.get("position"),
                    "team": row.get("team"),
                    "projected_rushing_yards": projected_rush,
                    "actual_rushing_yards": actual_rush,
                    "rush_error": abs(projected_rush - actual_rush),
                    "projected_receiving_yards": projected_rec,
                    "actual_receiving_yards": actual_rec,
                    "rec_error": abs(projected_rec - actual_rec),
                    "td_probability": round(td_prob * 100, 1),
                    "td_prob_decimal": td_prob,
                    "actual_td": actual_td,
                    "recent_carries": float(row.get("recent_carries", 0)),
                    "recent_targets": float(row.get("recent_targets", 0)),
                }
            )

    if not evaluated:
        return {
            "graded_predictions": 0,
            "graded_weeks": 0,
            "weeks": [],
            "rushing_mae": None,
            "receiving_mae": None,
            "td_brier": None,
            "weekly_results": [],
            "note": "Weekly grading will appear after an archived prediction week has completed.",
        }

    frame = pd.DataFrame(evaluated)
    rush = frame[frame["recent_carries"] >= 2]
    rec = frame[frame["recent_targets"] >= 1.5]
    td = frame[(frame["recent_carries"] + frame["recent_targets"]) >= 3]

    weekly_results = []
    for week in sorted((int(x) for x in frame["week"].unique()), reverse=True):
        wf = frame[frame["week"] == week].copy()
        wrush = wf[wf["recent_carries"] >= 2]
        wrec = wf[wf["recent_targets"] >= 1.5]
        wtd = wf[(wf["recent_carries"] + wf["recent_targets"]) >= 3]

        wf["display_projection"] = wf[
            ["projected_rushing_yards", "projected_receiving_yards"]
        ].max(axis=1)
        samples = (
            wf.sort_values("display_projection", ascending=False)
            .head(6)
            .to_dict("records")
        )

        weekly_results.append(
            {
                "season": CURRENT_SEASON,
                "week": week,
                "graded_players": int(len(wf)),
                "rushing_mae": round(float(wrush["rush_error"].mean()), 2)
                if not wrush.empty
                else None,
                "receiving_mae": round(float(wrec["rec_error"].mean()), 2)
                if not wrec.empty
                else None,
                "td_brier": round(
                    float(((wtd["td_prob_decimal"] - wtd["actual_td"]) ** 2).mean()),
                    4,
                )
                if not wtd.empty
                else None,
                "sample_predictions": [
                    {
                        "player": r["player"],
                        "position": r["position"],
                        "team": r["team"],
                        "projected_rushing_yards": round(
                            float(r["projected_rushing_yards"]), 1
                        ),
                        "actual_rushing_yards": round(
                            float(r["actual_rushing_yards"]), 1
                        ),
                        "projected_receiving_yards": round(
                            float(r["projected_receiving_yards"]), 1
                        ),
                        "actual_receiving_yards": round(
                            float(r["actual_receiving_yards"]), 1
                        ),
                        "td_probability": round(float(r["td_probability"]), 1),
                        "actual_td": bool(r["actual_td"]),
                    }
                    for r in samples
                ],
            }
        )

    return {
        "graded_predictions": int(len(frame)),
        "graded_weeks": int(frame["week"].nunique()),
        "weeks": sorted(int(x) for x in frame["week"].unique()),
        "rushing_mae": round(float(rush["rush_error"].mean()), 2)
        if not rush.empty
        else None,
        "receiving_mae": round(float(rec["rec_error"].mean()), 2)
        if not rec.empty
        else None,
        "td_brier": round(
            float(((td["td_prob_decimal"] - td["actual_td"]) ** 2).mean()), 4
        )
        if not td.empty
        else None,
        "weekly_results": weekly_results,
    }

def main():
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    stats = load_player_stats(TRAINING_SEASONS, refresh=True)
    stats = stats[stats["season"].isin(TRAINING_SEASONS)].copy()
    schedules = load_schedules(refresh=True)
    stats = attach_schedule_context(stats, schedules)
    current = stats[stats["season"] == CURRENT_SEASON]
    if current.empty:
        raise RuntimeError(f"No {CURRENT_SEASON} player stats found upstream.")

    completed_week = int(pd.to_numeric(current["week"], errors="coerce").max())
    player_context = current_season_player_context(
        stats, CURRENT_SEASON, completed_week
    )
    projection_week, opponents, home_games = next_week_context(
        schedules, CURRENT_SEASON, completed_week
    )

    training = make_training_frame(stats)
    bundle = fit_models(training)

    features = latest_player_features(stats)
    latest_current = features[features["season"] == CURRENT_SEASON].copy()
    latest_current = attach_matchup_features(
        latest_current, stats, opponents, home_games
    )
    latest_current["projection_week"] = projection_week
    preds = predict(bundle, latest_current)

    role = (
        (preds["carries_avg_3"] >= 2)
        | (preds["targets_avg_3"] >= 1.5)
        | (preds["projected_rushing_yards"] >= 8)
        | (preds["projected_receiving_yards"] >= 8)
    )
    preds = preds[role & (preds["opponent"] != "TBD")].copy()
    preds = add_edge_scores(preds, bundle.metrics)

    rows = []
    for _, r in preds.sort_values(
        ["projected_rushing_yards", "projected_receiving_yards"],
        ascending=False,
    ).iterrows():
        player_id = str(r["player_id"])
        context = player_context.get(player_id, {})
        rows.append(
            {
                "player_id": player_id,
                "player": str(r["player_display_name"]),
                "team": str(r["recent_team"]),
                "opponent": str(r["opponent"]),
                "position": str(r["position"]),
                "week": int(r["projection_week"]),
                "rushing_yards": round(float(r["projected_rushing_yards"]), 1),
                "receiving_yards": round(float(r["projected_receiving_yards"]), 1),
                "td_probability": round(float(r["touchdown_probability"]) * 100, 1),
                "recent_carries": round(float(r.get("carries_avg_3", 0)), 1),
                "recent_carries_5": round(float(r.get("carries_avg_5", 0)), 1),
                "recent_targets": round(float(r.get("targets_avg_3", 0)), 1),
                "recent_targets_5": round(float(r.get("targets_avg_5", 0)), 1),
                "recent_rush_yards": round(float(r.get("rushing_yards_avg_3", 0)), 1),
                "recent_rec_yards": round(float(r.get("receiving_yards_avg_3", 0)), 1),
                "rush_edge_score": round(float(r.get("rush_edge_score", 0)), 1),
                "receiving_edge_score": round(float(r.get("receiving_edge_score", 0)), 1),
                "td_edge_score": round(float(r.get("td_edge_score", 0)), 1),
                "rush_matchup_score": round(float(r.get("rush_matchup_score", 0)), 1),
                "receiving_matchup_score": round(float(r.get("receiving_matchup_score", 0)), 1),
                "td_matchup_score": round(float(r.get("td_matchup_score", 0)), 1),
                "opp_rush_def_rank": int(r.get("opp_rush_def_rank", 0)),
                "opp_rec_def_rank": int(r.get("opp_rec_def_rank", 0)),
                "opp_def_rank_total": int(r.get("opp_def_rank_total", 0)),
                "season_context": context,
            }
        )

    payload = {
        "season": CURRENT_SEASON,
        "week": projection_week,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "nflverse",
        "players": rows,
    }

    history_dir = SITE_DATA_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"{CURRENT_SEASON}_week_{projection_week:02d}.json"

    (SITE_DATA_DIR / "predictions.json").write_text(json.dumps(payload, indent=2))
    history_path.write_text(json.dumps(payload, indent=2))
    (SITE_DATA_DIR / "model_metrics.json").write_text(
        json.dumps(bundle.metrics, indent=2)
    )
    performance = evaluate_history(stats, projection_week)
    (SITE_DATA_DIR / "performance.json").write_text(
        json.dumps(performance, indent=2)
    )

    joblib.dump(bundle, MODELS_DIR / "model_bundle.joblib")
    print(
        f"Wrote {len(rows)} player projections for "
        f"{CURRENT_SEASON} week {projection_week}."
    )


if __name__ == "__main__":
    main()
