"""Player availability and usage context from free nflverse feeds.

Everything here is best-effort. A missing or malformed feed returns empty
context so a projection run never fails because an optional source is down.
"""
from __future__ import annotations

import pandas as pd

from .config import CACHE_DIR, INJURIES_URL, PLAYERS_URL, SNAP_COUNTS_URL
from .data import load_weekly_roster, read_parquet_url

# Official game-status designations from the weekly injury report.
REPORT_STATUSES = {"Out", "Doubtful", "Questionable"}
UNAVAILABLE_REPORT = {"Out"}

# Weekly roster status codes that mean the player cannot play this week.
ROSTER_UNAVAILABLE = {
    "RES": "Reserve list",
    "INA": "Inactive",
    "CUT": "Released",
    "RET": "Retired",
    "EXE": "Exempt list",
    "SUS": "Suspended",
}


def _safe(loader, label: str) -> pd.DataFrame:
    try:
        frame = loader()
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    except Exception as exc:  # optional feed: warn and keep publishing
        print(f"Warning: {label} unavailable: {exc}")
        return pd.DataFrame()


def load_injuries(season: int, refresh: bool = True) -> pd.DataFrame:
    return _safe(
        lambda: read_parquet_url(
            INJURIES_URL.format(season=season),
            CACHE_DIR / "injuries" / f"{season}.parquet",
            refresh=refresh,
        ),
        "injury report",
    )


def load_snap_counts(season: int, refresh: bool = True) -> pd.DataFrame:
    return _safe(
        lambda: read_parquet_url(
            SNAP_COUNTS_URL.format(season=season),
            CACHE_DIR / "snap_counts" / f"{season}.parquet",
            refresh=refresh,
        ),
        "snap counts",
    )


def load_player_ids(refresh: bool = True) -> pd.DataFrame:
    return _safe(
        lambda: read_parquet_url(
            PLAYERS_URL, CACHE_DIR / "players" / "players.parquet", refresh=refresh
        ),
        "player id map",
    )


def load_roster(season: int, refresh: bool = True) -> pd.DataFrame:
    return _safe(lambda: load_weekly_roster(season, refresh=refresh), "weekly roster")


def _week_rows(frame: pd.DataFrame, season: int, week: int, exact: bool) -> tuple[pd.DataFrame, int | None]:
    """Rows for the projection week, or the latest earlier week when allowed."""
    needed = {"season", "week"}
    if frame.empty or not needed.issubset(frame.columns):
        return pd.DataFrame(), None
    rows = frame.copy()
    rows["season"] = pd.to_numeric(rows["season"], errors="coerce")
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows = rows[rows["season"] == season]
    if "game_type" in rows.columns:
        regular = rows["game_type"].astype(str).eq("REG")
        if regular.any():
            rows = rows[regular]
    if exact:
        rows = rows[rows["week"] == week]
        return rows, (week if not rows.empty else None)
    rows = rows[rows["week"] <= week]
    if rows.empty:
        return rows, None
    latest = int(rows["week"].max())
    return rows[rows["week"] == latest], latest


