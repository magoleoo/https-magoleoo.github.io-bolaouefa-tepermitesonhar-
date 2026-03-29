#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def load_env_settings() -> dict[str, Any]:
    return {
        "api_key": os.getenv("API_FOOTBALL_KEY", "").strip(),
        "api_host": os.getenv("API_FOOTBALL_HOST", "v3.football.api-sports.io").strip(),
        "api_base_url": os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io").strip(),
        "league_id": int(os.getenv("API_FOOTBALL_LEAGUE_ID", "2")),
        "default_season": int(os.getenv("API_FOOTBALL_SEASON", "2025")),
    }


def request_fixtures(settings: dict[str, Any], season: int) -> list[dict[str, Any]]:
    if not settings["api_key"]:
        raise RuntimeError("API_FOOTBALL_KEY não configurada.")

    query = urlencode({"league": settings["league_id"], "season": season})
    url = f"{settings['api_base_url']}/fixtures?{query}"
    request = Request(
        url,
        headers={
            "x-apisports-key": settings["api_key"],
            "x-rapidapi-host": settings["api_host"],
        },
    )
    with urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("response", [])


def map_phase_key(round_label: str) -> str:
    lower = (round_label or "").lower()
    if "league" in lower:
        return "LEAGUE"
    if "play-off" in lower or "playoff" in lower:
        return "PLAYOFF"
    if "round of 16" in lower or "8th finals" in lower:
        return "ROUND_OF_16"
    if "quarter" in lower:
        return "QUARTER"
    if "semi" in lower:
        return "SEMI"
    if "final" in lower:
        return "FINAL"
    return "UNKNOWN"


def maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def derive_matchday_label(round_label: str) -> str | None:
    if "league" not in (round_label or "").lower():
        return None
    match = re.search(r"(\d+)", round_label or "")
    if not match:
        return None
    return f"Matchday {int(match.group(1))}"


def normalize_match(fixture: dict[str, Any]) -> dict[str, Any]:
    fixture_info = fixture.get("fixture", {}) or {}
    league_info = fixture.get("league", {}) or {}
    teams = fixture.get("teams", {}) or {}
    goals = fixture.get("goals", {}) or {}
    score = fixture.get("score", {}) or {}

    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}
    round_label = str(league_info.get("round") or "Champions League").strip()
    phase_key = map_phase_key(round_label)

    fulltime = score.get("fulltime") or {}
    score_home_90 = maybe_int(fulltime.get("home"))
    score_away_90 = maybe_int(fulltime.get("away"))
    if score_home_90 is None:
        score_home_90 = maybe_int(goals.get("home"))
    if score_away_90 is None:
        score_away_90 = maybe_int(goals.get("away"))

    qualified_team_name = None
    if home.get("winner") is True:
        qualified_team_name = home.get("name")
    elif away.get("winner") is True:
        qualified_team_name = away.get("name")

    status = fixture_info.get("status", {}) or {}

    return {
        "id": maybe_int(fixture_info.get("id")),
        "phase_key": phase_key,
        "round_label": round_label,
        "matchday_label": derive_matchday_label(round_label),
        "kickoff_utc": fixture_info.get("date"),
        "home_team_name": home.get("name"),
        "away_team_name": away.get("name"),
        "score_home_90": score_home_90,
        "score_away_90": score_away_90,
        "qualified_team_name": qualified_team_name,
        "status_short": status.get("short"),
        "status_long": status.get("long"),
    }


def write_outputs(project_root: Path, season: int, matches: list[dict[str, Any]]) -> None:
    payload = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matches": matches,
    }
    api_dir = project_root / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "matches.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (api_dir / "matches.js").write_text(
        "window.apiMatchesData = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza placares da Champions via API-Football para api/matches.*")
    parser.add_argument("--season", type=int, default=None, help="Temporada da API-Football (ex.: 2025 para Champions 2025/26)")
    args = parser.parse_args()

    settings = load_env_settings()
    season = args.season if args.season is not None else settings["default_season"]

    project_root = Path(__file__).resolve().parents[1]
    fixtures = request_fixtures(settings, season)
    matches = [normalize_match(item) for item in fixtures]
    matches = [item for item in matches if item.get("id") is not None and item.get("phase_key") != "UNKNOWN"]
    matches.sort(key=lambda item: ((item.get("kickoff_utc") or ""), int(item.get("id") or 0)))

    write_outputs(project_root, season, matches)

    phase_counts: dict[str, int] = {}
    for item in matches:
        phase = str(item.get("phase_key") or "UNKNOWN")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    print(f"[sync_api_matches] Temporada {season} | jogos sincronizados: {len(matches)}")
    print(f"[sync_api_matches] Por fase: {phase_counts}")
    print(f"[sync_api_matches] Saída: {project_root / 'api' / 'matches.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
