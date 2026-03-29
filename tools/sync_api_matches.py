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


SUPPORTED_PROVIDERS = {"api_football", "football_data"}


def parse_env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_env_settings() -> dict[str, Any]:
    provider = os.getenv("LIVE_SCORES_PROVIDER", "api_football").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise RuntimeError(
            "LIVE_SCORES_PROVIDER inválido. "
            f"Valores aceitos: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )

    return {
        "provider": provider,
        "default_season": int(os.getenv("API_FOOTBALL_SEASON", "2025")),
        "require_non_empty": parse_env_flag(
            "API_FOOTBALL_REQUIRE_NON_EMPTY",
            parse_env_flag("FOOTBALL_DATA_REQUIRE_NON_EMPTY", True),
        ),
        "api_football": {
            "api_key": os.getenv("API_FOOTBALL_KEY", "").strip(),
            "api_host": os.getenv("API_FOOTBALL_HOST", "v3.football.api-sports.io").strip(),
            "api_base_url": os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io").strip(),
            "league_id": int(os.getenv("API_FOOTBALL_LEAGUE_ID", "2")),
        },
        "football_data": {
            "api_key": (
                os.getenv("FOOTBALL_DATA_API_KEY", "").strip()
                or os.getenv("API_FOOTBALL_KEY", "").strip()
            ),
            "api_base_url": os.getenv("FOOTBALL_DATA_BASE_URL", "https://api.football-data.org/v4").strip(),
            "competition_code": os.getenv("FOOTBALL_DATA_COMPETITION_CODE", "CL").strip().upper(),
        },
    }


def maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def map_phase_key_from_round_label(round_label: str) -> str:
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


def map_phase_key_from_stage(stage: str) -> str:
    normalized = (stage or "").strip().upper()
    if normalized in {"LEAGUE_STAGE", "GROUP_STAGE"}:
        return "LEAGUE"
    if normalized in {"PLAY_OFF_ROUND", "PLAYOFF_ROUND"}:
        return "PLAYOFF"
    if normalized in {"ROUND_OF_16", "LAST_16"}:
        return "ROUND_OF_16"
    if normalized == "QUARTER_FINALS":
        return "QUARTER"
    if normalized == "SEMI_FINALS":
        return "SEMI"
    if normalized == "FINAL":
        return "FINAL"
    return "UNKNOWN"


def derive_matchday_label_from_round(round_label: str) -> str | None:
    if "league" not in (round_label or "").lower():
        return None
    match = re.search(r"(\d+)", round_label or "")
    if not match:
        return None
    return f"Matchday {int(match.group(1))}"


def derive_matchday_label_from_stage(stage: str, matchday: Any) -> str | None:
    if map_phase_key_from_stage(stage) != "LEAGUE":
        return None
    matchday_int = maybe_int(matchday)
    if matchday_int is None:
        return None
    return f"Matchday {matchday_int}"


def request_fixtures_api_football(settings: dict[str, Any], season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider_settings = settings["api_football"]
    api_key = provider_settings["api_key"]
    if not api_key:
        raise RuntimeError("API_FOOTBALL_KEY não configurada para provider api_football.")

    query = urlencode({"league": provider_settings["league_id"], "season": season})
    url = f"{provider_settings['api_base_url']}/fixtures?{query}"
    request = Request(
        url,
        headers={
            "x-apisports-key": api_key,
            "x-rapidapi-host": provider_settings["api_host"],
        },
    )
    with urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))

    errors = payload.get("errors")
    if isinstance(errors, dict) and errors:
        raise RuntimeError(f"API-Football retornou erro(s): {errors}")
    if isinstance(errors, list) and len(errors) > 0:
        raise RuntimeError(f"API-Football retornou erro(s): {errors}")

    fixtures = payload.get("response", [])
    if not isinstance(fixtures, list):
        raise RuntimeError("Resposta da API-Football em formato inesperado: campo 'response' inválido.")
    return fixtures, payload


def request_matches_football_data(settings: dict[str, Any], season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider_settings = settings["football_data"]
    api_key = provider_settings["api_key"]
    if not api_key:
        raise RuntimeError("FOOTBALL_DATA_API_KEY não configurada para provider football_data.")

    query = urlencode({"season": season})
    url = f"{provider_settings['api_base_url']}/competitions/{provider_settings['competition_code']}/matches?{query}"
    request = Request(
        url,
        headers={
            "X-Auth-Token": api_key,
        },
    )
    with urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))

    matches = payload.get("matches", [])
    if not isinstance(matches, list):
        error_message = payload.get("message") or payload.get("error") or payload
        raise RuntimeError(f"football-data retornou erro/estrutura inesperada: {error_message}")
    return matches, payload


