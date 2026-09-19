from __future__ import annotations

from pathlib import Path
import requests
import pandas as pd

from .config import CACHE_DIR, PLAYER_STATS_URL, ROSTER_URL, SCHEDULES_URL


def _download(url: str, cache_path: Path, timeout: int = 60) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    cache_path.write_bytes(response.content)
    return cache_path


def read_parquet_url(url: str, cache_path: Path, refresh: bool = True) -> pd.DataFrame:
    if refresh or not cache_path.exists():
        _download(url, cache_path)
    return pd.read_parquet(cache_path)


def load_player_stats(seasons: list[int], refresh: bool = True) -> pd.DataFrame:
    frames = []
    for season in seasons:
        url = PLAYER_STATS_URL.format(season=season)
        path = CACHE_DIR / "player_stats" / f"{season}.parquet"
        try:
            df = read_parquet_url(url, path, refresh=refresh)
        except Exception as exc:
            if season == max(seasons):
                print(f"Warning: current season stats unavailable: {exc}")
                continue
            raise
        if "season" not in df:
            df["season"] = season
        frames.append(df)
    if not frames:
        raise RuntimeError("No player stats were downloaded.")
    return pd.concat(frames, ignore_index=True, sort=False)


def load_weekly_roster(season: int, refresh: bool = True) -> pd.DataFrame:
    url = ROSTER_URL.format(season=season)
    path = CACHE_DIR / "rosters" / f"{season}.parquet"
    return read_parquet_url(url, path, refresh=refresh)


def load_schedules(refresh: bool = True) -> pd.DataFrame:
    path = CACHE_DIR / "schedules" / "games.parquet"
    return read_parquet_url(SCHEDULES_URL, path, refresh=refresh)
