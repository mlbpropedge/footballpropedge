from __future__ import annotations

import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import TRAINING_SEASONS, MODELS_DIR, SITE_DATA_DIR
from src.data import load_player_stats, load_schedules
from src.features import feature_columns, make_training_frame


def attach_schedule_context(stats: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    out = stats.copy()
    if "recent_team" not in out.columns:
        if "team" in out.columns:
            out["recent_team"] = out["team"]
        else:
            raise ValueError("Player stats are missing both recent_team and team columns.")
    games = schedules.copy()
    if "game_type" in games.columns:
        games = games[games["game_type"].astype(str).eq("REG")]
    home = games[["season", "week", "home_team"]].rename(columns={"home_team": "recent_team"})
    home["home_game"] = 1.0
    away = games[["season", "week", "away_team"]].rename(columns={"away_team": "recent_team"})
    away["home_game"] = 0.0
    context = pd.concat([home, away], ignore_index=True).drop_duplicates(["season", "week", "recent_team"])
    out = out.merge(context, on=["season", "week", "recent_team"], how="left", suffixes=("", "_schedule"))
    if "home_game_schedule" in out.columns:
        out["home_game"] = out["home_game_schedule"].fillna(out.get("home_game", 0.0))
        out = out.drop(columns=["home_game_schedule"])
    else:
        out["home_game"] = out.get("home_game", 0.0)
    out["home_game"] = pd.to_numeric(out["home_game"], errors="coerce").fillna(0.0)
    return out


def role_frame(df: pd.DataFrame, market: str) -> pd.DataFrame:
    if market == "rushing_yards":
        return df[(df["carries_avg_3"] >= 2.0) | (df["carries_avg_5"] >= 2.5)].copy()
    return df[(df["targets_avg_3"] >= 1.5) | (df["targets_avg_5"] >= 2.0)].copy()


def clean_x(df: pd.DataFrame) -> pd.DataFrame:
    return df[feature_columns()].replace([np.inf, -np.inf], np.nan).fillna(0.0)


def role_group(position: str, market: str) -> str:
    p = str(position).upper()
    if market == "rushing_yards":
        return "RB" if p in {"RB", "FB"} else "OTHER"
    return "WR" if p == "WR" else ("TE" if p == "TE" else "RB")


def walk_forward_residuals(frame: pd.DataFrame, base_model, market: str) -> pd.DataFrame:
    usable = role_frame(frame, market).copy()
    usable["season"] = pd.to_numeric(usable["season"], errors="coerce").astype(int)
    usable["week"] = pd.to_numeric(usable["week"], errors="coerce").astype(int)
    weeks = sorted({(int(r.season), int(r.week)) for r in usable[["season", "week"]].itertuples(index=False)})

    # Recent seasons best represent current NFL usage. Limit to the latest 28
    # eligible weeks to keep the daily workflow practical while retaining a
    # large out-of-sample calibration set.
    weeks = weeks[-28:]
    rows = []
    for season, week in weeks:
        train = usable[(usable["season"] < season) | ((usable["season"] == season) & (usable["week"] < week))]
        test = usable[(usable["season"] == season) & (usable["week"] == week)]
        if len(train) < 400 or len(test) < 12:
            continue
        model = clone(base_model)
        y_train = pd.to_numeric(train[market], errors="coerce").fillna(0.0)
        model.fit(clean_x(train), y_train)
        pred = np.clip(model.predict(clean_x(test)), 0, None)
        actual = pd.to_numeric(test[market], errors="coerce").fillna(0.0).to_numpy()
        for pos, p, a in zip(test["position"].astype(str), pred, actual):
            rows.append({
                "season": season,
                "week": week,
                "market": market,
                "role": role_group(pos, market),
                "prediction": float(p),
                "actual": float(a),
                "residual": float(a - p),
            })
    return pd.DataFrame(rows)


def interval_lookup(residuals: pd.DataFrame, market: str) -> dict:
    m = residuals[residuals["market"] == market]
    if m.empty:
        return {}
    global_q = (float(m["residual"].quantile(0.10)), float(m["residual"].quantile(0.90)))
    lookup = {"GLOBAL": global_q}
    for role, grp in m.groupby("role"):
        # Only specialize when the role has enough genuinely out-of-sample
        # observations to avoid unstable interval widths.
        if len(grp) >= 100:
            lookup[str(role)] = (float(grp["residual"].quantile(0.10)), float(grp["residual"].quantile(0.90)))
    return lookup


def main() -> None:
    predictions_path = SITE_DATA_DIR / "predictions.json"
    bundle_path = MODELS_DIR / "model_bundle.joblib"
    if not predictions_path.exists() or not bundle_path.exists():
        raise RuntimeError("Run build_predictions.py before interval calibration.")

    stats = load_player_stats(TRAINING_SEASONS, refresh=False)
    schedules = load_schedules(refresh=False)
    stats = attach_schedule_context(stats, schedules)
    frame = make_training_frame(stats)
    bundle = joblib.load(bundle_path)

    rush_res = walk_forward_residuals(frame, bundle.rushing_model, "rushing_yards")
    rec_res = walk_forward_residuals(frame, bundle.receiving_model, "receiving_yards")
    residuals = pd.concat([rush_res, rec_res], ignore_index=True)
    if residuals.empty:
        raise RuntimeError("Walk-forward calibration produced no residuals.")

    rush_lookup = interval_lookup(residuals, "rushing_yards")
    rec_lookup = interval_lookup(residuals, "receiving_yards")

    payload = json.loads(predictions_path.read_text())
    for row in payload.get("players", []):
        position = str(row.get("position", ""))
        rush_role = role_group(position, "rushing_yards")
        rec_role = role_group(position, "receiving_yards")
        rq = rush_lookup.get(rush_role, rush_lookup["GLOBAL"])
        cq = rec_lookup.get(rec_role, rec_lookup["GLOBAL"])
        rush = float(row.get("rushing_yards", 0.0))
        rec = float(row.get("receiving_yards", 0.0))
        row["rushing_range_80"] = [round(max(0.0, rush + rq[0]), 1), round(max(0.0, rush + rq[1]), 1)]
        row["receiving_range_80"] = [round(max(0.0, rec + cq[0]), 1), round(max(0.0, rec + cq[1]), 1)]

    payload["prediction_intervals"] = {
        "coverage": 0.80,
        "method": "empirical walk-forward residual quantiles",
        "leakage_safe": True,
        "calibration_samples": {
            "rushing": int(len(rush_res)),
            "receiving": int(len(rec_res)),
        },
        "role_aware_min_samples": 100,
    }
    predictions_path.write_text(json.dumps(payload, indent=2))

    history_path = SITE_DATA_DIR / "history" / f"{payload['season']}_week_{int(payload['week']):02d}.json"
    if history_path.exists():
        history_path.write_text(json.dumps(payload, indent=2))

    report = {
        "coverage": 0.80,
        "method": "weekly walk-forward; each test week trained only on earlier weeks",
        "rushing_samples": int(len(rush_res)),
        "receiving_samples": int(len(rec_res)),
        "rushing_quantiles": {k: [round(v[0], 2), round(v[1], 2)] for k, v in rush_lookup.items()},
        "receiving_quantiles": {k: [round(v[0], 2), round(v[1], 2)] for k, v in rec_lookup.items()},
    }
    (SITE_DATA_DIR / "prediction_intervals.json").write_text(json.dumps(report, indent=2))
    print(f"Added empirical 80% ranges from {len(rush_res)} rushing and {len(rec_res)} receiving walk-forward residuals.")


if __name__ == "__main__":
    main()
