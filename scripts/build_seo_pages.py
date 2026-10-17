"""Build static, search-engine-friendly pages from data/predictions.json.

The main site renders everything in the browser with JavaScript, so search
engines see almost nothing. This script writes plain HTML that needs no
JavaScript:

- players/<slug>.html       one page per player (stable URL, refreshed weekly)
- players/index.html        every player on the slate, grouped by team
- projections/*.html        ranked rushing, receiving and anytime-TD tables
- sitemap.xml               every indexable page, for Google Search Console

Player URLs never change between weeks, so each page keeps building search
history. Players who drop off the slate keep a short "not on this week's
slate" page (noindex) instead of a dead link. Slugs are stored in
data/seo_index.json so they stay stable when two players share a name.

Uses the standard library only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_URL = os.environ.get("SITE_URL", "https://mlbpropedge.github.io/footballpropedge").rstrip("/")
STYLE_VERSION = "6"

TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAR": "Los Angeles Rams",
    "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints",
    "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}
RUSH_FIRST = {"RB", "QB", "FB"}

RESPONSIBLE = (
    '<aside class="responsible-use"><div class="responsible-icon" aria-hidden="true">!</div><div>'
    "<strong>Informational use only</strong><p>Football Prop Edge is for informational and entertainment "
    "purposes only. No prediction is guaranteed. If you or someone you know is struggling with a gambling "
    'problem, call or text the National Problem Gambling Helpline at <a href="tel:+18006973738">1-800-MY-RESET</a>. '
    'Free, confidential help is available 24/7. <a href="https://www.ncpgambling.org/help-treatment/" '
    'target="_blank" rel="noopener noreferrer">Get help online</a>.</p></div></aside>'
)


# ---------------------------------------------------------------- helpers
def slugify(name: str) -> str:
    text = name.lower().replace("'", "").replace("’", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "player"


def team_name(code: str | None) -> str:
    return TEAMS.get(str(code or ""), str(code or "TBD"))


def num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_kickoff(player: dict) -> str:
    start = player.get("game_start")
    if start:
        try:
            dt = datetime.fromisoformat(start)
            hour = dt.strftime("%I").lstrip("0")
            return f"{dt.strftime('%a, %b')} {dt.day}, {hour}:{dt.strftime('%M %p')} ET"
        except ValueError:
            pass
    date = player.get("game_date")
    if date:
        try:
            dt = datetime.fromisoformat(date)
            return f"{dt.strftime('%a, %b')} {dt.day}"
        except ValueError:
            return str(date)
    return "Date pending"


def fmt_range(rng) -> str | None:
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        return f"{max(0.0, num(rng[0])):.0f}–{num(rng[1]):.0f}"
    return None


def ordinal_rank(rank, total) -> str | None:
    r = int(num(rank))
    if r <= 0:
        return None
    return f"#{r} of {int(num(total, 32)) or 32}"


def page(*, title: str, description: str, canonical: str | None, depth: int, body: str,
         noindex: bool = False) -> str:
    up = "../" * depth
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    canon = f'<link rel="canonical" href="{escape(canonical)}">' if canonical else ""
    og_url = f'<meta property="og:url" content="{escape(canonical)}">' if canonical else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#09111c">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
{robots}{canon}
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:type" content="article">
{og_url}
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{up}styles.css?v={STYLE_VERSION}">
</head>
<body class="player-page">
<div class="site-shell">
<nav class="topbar"><div class="topbar-inner"><a class="brand-lockup" href="{up}index.html"><span class="brand-mark">FPE</span><span class="brand-copy"><strong>Football Prop Edge</strong><small>Weekly NFL projections</small></span></a><div class="navlinks"><a href="{up}projections/rushing-yards.html">Rushing</a><a href="{up}projections/receiving-yards.html">Receiving</a><a href="{up}projections/anytime-touchdown.html">TDs</a><a href="{up}players/index.html">Players</a></div></div></nav>
<main class="player-main seo-main">
{body}
</main>
{RESPONSIBLE}
<footer><span>Football Prop Edge</span><span>Projections are statistical estimates, not guarantees.</span></footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------- slugs
def assign_slugs(players: list[dict], index: dict) -> dict:
    """Return {player_id: slug}, keeping every slug already in the index."""
    known = index.setdefault("players", {})
    taken = {v["slug"]: pid for pid, v in known.items()}
    out = {}
    for p in players:
        pid = str(p["player_id"])
        if pid in known:
            out[pid] = known[pid]["slug"]
            continue
        base = slugify(p["player"])
        slug = base if base not in taken else f"{base}-{re.sub(r'[^0-9a-z]', '', pid.lower())[-4:]}"
        n = 2
        while slug in taken:
            slug = f"{base}-{n}"
            n += 1
        taken[slug] = pid
        out[pid] = slug
    return out


# ---------------------------------------------------------------- player pages
def player_summary(p: dict, week: int) -> tuple[str, str, list[str]]:
    """Return (title, meta description, intro paragraphs)."""
    name, pos = p["player"], p.get("position", "")
    opp, team = p.get("opponent", ""), p.get("team", "")
    rush, rec, td = num(p.get("rushing_yards")), num(p.get("receiving_yards")), num(p.get("td_probability"))
    rush_first = pos in RUSH_FIRST
    if rush_first:
        stat_title = "Rushing Yards & TD Odds"
        lead = f"{rush:.1f} rushing yards" + (f" and {rec:.1f} receiving yards" if rec >= 5 else "")
    else:
        stat_title = "Receiving Yards & TD Odds"
        lead = f"{rec:.1f} receiving yards" + (f" and {rush:.1f} rushing yards" if rush >= 5 else "")
    title = f"{name} Week {week} Projection vs {opp}: {stat_title}"
    desc = (f"{name} ({pos}, {team}) is projected for {lead} vs the {team_name(opp)} in Week {week}, "
            f"with a {td:.0f}% chance to score an anytime touchdown. See ranges, trends and matchup data.")

    paras = [
        f"Our model projects <b>{escape(name)}</b> for <b>{escape(lead)}</b> when the {escape(team_name(team))} "
        f"face the {escape(team_name(opp))} in Week {week} ({escape(fmt_kickoff(p))}). It gives him a "
        f"<b>{td:.0f}% chance</b> to score an anytime touchdown."
    ]
    primary_range = fmt_range(p.get("rushing_range_80") if rush_first else p.get("receiving_range_80"))
    if primary_range:
        kind = "rushing" if rush_first else "receiving"
        paras.append(
            f"The model’s 80% range for his {kind} yards is <b>{primary_range} yards</b>, a range built to "
            f"catch about 8 in 10 outcomes."
        )
    ctx = p.get("season_context") or {}
    gp = int(num(ctx.get("games_played")))
    if gp:
        if rush_first:
            season = (f"Through {gp} game{'s' if gp != 1 else ''} in 2026 he is averaging "
                      f"{num(ctx.get('season_rushing_avg')):.1f} rushing yards on "
                      f"{num(ctx.get('season_carries_avg')):.1f} carries per game")
            if num(ctx.get("season_receiving_avg")) >= 5:
                season += f", plus {num(ctx.get('season_receiving_avg')):.1f} receiving yards"
        else:
            season = (f"Through {gp} game{'s' if gp != 1 else ''} in 2026 he is averaging "
                      f"{num(ctx.get('season_receiving_avg')):.1f} receiving yards on "
                      f"{num(ctx.get('season_targets_avg')):.1f} targets per game")
        if p.get("snap_share_3") is not None:
            season += f", and he has played {num(p.get('snap_share_3')):.0f}% of offensive snaps over his last three games"
        paras.append(season + ".")
    rank = ordinal_rank(p.get("opp_rush_def_rank") if rush_first else p.get("opp_rec_def_rank"),
                        p.get("opp_def_rank_total"))
    if rank:
        kind = "rushing" if rush_first else "receiving"
        paras.append(
            f"The {escape(team_name(opp))} rank {rank} against {escape(pos)} {kind} production this season "
            f"(No. 1 is the toughest matchup)."
        )
    if p.get("injury_status"):
        detail = f" ({escape(p['injury_detail'])})" if p.get("injury_detail") else ""
        paras.append(
            f"<b>Injury note:</b> he is listed <b>{escape(p['injury_status'])}</b>{detail} on this week’s "
            f"injury report. Check final inactives about 90 minutes before kickoff."
        )
    elif int(num(p.get("games_missed"))) > 0:
        gm = int(num(p.get("games_missed")))
        paras.append(f"He has missed his team’s last {gm} game{'s' if gm != 1 else ''}, so this projection leans on his earlier usage.")
    return title, desc, paras


def metric(label: str, value: str, sub: str, cls: str) -> str:
    return f'<div class="player-metric {cls}"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>'


def snap_text(value) -> str:
    return "—" if value is None else f"{num(value):.0f}%"


def game_log(p: dict) -> str:
    games = (p.get("season_context") or {}).get("recent_games") or []
    if not games:
        return '<p class="seo-note">No completed 2026 games yet.</p>'
    rows = "".join(
        "<tr>"
        f'<td data-label="Week">Week {int(num(g.get("week")))}</td>'
        f'<td data-label="Rush yds">{num(g.get("rushing_yards")):.0f}</td>'
        f'<td data-label="Carries">{num(g.get("carries")):.0f}</td>'
        f'<td data-label="Rec yds">{num(g.get("receiving_yards")):.0f}</td>'
        f'<td data-label="Targets">{num(g.get("targets")):.0f}</td>'
        f'<td data-label="TDs">{int(num(g.get("touchdowns")))}</td>'
        f'<td data-label="Snap %">{snap_text(g.get("snap_pct"))}</td>'
        "</tr>"
        for g in games
    )
    return ('<div class="table-wrap"><table><thead><tr><th>Week</th><th>Rush yds</th><th>Carries</th>'
            '<th>Rec yds</th><th>Targets</th><th>TDs</th><th>Snap %</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def track_record(perf: dict) -> str:
    if not perf.get("graded_predictions"):
        return ""
    return (
        '<section class="detail-panel seo-prose"><p class="eyebrow">TRACK RECORD</p><h2>How accurate is this model?</h2>'
        f"<p>Every week’s projections are archived before kickoff and graded against the real box scores. "
        f"Across {int(num(perf.get('graded_predictions'))):,} graded projections from {int(num(perf.get('graded_weeks')))} weeks of 2026, "
        f"rushing projections missed by {num(perf.get('rushing_mae')):.1f} yards on average and receiving projections by "
        f"{num(perf.get('receiving_mae')):.1f} yards. The 80% ranges contained the actual result "
        f"{num(perf.get('rushing_range_hit_rate')):.0f}% of the time for rushing and "
        f"{num(perf.get('receiving_range_hit_rate')):.0f}% for receiving.</p>"
        '<p><a href="../index.html#results">See every graded week →</a></p></section>'
    )


def player_page(p: dict, payload: dict, perf: dict, slug: str, teammates: list[tuple[str, str, str]]) -> str:
    week = int(num(payload.get("week")))
    title, desc, paras = player_summary(p, week)
    rush_first = p.get("position") in RUSH_FIRST
    metrics = [
        metric("Rushing", f"{num(p.get('rushing_yards')):.1f}", "projected yards", "rush-metric"),
        metric("Receiving", f"{num(p.get('receiving_yards')):.1f}", "projected yards", "rec-metric"),
        metric("Anytime TD", f"{num(p.get('td_probability')):.0f}%", "model probability", "td-metric"),
    ]
    if not rush_first:
        metrics[0], metrics[1] = metrics[1], metrics[0]
    details = []
    for label, key in (("Rushing 80% range", "rushing_range_80"), ("Receiving 80% range", "receiving_range_80")):
        r = fmt_range(p.get(key))
        if r:
            details.append(f"<div><span>{label}</span><strong>{r} yds</strong></div>")
    for label, key in (("Opponent vs position, rushing", "opp_rush_def_rank"),
                       ("Opponent vs position, receiving", "opp_rec_def_rank")):
        r = ordinal_rank(p.get(key), p.get("opp_def_rank_total"))
        if r:
            details.append(f"<div><span>{label}</span><strong>{r}</strong></div>")
    if p.get("snap_share_3") is not None:
        details.append(f"<div><span>Snap share, last 3 games</span><strong>{num(p.get('snap_share_3')):.0f}%</strong></div>")
    mates = "".join(f'<li><a href="{s}.html">{escape(n)}</a> <small>{escape(pos)}</small></li>'
                    for s, n, pos in teammates)
    updated = fmt_generated(payload)
    body = f"""
