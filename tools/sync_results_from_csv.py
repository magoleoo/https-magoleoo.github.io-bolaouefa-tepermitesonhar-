#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_CSV = PROJECT_ROOT / "data" / "results_update.csv"


TEAM_ALIASES = {
    "bayern de munique": "bayern munchen",
    "bayern munich": "bayern munchen",
    "bayern munchen": "bayern munchen",
    "bayern münchen": "bayern munchen",
    "paris saint germain": "paris saint germain",
    "paris saint-germain": "paris saint germain",
    "psg": "paris saint germain",
    "atletico de madrid": "atletico de madrid",
    "atletico madrid": "atletico de madrid",
    "atlético de madrid": "atletico de madrid",
}


def split_fixture_label(label: Any) -> tuple[str, str]:
    text = str(label or "").strip()
    parts = re.split(r"\s+[xX]\s+", text, maxsplit=1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonical_team_key(name: Any) -> str:
    normalized = normalize_text(name)
    return TEAM_ALIASES.get(normalized, normalized)


def normalize_phase_key(value: Any) -> str:
    normalized = normalize_text(value)
    mapping = {
        "league": "LEAGUE",
        "1a fase": "LEAGUE",
        "primeira fase": "LEAGUE",
        "fase de liga": "LEAGUE",
        "playoff": "PLAYOFF",
        "play off": "PLAYOFF",
        "play-offs": "PLAYOFF",
        "play offs": "PLAYOFF",
        "round of 16": "ROUND_OF_16",
        "oitavas": "ROUND_OF_16",
        "oitavas de final": "ROUND_OF_16",
        "quarter": "QUARTER",
        "quartas": "QUARTER",
        "quartas de final": "QUARTER",
        "semi": "SEMI",
        "semifinal": "SEMI",
        "semifinais": "SEMI",
        "semi finais": "SEMI",
        "final": "FINAL",
    }
    return mapping.get(normalized, str(value or "").strip().upper())


def normalize_leg(value: Any) -> str:
    normalized = normalize_text(value)
    if "ida" in normalized:
        return "IDA"
    if "volta" in normalized:
        return "VOLTA"
    return ""


def is_classification_fixture(fixture: dict[str, Any]) -> bool:
    label = normalize_text(fixture.get("label", ""))
    matchday = normalize_text(fixture.get("matchday", ""))
    return (
        label.startswith("classificado em")
        or label.startswith("classificado")
        or matchday.startswith("classificado")
    )


def parse_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def parse_score_token(value: Any) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    match = re.match(r"^\s*(\d+)\s*[xX\-\:]\s*(\d+)\s*$", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def normalize_header(value: Any) -> str:
    return normalize_text(value).replace(" ", "_")


def first_non_empty(row: dict[str, str], aliases: list[str]) -> str:
    for alias in aliases:
        value = str(row.get(alias, "")).strip()
        if value:
            return value
    return ""


def sniff_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        return dialect.delimiter
    except csv.Error:
        return ","


def read_csv_rows_from_text(text: str) -> list[dict[str, str]]:
    delimiter = sniff_delimiter(text)
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        return []
    normalized_fields = [normalize_header(field) for field in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for raw in reader:
        normalized_row: dict[str, str] = {}
        for field, norm_field in zip(reader.fieldnames, normalized_fields):
            normalized_row[norm_field] = str(raw.get(field, "")).strip()
        rows.append(normalized_row)
    return rows


def load_csv_rows(csv_url: str, csv_path: Path) -> tuple[list[dict[str, str]], str]:
    if csv_url:
        with urlopen(csv_url, timeout=60) as response:
            text = response.read().decode("utf-8-sig", errors="replace")
        return read_csv_rows_from_text(text), f"url:{csv_url}"

    if csv_path.exists():
        text = csv_path.read_text(encoding="utf-8-sig")
        return read_csv_rows_from_text(text), f"file:{csv_path}"

    raise FileNotFoundError(
        "Nenhuma fonte de CSV encontrada. "
        "Defina BOLAO_RESULTS_CSV_URL ou crie data/results_update.csv."
    )


@dataclass
class ParsedUpdate:
    row_index: int
    phase_key: str
    leg: str
    round_label: str
    home_team_name: str
    away_team_name: str
    score_home_90: int
    score_away_90: int
    qualified_team_name: str
    status_short: str
    status_long: str


def bootstrap_matches_from_ranking(ranking_json_path: Path) -> list[dict[str, Any]]:
    if not ranking_json_path.exists():
        return []
    backtest_data = json.loads(ranking_json_path.read_text(encoding="utf-8"))
    phases = backtest_data.get("phases", {})
    if not isinstance(phases, dict):
        return []

    matches: list[dict[str, Any]] = []
    next_id = 1
    for phase_key in ("LEAGUE", "PLAYOFF", "ROUND_OF_16", "QUARTER", "SEMI", "FINAL"):
        phase_payload = phases.get(phase_key) or {}
        fixtures = phase_payload.get("fixtures") or []
        if not isinstance(fixtures, list):
            continue
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            if is_classification_fixture(fixture):
                continue

            home, away = split_fixture_label(fixture.get("label"))
            if not home or not away:
                continue

            score_home_90, score_away_90 = parse_score_token(fixture.get("official"))
            leg = normalize_leg(fixture.get("leg"))
            round_label = str(fixture.get("matchday") or phase_key).strip()
            if leg:
                round_label = f"{phase_key} {leg.title()}"

            matches.append(
                {
                    "id": next_id,
                    "phase_key": phase_key,
                    "round_label": round_label,
                    "matchday_label": fixture.get("matchday") if phase_key == "LEAGUE" else None,
                    "kickoff_utc": None,
                    "home_team_name": home,
                    "away_team_name": away,
                    "score_home_90": score_home_90,
                    "score_away_90": score_away_90,
                    "qualified_team_name": "",
                    "status_short": "FT" if score_home_90 is not None and score_away_90 is not None else "NS",
                    "status_long": "Finalizado"
                    if score_home_90 is not None and score_away_90 is not None
                    else "Agendado",
                }
            )
            next_id += 1

    return matches


def parse_update_row(row: dict[str, str], row_index: int) -> ParsedUpdate | None:
    home_team_name = first_non_empty(
        row,
        [
            "home_team",
            "time_casa",
            "mandante",
            "casa",
            "home",
            "time_1",
            "clube_casa",
        ],
    )
    away_team_name = first_non_empty(
        row,
        [
            "away_team",
            "time_fora",
            "visitante",
            "fora",
            "away",
            "time_2",
            "clube_fora",
        ],
    )
    if not home_team_name or not away_team_name:
        return None

    score_home_90 = parse_int(
        first_non_empty(
            row,
            ["score_home", "gols_casa", "placar_casa", "home_score", "gols_mandante"],
        )
    )
    score_away_90 = parse_int(
        first_non_empty(
            row,
            ["score_away", "gols_fora", "placar_fora", "away_score", "gols_visitante"],
        )
    )

    if score_home_90 is None or score_away_90 is None:
        score_home_90, score_away_90 = parse_score_token(
            first_non_empty(row, ["score", "placar", "resultado", "resultado_oficial", "oficial"])
        )

    if score_home_90 is None or score_away_90 is None:
        return None

    phase_key = normalize_phase_key(
        first_non_empty(row, ["phase_key", "fase", "phase", "etapa", "fase_key"])
    )
    leg = normalize_leg(first_non_empty(row, ["leg", "perna", "jogo", "ida_volta"]))
    round_label = first_non_empty(row, ["round_label", "rodada", "round", "fase_label"])
    qualified_team_name = first_non_empty(
        row, ["qualified_team_name", "classificado", "classificado_oficial", "qualified"]
    )
    status_short = first_non_empty(row, ["status_short", "status", "status_code"])
    status_long = first_non_empty(row, ["status_long", "status_label", "status_extenso"])

    return ParsedUpdate(
        row_index=row_index,
        phase_key=phase_key,
        leg=leg,
        round_label=round_label,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        score_home_90=score_home_90,
        score_away_90=score_away_90,
        qualified_team_name=qualified_team_name,
        status_short=status_short,
        status_long=status_long,
    )


def leg_matches(round_label: str, leg: str) -> bool:
    if not leg:
        return True
    text = normalize_text(round_label)
    if leg == "IDA":
        return "ida" in text
    if leg == "VOLTA":
        return "volta" in text
    return True


def find_best_match_index(matches: list[dict[str, Any]], update: ParsedUpdate) -> int:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for idx, match in enumerate(matches):
        home = canonical_team_key(match.get("home_team_name"))
        away = canonical_team_key(match.get("away_team_name"))
        if home != canonical_team_key(update.home_team_name):
            continue
        if away != canonical_team_key(update.away_team_name):
            continue
        candidates.append((idx, match))

    if not candidates:
        return -1

    if update.phase_key:
        filtered = [
            item for item in candidates if normalize_phase_key(item[1].get("phase_key")) == update.phase_key
        ]
        if filtered:
            candidates = filtered

    if update.leg:
        filtered = [item for item in candidates if leg_matches(str(item[1].get("round_label", "")), update.leg)]
        if filtered:
            candidates = filtered

    if update.round_label:
        target = normalize_text(update.round_label)
        filtered = [
            item
            for item in candidates
            if target and target in normalize_text(str(item[1].get("round_label", "")))
        ]
        if filtered:
            candidates = filtered

    return candidates[0][0]


def apply_update(match: dict[str, Any], update: ParsedUpdate) -> bool:
    before = json.dumps(match, ensure_ascii=False, sort_keys=True)

    match["score_home_90"] = update.score_home_90
    match["score_away_90"] = update.score_away_90

    if update.qualified_team_name:
        match["qualified_team_name"] = update.qualified_team_name

    if update.status_short:
        match["status_short"] = update.status_short
    elif update.score_home_90 is not None and update.score_away_90 is not None:
        match["status_short"] = "FT"

    if update.status_long:
        match["status_long"] = update.status_long
    elif update.score_home_90 is not None and update.score_away_90 is not None:
        match["status_long"] = "Finalizado"

    after = json.dumps(match, ensure_ascii=False, sort_keys=True)
    return before != after


def write_outputs(payload: dict[str, Any], api_dir: Path) -> None:
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
    parser = argparse.ArgumentParser(
        description=(
            "Atualiza api/matches.{json,js} a partir de CSV de resultados oficiais, "
            "mantendo o contrato atual do projeto."
        )
    )
    parser.add_argument("--csv-url", default=os.getenv("BOLAO_RESULTS_CSV_URL", "").strip())
    parser.add_argument(
        "--csv-path",
        default=str(DEFAULT_LOCAL_CSV),
        help="Arquivo local de fallback quando não houver URL.",
    )
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_dir = PROJECT_ROOT / "api"
    matches_json_path = api_dir / "matches.json"
    ranking_json_path = api_dir / "ranking.json"
    if not matches_json_path.exists():
        raise FileNotFoundError(f"Arquivo base não encontrado: {matches_json_path}")

    payload = json.loads(matches_json_path.read_text(encoding="utf-8"))
    matches = payload.get("matches", [])
    if not isinstance(matches, list):
        raise RuntimeError("Formato inválido: api/matches.json sem lista em 'matches'.")
    if len(matches) == 0:
        matches = bootstrap_matches_from_ranking(ranking_json_path)
        payload["matches"] = matches

    csv_rows, source_label = load_csv_rows(args.csv_url, Path(args.csv_path).expanduser().resolve())
    parsed_updates: list[ParsedUpdate] = []
    for row_index, row in enumerate(csv_rows, start=2):
        parsed = parse_update_row(row, row_index=row_index)
        if parsed:
            parsed_updates.append(parsed)

    if not parsed_updates:
        print(
            f"[sync_results_from_csv] fonte={source_label} | linhas_csv={len(csv_rows)} | "
            "linhas_validas=0 | nenhuma atualização aplicada (aguardando placares)."
        )
        print("[sync_results_from_csv] dry_run=True (implícito por no-op)")
        return 0

    updated = 0
    unmatched_rows: list[int] = []
    for update in parsed_updates:
        match_idx = find_best_match_index(matches, update)
        if match_idx < 0:
            unmatched_rows.append(update.row_index)
            continue
        changed = apply_update(matches[match_idx], update)
        if changed:
            updated += 1

    payload["provider"] = "results_csv"
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    if args.season is not None:
        payload["season"] = args.season

    if not args.dry_run:
        write_outputs(payload, api_dir)

    print(
        f"[sync_results_from_csv] fonte={source_label} | linhas_csv={len(csv_rows)} | "
        f"linhas_validas={len(parsed_updates)} | partidas_atualizadas={updated} | "
        f"linhas_nao_casadas={len(unmatched_rows)}"
    )
    if unmatched_rows:
        print(f"[sync_results_from_csv] linhas sem match: {unmatched_rows}")
    print(f"[sync_results_from_csv] dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
