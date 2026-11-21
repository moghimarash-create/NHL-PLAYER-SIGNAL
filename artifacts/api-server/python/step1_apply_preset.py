"""Syncs scheduled NHL games (DEG1 = 88 • 28 GEMINI / AIR) from nhl_schedule_2024_2027.json
into local JSON backup (artifacts/api-server/data/nhl_sheet_input_backup.json) and, ONLY if
NHL_PLAYER_INPUT_SHEET_ID + GOOGLE_SERVICE_ACCOUNT_JSON are set, into the dedicated NHL Google Sheet.
"""
import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone

from _lib.runner import emit_result, log
from _lib.sheets import open_sheet

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(HERE, "..", "data"))
SPREADSHEET_ID = os.environ.get("NHL_PLAYER_INPUT_SHEET_ID", "").strip()
SCHEDULE_TAB = "NHL_SCHEDULE_2024_2027"
DEG1_DEFAULT = 88  # 28 GEMINI / Element AIR

WEEKDAY_NUM = {
    "MONDAY": 9, "TUESDAY": 5, "WEDNESDAY": 8,
    "THURSDAY": 4, "FRIDAY": 7, "SATURDAY": 6, "SUNDAY": 3,
}
ARCANUM_TO_CARD = {
    1: "Scorpio - [Water]",    2: "Leo - [Fire]",
    3: "Gemini - [Air]",       4: "Aries - [Fire]",
    5: "Gemini - [Air]",       6: "Gemini - [Air]",
    7: "Capricorn - [Earth]",  8: "Libra - [Air]",
    9: "Capricorn - [Earth]",  10: "Gemini - [Air]",
    11: "Taurus - [Earth]",    12: "Cancer - [Water]",
    13: "Gemini - [Air]",      14: "Leo - [Fire]",
    15: "Aries - [Fire]",      16: "Gemini - [Air]",
    17: "Taurus - [Earth]",    18: "Scorpio - [Water]",
    19: "Capricorn - [Earth]", 20: "Leo - [Fire]",
    21: "Aquarius - [Air]",    22: "Virgo - [Earth]",
}
ELEMENT_QUALITIES = {
    "Fire": ("HOT", "DRY"),
    "Earth": ("COLD", "DRY"),
    "Air": ("HOT", "MOIST"),
    "Water": ("COLD", "MOIST"),
}