def normalize_api_football_match(fixture: dict[str, Any]) -> dict[str, Any]:
    fixture_info = fixture.get("fixture", {}) or {}
    league_info = fixture.get("league", {}) or {}
    teams = fixture.get("teams", {}) or {}
    goals = fixture.get("goals", {}) or {}
    score = fixture.get("score", {}) or {}

    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}
    round_label = str(league_info.get("round") or "Champions League").strip()
    phase_key = map_phase_key_from_round_label(round_label)

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
        "matchday_label": derive_matchday_label_from_round(round_label),
        "kickoff_utc": fixture_info.get("date"),
        "home_team_name": home.get("name"),
        "away_team_name": away.get("name"),
        "score_home_90": score_home_90,
        "score_away_90": score_away_90,
        "qualified_team_name": qualified_team_name,
        "status_short": status.get("short"),
        "status_long": status.get("long"),
    }


def normalize_football_data_match(match: dict[str, Any]) -> dict[str, Any]:
    home = match.get("homeTeam", {}) or {}
    away = match.get("awayTeam", {}) or {}
    score = match.get("score", {}) or {}
    fulltime = score.get("fullTime", {}) or {}
    winner = score.get("winner")
    stage = str(match.get("stage") or "").strip().upper()
    group = str(match.get("group") or "").strip()
    round_label = group or stage.replace("_", " ").title() or "Champions League"

    qualified_team_name = None
    if winner == "HOME_TEAM":
        qualified_team_name = home.get("name")
    elif winner == "AWAY_TEAM":
        qualified_team_name = away.get("name")

    status = str(match.get("status") or "").strip()

    return {
        "id": maybe_int(match.get("id")),
        "phase_key": map_phase_key_from_stage(stage),
        "round_label": round_label,
        "matchday_label": derive_matchday_label_from_stage(stage, match.get("matchday")),
        "kickoff_utc": match.get("utcDate"),
        "home_team_name": home.get("name"),
        "away_team_name": away.get("name"),
        "score_home_90": maybe_int(fulltime.get("home")),
        "score_away_90": maybe_int(fulltime.get("away")),
        "qualified_team_name": qualified_team_name,
        "status_short": status,
        "status_long": status,
    }


def write_outputs(project_root: Path, season: int, provider: str, matches: list[dict[str, Any]]) -> None:
    payload = {
        "season": season,
        "provider": provider,
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


def request_matches_by_provider(settings: dict[str, Any], season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider = settings["provider"]
    if provider == "api_football":
        return request_fixtures_api_football(settings, season)
    if provider == "football_data":
        return request_matches_football_data(settings, season)
    raise RuntimeError(f"Provider não suportado: {provider}")


def normalize_matches(provider: str, raw_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if provider == "api_football":
        return [normalize_api_football_match(item) for item in raw_matches]
    if provider == "football_data":
        return [normalize_football_data_match(item) for item in raw_matches]
    return []


def extract_api_results(provider: str, payload: dict[str, Any], raw_count: int) -> Any:
    if provider == "api_football":
        return payload.get("results")
    if provider == "football_data":
        result_set = payload.get("resultSet") or {}
        if isinstance(result_set, dict) and "count" in result_set:
            return result_set.get("count")
    return raw_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sincroniza placares da Champions para api/matches.* "
            "via provider configurado (api_football ou football_data)."
        )
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Temporada da competição (ex.: 2025 para Champions 2025/26).",
    )
    args = parser.parse_args()

    settings = load_env_settings()
    season = args.season if args.season is not None else settings["default_season"]
    provider = settings["provider"]

    project_root = Path(__file__).resolve().parents[1]
    raw_matches, payload = request_matches_by_provider(settings, season)
    matches = normalize_matches(provider, raw_matches)
    matches = [item for item in matches if item.get("id") is not None and item.get("phase_key") != "UNKNOWN"]
    matches.sort(key=lambda item: ((item.get("kickoff_utc") or ""), int(item.get("id") or 0)))

    api_results = extract_api_results(provider, payload, len(raw_matches))
    total_matches = len(raw_matches)
    if total_matches > 0 and len(matches) == 0:
        raise RuntimeError(
            "API retornou jogos, mas nenhum foi mapeado para fase conhecida. "
            "Revisar mapeamento de rounds/stages para o formato atual."
        )
    if settings["require_non_empty"] and len(matches) == 0:
        raise RuntimeError(
            "Sincronização bloqueada: API retornou zero jogos mapeados. "
            "Verifique chave, cota, temporada, competição ou status da API."
        )

    write_outputs(project_root, season, provider, matches)

    phase_counts: dict[str, int] = {}
    for item in matches:
        phase = str(item.get("phase_key") or "UNKNOWN")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    print(
        f"[sync_api_matches] Provider: {provider} | Temporada {season} | "
        f"resultados API: {api_results} | jogos brutos: {total_matches} | "
        f"jogos sincronizados: {len(matches)}"
    )
    print(f"[sync_api_matches] Por fase: {phase_counts}")
    print(f"[sync_api_matches] Saída: {project_root / 'api' / 'matches.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