<nav class="seo-crumbs" aria-label="Breadcrumb"><a href="../index.html">Home</a> › <a href="index.html">Players</a> › {escape(p['player'])}</nav>
<section class="player-hero"><div class="player-identity"><div>
<p class="eyebrow">WEEK {week} PROJECTION • {escape(p.get('position', ''))} • {escape(team_name(p.get('team')))}</p>
<h1>{escape(p['player'])} Week {week} Projection vs {escape(p.get('opponent', ''))}</h1>
<p>{escape(p.get('team', ''))} vs {escape(p.get('opponent', ''))} • {escape(fmt_kickoff(p))}</p>
</div></div><div class="player-status"><span>Updated {escape(updated)}</span></div></section>
<section class="player-metrics-grid">{''.join(metrics)}</section>
<section class="detail-panel seo-prose"><p class="eyebrow">THE PROJECTION</p><h2>Week {week} outlook</h2>{''.join(f'<p>{x}</p>' for x in paras)}
<p><a class="primary-btn" href="../player.html?id={escape(str(p['player_id']))}">Open the interactive breakdown</a></p></section>
{f'<section class="detail-panel"><p class="eyebrow">DETAIL</p><h2>Ranges and matchup</h2><div class="detail-list">{"".join(details)}</div></section>' if details else ''}
<section class="detail-panel"><p class="eyebrow">2026 GAME LOG</p><h2>{escape(p['player'])} this season</h2>{game_log(p)}</section>
{track_record(perf)}
{f'<section class="detail-panel seo-links"><p class="eyebrow">SAME TEAM</p><h2>More {escape(team_name(p.get("team")))} projections</h2><ul>{mates}</ul></section>' if mates else ''}
"""
    return page(title=title, description=desc, canonical=f"{SITE_URL}/players/{slug}.html", depth=1, body=body)


def ruled_out_page(p: dict, payload: dict, slug: str) -> str:
    week = int(num(payload.get("week")))
    name = p["player"]
    status = p.get("status") or "Out"
    detail = f" ({p['detail']})" if p.get("detail") else ""
    title = f"{name} Week {week} Projection vs {p.get('opponent', '')}: Ruled {status}"
    desc = (f"{name} ({p.get('position', '')}, {p.get('team', '')}) is listed {status}{detail} for Week {week}, "
            f"so Football Prop Edge has no projection for him this week.")
    body = f"""
