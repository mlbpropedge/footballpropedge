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
    "team_carries",
    "team_targets",
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
    "opp_pos_rush_yards_allowed_avg_4",
    "opp_pos_rec_yards_allowed_avg_4",
    "opp_pos_td_allowed_avg_4",
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
    df["team_carries"] = team_carries.astype(float)
    df["team_targets"] = team_targets.astype(float)

    return df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


def _opponent_history(raw: pd.DataFrame) -> pd.DataFrame:
    usable = raw[raw["opponent_team"].astype(str).str.len() > 0].copy()
    if usable.empty:
        return pd.DataFrame(
            columns=["season", "week", "opponent_team", "position"] + DEFENSE_FEATURES
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

    for source in ["opp_rush_yards_allowed", "opp_rec_yards_allowed", "opp_td_allowed"]:
        shifted = weekly.groupby("opponent_team")[source].shift(1)
        for window in (2, 4, 8):
            weekly[f"{source}_avg_{window}"] = (
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
    weekly["opp_rush_form_trend"] = weekly["opp_rush_yards_allowed_avg_2"] - weekly["opp_rush_yards_allowed_avg_8"]
    weekly["opp_rec_form_trend"] = weekly["opp_rec_yards_allowed_avg_2"] - weekly["opp_rec_yards_allowed_avg_8"]

    positional = (
        usable.groupby(["season", "week", "opponent_team", "position"], as_index=False)
        .agg(
            pos_rush=("rushing_yards", "sum"),
            pos_rec=("receiving_yards", "sum"),
            pos_td=("touchdown", "sum"),
        )
        .sort_values(["opponent_team", "position", "season", "week"])
    )
    for source, dest in [
        ("pos_rush", "opp_pos_rush_yards_allowed_avg_4"),
        ("pos_rec", "opp_pos_rec_yards_allowed_avg_4"),
        ("pos_td", "opp_pos_td_allowed_avg_4"),
    ]:
        shifted = positional.groupby(["opponent_team", "position"])[source].shift(1)
        positional[dest] = (
            shifted.groupby([positional["opponent_team"], positional["position"]])
            .rolling(4, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
        )

    overall_cols = [
        "season", "week", "opponent_team",
        "opp_rush_yards_allowed_avg_2","opp_rush_yards_allowed_avg_4","opp_rush_yards_allowed_avg_8",
        "opp_rec_yards_allowed_avg_2","opp_rec_yards_allowed_avg_4","opp_rec_yards_allowed_avg_8",
        "opp_td_allowed_avg_2","opp_td_allowed_avg_4","opp_td_allowed_avg_8",
        "opp_opportunities_allowed_avg_4","opp_rush_form_trend","opp_rec_form_trend",
    ]
    pos_cols = [
        "season","week","opponent_team","position",
        "opp_pos_rush_yards_allowed_avg_4",
        "opp_pos_rec_yards_allowed_avg_4",
        "opp_pos_td_allowed_avg_4",
    ]
    return positional[pos_cols].merge(weekly[overall_cols], on=["season","week","opponent_team"], how="left")


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
    out = out.merge(defense, on=["season", "week", "opponent_team", "position"], how="left")

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
        return pd.DataFrame(columns=["def_team", "position"] + DEFENSE_FEATURES)

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
    positional = (
        usable.groupby(["season","week","opponent_team","position"],as_index=False)
        .agg(pos_rush=("rushing_yards","sum"),pos_rec=("receiving_yards","sum"),pos_td=("touchdown","sum"))
        .sort_values(["opponent_team","position","season","week"])
    )

    rows = []
    positions = sorted(str(x) for x in usable["position"].dropna().unique())
    for team, grp in weekly.groupby("opponent_team"):
        def mean_tail(col, n):
            return float(grp[col].tail(n).mean())
        base = {
            "opp_rush_yards_allowed_avg_2": mean_tail("opp_rush_yards_allowed",2),
            "opp_rush_yards_allowed_avg_4": mean_tail("opp_rush_yards_allowed",4),
            "opp_rush_yards_allowed_avg_8": mean_tail("opp_rush_yards_allowed",8),
            "opp_rec_yards_allowed_avg_2": mean_tail("opp_rec_yards_allowed",2),
            "opp_rec_yards_allowed_avg_4": mean_tail("opp_rec_yards_allowed",4),
            "opp_rec_yards_allowed_avg_8": mean_tail("opp_rec_yards_allowed",8),
            "opp_td_allowed_avg_2": mean_tail("opp_td_allowed",2),
            "opp_td_allowed_avg_4": mean_tail("opp_td_allowed",4),
            "opp_td_allowed_avg_8": mean_tail("opp_td_allowed",8),
            "opp_opportunities_allowed_avg_4": mean_tail("opp_opportunities_allowed",4),
        }
        base["opp_rush_form_trend"] = base["opp_rush_yards_allowed_avg_2"] - base["opp_rush_yards_allowed_avg_8"]
        base["opp_rec_form_trend"] = base["opp_rec_yards_allowed_avg_2"] - base["opp_rec_yards_allowed_avg_8"]
        for pos in positions:
            pg = positional[(positional["opponent_team"]==team)&(positional["position"].astype(str)==pos)]
            row={"def_team":team,"position":pos,**base}
            row["opp_pos_rush_yards_allowed_avg_4"]=float(pg["pos_rush"].tail(4).mean()) if not pg.empty else 0.0
            row["opp_pos_rec_yards_allowed_avg_4"]=float(pg["pos_rec"].tail(4).mean()) if not pg.empty else 0.0
            row["opp_pos_td_allowed_avg_4"]=float(pg["pos_td"].tail(4).mean()) if not pg.empty else 0.0
            rows.append(row)
    return pd.DataFrame(rows)