def _parse_date(s: str) -> str:
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def _calc_f_and_el(date_ymd: str, weekday_str: str, deg1: int, deg2: int, deg3: int):
    try:
        y, m, d = [int(x) for x in str(date_ymd).strip().split("-")]
        d_sum = sum(int(c) for c in f"{y:04d}{m:02d}{d:02d}")
    except Exception:
        d_sum = 20
    w_num = WEEKDAY_NUM.get(str(weekday_str).strip().upper(), 3)
    fh = w_num + d_sum
    f1, f2, f3 = int(deg1) + fh, int(deg2) + fh, int(deg3) + fh
    main_pairs, sub_pairs = [], []
    for p in (f1, f2, f3):
        r = int(p) % 22
        arc = 22 if r == 0 else r
        card = ARCANUM_TO_CARD[arc]
        elem = re.search(r"\[(\w+)\]", card).group(1)
        prim, sec = ELEMENT_QUALITIES[elem]
        main_pairs.append((arc, prim))
        sub_pairs.append((arc, sec))

    def _net(pairs, pos_l, neg_l):
        pos = sum(n for n, t in pairs if t == pos_l)
        neg = sum(n for n, t in pairs if t == neg_l)
        diff = pos - neg
        return f"{diff} {pos_l}" if diff > 0 else (f"{abs(diff)} {neg_l}" if diff < 0 else "0 NEUTRAL")

    return f1, f2, f3, _net(main_pairs, "HOT", "COLD"), _net(sub_pairs, "MOIST", "DRY")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", default="2026-11-20")
    ap.add_argument("--end-date", default="2026-11-21")
    ap.add_argument("--utc-control", default="0")
    ap.add_argument("--deg1", type=int, default=DEG1_DEFAULT)
    ap.add_argument("--deg2-mode", default="full")
    args = ap.parse_args()

    start_ymd = _parse_date(args.start_date) or "2026-11-20"
    end_ymd = _parse_date(args.end_date) or start_ymd
    if end_ymd < start_ymd:
        end_ymd = start_ymd
    utc_ctrl = str(args.utc_control).strip() in ("1", "true", "True", "yes")
    deg1_v = int(args.deg1) if args.deg1 else DEG1_DEFAULT

    try:
        gem_raw = json.load(open(os.path.join(HERE, "nhl_gem_sheet.json"), "r", encoding="utf-8"))["values"]
        team_meta = {}
        for r in gem_raw[1:]:
            if r and r[0]:
                team_meta[str(r[0]).strip()] = {
                    "deg2_full": int(r[3]),
                    "arena": str(r[7]),
                    "deg3_arena": int(r[13]),
                    "code": str(r[17]),
                    "lat": str(r[21]),
                    "lon": str(r[22]),
                    "tz": str(r[23]),
                    "deg2_code": int(r[24]),
                }

        sched_rows = json.load(open(os.path.join(HERE, "nhl_schedule_2024_2027.json"), "r", encoding="utf-8"))["values"]
        matched = [r for r in sched_rows[1:] if r and start_ymd <= str(r[0]).strip() <= end_ymd]
        if not matched:
            emit_result(ok=False, rows_written=0, error=f"No NHL games scheduled between {start_ymd} and {end_ymd}")
            return 1

        use_code_deg2 = str(args.deg2_mode).strip().lower() == "code"
        headers = [
            "DATE", "MATCHUP", "WEEKDAY", "TEAM", "ROLE", "HOST_TEAM",
            "DEG1", "DEG2", "ARENA_DEG3", "F", "F2", "F3", "EL1", "EL2",
            "ARENA_NAME", "Time", "Zone", "Lat", "Lon", "OPPONENT", "TEAM_SCORE", "OPP_SCORE", "WINNER",
        ]
        out_rows = [headers]
        preview_games = []

        for idx_g, r in enumerate(matched, 1):
            d_iso, wk, s_lbl, home_t, away_t = str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])
            hp, ap, done, arena_in = int(r[5] or 0), int(r[6] or 0), bool(r[7]), str(r[8] or "")
            hm = team_meta.get(home_t, {})
            am = team_meta.get(away_t, {})
            h_deg2 = hm.get("deg2_code" if use_code_deg2 else "deg2_full", 0)
            a_deg2 = am.get("deg2_code" if use_code_deg2 else "deg2_full", 0)
            arena_deg3 = hm.get("deg3_arena", 0)
            arena_nm = arena_in or hm.get("arena", "")
            tz_str = "UTC" if utc_ctrl else hm.get("tz", "America/New_York")
            tm_str = "00:00" if utc_ctrl else "19:30"
            win_nm = (home_t if hp > ap else away_t) if done else ""

            hf1, hf2, hf3, hel1, hel2 = _calc_f_and_el(d_iso, wk, deg1_v, h_deg2, arena_deg3)
            af1, af2, af3, ael1, ael2 = _calc_f_and_el(d_iso, wk, deg1_v, a_deg2, arena_deg3)

            out_rows.append([
                d_iso, f"{home_t} vs {away_t}", wk, home_t, "HOME", home_t,
                deg1_v, h_deg2, arena_deg3, hf1, hf2, hf3, hel1, hel2,
                arena_nm, tm_str, tz_str, hm.get("lat", ""), hm.get("lon", ""),
                away_t, str(hp) if done else "", str(ap) if done else "", win_nm,
            ])
            out_rows.append([
                d_iso, f"{away_t} @ {home_t}", wk, away_t, "AWAY", home_t,
                deg1_v, a_deg2, arena_deg3, af1, af2, af3, ael1, ael2,
                arena_nm, tm_str, tz_str, hm.get("lat", ""), hm.get("lon", ""),
                home_t, str(ap) if done else "", str(hp) if done else "", win_nm,
            ])

            preview_games.append({
                "date": d_iso,
                "weekday": wk,
                "time": tm_str,
                "homeTeam": f"{home_t} (EL: {hel1}, {hel2})",
                "awayTeam": f"{away_t} (EL: {ael1}, {ael2})",
                "deg1": deg1_v,
                "homeDeg2": str(h_deg2),
                "awayDeg2": str(a_deg2),
                "arenaDeg3": str(arena_deg3),
                "arena": arena_nm,
                "tz": tz_str,
                "lat": hm.get("lat", ""),
                "lon": hm.get("lon", ""),
                "season": s_lbl,
                "gameType": "Regular Season",
                "homeScore": str(hp) if done else "",
                "awayScore": str(ap) if done else "",
                "winner": win_nm,
            })

        os.makedirs(DATA_DIR, exist_ok=True)
        local_backup_path = os.path.join(DATA_DIR, "nhl_preset_sheet1_backup.json")
        json.dump(
            {
                "deg1": deg1_v,
                "deg1Sign": "28 GEMINI",
                "deg1Element": "AIR",
                "startDate": start_ymd,
                "endDate": end_ymd,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "rows": out_rows,
            },
            open(local_backup_path, "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=2,
        )

        synced_remote = False
        if SPREADSHEET_ID and os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
            ss = open_sheet(SPREADSHEET_ID)
            ws = ss.sheet1
            ws.clear()
            ws.update(range_name=f"A1:W{len(out_rows)}", values=out_rows, value_input_option="RAW")
            synced_remote = True

        msg = (
            f"Prepared {len(matched)} NHL games ({len(out_rows)-1} Home/Away rows: {start_ymd} to {end_ymd}, "
            f"DEG1={deg1_v} • 28 GEMINI / AIR) — "
            f"{'Synced to NHL Google Sheet + Local JSON' if synced_remote else 'Saved to Local JSON Backup (live NBA sheets untouched)'}"
        )
        log(msg)
        emit_result(ok=True, rows_written=len(out_rows) - 1, message=msg, extra={"games": preview_games[:50]})
        return 0
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        emit_result(ok=False, rows_written=0, error=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
