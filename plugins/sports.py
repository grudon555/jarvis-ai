"""Sports schedules and scores via ESPN public API (no key required)."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from plugins import jarvis_tool

_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

_LEAGUES = {
    "nba": ("basketball", "nba"),
    "nfl": ("football", "nfl"),
    "nhl": ("hockey", "nhl"),
    "mlb": ("baseball", "mlb"),
    "bundesliga": ("soccer", "ger.1"),
    "premier league": ("soccer", "eng.1"),
    "champions league": ("soccer", "uefa.champions"),
    "la liga": ("soccer", "esp.1"),
    "serie a": ("soccer", "ita.1"),
}


def _scoreboard_url(sport: str, league: str) -> str:
    return f"{_ESPN_BASE}/{sport}/{league}/scoreboard"


def _format_event(event: dict) -> str:
    name = event.get("shortName", event.get("name", "?"))
    date_str = event.get("date", "")
    status_obj = event.get("status", {}).get("type", {})
    state = status_obj.get("state", "")     # "pre" | "in" | "post"
    description = status_obj.get("description", "")

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        time_label = local_dt.strftime("%a %d %b  %H:%M")
    except Exception:
        time_label = date_str[:16]

    comps = event.get("competitions", [{}])[0]
    competitors = comps.get("competitors", [])
    score_parts = []
    for c in competitors:
        team = c.get("team", {}).get("abbreviation", "?")
        score = c.get("score", "")
        score_parts.append(f"{team} {score}".strip())
    score_str = " — ".join(score_parts) if score_parts else name

    if state == "in":
        clock = comps.get("status", {}).get("displayClock", "")
        period = comps.get("status", {}).get("period", "")
        live_label = f"  🔴 LIVE  {clock} | Period {period}" if clock else "  🔴 LIVE"
        return f"  {score_str}{live_label}"
    elif state == "post":
        return f"  {score_str}  ✅ Final"
    else:
        return f"  {time_label}  {score_str}"


@jarvis_tool(
    name="get_sports_scores",
    description=(
        "Get today's live scores, upcoming games, and results for NBA, NFL, NHL, MLB, "
        "Bundesliga, Premier League, Champions League, La Liga, or Serie A."
    ),
    params={
        "league": {
            "type": "string",
            "description": (
                "League name: 'nba', 'nfl', 'nhl', 'mlb', 'bundesliga', "
                "'premier league', 'champions league', 'la liga', 'serie a'"
            ),
            "required": True,
        },
    },
)
def get_sports_scores(league: str) -> str:
    key = league.strip().lower()
    mapping = _LEAGUES.get(key)
    if not mapping:
        available = ", ".join(_LEAGUES.keys())
        return f"Unknown league '{league}'. Available: {available}"

    sport, league_id = mapping
    url = _scoreboard_url(sport, league_id)

    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"Could not fetch {league} data: {exc}"

    events = data.get("events", [])
    if not events:
        return f"No {league.upper()} games scheduled today."

    live, upcoming, finished = [], [], []
    for ev in events:
        state = ev.get("status", {}).get("type", {}).get("state", "")
        line = _format_event(ev)
        if state == "in":
            live.append(line)
        elif state == "post":
            finished.append(line)
        else:
            upcoming.append(line)

    sections = []
    league_label = league.upper()
    if live:
        sections.append(f"🔴 {league_label} — LIVE NOW:\n" + "\n".join(live))
    if upcoming:
        sections.append(f"📅 {league_label} — Upcoming:\n" + "\n".join(upcoming))
    if finished:
        sections.append(f"✅ {league_label} — Results:\n" + "\n".join(finished))

    return "\n\n".join(sections) if sections else f"No {league_label} data available."


@jarvis_tool(
    name="get_nba_schedule",
    description="Get today's NBA games — live scores, upcoming tip-offs, and final results.",
    params={},
)
def get_nba_schedule() -> str:
    return get_sports_scores("nba")