<nav class="seo-crumbs" aria-label="Breadcrumb"><a href="../index.html">Home</a> › <a href="index.html">Players</a> › {escape(name)}</nav>
<section class="player-empty"><p class="eyebrow">WEEK {week} • {escape(p.get('position', ''))} • {escape(team_name(p.get('team')))}</p>
<h1>{escape(name)} is not projected for Week {week}</h1>
<p>{escape(name)} is listed <b>{escape(status)}</b>{escape(detail)} for the {escape(team_name(p.get('team')))}’ game against the {escape(team_name(p.get('opponent')))}, so no projection is published this week. This page updates automatically when he returns to the slate.</p>
<p><a class="primary-btn" href="../projections/rushing-yards.html">See this week’s top projections</a></p></section>
"""
    return page(title=title, description=desc, canonical=f"{SITE_URL}/players/{slug}.html", depth=1, body=body)


def stale_page(info: dict, payload: dict) -> str:
    week = int(num(payload.get("week")))
    name = info.get("name", "This player")
    body = f"""
<nav class="seo-crumbs" aria-label="Breadcrumb"><a href="../index.html">Home</a> › <a href="index.html">Players</a> › {escape(name)}</nav>
<section class="player-empty"><h1>{escape(name)} is not on the Week {week} slate</h1>
<p>{escape(name)} ({escape(info.get('position', ''))}, {escape(info.get('team', ''))}) was last projected in Week {int(num(info.get('last_week')))}. This page updates automatically if he returns to the slate.</p>
<p><a class="primary-btn" href="index.html">Browse this week’s players</a></p></section>
"""
    return page(title=f"{name} Projection • Football Prop Edge",
                description=f"{name} is not on this week's Football Prop Edge slate.",
                canonical=None, depth=1, body=body, noindex=True)


def fmt_generated(payload: dict) -> str:
    try:
        dt = datetime.fromisoformat(payload["generated_at"]).astimezone(timezone.utc)
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except (KeyError, ValueError):
        return "this week"


# ---------------------------------------------------------------- hub pages
def ranked_page(players: list[dict], slugs: dict, payload: dict, kind: str) -> tuple[str, str]:
    week = int(num(payload.get("week")))
    if kind == "rushing":
        key, label, file = "rushing_yards", "Rushing Yards", "rushing-yards"
        pool = [p for p in players if num(p.get(key)) >= 10]
        rng_key = "rushing_range_80"
    elif kind == "receiving":
        key, label, file = "receiving_yards", "Receiving Yards", "receiving-yards"
        pool = [p for p in players if num(p.get(key)) >= 10]
        rng_key = "receiving_range_80"
    else:
        key, label, file = "td_probability", "Anytime Touchdown", "anytime-touchdown"
        pool = [p for p in players if num(p.get(key)) >= 10]
        rng_key = None
    pool.sort(key=lambda p: num(p.get(key)), reverse=True)
    rows = []
    for i, p in enumerate(pool, 1):
        val = f"{num(p.get(key)):.0f}%" if kind == "td" else f"{num(p.get(key)):.1f}"
        rng = (fmt_range(p.get(rng_key)) or "—") if rng_key else ""
        rows.append(
            "<tr>"
            f'<td data-label="Player"><a href="../players/{slugs[str(p["player_id"])]}.html">{i}. {escape(p["player"])}</a></td>'
            f'<td data-label="Pos">{escape(p.get("position", ""))}</td>'
            f'<td data-label="Game">{escape(p.get("team", ""))} vs {escape(p.get("opponent", ""))}</td>'
            f'<td data-label="{"TD chance" if kind == "td" else "Projection"}">{val}</td>'
            + (f'<td data-label="80% range">{rng}</td>' if rng_key else "")
            + "</tr>"
        )
    head = ("<th>Player</th><th>Pos</th><th>Game</th>"
            + ("<th>TD chance</th>" if kind == "td" else "<th>Projection</th><th>80% range</th>"))
    top = ", ".join(p["player"] for p in pool[:3])
    title = f"NFL Week {week} {label} Projections & Player Prop Rankings"
    desc = (f"Every NFL Week {week} {label.lower()} projection, ranked. Top of the board: {top}. "
            f"Updated daily with injury checks and model ranges.")
    intro = {
        "rushing": "Projected rushing yards for every running back, quarterback and ball-carrier on this week’s slate.",
        "receiving": "Projected receiving yards for every wide receiver, tight end and running back on this week’s slate.",
        "td": "The model’s probability that each player scores at least one rushing or receiving touchdown this week.",
    }[kind]
    others = "".join(f'<a class="secondary-btn" href="{f}.html">{l}</a> ' for f, l in
                     (("rushing-yards", "Rushing"), ("receiving-yards", "Receiving"), ("anytime-touchdown", "Anytime TD"))
                     if f != file)
    body = f"""
