#!/usr/bin/env python3
"""
Fetch complete NHL player rosters (32 teams including Utah Mammoth), jersey names,
jersey numbers, injury statuses (OUT, IR, IR-LT, IR-NR, Suspension), seasonal
Time On Ice (TOI) stats (2009-10 through 2026-27), and 2026-27 game-by-game boxscores
from ESPN's sports/hockey/nhl endpoints, and build the NHL-PLAYERS-GEM database.
"""
import datetime
import json
import os
import time
import unicodedata
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

t0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(HERE, "..", "data"))
PUB_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "calc-dashboard", "public"))
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PUB_DIR, exist_ok=True)

EGEM_MAP = {
    "A": 1, "B": 2, "C": 20, "D": 4, "E": 5, "F": 80, "G": 3, "H": 8, "I": 10, "J": 10,
    "K": 20, "L": 30, "M": 40, "N": 50, "O": 70, "P": 80, "Q": 100, "R": 200, "S": 60,
    "T": 400, "U": 6, "V": 6, "W": 6, "X": 70, "Y": 10, "Z": 7,
}
SIGNS_12 = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS", "PISCES",
]

LETTER_EL = {}
for ch in "EIJYOSUVW":
    LETTER_EL[ch] = 0  # Fire
for ch in "DGLQZ":
    LETTER_EL[ch] = 1  # Air
for ch in "ACKFPMNX":
    LETTER_EL[ch] = 2  # Water
for ch in "BHRT":
    LETTER_EL[ch] = 3  # Earth


