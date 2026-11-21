#!/usr/bin/env python3
"""
Populate dedicated NHL-PLAYER-SIGNAL Google Spreadsheets (5 Input tabs + 5 Calculation tabs):
  - NHL-PLAYERS-GEOMANTIC-INPUT : 1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE
  - NHL-PLAYERS-CALCULATION     : 16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs
"""
import os, sys, json, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PUB_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "calc-dashboard", "public"))
sys.path.insert(0, HERE)

INPUT_SHEET_ID = "1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE"
CALC_SHEET_ID  = "16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs"

EGEM_MAP = {
    'A':1,'B':2,'C':20,'D':4,'E':5,'F':80,'G':3,'H':8,'I':10,'J':10,
    'K':20,'L':30,'M':40,'N':50,'O':70,'P':80,'Q':100,'R':200,'S':60,
    'T':400,'U':6,'V':6,'W':6,'X':70,'Y':10,'Z':7
}
LETTER_EL = {}
for ch in "EIJYOSUVW": LETTER_EL[ch] = 0
for ch in "DGLQZ":     LETTER_EL[ch] = 1
for ch in "ACKFPMNX":  LETTER_EL[ch] = 2
for ch in "BHRT":      LETTER_EL[ch] = 3

SIGN_NAMES_12 = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS", "PISCES"
]

def egem(s):
    return sum(EGEM_MAP.get(ch, 0) for ch in str(s or "").upper())

def word_fawe(s):
    out = [0, 0, 0, 0]
    for ch in str(s or "").upper():
        if ch in LETTER_EL:
            out[LETTER_EL[ch]] += 1
    return f"{out[0]}F-{out[1]}A-{out[2]}W-{out[3]}E"

def jersey_eff_num(j_str):
    s = str(j_str or "").strip()
    if s == "00": return 20
    if s == "0": return 10
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits: return 10
    v = int(digits)
    return 10 if v == 0 else v

def deg_sign_label(deg):
    d = int(deg) % 360
    return f"{(d % 30) + 1} {SIGN_NAMES_12[d // 30]}"

def run_gsheets_batch(spreadsheet_id, ops):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(ops, tf, ensure_ascii=False)
        tpath = tf.name
    try:
        subprocess.run(["gsheets", "mutate", "batch", spreadsheet_id, "-f", tpath], check=True)
    finally:
        if os.path.exists(tpath):
            os.remove(tpath)

