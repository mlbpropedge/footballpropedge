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
DERIVED_STATS = [
    "opportunities",
    "touchdown",
    "yards_per_carry",
    "yards_per_target",
    "catch_rate",
    "team_rush_share",
    "team_target_share",
    "target_share",
    "air_yards_share",
    "wopr",
]
DEFENSE_FEATURES = [
    "opp_rush_yards_allowed_avg_4",
    "opp_rec_yards_allowed_avg_4",
    "opp_td_allowed_avg_4",
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

    required = ["player_id", "player_display_name", "position", "recent_team", "season", "week"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Required column missing: {c}")

    for c in BASE_STATS + ["target_share", "air_yards_share", "wopr"]:
        _col(df, c, 0.0)
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    if "opponent_team" not in df.columns:
        df["opponent_team"] = ""

    # QBs matter for rushing projections (e.g. designed runs/scrambles).
    df = df[df["position"].isin(["QB", "RB", "WR", "TE", "FB"])].copy()

    df["touchdown"] = ((df["rushing_tds"] + df["receiving_tds"]) > 0).astype(int)
    df["opportunities"] = df["carries"] + df["targets"]
    df["yards_per_carry"] = np.where(
        df["carries"] > 0, df["rushing_yards"] / df["carries"], np.nan
    )
    df["yards_per_target"] = np.where(
        df["targets"] > 0, df["receiving_yards"] / df["targets"], np.nan
    )
    df["catch_rate"] = np.where(
        df["targets"] > 0, df["receptions"] / df["targets"], np.nan
    )

    team_keys = ["season", "week", "recent_team"]
    team_carries = df.groupby(team_keys)["carries"].transform("sum")
    team_targets = df.groupby(team_keys)["targets"].transform("sum")
    df["team_rush_share"] = (df["carries"] / team_carries.replace(0, np.nan)).fillna(0.0)
    df["team_target_share"] = (df["targets"] / team_targets.replace(0, np.nan)).fillna(0.0)

    return df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


def _opponent_history(raw: pd.DataFrame) -> pd.DataFrame:
    usable = raw[raw["opponent_team"].astype(str).str.len() > 0].copy()
    if usable.empty:
        return pd.DataFrame(
            columns=["season", "week", "opponent_team"] + DEFENSE_FEATURES
        )

    weekly = (
        usable.groupby(["season", "week", "opponent_team"], as_index=False)
        .agg(
            opp_rush_yards_allowed=("rushing_yards", "sum"),
            opp_rec_yards_allowed=("receiving_yards", "sum"),
            opp_td_allowed=("touchdown", "sum"),
        )
        .sort_values(["opponent_team", "season", "week"])
    )

    for source, out_col in [
        ("opp_rush_yards_allowed", "opp_rush_yards_allowed_avg_4"),
        ("opp_rec_yards_allowed", "opp_rec_yards_allowed_avg_4"),
        ("opp_td_allowed", "opp_td_allowed_avg_4"),
    ]:
        shifted = weekly.groupby("opponent_team")[source].shift(1)
        weekly[out_col] = (
            shifted.groupby(weekly["opponent_team"])
            .rolling(4, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    return weekly[["season", "week", "opponent_team"] + DEFENSE_FEATURES]


def add_history_features(df: pd.DataFrame) -> pd.DataFrame:
    raw = normalize_player_stats(df)
    out = raw.copy()
    group = out.groupby("player_id", group_keys=False)

    rolling_stats = BASE_STATS + DERIVED_STATS
    for stat in rolling_stats:
        shifted = group[stat].shift(1)
        for window in ROLL_WINDOWS:
            out[f"{stat}_avg_{window}"] = (
                shifted.groupby(out["player_id"])
                .rolling(window, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
            )

    defense = _opponent_history(raw)
    out = out.merge(defense, on=["season", "week", "opponent_team"], how="left")

    out["games_prior"] = group.cumcount()
    out["season_week_index"] = pd.to_numeric(out["week"], errors="coerce").fillna(0)
    for col in DEFENSE_FEATURES:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def feature_columns() -> list[str]:
    cols = ["games_prior", "season_week_index"] + DEFENSE_FEATURES
    for stat in BASE_STATS + DERIVED_STATS:
        for window in ROLL_WINDOWS:
            cols.append(f"{stat}_avg_{window}")
    return cols


def make_training_frame(stats: pd.DataFrame) -> pd.DataFrame:
    df = add_history_features(stats)
    return df[df["games_prior"] >= 2].copy()


def latest_player_features(stats: pd.DataFrame) -> pd.DataFrame:
    raw = normalize_player_stats(stats)
    latest = (
        raw.sort_values(["season", "week"])
        .groupby("player_id", as_index=False)
        .tail(1)
        .copy()
    )

    for stat in BASE_STATS + DERIVED_STATS:
        for window in ROLL_WINDOWS:
            rolled = raw.groupby("player_id")[stat].rolling(window, min_periods=1).mean()
            rolled = rolled.groupby(level=0).tail(1).droplevel(1)
            latest[f"{stat}_avg_{window}"] = latest["player_id"].map(rolled)

    sizes = raw.groupby("player_id").size()
    latest["games_prior"] = latest["player_id"].map(sizes).astype(float)
    latest["season_week_index"] = (
        pd.to_numeric(latest["week"], errors="coerce").fillna(0) + 1
    )
    for col in DEFENSE_FEATURES:
        latest[col] = 0.0
    return latest


def latest_defense_features(stats: pd.DataFrame) -> pd.DataFrame:
    raw = normalize_player_stats(stats)
    usable = raw[raw["opponent_team"].astype(str).str.len() > 0].copy()
    if usable.empty:
        return pd.DataFrame(columns=["def_team"] + DEFENSE_FEATURES)

    weekly = (
        usable.groupby(["season", "week", "opponent_team"], as_index=False)
        .agg(
            opp_rush_yards_allowed=("rushing_yards", "sum"),
            opp_rec_yards_allowed=("receiving_yards", "sum"),
            opp_td_allowed=("touchdown", "sum"),
        )
        .sort_values(["opponent_team", "season", "week"])
    )

    rows = []
    for team, grp in weekly.groupby("opponent_team"):
        tail = grp.tail(4)
        rows.append(
            {
                "def_team": team,
                "opp_rush_yards_allowed_avg_4": float(tail["opp_rush_yards_allowed"].mean()),
                "opp_rec_yards_allowed_avg_4": float(tail["opp_rec_yards_allowed"].mean()),
                "opp_td_allowed_avg_4": float(tail["opp_td_allowed"].mean()),
            }
        )
    return pd.DataFrame(rows)