<nav class="seo-crumbs" aria-label="Breadcrumb"><a href="../index.html">Home</a> › {label} projections</nav>
<section class="player-hero"><div class="player-identity"><div><p class="eyebrow">WEEK {week} • UPDATED {escape(fmt_generated(payload).upper())}</p>
<h1>NFL Week {week} {label} Projections</h1><p>{intro} Players listed Out or on a reserve list are removed automatically.</p></div></div></section>
<p class="seo-switch">{others}</p>
<section class="detail-panel"><div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
"""
    return file, page(title=title, description=desc, canonical=f"{SITE_URL}/projections/{file}.html", depth=1, body=body)


def players_index(players: list[dict], ruled_out: list[dict], slugs: dict, payload: dict) -> str:
    week = int(num(payload.get("week")))
    by_team: dict[str, list[str]] = {}
    for p in players:
        by_team.setdefault(p.get("team", ""), []).append(
            f'<li><a href="{slugs[str(p["player_id"])]}.html">{escape(p["player"])}</a> <small>{escape(p.get("position", ""))}</small></li>')
    for p in ruled_out:
        by_team.setdefault(p.get("team", ""), []).append(
            f'<li><a href="{slugs[str(p["player_id"])]}.html">{escape(p["player"])}</a> <small>{escape(p.get("status") or "Out")}</small></li>')
    sections = "".join(
        f'<section class="detail-panel seo-links"><h2>{escape(team_name(t))}</h2><ul>{"".join(items)}</ul></section>'
        for t, items in sorted(by_team.items(), key=lambda kv: team_name(kv[0]))
    )
    body = f"""