def main():
    pb = json.load(open(os.path.join(HERE, "nhl_players_2010_2027.json"), "r", encoding="utf-8"))
    teams_gem = json.load(open(os.path.join(HERE, "nhl_gem_sheet.json"), "r", encoding="utf-8"))["values"]
    comp = json.load(open(os.path.join(PUB_DIR, "player_modes_comparison.json"), "r", encoding="utf-8"))
    preds_c = json.load(open(os.path.join(PUB_DIR, "player_nhl_preds_mode_c.json"), "r", encoding="utf-8"))["games"]
    preds_b = json.load(open(os.path.join(PUB_DIR, "player_nhl_preds_mode_b.json"), "r", encoding="utf-8"))["games"]
    preds_a = json.load(open(os.path.join(PUB_DIR, "player_nhl_preds_mode_a.json"), "r", encoding="utf-8"))["games"]

    # Find best mode dynamically
    best_mk = max(["mode_c", "mode_b", "mode_a"], key=lambda m: comp[m]["total_2427"]["pct"])

    # 1. Sheet1: Active Slate (2026-11-20 or latest pending date)
    slate_date = "2026-11-20"
    slate_games = [g for g in preds_c if g["d"] == slate_date]
    if not slate_games:
        pend = [g for g in preds_c if not g["done"]]
        slate_date = pend[0]["d"] if pend else preds_c[-1]["d"]
        slate_games = [g for g in preds_c if g["d"] == slate_date]

    sheet1_rows = [["DATE", "WEEKDAY", "DEG1", "HOME_TEAM", "AWAY_TEAM", "ARENA", "PUCKDROP_LOCAL", "DEG3_MODE"]]
    for g in slate_games:
        sheet1_rows.append([g["d"], g["day"], 88, g["h"], g["a"], g.get("venue", ""), "19:30:00", f"{best_mk.upper()}"])

    # 2. NHL-PLAYERS-GEM (all active NHL players across 32 rosters)
    stp_2627 = {}
    for k, lst in pb["season_team_players"].items():
        if k.startswith("2026-27||") or k.startswith("2025-26||"):
            for r in lst:
                if k.startswith("2026-27||") or r["pid"] not in stp_2627:
                    stp_2627[r["pid"]] = float(r.get("mpg") or 15.0)

    pgem_rows = [[
        "PLAYER_NO", "TEAM_NAME", "TEAM_CODE", "FULL_NAME", "JERSEY_NAME", "JERSEY_NO",
        "JERSEY_EFF_NO", "POS", "INJURY_STATUS", "PREGAME_TOI", "FULL_NAME_GEM",
        "DEG2_FULL_NAME", "DEG2_SIGN", "JERSEY_NAME_GEM", "DEG3_MODE_A_NAME",
        "DEG3_MODE_B_NAME_PLUS_NO", "DEG3_MODE_C_NO_ONLY", "NAM_ELE_FAWE", "ESPN_PLAYER_ID"
    ]]
    pno = 0
    for tname in sorted(pb["live_rosters"].keys()):
        plist = sorted(pb["live_rosters"][tname], key=lambda x: (x.get("pos") == "G", stp_2627.get(x["pid"], 12.0)), reverse=True)
        for p in plist:
            pno += 1
            fn = p.get("full_name", "")
            jn = p.get("jersey_name", "")
            jno = str(p.get("jersey") or "0")
            jeff = jersey_eff_num(jno)
            fgem = egem(fn)
            d2 = fgem % 360
            jgem = egem(jn)
            da = jgem % 360
            db = (jgem + jeff) % 360
            dc = jeff % 360
            toi = round(stp_2627.get(p["pid"], 55.0 if p.get("pos") == "G" else 14.5), 1)
            pgem_rows.append([
                pno, tname, p.get("team_code", ""), fn, jn, jno,
                jeff, p.get("pos", "F"), p.get("status", "Healthy"), toi, fgem,
                d2, deg_sign_label(d2), jgem, da, db, dc, word_fawe(fn), p["pid"]
            ])

    # 3. DECAN_TABLE_36
    decan_rows = json.load(open("/tmp/decan36.json", "r", encoding="utf-8")) if os.path.exists("/tmp/decan36.json") else []

    # 4. NHL_SCHEDULE_2025_2027 (compact 2025-2027 schedule rows)
    team_meta_by_name = {str(r[1]): r for r in teams_gem[1:]}
    sched_rows = [[
        "DATE", "PRIC-CH", "WEEKDAY", "HOME_TEAM", "AWAY_TEAM", "DEG1",
        "HOME_DEG2", "AWAY_DEG2", "ARENA_DEG3", "ARENA_NAME", "Time", "Zone",
        "Lat", "Lon", "SEASON", "GAME_TYPE", "HOME_SCORE", "AWAY_SCORE", "WINNER", "GAME_ID"
    ]]
    for g in preds_c:
        if g["d"] < "2025-01-01":
            continue
        y, m, d = map(int, g["d"].split("-"))
        d_slash = f"{m}/{d}/{y}"
        tm_h = team_meta_by_name.get(g["h"], [0]*22)
        tm_a = team_meta_by_name.get(g["a"], [0]*22)
        if g["done"]:
            diff = g["hp"] - g["ap"]
            pch = f"{g['h']} {g['hp']}-{g['ap']} {g['a']} ({diff:+d} | WIN: {g['aw']})"
            hs, as_v, win = g["hp"], g["ap"], g["aw"]
        else:
            pch, hs, as_v, win = "PENDING", "", "", ""
        sched_rows.append([
            d_slash, pch, g["day"], g["h"], g["a"], 88,
            tm_h[6], tm_a[6], tm_h[16], g.get("venue", ""), "7:30 PM", tm_h[21] or "America/New_York",
            tm_h[19], tm_h[20], g["s"], "Regular Season", hs, as_v, win, g["n"]
        ])

    print(f"Writing NHL-PLAYERS-GEOMANTIC-INPUT ({len(pgem_rows)-1} players, {len(sched_rows)-1} schedule games)...")
    in_ops = [
        {"op": "write", "range": "'Sheet1'!A1", "data": sheet1_rows},
        {"op": "write", "range": "'NHL-PLAYERS-GEM'!A1", "data": pgem_rows},
        {"op": "write", "range": "'TEAMS'!A1", "data": teams_gem},
    ]
    if decan_rows:
        in_ops.append({"op": "write", "range": "'DECAN_TABLE_36'!A1", "data": decan_rows})
    run_gsheets_batch(INPUT_SHEET_ID, in_ops)
    # Write schedule in chunks of 1500 rows to keep payload crisp
    for start_i in range(0, len(sched_rows), 1500):
        chunk = sched_rows[start_i:start_i+1500]
        if start_i == 0:
            run_gsheets_batch(INPUT_SHEET_ID, [{"op": "write", "range": "'NHL_SCHEDULE_2025_2027'!A1", "data": chunk}])
        else:
            run_gsheets_batch(INPUT_SHEET_ID, [{"op": "append", "range": "'NHL_SCHEDULE_2025_2027'!A1", "data": chunk}])

    # 5. Calculation Sheet: DEG3_Mode_Benchmark + Game_Predictions_Mode{C,B,A} + Active_Player_Calculations
    bench_rows = [[
        "MODE_KEY", "DEG1", "DEG2_FORMULA", "DEG3_FORMULA",
        "2024_27_WIN_PCT", "2024_27_RECORD", "VIP_WIN_PCT", "VIP_RECORD",
        "2024_25_PCT", "2025_26_PCT", "2026_27_LIVE_PCT", "2026_27_RECORD", "RECENT_50_PCT", "NOTES"
    ]]
    f_desc = {
        "mode_c": ("Jersey_No_Eff mod 360 (جایگزین کامل)", "Orthogonal F1/F2/F3 — Pure Jersey Number"),
        "mode_b": ("(EnglishGem(Jersey_Name) + Jersey_No_Eff) mod 360 (جمع با نام پیراهن)", "Combined Jersey Name + Number"),
        "mode_a": ("EnglishGem(Jersey_Name) mod 360 (فقط نام پیراهن)", "Baseline Jersey Surname Gematria"),
    }
    for mk in ["mode_c", "mode_b", "mode_a"]:
        st = comp[mk]
        t = st["total_2427"]; v = st["vip_2427"]; s24 = st["s2425"]; s25 = st["s2526"]; s26 = st["s2627"]; l50 = st["last50"]
        note_prefix = "BEST OVERALL (Default Recommended) — " if mk == best_mk else ""
        bench_rows.append([
            mk.upper(), 88, "EnglishGem(Full_Name) mod 360", f_desc[mk][0],
            f"{t['pct']}%", f"{t['w']}/{t['n']}",
            f"{v['pct']}%", f"{v['w']}/{v['n']}",
            f"{s24['pct']}% ({s24['w']}/{s24['n']})",
            f"{s25['pct']}% ({s25['w']}/{s25['n']})",
            f"{s26['pct']}%", f"{s26['w']}/{s26['n']}",
            f"{l50['pct']}% ({l50['w']}/{l50['n']})",
            note_prefix + f_desc[mk][1]
        ])

    def build_pred_tab_rows(g_list):
        rows = [[
            "GAME_NO", "DATE", "WEEKDAY", "SEASON", "HOME_TEAM", "AWAY_TEAM", "SCORE",
            "PICK_WINNER", "TWIN_VOTES", "TWIN_PCT", "NATURAL_POOL", "PLAYER_F30",
            "4CH_FAV_VOTES", "WEEKLY_DTP", "LOG5_ELEMENT", "TRAP_GUARD",
            "QUALIFIED_FINAL", "VIP_SIGNAL", "RESULT_STATUS"
        ]]
        for g in g_list:
            if not g.get("f1_wtp") and not (not g["done"] and g["d"] <= "2026-11-25"):
                continue
            idx3 = g.get("idx3") or {}
            fav_v = idx3.get("vh", 0) if g.get("ph") else idx3.get("va", 0)
            wtp = g.get("wtp") or {}
            rows.append([
                g["n"], g["d"], g["day"], g["s"], g["h"], g["a"], g["sc"],
                g["sys_win"], g["twVotes"], g["twPct"],
                "NAT" if g.get("is_nat") else "CAP7",
                g.get("f30", 0), f"{fav_v}/4", wtp.get("dtp", 0), wtp.get("mel", ""),
                "CLEAN" if not g.get("trap_tag") else g.get("trap_tag"),
                "YES" if g.get("f1_wtp") else "NO",
                "VIP" if g.get("vip_idx3") else "",
                g["st"]
            ])
        return rows

    # Active_Player_Calculations for recent + today's games (2026-11-18 .. 2026-11-21)
    by_n_a = {g["n"]: g for g in preds_a}
    by_n_b = {g["n"]: g for g in preds_b}
    act_rows = [[
        "DATE", "MATCHUP", "SIDE", "TEAM", "PLAYER_FULL_NAME", "JERSEY_NAME", "JERSEY_NO",
        "ROLE", "PREGAME_TOI", "DEG1", "DEG2_FULL_NAME", "DEG3_MODE_A", "DEG3_MODE_B", "DEG3_MODE_C",
        "ELE_P_FAWE (ModeC)", "ELE_FINAL_FAWE (ModeC)", "QUALITY_FIN (ModeC)", "DECAN (ModeC)", "NIGHTLY_POWER (ModeC)"
    ]]
    for g in preds_c:
        if not ("2026-11-18" <= g["d"] <= "2026-11-21"):
            continue
        ga = by_n_a.get(g["n"], {})
        gb = by_n_b.get(g["n"], {})
        d3a_map = {p["pid"]: p["d3"] for p in (ga.get("h_players") or []) + (ga.get("a_players") or [])}
        d3b_map = {p["pid"]: p["d3"] for p in (gb.get("h_players") or []) + (gb.get("a_players") or [])}
        matchup = f"{g['a']} @ {g['h']}"
        for side_lbl, tm_lbl, plist in [("HOME", g["h"], g.get("h_players") or []), ("AWAY", g["a"], g.get("a_players") or [])]:
            for pl in plist:
                pid = pl["pid"]
                role = "GOALIE_1" if pl.get("pos") == "G" else ("TOP_LINE" if pl.get("st") else f"SKATER ({pl.get('pos','F')})")
                act_rows.append([
                    g["d"], matchup, side_lbl, tm_lbl, pl["fn"], pl["jn"], pl["no"],
                    role, pl["mpg"], 88, pl["d2"],
                    d3a_map.get(pid, 0), d3b_map.get(pid, 0), pl["d3"],
                    pl["ep"], pl["ef"], pl["qf"], pl["dec"], pl["pwr"]
                ])

    print(f"Writing NHL-PLAYERS-CALCULATION (Benchmark + ModeC/B/A + {len(act_rows)-1} active player rows)...")
    calc_ops = [
        {"op": "write", "range": "'DEG3_Mode_Benchmark'!A1", "data": bench_rows},
        {"op": "write", "range": "'Game_Predictions_ModeC'!A1", "data": build_pred_tab_rows(preds_c)},
        {"op": "write", "range": "'Game_Predictions_ModeB'!A1", "data": build_pred_tab_rows(preds_b)},
        {"op": "write", "range": "'Game_Predictions_ModeA'!A1", "data": build_pred_tab_rows(preds_a)},
        {"op": "write", "range": "'Active_Player_Calculations'!A1", "data": act_rows[:1800]},
    ]
    run_gsheets_batch(CALC_SHEET_ID, calc_ops)
    print("ALL 10 GOOGLE SHEETS TABS POPULATED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
