import json

from scripts.build_seo_pages import build, slugify


def _player(pid, name, team="KC", pos="RB", **extra):
    base = {
        "player_id": pid, "player": name, "team": team, "opponent": "LAC", "position": pos,
        "week": 6, "game_start": "2026-10-18T16:25:00-04:00", "rushing_yards": 80.0,
        "receiving_yards": 20.0, "td_probability": 45.0, "rushing_range_80": [60, 120],
        "receiving_range_80": [5, 40], "opp_rush_def_rank": 10, "opp_rec_def_rank": 5,
        "opp_def_rank_total": 32, "snap_share_3": 70.0,
        "season_context": {"games_played": 1, "season_rushing_avg": 90, "season_carries_avg": 18,
                           "season_receiving_avg": 12, "season_targets_avg": 3,
                           "recent_games": [{"week": 5, "rushing_yards": 90, "carries": 18,
                                             "receiving_yards": 12, "targets": 3, "touchdowns": 1,
                                             "snap_pct": None}]},
    }
    base.update(extra)
    return base


def _write(root, players, ruled_out=(), week=6):
    (root / "data").mkdir(exist_ok=True)
    (root / "data/predictions.json").write_text(json.dumps({
        "season": 2026, "week": week, "generated_at": "2026-10-17T11:20:20+00:00",
        "players": list(players), "ruled_out": list(ruled_out)}))


def test_slugify_handles_punctuation():
    assert slugify("Ja'Marr Chase") == "jamarr-chase"
    assert slugify("Kenneth Walker III") == "kenneth-walker-iii"
    assert slugify("A.J. Brown") == "aj-brown"


def test_pages_sitemap_and_stable_slugs(tmp_path):
    _write(tmp_path, [_player("00-1", "Mike Williams"), _player("00-2", "Mike Williams", team="NYJ", pos="WR"),
                      _player("00-3", "<Bad> Name")],
           ruled_out=[{"player_id": "00-9", "player": "Hurt Guy", "team": "KC", "opponent": "LAC",
                       "position": "WR", "status": "Out", "detail": "Ankle"}])
    stats = build(tmp_path)
    assert stats["player_pages"] == 4
    first = (tmp_path / "players/mike-williams.html").read_text()
    assert "Mike Williams Week 6 Projection vs LAC" in first
    assert (tmp_path / "players/mike-williams-2.html").exists() or any(
        p.name.startswith("mike-williams-") for p in (tmp_path / "players").iterdir())
    assert "&lt;Bad&gt;" in (tmp_path / "players/bad-name.html").read_text()
    assert "ruled" in (tmp_path / "players/hurt-guy.html").read_text().lower() or "not projected" in (
        tmp_path / "players/hurt-guy.html").read_text()
    for name in ("rushing-yards", "receiving-yards", "anytime-touchdown"):
        assert (tmp_path / f"projections/{name}.html").exists()
    sitemap = (tmp_path / "sitemap.xml").read_text()
    assert sitemap.count("<url>") == stats["indexed_urls"]

    # Next week: player 00-1 drops off, 00-2 stays. Slugs must not move.
    index = json.loads((tmp_path / "data/seo_index.json").read_text())
    slug_2 = index["players"]["00-2"]["slug"]
    _write(tmp_path, [_player("00-2", "Mike Williams", team="NYJ", pos="WR", week=7)], week=7)
    build(tmp_path)
    index = json.loads((tmp_path / "data/seo_index.json").read_text())
    assert index["players"]["00-2"]["slug"] == slug_2
    stale = (tmp_path / "players/mike-williams.html").read_text()
    assert "noindex" in stale and "not on the Week 7 slate" in stale
    assert "players/mike-williams.html" not in (tmp_path / "sitemap.xml").read_text()
