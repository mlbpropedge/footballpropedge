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
    "opp_rush_yards_allowed_avg_2",
    "opp_rush_yards_allowed_avg_4",
    "opp_rush_yards_allowed_avg_8",
    "opp_rec_yards_allowed_avg_2",
    "opp_rec_yards_allowed_avg_4",
    "opp_rec_yards_allowed_avg_8",
    "opp_td_allowed_avg_2",
    "opp_td_allowed_avg_4",
    "opp_td_allowed_avg_8",
    "opp_opportunities_allowed_avg_4",
    "opp_rush_form_trend",
    "opp_rec_form_trend",
]
CONTEXT_FEATURES = ["home_game"]


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
    _col(df, "home_game", 0.0)
    df["home_game"] = pd.to_numeric(df["home_game"], errors="coerce").fillna(0.0)

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
            opp_opportunities_allowed=("opportunities", "sum"),
        )
        .sort_values(["opponent_team", "season", "week"])
    )

    sources = {
        "opp_rush_yards_allowed": "opp_rush_yards_allowed",
        "opp_rec_yards_allowed": "opp_rec_yards_allowed",
        "opp_td_allowed": "opp_td_allowed",
    }
    for source, prefix in sources.items():
        shifted = weekly.groupby("opponent_team")[source].shift(1)
        for window in (2, 4, 8):
            weekly[f"{prefix}_avg_{window}"] = (
                shifted.groupby(weekly["opponent_team"])
                .rolling(window, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
            )

    shifted_opp = weekly.groupby("opponent_team")["opp_opportunities_allowed"].shift(1)
    weekly["opp_opportunities_allowed_avg_4"] = (
        shifted_opp.groupby(weekly["opponent_team"])
        .rolling(4, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    weekly["opp_rush_form_trend"] = (
        weekly["opp_rush_yards_allowed_avg_2"]
        - weekly["opp_rush_yards_allowed_avg_8"]
    )
    weekly["opp_rec_form_trend"] = (
        weekly["opp_rec_yards_allowed_avg_2"]
        - weekly["opp_rec_yards_allowed_avg_8"]
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

    # Leakage-safe season-to-date averages: current game is excluded.
    season_group = out.groupby(["player_id", "season"], group_keys=False)
    for stat in ["rushing_yards", "receiving_yards"]:
        shifted = season_group[stat].shift(1)
        counts = season_group.cumcount().replace(0, np.nan)
        cumulative = shifted.groupby(
            [out["player_id"], out["season"]]
        ).cumsum()
        out[f"{stat}_season_avg"] = (cumulative / counts).fillna(0.0)

    defense = _opponent_history(raw)
    out = out.merge(defense, on=["season", "week", "opponent_team"], how="left")

    out["games_prior"] = group.cumcount()
    out["season_week_index"] = pd.to_numeric(out["week"], errors="coerce").fillna(0)
    for col in DEFENSE_FEATURES:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def feature_columns() -> list[str]:
    cols = [
        "games_prior",
        "season_week_index",
        "rushing_yards_season_avg",
        "receiving_yards_season_avg",
    ] + CONTEXT_FEATURES + DEFENSE_FEATURES
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

    current_season = raw.groupby("player_id")["season"].transform("max")
    season_rows = raw[raw["season"].eq(current_season)].copy()
    for stat in ["rushing_yards", "receiving_yards"]:
        season_avg = season_rows.groupby("player_id")[stat].mean()
        latest[f"{stat}_season_avg"] = latest["player_id"].map(season_avg).fillna(0.0)

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
            opp_opportunities_allowed=("opportunities", "sum"),
        )
        .sort_values(["opponent_team", "season", "week"])
    )

    rows = []
    for team, grp in weekly.groupby("opponent_team"):
        def mean_tail(col, n):
            return float(grp[col].tail(n).mean())

        rush2 = mean_tail("opp_rush_yards_allowed", 2)
        rush4 = mean_tail("opp_rush_yards_allowed", 4)
        rush8 = mean_tail("opp_rush_yards_allowed", 8)
        rec2 = mean_tail("opp_rec_yards_allowed", 2)
        rec4 = mean_tail("opp_rec_yards_allowed", 4)
        rec8 = mean_tail("opp_rec_yards_allowed", 8)
        td2 = mean_tail("opp_td_allowed", 2)
        td4 = mean_tail("opp_td_allowed", 4)
        td8 = mean_tail("opp_td_allowed", 8)

        rows.append(
            {
                "def_team": team,
                "opp_rush_yards_allowed_avg_2": rush2,
                "opp_rush_yards_allowed_avg_4": rush4,
                "opp_rush_yards_allowed_avg_8": rush8,
                "opp_rec_yards_allowed_avg_2": rec2,
                "opp_rec_yards_allowed_avg_4": rec4,
                "opp_rec_yards_allowed_avg_8": rec8,
                "opp_td_allowed_avg_2": td2,
                "opp_td_allowed_avg_4": td4,
                "opp_td_allowed_avg_8": td8,
                "opp_opportunities_allowed_avg_4": mean_tail("opp_opportunities_allowed", 4),
                "opp_rush_form_trend": rush2 - rush8,
                "opp_rec_form_trend": rec2 - rec8,
            }
        )
    return pd.DataFrame(rows)