def _text(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def player_availability(
    injuries: pd.DataFrame, roster: pd.DataFrame, season: int, week: int
) -> dict:
    """Return {availability, teams, info} for the projection week.

    Injury designations only count when they were filed for this exact week,
    so last week's report can never rule a player out of this week's slate.
    """
    out: dict[str, dict] = {}
    report, report_week = _week_rows(injuries, season, week, exact=True)
    if not report.empty and {"gsis_id", "report_status"}.issubset(report.columns):
        for _, row in report.iterrows():
            pid, status = _text(row.get("gsis_id")), _text(row.get("report_status"))
            if not pid or status not in REPORT_STATUSES:
                continue
            out[pid] = {
                "status": status,
                "detail": _text(row.get("report_primary_injury")),
                "unavailable": status in UNAVAILABLE_REPORT,
                "source": "injury report",
            }

    roster_rows, roster_week = _week_rows(roster, season, week, exact=False)
    teams: dict[str, str] = {}
    if not roster_rows.empty and "gsis_id" in roster_rows.columns:
        for _, row in roster_rows.iterrows():
            pid = _text(row.get("gsis_id"))
            if not pid:
                continue
            team = _text(row.get("team"))
            if team:
                teams[pid] = team
            code = (_text(row.get("status")) or "").upper()
            # Game-day inactives only apply to the week they were announced.
            if code == "INA" and roster_week != week:
                continue
            if code in ROSTER_UNAVAILABLE and not out.get(pid, {}).get("unavailable"):
                out[pid] = {
                    "status": ROSTER_UNAVAILABLE[code],
                    "detail": out.get(pid, {}).get("detail"),
                    "unavailable": True,
                    "source": "weekly roster",
                }

    info = {
        "injury_report_week": report_week,
        "injury_designations": int(sum(1 for v in out.values() if v["source"] == "injury report")),
        "roster_week": roster_week,
        "roster_players": len(teams),
    }
    return {"availability": out, "teams": teams, "info": info}


def snap_share_context(
    snaps: pd.DataFrame, players: pd.DataFrame, season: int, through_week: int
) -> dict[str, dict]:
    """Offensive snap share (percent) by player, keyed by nflverse gsis id."""
    needed = {"pfr_player_id", "offense_pct", "week", "season"}
    if snaps.empty or players.empty or not needed.issubset(snaps.columns):
        return {}
    if not {"gsis_id", "pfr_id"}.issubset(players.columns):
        return {}
    ids = players[["gsis_id", "pfr_id"]].dropna().drop_duplicates("pfr_id")
    rows = snaps.copy()
    rows["season"] = pd.to_numeric(rows["season"], errors="coerce")
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows = rows[(rows["season"] == season) & (rows["week"] <= through_week)]
    if "game_type" in rows.columns:
        rows = rows[rows["game_type"].astype(str).eq("REG")]
    rows = rows.merge(ids, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    if rows.empty:
        return {}
    rows["offense_pct"] = pd.to_numeric(rows["offense_pct"], errors="coerce").fillna(0.0)
    # nflverse stores shares as 0-1; tolerate percent-scaled feeds too.
    if rows["offense_pct"].max() > 1.5:
        rows["offense_pct"] = rows["offense_pct"] / 100.0

    context = {}
    for pid, group in rows.groupby("gsis_id"):
        group = group.sort_values("week").drop_duplicates("week", keep="last")
        pct = group["offense_pct"] * 100.0
        context[str(pid)] = {
            "snap_share_3": round(float(pct.tail(3).mean()), 1),
            "snap_share_season": round(float(pct.mean()), 1),
            "by_week": {int(w): round(float(p), 1) for w, p in zip(group["week"], pct)},
        }
    return context


def games_missed(stats: pd.DataFrame, season: int, through_week: int) -> dict[str, dict]:
    """How many of his team's completed games each player has missed in a row.

    Counts team games (not calendar weeks), so bye weeks are never mistaken
    for absences.
    """
    needed = {"player_id", "season", "week"}
    if stats.empty or not needed.issubset(stats.columns):
        return {}
    team_col = "recent_team" if "recent_team" in stats.columns else "team"
    if team_col not in stats.columns:
        return {}
    rows = stats.copy()
    rows["season"] = pd.to_numeric(rows["season"], errors="coerce")
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows = rows[(rows["season"] == season) & (rows["week"] <= through_week)]
    if rows.empty:
        return {}
    team_weeks = rows.groupby(team_col)["week"].apply(lambda s: sorted(set(int(w) for w in s)))
    out = {}
    for pid, group in rows.sort_values("week").groupby("player_id"):
        last = group.iloc[-1]
        team = last[team_col]
        last_week = int(last["week"])
        later = [w for w in team_weeks.get(team, []) if w > last_week]
        out[str(pid)] = {"last_played_week": last_week, "games_missed": len(later)}
    return out
