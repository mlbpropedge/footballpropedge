from __future__ import annotations

import numpy as np
import pandas as pd

ROLL_WINDOWS = (3, 5, 8)
BASE_STATS = [
    "carries",
    "rushing_yards",
    "rushing_tds",
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
]


def _col(df: pd.DataFrame, name: str, default=0.0):
    if name not in df.columns:
        df[name] = default


def normalize_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    aliases = {
        "player_display_name": ["player_display_name", "player_name"],
        "recent_team": ["recent_team", "team"],
    }
    for target, candidates in aliases.items():
        if target not in df.columns:
            for candidate in candidates:
                if candidate in df.columns:
                    df[target] = df[candidate]
                    break
    for c in ["player_id", "player_display_name", "position", "recent_team", "season", "week"]:
        if c not in df.columns:
            raise ValueError(f"Required column missing: {c}")
    for c in BASE_STATS:
        _col(df, c, 0.0)
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    if "fantasy_points" not in df:
        df["fantasy_points"] = 0.0
    df = df[df["position"].isin(["RB", "WR", "TE", "FB"])].copy()
    df["touchdown"] = ((df["rushing_tds"] + df["receiving_tds"]) > 0).astype(int)
    df["opportunities"] = df["carries"] + df["targets"]
    return df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


def add_history_features(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_player_stats(df)
    group = df.groupby("player_id", group_keys=False)

    for stat in BASE_STATS + ["opportunities", "touchdown"]:
        shifted = group[stat].shift(1)
        for window in ROLL_WINDOWS:
            df[f"{stat}_avg_{window}"] = (
                shifted.groupby(df["player_id"])
                .rolling(window, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
            )

    df["games_prior"] = group.cumcount()
    df["season_week_index"] = pd.to_numeric(df["week"], errors="coerce").fillna(0)
    df["rush_share_proxy"] = (
        df["carries_avg_5"] / df["opportunities_avg_5"].replace(0, np.nan)
    ).fillna(0)
    df["target_share_proxy"] = (
        df["targets_avg_5"] / df["opportunities_avg_5"].replace(0, np.nan)
    ).fillna(0)
    return df


def feature_columns() -> list[str]:
    cols = ["games_prior", "season_week_index", "rush_share_proxy", "target_share_proxy"]
    for stat in BASE_STATS + ["opportunities", "touchdown"]:
        for window in ROLL_WINDOWS:
            cols.append(f"{stat}_avg_{window}")
    return cols


def make_training_frame(stats: pd.DataFrame) -> pd.DataFrame:
    df = add_history_features(stats)
    return df[df["games_prior"] >= 2].copy()


def latest_player_features(stats: pd.DataFrame) -> pd.DataFrame:
    raw = normalize_player_stats(stats)
    latest = raw.sort_values(["season", "week"]).groupby("player_id", as_index=False).tail(1).copy()

    for stat in BASE_STATS + ["opportunities", "touchdown"]:
        for window in ROLL_WINDOWS:
            rolled = raw.groupby("player_id")[stat].rolling(window, min_periods=1).mean()
            rolled = rolled.groupby(level=0).tail(1).droplevel(1)
            latest[f"{stat}_avg_{window}"] = latest["player_id"].map(rolled)

    sizes = raw.groupby("player_id").size()
    latest["games_prior"] = latest["player_id"].map(sizes).astype(float)
    latest["season_week_index"] = pd.to_numeric(latest["week"], errors="coerce").fillna(0) + 1
    latest["rush_share_proxy"] = (
        latest["carries_avg_5"] / latest["opportunities_avg_5"].replace(0, np.nan)
    ).fillna(0)
    latest["target_share_proxy"] = (
        latest["targets_avg_5"] / latest["opportunities_avg_5"].replace(0, np.nan)
    ).fillna(0)
    return latest
