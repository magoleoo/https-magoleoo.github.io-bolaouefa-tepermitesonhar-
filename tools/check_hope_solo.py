#!/usr/bin/env python3
import json
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    ranking_path = project_root / "api" / "ranking.json"

    if not ranking_path.exists():
        print(f"Arquivo não encontrado: {ranking_path}")
        return 1

    with ranking_path.open("r", encoding="utf-8") as handler:
        payload = json.load(handler)

    ranking_rows = payload.get("ranking", [])
    phases = payload.get("phases", {})
    matches_analyzed = sum(len(phase.get("fixtures", [])) for phase in phases.values())

    hope_solos = sorted(
        (
            {
                "name": row.get("name", ""),
                "hits": int(row.get("hope_solo_hits", 0) or 0),
            }
            for row in ranking_rows
            if int(row.get("hope_solo_hits", 0) or 0) > 0
        ),
        key=lambda item: (-item["hits"], item["name"]),
    )

    print(f"Partidas analisadas: {matches_analyzed}")
    if not hope_solos:
        print("Nenhum Hope Solo identificado.")
        return 0

    print("Hope Solo por participante:")
    for row in hope_solos:
        print(f"- {row['name']}: {row['hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