def clean_ascii(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip()


def egem(s):
    return sum(EGEM_MAP.get(ch, 0) for ch in clean_ascii(s).upper())


def deg_sign(deg):
    d = int(deg) % 360
    return f"{d % 30} {SIGNS_12[d // 30]}"


def jersey_eff_num(j_str, zero_rule=True):
    s = str(j_str or "").strip()
    if s == "00":
        return 20 if zero_rule else 100
    if s == "0":
        return 10 if zero_rule else 0
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return 10 if zero_rule else 0
    v = int(digits)
    if v == 0 and zero_rule:
        return 10
    return v


def word_fawe(s):
    out = [0, 0, 0, 0]
    for ch in clean_ascii(s).upper():
        if ch in LETTER_EL:
            out[LETTER_EL[ch]] += 1
    return out


ESPN_ABBR_TO_CANON = {
    "ANA": ("Anaheim Ducks", "ANA"),
    "BOS": ("Boston Bruins", "BOS"),
    "BUF": ("Buffalo Sabres", "BUF"),
    "CGY": ("Calgary Flames", "CGY"),
    "CAL": ("Calgary Flames", "CGY"),
    "CAR": ("Carolina Hurricanes", "CAR"),
    "CHI": ("Chicago Blackhawks", "CHI"),
    "COL": ("Colorado Avalanche", "COL"),
    "CBJ": ("Columbus Blue Jackets", "CBJ"),
    "CLS": ("Columbus Blue Jackets", "CBJ"),
    "DAL": ("Dallas Stars", "DAL"),
    "DET": ("Detroit Red Wings", "DET"),
    "EDM": ("Edmonton Oilers", "EDM"),
    "FLA": ("Florida Panthers", "FLA"),
    "LA": ("Los Angeles Kings", "LAK"),
    "LAK": ("Los Angeles Kings", "LAK"),
    "MIN": ("Minnesota Wild", "MIN"),
    "MTL": ("Montreal Canadiens", "MTL"),
    "MON": ("Montreal Canadiens", "MTL"),
    "NSH": ("Nashville Predators", "NSH"),
    "NAS": ("Nashville Predators", "NSH"),
    "NJ": ("New Jersey Devils", "NJD"),
    "NJD": ("New Jersey Devils", "NJD"),
    "NYI": ("New York Islanders", "NYI"),
    "NYR": ("New York Rangers", "NYR"),
    "OTT": ("Ottawa Senators", "OTT"),
    "PHI": ("Philadelphia Flyers", "PHI"),
    "PIT": ("Pittsburgh Penguins", "PIT"),
    "SJ": ("San Jose Sharks", "SJS"),
    "SJS": ("San Jose Sharks", "SJS"),
    "SEA": ("Seattle Kraken", "SEA"),
    "STL": ("St. Louis Blues", "STL"),
    "TB": ("Tampa Bay Lightning", "TBL"),
    "TBL": ("Tampa Bay Lightning", "TBL"),
    "TOR": ("Toronto Maple Leafs", "TOR"),
    "UTAH": ("Utah Mammoth", "UTA"),
    "UTA": ("Utah Mammoth", "UTA"),
    "ARI": ("Utah Mammoth", "UTA"),
    "PHX": ("Utah Mammoth", "UTA"),
    "VAN": ("Vancouver Canucks", "VAN"),
    "VGK": ("Vegas Golden Knights", "VGK"),
    "VEG": ("Vegas Golden Knights", "VGK"),
    "WSH": ("Washington Capitals", "WSH"),
    "WAS": ("Washington Capitals", "WSH"),
    "WPG": ("Winnipeg Jets", "WPG"),
    "ATL": ("Winnipeg Jets", "WPG"),
}

HIST_TEAM_NORM = {
    "Utah Hockey Club": "Utah Mammoth",
    "Arizona Coyotes": "Utah Mammoth",
    "Phoenix Coyotes": "Utah Mammoth",
    "Atlanta Thrashers": "Winnipeg Jets",
    "Montréal Canadiens": "Montreal Canadiens",
    "St Louis Blues": "St. Louis Blues",
}


def norm_team(name):
    s = str(name or "").strip()
    return HIST_TEAM_NORM.get(s, s)


def normalize_nhl_injury_status(injs):
    """
    Normalize ESPN NHL injury objects into canonical NHL statuses:
      Healthy, Day-To-Day, OUT, IR, IR-LT, IR-NR, Suspension
    """
    if not injs:
        return "Healthy", ""
    inj0 = injs[0] or {}
    raw_st = str(inj0.get("status") or "").strip()
    tp = inj0.get("type") or {}
    tp_abbr = str(tp.get("abbreviation") or "").strip().upper()
    tp_desc = str(tp.get("description") or tp.get("name") or "").strip().lower()
    det = inj0.get("details") or {}
    det_type = str(det.get("type") or "").strip()
    comment = f"{ str(inj0.get('shortComment') or '') } { str(inj0.get('longComment') or '') }".lower()

    low = raw_st.lower()
    if tp_abbr in ("OUT", "IR", "IR-LT", "IR-NR", "SUSP"):
        canon = "Suspension" if tp_abbr == "SUSP" else tp_abbr
        return canon, det_type
    if "suspens" in low or "suspend" in low or "suspens" in tp_desc:
        return "Suspension", det_type
    if low in ("ir-lt", "ltir") or "long-term injured reserve" in low or "ltir" in comment or "long-term injured reserve" in comment:
        return "IR-LT", det_type
    if low == "ir-nr" or "non-roster" in low or "ir-nr" in comment or "non-roster injured" in comment:
        return "IR-NR", det_type
    if low in ("ir", "injured reserve") or "injured reserve" in low:
        return "IR", det_type
    if low == "out":
        return "OUT", det_type
    if not raw_st:
        return "Healthy", det_type
    return raw_st, det_type


def is_inactive_nhl_status(status_str):
    s = str(status_str or "").strip().upper()
    if s in ("OUT", "IR", "IR-LT", "IR-NR", "LTIR", "INJURED RESERVE", "SUSPENSION", "SUSPENDED", "SUSP"):
        return True
    if s.startswith("IR-") or "INJURED RESERVE" in s or "SUSPENS" in s:
        return True
    return False


def parse_mmss_minutes(raw_s):
    s = str(raw_s or "").strip()
    if not s:
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return round(int(parts[0]) + int(parts[1]) / 60.0, 2)
        except Exception:
            return 0.0
    try:
        return round(float(s), 2)
    except Exception:
        return 0.0


def fetch_json(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
            return json.loads(raw)
        except Exception:
            if attempt == retries:
                return None
            time.sleep(0.25 * (attempt + 1))
    return None


# 1. Fetch all 32 live NHL team rosters
teams_meta = fetch_json("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams")
espn_teams = [t["team"] for t in teams_meta["sports"][0]["leagues"][0]["teams"]]
print(f"[1/5] Fetching {len(espn_teams)} live NHL rosters from sports/hockey/nhl...")

live_rosters = {}   # canon_team -> list of player dicts
player_master = {}  # pid -> master dict


def fetch_one_roster(tm_obj):
    tid = tm_obj["id"]
    abbr = str(tm_obj.get("abbreviation") or "").upper()
    canon_name, canon_code = ESPN_ABBR_TO_CANON.get(abbr, (norm_team(tm_obj.get("displayName", "")), abbr))
    d = fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/{tid}/roster")
    out = []
    seen_pids = set()
    for grp in (d or {}).get("athletes", []):
        items = grp.get("items", [grp]) if isinstance(grp, dict) and "items" in grp else ([grp] if isinstance(grp, dict) else [])
        for a in items:
            pid = str(a.get("id", ""))
            if not pid or pid in seen_pids:
                continue
            seen_pids.add(pid)
            full_name = clean_ascii(a.get("fullName") or a.get("displayName") or "")
            last_name = clean_ascii(a.get("lastName") or "")
            if not last_name and full_name:
                last_name = full_name.split()[-1]
            jersey_str = str(a.get("jersey") or "").strip()
            pos = (a.get("position") or {}).get("abbreviation", "")
            inj_status, inj_detail = normalize_nhl_injury_status(a.get("injuries") or [])
            rec = {
                "pid": pid,
                "full_name": full_name,
                "jersey_name": last_name,
                "jersey": jersey_str,
                "pos": pos,
                "team": canon_name,
                "team_code": canon_code,
                "status": inj_status,
                "injury_detail": inj_detail,
            }
            out.append(rec)
    return canon_name, out


with ThreadPoolExecutor(max_workers=16) as ex:
    for cname, plist in ex.map(fetch_one_roster, espn_teams):
        live_rosters[cname] = plist
        for p in plist:
            player_master[p["pid"]] = p.copy()

inactive_cnt = sum(1 for plist in live_rosters.values() for p in plist if is_inactive_nhl_status(p["status"]))
print(f"  Live NHL rosters loaded: {len(live_rosters)} teams, {len(player_master)} roster players ({inactive_cnt} excluded via OUT/IR/IR-LT/IR-NR/Suspension) ({time.time()-t0:.1f}s)")

# 2. Fetch seasonal athlete TOI stats for ESPN seasons 2010..2027 (2009-10 .. 2026-27)
print("[2/5] Fetching seasonal NHL player TOI stats 2009-10..2026-27 (seasons 2010..2027)...")


def season_label_from_espn_yr(yr):
    return f"{yr-1}-{str(yr)[-2:]}"


def fetch_season_stats(yr):
    s_lbl = season_label_from_espn_yr(yr)
    base_u = (
        "https://site.web.api.espn.com/apis/common/v3/sports/hockey/nhl/statistics/byathlete"
        f"?region=us&lang=en&contentorigin=espn&isqualified=false&limit=100&season={yr}&seasontype=2"
    )
    d1 = fetch_json(base_u + "&page=1")
    if not d1:
        return s_lbl, []
    pages = int((d1.get("pagination") or {}).get("pages", 1))
    cat_meta = {c.get("name"): (c.get("names") or []) for c in (d1.get("categories") or [])}
    gen_names = cat_meta.get("general", [])
    off_names = cat_meta.get("offensive", [])
    gp_idx = gen_names.index("games") if "games" in gen_names else 0
    toipg_idx = gen_names.index("timeOnIcePerGame") if "timeOnIcePerGame" in gen_names else 2
    toi_idx = gen_names.index("timeOnIce") if "timeOnIce" in gen_names else 7
    pts_idx = off_names.index("points") if "points" in off_names else 2

    all_aths = list(d1.get("athletes") or [])
    for pg in range(2, pages + 1):
        dp = fetch_json(base_u + f"&page={pg}")
        if dp and dp.get("athletes"):
            all_aths.extend(dp["athletes"])

    parsed = []
    for item in all_aths:
        ath = item.get("athlete") or {}
        pid = str(ath.get("id", ""))
        if not pid:
            continue
        full_name = clean_ascii(ath.get("displayName") or ath.get("fullName") or "")
        last_name = clean_ascii(ath.get("lastName") or "")
        if not last_name and full_name:
            last_name = full_name.split()[-1]
        pos = (ath.get("position") or {}).get("abbreviation", "")
        gp, toi_pg, tot_min, pts = 0, 0.0, 0.0, 0.0
        for cat in (item.get("categories") or []):
            vals = cat.get("values") or []
            cname_cat = cat.get("name")
            if cname_cat == "general":
                if gp_idx < len(vals) and vals[gp_idx] is not None:
                    gp = int(round(float(vals[gp_idx])))
                if toipg_idx < len(vals) and vals[toipg_idx] is not None:
                    # ESPN NHL timeOnIcePerGame is reported in seconds -> convert to minutes
                    toi_pg = round(float(vals[toipg_idx]) / 60.0, 2)
                if toi_idx < len(vals) and vals[toi_idx] is not None:
                    tot_min = round(float(vals[toi_idx]) / 60.0, 1)
            elif cname_cat == "offensive":
                if pts_idx < len(vals) and vals[pts_idx] is not None:
                    pts = round(float(vals[pts_idx]), 1)
        if tot_min <= 0 and gp > 0 and toi_pg > 0:
            tot_min = round(gp * toi_pg, 1)
        teams_arr = ath.get("teams") or []
        t_codes = []
        for t_obj in teams_arr:
            ab = str(t_obj.get("abbreviation") or "").upper()
            if ab in ESPN_ABBR_TO_CANON:
                t_codes.append(ESPN_ABBR_TO_CANON[ab])
        if not t_codes:
            ab = str(ath.get("teamShortName") or "").upper()
            if ab in ESPN_ABBR_TO_CANON:
                t_codes.append(ESPN_ABBR_TO_CANON[ab])
        for cname, ccode in t_codes:
            parsed.append({
                "pid": pid,
                "season": s_lbl,
                "team": cname,
                "team_code": ccode,
                "full_name": full_name,
                "jersey_name": last_name,
                "pos": pos,
                "gp": gp,
                "toi": toi_pg,
                "mpg": toi_pg,  # kept as alias for schema compatibility
                "tot_min": round(tot_min / max(1, len(t_codes)), 1),
                "ppg": round(pts / max(1, gp), 2),
            })
    return s_lbl, parsed


season_team_players = defaultdict(list)
all_season_rows = []

with ThreadPoolExecutor(max_workers=9) as ex:
    for s_lbl, rows in ex.map(fetch_season_stats, range(2010, 2028)):
        all_season_rows.extend(rows)
        for r in rows:
            season_team_players[(r["season"], r["team"])].append(r)

need_jersey_pids = set()
for key, lst in season_team_players.items():
    lst.sort(key=lambda x: (x["tot_min"], x["toi"], x["ppg"]), reverse=True)
    for r in lst[:14]:
        pid = r["pid"]
        if pid not in player_master:
            player_master[pid] = {
                "pid": pid,
                "full_name": r["full_name"],
                "jersey_name": r["jersey_name"],
                "jersey": "",
                "pos": r["pos"],
                "team": r["team"],
                "team_code": r["team_code"],
                "status": "Historical",
                "injury_detail": "",
            }
        if not player_master[pid].get("jersey"):
            need_jersey_pids.add(pid)

print(f"  Seasonal rows: {len(all_season_rows)} across {len(season_team_players)} team-seasons. Missing jersey PIDs to fetch: {len(need_jersey_pids)} ({time.time()-t0:.1f}s)")

# 3. Fetch jersey numbers for historical rotation players via ESPN common/v3/sports/hockey/nhl/athletes/{pid}
print(f"[3/5] Fetching jersey numbers for {len(need_jersey_pids)} historical NHL rotation players...")


def fetch_ath_jersey(pid):
    d = fetch_json(f"https://site.web.api.espn.com/apis/common/v3/sports/hockey/nhl/athletes/{pid}", retries=1)
    ath = (d or {}).get("athlete") or {}
    j = str(ath.get("jersey") or "").strip()
    fn = clean_ascii(ath.get("fullName") or ath.get("displayName") or "")
    ln = clean_ascii(ath.get("lastName") or "")
    pos = (ath.get("position") or {}).get("abbreviation", "")
    return pid, j, fn, ln, pos


with ThreadPoolExecutor(max_workers=32) as ex:
    for pid, j, fn, ln, pos in ex.map(fetch_ath_jersey, sorted(need_jersey_pids)):
        if j:
            player_master[pid]["jersey"] = j
        if fn and len(fn) > len(player_master[pid]["full_name"]):
            player_master[pid]["full_name"] = fn
        if ln and not player_master[pid]["jersey_name"]:
            player_master[pid]["jersey_name"] = ln
        if pos and not player_master[pid].get("pos"):
            player_master[pid]["pos"] = pos

missing_j = sum(1 for pid in need_jersey_pids if not player_master[pid].get("jersey"))
print(f"  Historical NHL jerseys resolved! Remaining without jersey: {missing_j}/{len(need_jersey_pids)} ({time.time()-t0:.1f}s)")

# 4. Fetch 2026-27 live NHL season scoreboards + boxscores (2026-10-04 through today + 2 days)
print("[4/5] Fetching 2026-27 NHL game scoreboards & player TOI boxscores...")
start_d = datetime.date(2026, 10, 4)
end_d = datetime.date(2026, 11, 22)
dates_2627 = [start_d + datetime.timedelta(days=i) for i in range((end_d - start_d).days + 1)]


def fetch_sb_day(dt_obj):
    ymd = dt_obj.strftime("%Y%m%d")
    d_iso = dt_obj.isoformat()
    d = fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={ymd}")
    evts = []
    for ev in (d or {}).get("events", []):
        eid = str(ev.get("id", ""))
        st_type = (ev.get("status") or {}).get("type") or {}
        completed = bool(st_type.get("completed"))
        comps = (ev.get("competitions") or [{}])[0]
        # Skip preseason games (season.type == 1)
        ev_season_type = int(((ev.get("season") or {}).get("type")) or 2)
        if ev_season_type == 1:
            continue
        competitors = comps.get("competitors") or []
        hc = next((c for c in competitors if c.get("homeAway") == "home"), None)
        ac = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not hc or not ac:
            continue
        hab = str((hc.get("team") or {}).get("abbreviation", "")).upper()
        aab = str((ac.get("team") or {}).get("abbreviation", "")).upper()
        h_name = ESPN_ABBR_TO_CANON.get(hab, (norm_team((hc.get("team") or {}).get("displayName", "")), hab))[0]
        a_name = ESPN_ABBR_TO_CANON.get(aab, (norm_team((ac.get("team") or {}).get("displayName", "")), aab))[0]
        hp = int(float(hc.get("score") or 0)) if completed else 0
        ap = int(float(ac.get("score") or 0)) if completed else 0
        venue_nm = str(((comps.get("venue") or {}).get("fullName")) or "").strip()
        evts.append({
            "eid": eid, "d": d_iso, "completed": completed,
            "h": h_name, "a": a_name, "hp": hp, "ap": ap, "venue": venue_nm
        })
    return evts


events_2627 = []
with ThreadPoolExecutor(max_workers=16) as ex:
    for ev_list in ex.map(fetch_sb_day, dates_2627):
        events_2627.extend(ev_list)

completed_evts = [e for e in events_2627 if e["completed"] and e["hp"] != e["ap"]]
print(f"  Found {len(events_2627)} regular-season NHL events in 2026-10-04..11-22 ({len(completed_evts)} completed). Fetching boxscores...")


def fetch_box(ev):
    eid = ev["eid"]
    d = fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event={eid}")
    bx_teams = ((d or {}).get("boxscore") or {}).get("players") or []
    team_players = {}
    for bt in bx_teams:
        ab = str((bt.get("team") or {}).get("abbreviation", "")).upper()
        tname = ESPN_ABBR_TO_CANON.get(ab, (norm_team((bt.get("team") or {}).get("displayName", "")), ab))[0]
        seen_p = set()
        plist = []
        for sg in (bt.get("statistics") or []):
            sg_name = str(sg.get("name") or "").lower()
            if sg_name == "skaters" and not (sg.get("athletes") or []):
                continue
            labels = sg.get("labels") or []
            toi_i = labels.index("TOI") if "TOI" in labels else -1
            g_i = labels.index("G") if "G" in labels else -1
            a_i = labels.index("A") if "A" in labels else -1
            is_goalie_grp = (sg_name == "goalies")
            for row in (sg.get("athletes") or []):
                if row.get("didNotPlay"):
                    continue
                ath = row.get("athlete") or {}
                pid = str(ath.get("id", ""))
                st_vals = row.get("stats") or []
                if not pid or pid in seen_p or not st_vals or toi_i < 0 or toi_i >= len(st_vals):
                    continue
                mins = parse_mmss_minutes(st_vals[toi_i])
                if mins <= 0:
                    continue
                seen_p.add(pid)
                pts = 0
                if not is_goalie_grp:
                    try:
                        gv = int(st_vals[g_i]) if 0 <= g_i < len(st_vals) else 0
                        av = int(st_vals[a_i]) if 0 <= a_i < len(st_vals) else 0
                        pts = gv + av
                    except Exception:
                        pts = 0
                fn = clean_ascii(ath.get("displayName") or ath.get("fullName") or "")
                ln = clean_ascii(ath.get("lastName") or "")
                if not ln and fn:
                    ln = fn.split()[-1]
                j = str(ath.get("jersey") or "").strip()
                pos = "G" if is_goalie_grp else ((ath.get("position") or {}).get("abbreviation") or ("D" if sg_name == "defenses" else "F"))
                if pid not in player_master:
                    player_master[pid] = {
                        "pid": pid, "full_name": fn, "jersey_name": ln, "jersey": j,
                        "pos": pos, "team": tname, "team_code": ab, "status": "Healthy", "injury_detail": ""
                    }
                else:
                    if j and not player_master[pid].get("jersey"):
                        player_master[pid]["jersey"] = j
                    if pos and not player_master[pid].get("pos"):
                        player_master[pid]["pos"] = pos
                plist.append({
                    "pid": pid,
                    "pos": pos,
                    "starter": bool(row.get("starter")),
                    "min": mins,
                    "toi": mins,
                    "pts": pts,
                    "jersey": j or player_master[pid].get("jersey", ""),
                })
        # Mark top 5 skaters + primary goalie (>=30m TOI) as starters when ESPN leaves starter=None
        skaters_sorted = sorted([p for p in plist if p["pos"] != "G"], key=lambda x: x["min"], reverse=True)
        top5_skater_pids = {p["pid"] for p in skaters_sorted[:5]}
        goalies_sorted = sorted([p for p in plist if p["pos"] == "G"], key=lambda x: x["min"], reverse=True)
        top1_goalie_pid = goalies_sorted[0]["pid"] if goalies_sorted else None
        for p in plist:
            if p["pid"] in top5_skater_pids or (p["pid"] == top1_goalie_pid and p["min"] >= 25.0):
                p["starter"] = True
        plist.sort(key=lambda x: (x["starter"], x["min"]), reverse=True)
        team_players[tname] = plist
    return eid, {"d": ev["d"], "h": ev["h"], "a": ev["a"], "hp": ev["hp"], "ap": ev["ap"], "box": team_players}


boxscores_2627 = {}
with ThreadPoolExecutor(max_workers=24) as ex:
    for eid, bobj in ex.map(fetch_box, completed_evts):
        boxscores_2627[eid] = bobj

# Attach resolved jersey numbers onto season_team_players (keep top 16 per team-season so IR depth never starves Top-8)
serializable_stp = {}
for (s_lbl, tname), lst in season_team_players.items():
    enriched = []
    for r in lst[:16]:
        pm = player_master.get(r["pid"], {})
        r2 = dict(r)
        r2["jersey"] = pm.get("jersey", "")
        r2["pos"] = pm.get("pos") or r.get("pos", "")
        r2["full_name"] = pm.get("full_name") or r["full_name"]
        r2["jersey_name"] = pm.get("jersey_name") or r["jersey_name"]
        enriched.append(r2)
    serializable_stp[f"{s_lbl}||{tname}"] = enriched

# 5. Build NHL-PLAYERS-GEM database for all 32 NHL teams (exact 19-column schema matching NBA-PLAYERS-GEM with PREGAME_TOI)
print("[5/5] Building NHL-PLAYERS-GEM database for all 32 NHL teams...")
toi_lookup_2627 = {}
for (s_lbl, tname), lst in season_team_players.items():
    if s_lbl in ("2025-26", "2026-27"):
        for r in lst:
            if s_lbl == "2026-27" or (r["pid"] not in toi_lookup_2627):
                toi_lookup_2627[r["pid"]] = float(r.get("toi") or 0.0)

# Also compute rolling 2026-27 observed TOI from boxscores
box_min_sum = defaultdict(float)
box_gp_cnt = defaultdict(int)
for bobj in boxscores_2627.values():
    for plist in bobj["box"].values():
        for pr in plist:
            box_min_sum[pr["pid"]] += pr["min"]
            box_gp_cnt[pr["pid"]] += 1

gem_headers = [
    "PLAYER_NO",
    "TEAM_NAME",
    "TEAM_CODE",
    "FULL_NAME",
    "JERSEY_NAME",
    "JERSEY_NO",
    "JERSEY_EFF_NO",
    "POS",
    "INJURY_STATUS",
    "PREGAME_TOI",
    "FULL_NAME_GEM",
    "DEG2_FULL_NAME",
    "DEG2_SIGN",
    "JERSEY_NAME_GEM",
    "DEG3_MODE_A_NAME",
    "DEG3_MODE_B_NAME_PLUS_NO",
    "DEG3_MODE_C_NO_ONLY",
    "NAM_ELE_FAWE",
    "ESPN_PLAYER_ID",
]
gem_rows = [gem_headers]
gem_records = []
p_counter = 0

for tname in sorted(live_rosters.keys()):
    roster_list = list(live_rosters[tname])
    enriched_team = []
    for p in roster_list:
        pid = p["pid"]
        gc = box_gp_cnt.get(pid, 0)
        obs_toi = (box_min_sum[pid] / gc) if gc > 0 else 0.0
        prior_toi = toi_lookup_2627.get(pid, 14.0 if p.get("pos") != "G" else 55.0)
        pre_toi = round((gc * obs_toi + 2.0 * prior_toi) / (gc + 2.0) if gc > 0 else prior_toi, 1)
        enriched_team.append((pre_toi, p))
    enriched_team.sort(key=lambda x: (not is_inactive_nhl_status(x[1]["status"]), x[0]), reverse=True)
    for pre_toi, p in enriched_team:
        p_counter += 1
        fn = p["full_name"]
        jn = p["jersey_name"]
        jno = p["jersey"] or "0"
        jeff = jersey_eff_num(jno, zero_rule=True)
        fn_gem = egem(fn)
        deg2 = fn_gem % 360
        jn_gem = egem(jn)
        d3_a = jn_gem % 360
        d3_b = (jn_gem + jeff) % 360
        d3_c = jeff % 360
        fawe = word_fawe(fn)
        fawe_str = f"{fawe[0]}F-{fawe[1]}A-{fawe[2]}W-{fawe[3]}E"
        row = [
            str(p_counter),
            tname,
            p["team_code"],
            fn,
            jn,
            jno,
            str(jeff),
            p["pos"],
            p["status"],
            f"{pre_toi:.1f}",
            str(fn_gem),
            str(deg2),
            deg_sign(deg2),
            str(jn_gem),
            str(d3_a),
            str(d3_b),
            str(d3_c),
            fawe_str,
            pid,
        ]
        gem_rows.append(row)
        gem_records.append({
            "playerNo": p_counter,
            "team": tname,
            "teamCode": p["team_code"],
            "fullName": fn,
            "jerseyName": jn,
            "jerseyNo": jno,
            "jerseyEffNo": jeff,
            "pos": p["pos"],
            "injuryStatus": p["status"],
            "eligibleActive": not is_inactive_nhl_status(p["status"]),
            "pregameToi": pre_toi,
            "fullNameGem": fn_gem,
            "deg1": 88,
            "deg1Sign": "28 GEMINI",
            "deg1Element": "AIR",
            "deg2": deg2,
            "deg2Sign": deg_sign(deg2),
            "jerseyNameGem": jn_gem,
            "deg3ModeA": d3_a,
            "deg3ModeB": d3_b,
            "deg3ModeC": d3_c,
            "namFawe": fawe_str,
            "pid": pid,
        })

nhl_players_gem_payload = {
    "sheetTitle": "NHL-PLAYERS-GEM",
    "league": "NHL",
    "deg1": 88,
    "deg1Sign": "28 GEMINI",
    "deg1Element": "AIR",
    "teamsCount": len(live_rosters),
    "playersCount": p_counter,
    "excludedStatuses": ["OUT", "IR", "IR-LT", "IR-NR", "Suspension"],
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "headers": gem_headers,
    "values": gem_rows,
    "players": gem_records,
}

for out_p in (
    os.path.join(DATA_DIR, "nhl_players_gem.json"),
    os.path.join(PUB_DIR, "nhl_players_gem.json"),
):
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(nhl_players_gem_payload, f, ensure_ascii=False, separators=(",", ":"))

out_bundle = {
    "player_master": player_master,
    "live_rosters": live_rosters,
    "season_team_players": serializable_stp,
    "events_2627": events_2627,
    "boxscores_2627": boxscores_2627,
}
with open(os.path.join(HERE, "nhl_players_2010_2027.json"), "w", encoding="utf-8") as f:
    json.dump(out_bundle, f, ensure_ascii=False, separators=(",", ":"))

print(
    f"DONE in {time.time()-t0:.1f}s! Saved nhl_players_2010_2027.json ({len(player_master)} master NHL players, "
    f"{len(boxscores_2627)} 2026-27 boxscores) & NHL-PLAYERS-GEM ({p_counter} active-roster players across {len(live_rosters)} teams)."
)
