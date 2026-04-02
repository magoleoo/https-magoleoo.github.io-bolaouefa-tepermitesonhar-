#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RANKING_PATH = PROJECT_ROOT / "api" / "ranking.json"
DEFAULT_MATCHES_PATH = PROJECT_ROOT / "api" / "matches.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugify(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def split_fixture_label(label: Any) -> tuple[str, str]:
    text = str(label or "").strip()
    parts = re.split(r"\s+[xX]\s+", text, maxsplit=1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def parse_score(value: Any) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    match = re.match(r"^\s*(\d+)\s*[xX:-]\s*(\d+)\s*$", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


class PostgrestClient:
    def __init__(self, base_url: str, service_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.timeout = timeout

    def _request(
        self,
        method: str,
        table: str,
        query: dict[str, str] | None = None,
        payload: Any | None = None,
        prefer: str | None = None,
    ) -> None:
        query_str = f"?{urlencode(query)}" if query else ""
        url = f"{self.base_url}/rest/v1/{table}{query_str}"
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer

        req = Request(url=url, data=body, headers=headers, method=method.upper())
        with urlopen(req, timeout=self.timeout) as response:
            _ = response.read()

    def upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
        if not rows:
            return
        self._request(
            method="POST",
            table=table,
            query={"on_conflict": on_conflict},
            payload=rows,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self._request(
            method="POST",
            table=table,
            payload=rows,
            prefer="return=minimal",
        )

    def patch_eq(self, table: str, field: str, value: str, payload: dict[str, Any]) -> None:
        self._request(
            method="PATCH",
            table=table,
            query={field: f"eq.{value}"},
            payload=payload,
            prefer="return=minimal",
        )


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Formato inválido em {path}: esperado objeto JSON")
    return data


def build_participants_rows(ranking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in ranking_rows:
        participant_name = str(row.get("name") or "").strip()
        if not participant_name:
            continue
        participant_id = str(row.get("participant_id") or slugify(participant_name))
        if participant_id in seen_ids:
            continue
        seen_ids.add(participant_id)
        rows.append(
            {
                "participant_id": participant_id,
                "participant_name": participant_name,
            }
        )
    return rows


def build_ranking_rows(
    season_id: str,
    ranking_rows: list[dict[str, Any]],
    source: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(ranking_rows, start=1):
        participant_name = str(row.get("name") or "").strip()
        if not participant_name:
            continue
        participant_id = str(row.get("participant_id") or slugify(participant_name))
        out.append(
            {
                "season_id": season_id,
                "participant_id": participant_id,
                "position": idx,
                "total_points": round(to_float(row.get("total_points")), 2),
                "first_phase_points": round(to_float(row.get("first_phase_points")), 2),
                "playoff_points": round(to_float(row.get("playoff_points")), 2),
                "round_of_16_points": round(to_float(row.get("round_of_16_points")), 2),
                "quarter_points": round(to_float(row.get("quarter_points")), 2),
                "semi_points": round(to_float(row.get("semi_points")), 2),
                "final_points": round(to_float(row.get("final_points")), 2),
                "superclassic_points": round(to_float(row.get("superclassic_points")), 2),
                "hope_solo_hits": to_int(row.get("hope_solo_hits"), default=0),
                "favorite_team": str(row.get("favorite_team") or "").strip() or None,
                "scorer_pick": str(row.get("scorer_pick") or "").strip() or None,
                "assist_pick": str(row.get("assist_pick") or "").strip() or None,
                "delta_vs_ranking_sheet": round(to_float(row.get("delta_vs_ranking_sheet")), 2),
                "captured_at": now_iso(),
                "source": source,
            }
        )
    return out


def build_matches_from_ranking_phases(
    season_id: str,
    ranking_payload: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    phases = ranking_payload.get("phases") or {}
    if not isinstance(phases, dict):
        return []

    by_key: dict[str, dict[str, Any]] = {}

    for phase_key, phase_payload in phases.items():
        if not isinstance(phase_payload, dict):
            continue
        fixtures = phase_payload.get("fixtures") or []
        if not isinstance(fixtures, list):
            continue

        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            home_team, away_team = split_fixture_label(fixture.get("label"))
            if not home_team or not away_team:
                continue

            leg = str(fixture.get("leg") or "").strip().upper()
            round_label = str(fixture.get("matchday") or "").strip()
            official = str(fixture.get("official") or "").strip()
            score_home, score_away = parse_score(official)
            status_short = "FT" if score_home is not None and score_away is not None else "NS"
            status_long = "Finalizado" if status_short == "FT" else "Agendado"

            key_seed = f"{season_id}|{phase_key}|{leg}|{round_label}|{home_team}|{away_team}"
            match_key = slugify(key_seed)
            row = {
                "season_id": season_id,
                "match_key": match_key,
                "phase_key": str(phase_key).strip().upper(),
                "round_label": round_label or None,
                "leg": leg or None,
                "matchday_label": round_label or None,
                "kickoff_utc": None,
                "home_team_name": home_team,
                "away_team_name": away_team,
                "score_home_90": score_home,
                "score_away_90": score_away,
                "qualified_team_name": None,
                "status_short": status_short,
                "status_long": status_long,
                "source": source,
            }

            current = by_key.get(match_key)
            if not current:
                by_key[match_key] = row
                continue

            current_has_score = current.get("score_home_90") is not None and current.get("score_away_90") is not None
            row_has_score = row.get("score_home_90") is not None and row.get("score_away_90") is not None
            if row_has_score and not current_has_score:
                by_key[match_key] = row

    return list(by_key.values())


def maybe_append_matches_from_api_matches(
    season_id: str,
    source: str,
    base_rows: list[dict[str, Any]],
    matches_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    matches = matches_payload.get("matches") or []
    if not isinstance(matches, list) or not matches:
        return base_rows

    by_key = {row["match_key"]: row for row in base_rows}
    for item in matches:
        if not isinstance(item, dict):
            continue
        home_team = str(item.get("home_team_name") or "").strip()
        away_team = str(item.get("away_team_name") or "").strip()
        if not home_team or not away_team:
            continue

        phase_key = str(item.get("phase_key") or "").strip().upper() or "UNKNOWN"
        leg = ""
        round_label = str(item.get("round_label") or "").strip()
        if " ida" in normalize_text(round_label):
            leg = "IDA"
        elif " volta" in normalize_text(round_label):
            leg = "VOLTA"

        key_seed = f"{season_id}|{phase_key}|{leg}|{round_label}|{home_team}|{away_team}"
        match_key = slugify(key_seed)
        by_key[match_key] = {
            "season_id": season_id,
            "match_key": match_key,
            "phase_key": phase_key,
            "round_label": round_label or None,
            "leg": leg or None,
            "matchday_label": str(item.get("matchday_label") or "").strip() or None,
            "kickoff_utc": item.get("kickoff_utc"),
            "home_team_name": home_team,
            "away_team_name": away_team,
            "score_home_90": item.get("score_home_90"),
            "score_away_90": item.get("score_away_90"),
            "qualified_team_name": str(item.get("qualified_team_name") or "").strip() or None,
            "status_short": str(item.get("status_short") or "").strip() or None,
            "status_long": str(item.get("status_long") or "").strip() or None,
            "source": source,
        }

    return list(by_key.values())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza snapshot atual do bolão para Supabase (modo paralelo/shadow)."
    )
    parser.add_argument("--ranking-json", default=str(DEFAULT_RANKING_PATH))
    parser.add_argument("--matches-json", default=str(DEFAULT_MATCHES_PATH))
    parser.add_argument("--season-id", default=os.getenv("BOLAO_SEASON_ID", "").strip())
    parser.add_argument("--source", default="shadow-sync")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    ranking_payload = load_json(Path(args.ranking_json).expanduser().resolve())
    matches_payload = load_json(Path(args.matches_json).expanduser().resolve())
    ranking_rows = ranking_payload.get("ranking") or []
    if not isinstance(ranking_rows, list):
        raise RuntimeError("Formato inválido: ranking.json sem lista em 'ranking'.")
    if not ranking_rows:
        raise RuntimeError("ranking.json não possui linhas de ranking para sincronizar.")

    season_from_file = ranking_payload.get("season")
    season_id = str(args.season_id or season_from_file or "2025-26").strip()
    season_label = f"Bolão UEFA {season_id}"
    source = args.source.strip() or "shadow-sync"

    participants_rows = build_participants_rows(ranking_rows)
    ranking_snapshot_rows = build_ranking_rows(season_id, ranking_rows, source)
    matches_rows = build_matches_from_ranking_phases(season_id, ranking_payload, source)
    matches_rows = maybe_append_matches_from_api_matches(
        season_id=season_id,
        source=source,
        base_rows=matches_rows,
        matches_payload=matches_payload,
    )

    print(
        f"[shadow-sync] season_id={season_id} participants={len(participants_rows)} "
        f"ranking_rows={len(ranking_snapshot_rows)} matches={len(matches_rows)} dry_run={args.dry_run}"
    )

    if args.dry_run:
        return 0

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not supabase_service_key:
        raise RuntimeError(
            "SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são obrigatórios para sync real."
        )

    client = PostgrestClient(
        base_url=supabase_url,
        service_key=supabase_service_key,
        timeout=args.timeout,
    )

    run_id = f"shadow-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    client.insert(
        "bolao_sync_runs",
        [
            {
                "run_id": run_id,
                "season_id": season_id,
                "source": source,
                "status": "running",
                "message": "Sincronização iniciada.",
                "started_at": now_iso(),
            }
        ],
    )

    try:
        client.upsert(
            "bolao_seasons",
            [
                {
                    "season_id": season_id,
                    "season_label": season_label,
                    "is_active": True,
                }
            ],
            on_conflict="season_id",
        )
        client.upsert("bolao_participants", participants_rows, on_conflict="participant_id")
        client.upsert(
            "bolao_ranking_snapshot",
            ranking_snapshot_rows,
            on_conflict="season_id,participant_id",
        )
        client.upsert(
            "bolao_matches",
            matches_rows,
            on_conflict="season_id,match_key",
        )
        client.patch_eq(
            "bolao_sync_runs",
            "run_id",
            run_id,
            {
                "status": "success",
                "message": "Sincronização concluída com sucesso.",
                "participants_upserted": len(participants_rows),
                "ranking_upserted": len(ranking_snapshot_rows),
                "matches_upserted": len(matches_rows),
                "finished_at": now_iso(),
            },
        )
    except Exception as exc:
        client.patch_eq(
            "bolao_sync_runs",
            "run_id",
            run_id,
            {
                "status": "error",
                "message": str(exc)[:900],
                "participants_upserted": len(participants_rows),
                "ranking_upserted": len(ranking_snapshot_rows),
                "matches_upserted": len(matches_rows),
                "finished_at": now_iso(),
            },
        )
        raise

    print("[shadow-sync] Supabase sincronizado com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
