import json
import os
import re
from pathlib import Path
import openpyxl

def slugify(s):
    if not s: return ""
    return str(s).strip().lower().replace(" ", "-")

def normalize(s):
    if s is None:
        return ""
    text = str(s).strip()
    if text == "None":
        return ""
    return text

def format_numeric_cell(value):
    text = normalize(value)
    if text == "":
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return str(number).rstrip("0").rstrip(".")

def main():
    print("=== INICIANDO PARSER OFICIAL DO EXCEL ===")
    project_root = Path(os.path.dirname(__file__)).parent
    file_path = project_root / "data" / "Bolao_UEFA_25_26_OFICIAL.xlsx"
    if not os.path.exists(file_path):
        print(f"ERRO: Não encontrou {file_path}")
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)

    # 1. PARSE 1a FASE (For Base Participants and Matchday 1)
    ws_1a = wb['1a FASE'] if '1a FASE' in wb.sheetnames else None
    
    participants = []
    part_meta = {} # name -> {artilheiro, garcom, favorito}

    if ws_1a:
        # Participantes estão na Row 2, a partir da Coluna 3.
        # Há uma repetição do bloco de participantes no arquivo oficial, então
        # paramos no primeiro nome repetido para evitar duplicação de palpites.
        r_palpite = 2
        col_start = 3
        seen_participants = set()
        while col_start < 60:
            p_name = normalize(ws_1a.cell(row=r_palpite, column=col_start).value)
            if p_name == "":
                break
            if p_name in seen_participants:
                break
            participants.append({"name": p_name, "col": col_start})
            seen_participants.add(p_name)
            col_start += 1

        # Metadados
        r_art = 5
        r_gar = 6
        r_fav = 7
        for p in participants:
            c = p["col"]
            part_meta[p["name"]] = {
                "artilheiro": normalize(ws_1a.cell(row=r_art, column=c).value),
                "garcom": normalize(ws_1a.cell(row=r_gar, column=c).value),
                "favorito": normalize(ws_1a.cell(row=r_fav, column=c).value)
            }

    # 2. PARSE RANKING TAB
    ranking_list = []
    ws_rank = wb['Ranking'] if 'Ranking' in wb.sheetnames else None
    if ws_rank:
        for r in range(5, 50):
            name = normalize(ws_rank.cell(row=r, column=4).value)
            if not name:
                continue
            
            try:
                total = float(ws_rank.cell(row=r, column=5).value or 0)
                p_1a = float(ws_rank.cell(row=r, column=6).value or 0)
                p_po = float(ws_rank.cell(row=r, column=7).value or 0)
                p_o8 = float(ws_rank.cell(row=r, column=8).value or 0)
                p_sc = float(ws_rank.cell(row=r, column=12).value or 0)
            except:
                total, p_1a, p_po, p_o8, p_sc = 0, 0, 0, 0, 0

            favorito = normalize(ws_rank.cell(row=r, column=13).value)
            garcom = normalize(ws_rank.cell(row=r, column=14).value)
            artilheiro = normalize(ws_rank.cell(row=r, column=15).value)

            ranking_list.append({
                "participant_id": slugify(name),
                "name": name,
                "total_points": total,
                "first_phase_points": p_1a,
                "playoff_points": p_po,
                "round_of_16_points": p_o8,
                "superclassic_points": p_sc,
                "hope_solo_hits": 0,
                "favorite_team": favorito if favorito else "-",
                "scorer_pick": artilheiro if artilheiro else "-",
                "assist_pick": garcom if garcom else "-"
            })

    # Sort Ranking by Total
    ranking_list.sort(key=lambda x: x["total_points"], reverse=True)

    # 3. EXTRAIR PHASES (Palpites)
    phases = {}

    matches_list = []

    def extract_knockout_block(ws, header_row, pick_row_start, pick_row_end, official_row, leg_label):
        fixtures = []
        for c in range(3, 200, 5):
            match_lbl = normalize(ws.cell(row=header_row, column=c).value)
            if not match_lbl or " x " not in match_lbl:
                continue

            official_h = format_numeric_cell(ws.cell(row=official_row, column=c).value)
            official_sep = normalize(ws.cell(row=official_row, column=c + 1).value).lower()
            official_a = format_numeric_cell(ws.cell(row=official_row, column=c + 2).value)
            official_res = (
                f"{official_h}x{official_a}"
                if official_h != "" and official_a != "" and official_sep == "x"
                else "-"
            )

            fixture = {
                "label": match_lbl,
                "leg": leg_label,
                "official": official_res,
                "picks": []
            }

            for r in range(pick_row_start, pick_row_end + 1):
                p_name = normalize(ws.cell(row=r, column=2).value)
                if not p_name or p_name.lower() in ["oficial", "resultado", "resultado oficial", "placar"]:
                    continue

                ph = format_numeric_cell(ws.cell(row=r, column=c).value)
                sep = normalize(ws.cell(row=r, column=c + 1).value).lower()
                pa = format_numeric_cell(ws.cell(row=r, column=c + 2).value)
                pts = format_numeric_cell(ws.cell(row=r, column=c + 4).value)

                if sep == "x" and ph != "" and pa != "":
                    fixture["picks"].append({
                        "participant": p_name,
                        "pick": f"{ph}x{pa}",
                        "rank_value": pts
                    })

            fixtures.append(fixture)
        return fixtures

    def extract_knockout(sheet_name, phase_key):
        if sheet_name not in wb.sheetnames:
            return
        ws = wb[sheet_name]
        fixtures = []
        fixtures.extend(
            extract_knockout_block(
                ws=ws,
                header_row=2,
                pick_row_start=3,
                pick_row_end=23,
                official_row=24,
                leg_label="IDA"
            )
        )
        fixtures.extend(
            extract_knockout_block(
                ws=ws,
                header_row=26,
                pick_row_start=27,
                pick_row_end=47,
                official_row=48,
                leg_label="VOLTA"
            )
        )

        if fixtures:
            phases[phase_key] = {"fixtures": fixtures}

    extract_knockout('PLAYOFF_1aFASE', 'PLAYOFF')
    extract_knockout('OITAVAS', 'ROUND_OF_16')

    # LEAGUE PHASE
    if ws_1a:
        ws_form = wb['Form_PrimeiraFase'] if 'Form_PrimeiraFase' in wb.sheetnames else None
        fixtures_1a = []
        r = 8
        while r < 200:
            md = normalize(ws_1a.cell(row=r, column=1).value)
            if not md: break
            
            off = normalize(ws_1a.cell(row=r, column=2).value)
            
            # Extrair título original do confronto a partir da aba Form_PrimeiraFase
            real_match_title = ""
            if ws_form:
                col_index = r - 4
                real_val = ws_form.cell(row=1, column=col_index).value
                if real_val:
                    real_match_title = str(real_val).strip()
            
            if not real_match_title:
                real_match_title = f"{md} - Jogo {r-7}"

            h = ""
            a = ""
            if " x " in real_match_title:
                h = real_match_title.split(" x ")[0]
                a = real_match_title.split(" x ")[1]
            
            fixture = {
                "matchday": md,
                "label": real_match_title,
                "home": h,
                "away": a,
                "official": off,
                "picks": []
            }
            
            for p in participants:
                pick_val = normalize(ws_1a.cell(row=r, column=p["col"]).value)
                if pick_val:
                    fixture["picks"].append({
                        "participant": p["name"],
                        "pick": pick_val,
                        "rank_value": ""
                    })
            if fixture["picks"]:
                fixtures_1a.append(fixture)
            r += 1
            
        if fixtures_1a:
            phases["LEAGUE"] = {"fixtures": fixtures_1a}


    # Calculate Hope Solo Hits
    hope_solos = {p["name"]: 0 for p in ranking_list}
    for phase_key, phase_data in phases.items():
        for fixture in phase_data["fixtures"]:
            off = fixture.get("official", "")
            if not off or off == "-" or off == "None": continue

            def is_hit(p, o):
                if not p or p == "None": return False
                if p == o: return True
                if "x" in p and "x" in o:
                    try:
                        ph, pa = map(int, p.split("x"))
                        oh, oa = map(int, o.split("x"))
                        if (ph > pa and oh > oa) or (ph < pa and oh < oa) or (ph == pa and oh == oa):
                            return True
                    except: pass
                return False

            correct_picks = []
            for pk in fixture["picks"]:
                if is_hit(pk["pick"], off):
                    correct_picks.append(pk["participant"])
            
            if len(correct_picks) == 1:
                hope_solos[correct_picks[0]] = hope_solos.get(correct_picks[0], 0) + 1
                        
    for r in ranking_list:
        r["hope_solo_hits"] = hope_solos.get(r["name"], 0)

    # OUTPUT JSON
    out_dir = project_root / "api"
    out_dir.mkdir(exist_ok=True)

    ranking_json = {
        "season": 2026,
        "ranking": ranking_list,
        "phases": phases
    }

    with open(out_dir / "ranking.json", "w", encoding="utf-8") as f:
        json.dump(ranking_json, f, ensure_ascii=False, indent=2)

    with open(out_dir / "ranking.js", "w", encoding="utf-8") as f:
        f.write("window.backtestData = " + json.dumps(ranking_json, ensure_ascii=False) + ";\n")

    with open(out_dir / "matches.json", "w", encoding="utf-8") as f:
        json.dump({"matches": matches_list}, f, ensure_ascii=False, indent=2)

    with open(out_dir / "matches.js", "w", encoding="utf-8") as f:
        f.write("window.apiMatchesData = " + json.dumps({"matches": matches_list}, ensure_ascii=False) + ";\n")

    print(f"=== SUCESSO! api/ranking.js E api/matches.js GERAÇÃO CONCLUÍDA ({len(ranking_list)} particpantes) ===")

if __name__ == "__main__":
    main()