<nav class="seo-crumbs" aria-label="Breadcrumb"><a href="../index.html">Home</a> › Players</nav>
<section class="player-hero"><div class="player-identity"><div><p class="eyebrow">WEEK {week}</p>
<h1>NFL Week {week} Player Projections by Team</h1><p>Rushing yards, receiving yards and anytime-touchdown odds for {len(players)} players.</p></div></div></section>
{sections}
"""
    return page(title=f"NFL Week {week} Player Projections by Team • Football Prop Edge",
                description=f"Week {week} NFL player projections for all {len(players)} players on the slate, grouped by team.",
                canonical=f"{SITE_URL}/players/index.html", depth=1, body=body)


def sitemap(urls: list[str], lastmod: str) -> str:
    items = "".join(f"<url><loc>{escape(u)}</loc><lastmod>{lastmod}</lastmod></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + items + "</urlset>\n")


# ---------------------------------------------------------------- main
def build(root: Path = ROOT) -> dict:
    payload = json.loads((root / "data/predictions.json").read_text())
    perf_path = root / "data/performance.json"
    perf = json.loads(perf_path.read_text()) if perf_path.exists() else {}
    index_path = root / "data/seo_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"players": {}}

    players = [p for p in payload.get("players", []) if p.get("player_id") and p.get("player")]
    ruled_out = [p for p in payload.get("ruled_out", []) if p.get("player_id") and p.get("player")]
    slugs = assign_slugs(players + ruled_out, index)
    week = int(num(payload.get("week")))

    players_dir, proj_dir = root / "players", root / "projections"
    players_dir.mkdir(exist_ok=True)
    proj_dir.mkdir(exist_ok=True)

    by_team: dict[str, list[dict]] = {}
    for p in players:
        by_team.setdefault(p.get("team", ""), []).append(p)

    urls = [f"{SITE_URL}/", f"{SITE_URL}/players/index.html"]
    written = set()
    for p in players:
        pid, slug = str(p["player_id"]), slugs[str(p["player_id"])]
        mates = sorted((m for m in by_team.get(p.get("team", ""), []) if m is not p),
                       key=lambda m: -max(num(m.get("rushing_yards")), num(m.get("receiving_yards"))))[:8]
        teammates = [(slugs[str(m["player_id"])], m["player"], m.get("position", "")) for m in mates]
        (players_dir / f"{slug}.html").write_text(player_page(p, payload, perf, slug, teammates))
        urls.append(f"{SITE_URL}/players/{slug}.html")
        index["players"][pid] = {"slug": slug, "name": p["player"], "team": p.get("team"),
                                 "position": p.get("position"), "last_week": week}
        written.add(slug)
    for p in ruled_out:
        pid, slug = str(p["player_id"]), slugs[str(p["player_id"])]
        if slug in written:
            continue
        (players_dir / f"{slug}.html").write_text(ruled_out_page(p, payload, slug))
        urls.append(f"{SITE_URL}/players/{slug}.html")
        prior = index["players"].get(pid, {})
        index["players"][pid] = {"slug": slug, "name": p["player"], "team": p.get("team"),
                                 "position": p.get("position"), "last_week": prior.get("last_week", week)}
        written.add(slug)
    for pid, info in index["players"].items():
        if info["slug"] not in written:
            (players_dir / f"{info['slug']}.html").write_text(stale_page(info, payload))

    (players_dir / "index.html").write_text(players_index(players, ruled_out, slugs, payload))
    for kind in ("rushing", "receiving", "td"):
        file, html = ranked_page(players, slugs, payload, kind)
        (proj_dir / f"{file}.html").write_text(html)
        urls.append(f"{SITE_URL}/projections/{file}.html")

    lastmod = (payload.get("generated_at") or datetime.now(timezone.utc).isoformat())[:10]
    (root / "sitemap.xml").write_text(sitemap(urls, lastmod))
    index_path.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    return {"player_pages": len(written), "indexed_urls": len(urls)}


if __name__ == "__main__":
    stats = build()
    print(f"Wrote {stats['player_pages']} player pages; sitemap has {stats['indexed_urls']} URLs.")
    sys.exit(0)
