#!/usr/bin/env python3
"""
Fetch complete NHL player rosters, jersey names, jersey numbers, injury status,
seasonal Time-On-Ice / games (2009-10 through 2026-27), and 2026-27 game-by-game boxscores.
"""
import os, json, time, datetime, unicodedata, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

t0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))

EGEM_MAP = {
    'A':1,'B':2,'C':20,'D':4,'E':5,'F':80,'G':3,'H':8,'I':10,'J':10,
    'K':20,'L':30,'M':40,'N':50,'O':70,'P':80,'Q':100,'R':200,'S':60,
    'T':400,'U':6,'V':6,'W':6,'X':70,'Y':10,'Z':7
}

SIGN_NAMES_12 = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS", "PISCES"
]

def clean_ascii(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip()

def egem(s):
    return sum(EGEM_MAP.get(ch, 0) for ch in clean_ascii(s).upper())

def deg_sign_label(deg):
    d = int(deg) % 360
    si = d // 30
    within = (d % 30) + 1
    return f"{within} {SIGN_NAMES_12[si]}"

def dig_sum_str(n):
    return sum(int(c) for c in str(abs(int(n))) if c.isdigit())

NHL_TEAMS_32_META = [
    ("Anaheim Ducks", "ANA", "Western Conference", "Pacific", "California", "Anaheim", "Honda Center", 33.8078, -117.8765, "America/Los_Angeles"),
    ("Boston Bruins", "BOS", "Eastern Conference", "Atlantic", "Massachusetts", "Boston", "TD Garden", 42.3663, -71.0622, "America/New_York"),
    ("Buffalo Sabres", "BUF", "Eastern Conference", "Atlantic", "New York", "Buffalo", "KeyBank Center", 42.8750, -78.8764, "America/New_York"),
    ("Calgary Flames", "CGY", "Western Conference", "Pacific", "Alberta", "Calgary", "Scotiabank Saddledome", 51.0375, -114.0519, "America/Edmonton"),
    ("Carolina Hurricanes", "CAR", "Eastern Conference", "Metropolitan", "North Carolina", "Raleigh", "Lenovo Center", 35.8033, -78.7219, "America/New_York"),
    ("Chicago Blackhawks", "CHI", "Western Conference", "Central", "Illinois", "Chicago", "United Center", 41.8807, -87.6742, "America/Chicago"),
    ("Colorado Avalanche", "COL", "Western Conference", "Central", "Colorado", "Denver", "Ball Arena", 39.7487, -105.0075, "America/Denver"),
    ("Columbus Blue Jackets", "CBJ", "Eastern Conference", "Metropolitan", "Ohio", "Columbus", "Nationwide Arena", 39.9693, -83.0061, "America/New_York"),
    ("Dallas Stars", "DAL", "Western Conference", "Central", "Texas", "Dallas", "American Airlines Center", 32.7905, -96.8104, "America/Chicago"),
    ("Detroit Red Wings", "DET", "Eastern Conference", "Atlantic", "Michigan", "Detroit", "Little Caesars Arena", 42.3410, -83.0550, "America/Detroit"),
    ("Edmonton Oilers", "EDM", "Western Conference", "Pacific", "Alberta", "Edmonton", "Rogers Place", 53.5469, -113.4979, "America/Edmonton"),
    ("Florida Panthers", "FLA", "Eastern Conference", "Atlantic", "Florida", "Sunrise", "Amerant Bank Arena", 26.1584, -80.3256, "America/New_York"),
    ("Los Angeles Kings", "LAK", "Western Conference", "Pacific", "California", "Los Angeles", "Crypto.com Arena", 34.0430, -118.2673, "America/Los_Angeles"),
    ("Minnesota Wild", "MIN", "Western Conference", "Central", "Minnesota", "Saint Paul", "Grand Casino Arena", 44.9448, -93.1011, "America/Chicago"),
    ("Montreal Canadiens", "MTL", "Eastern Conference", "Atlantic", "Quebec", "Montreal", "Centre Bell", 45.4961, -73.5693, "America/Toronto"),
    ("Nashville Predators", "NSH", "Western Conference", "Central", "Tennessee", "Nashville", "Bridgestone Arena", 36.1592, -86.7785, "America/Chicago"),
    ("New Jersey Devils", "NJD", "Eastern Conference", "Metropolitan", "New Jersey", "Newark", "Prudential Center", 40.7336, -74.1711, "America/New_York"),
    ("New York Islanders", "NYI", "Eastern Conference", "Metropolitan", "New York", "Elmont", "UBS Arena", 40.7118, -73.7260, "America/New_York"),
    ("New York Rangers", "NYR", "Eastern Conference", "Metropolitan", "New York", "New York City", "Madison Square Garden", 40.7505, -73.9935, "America/New_York"),
    ("Ottawa Senators", "OTT", "Eastern Conference", "Atlantic", "Ontario", "Ottawa", "Canadian Tire Centre", 45.2969, -75.9272, "America/Toronto"),
    ("Philadelphia Flyers", "PHI", "Eastern Conference", "Metropolitan", "Pennsylvania", "Philadelphia", "Xfinity Mobile Arena", 39.9012, -75.1720, "America/New_York"),
    ("Pittsburgh Penguins", "PIT", "Eastern Conference", "Metropolitan", "Pennsylvania", "Pittsburgh", "PPG Paints Arena", 40.4396, -79.9892, "America/New_York"),
    ("San Jose Sharks", "SJS", "Western Conference", "Pacific", "California", "San Jose", "SAP Center at San Jose", 37.3328, -121.9012, "America/Los_Angeles"),
    ("Seattle Kraken", "SEA", "Western Conference", "Pacific", "Washington", "Seattle", "Climate Pledge Arena", 47.6221, -122.3540, "America/Los_Angeles"),
    ("St. Louis Blues", "STL", "Western Conference", "Central", "Missouri", "St. Louis", "Enterprise Center", 38.6268, -90.2026, "America/Chicago"),
    ("Tampa Bay Lightning", "TBL", "Eastern Conference", "Atlantic", "Florida", "Tampa", "Benchmark International Arena", 27.9427, -82.4519, "America/New_York"),
    ("Toronto Maple Leafs", "TOR", "Eastern Conference", "Atlantic", "Ontario", "Toronto", "Scotiabank Arena", 43.6435, -79.3791, "America/Toronto"),
    ("Utah Mammoth", "UTA", "Western Conference", "Central", "Utah", "Salt Lake City", "Delta Center", 40.7683, -111.9011, "America/Denver"),
    ("Vancouver Canucks", "VAN", "Western Conference", "Pacific", "British Columbia", "Vancouver", "Rogers Arena", 49.2778, -123.1089, "America/Vancouver"),
    ("Vegas Golden Knights", "VGK", "Western Conference", "Pacific", "Nevada", "Las Vegas", "T-Mobile Arena", 36.1028, -115.1784, "America/Los_Angeles"),
    ("Washington Capitals", "WSH", "Eastern Conference", "Metropolitan", "District of Columbia", "Washington", "Capital One Arena", 38.8981, -77.0209, "America/New_York"),
    ("Winnipeg Jets", "WPG", "Western Conference", "Central", "Manitoba", "Winnipeg", "Canada Life Centre", 49.8928, -97.1436, "America/Winnipeg"),
]

HIST_TEAMS_EXTRA = [
    ("Atlanta Thrashers", "ATL", "Eastern Conference", "Southeast", "Georgia", "Atlanta", "State Farm Arena", 33.7573, -84.3963, "America/New_York"),
    ("Phoenix Coyotes", "PHX", "Western Conference", "Pacific", "Arizona", "Glendale", "Desert Diamond Arena", 33.5319, -112.2612, "America/Phoenix"),
    ("Arizona Coyotes", "ARI", "Western Conference", "Central", "Arizona", "Tempe", "Mullett Arena", 33.4255, -111.9281, "America/Phoenix"),
]

# Build nhl_gem_sheet.json (22-col TEAMS table + historical lookup)
teams_sheet_rows = [[
    "NO", "NAME", "TEAM_CODE", "CONFERENCE", "DIVISION", "TEAM_GEM", "DEG2",
    "NAME_DIG", "TEAM_SIGN", "STATE_PROVINCE", "CITY", "ARENA", "CITY_GEM",
    "ARENA_GEM", "CITY_DEG", "ARENA_DEG", "DEG3", "ARENA_DIG", "ARENA_SIGN",
    "LAT", "LON", "TIMEZONE_IANA"
]]
for idx, (nm, cd, conf, div, st, city, arena, lat, lon, tz) in enumerate(NHL_TEAMS_32_META + HIST_TEAMS_EXTRA, 1):
    t_gem = egem(nm)
    t_deg = t_gem % 360
    c_gem = egem(city)
    a_gem = egem(arena)
    c_deg = c_gem % 360
    a_deg = a_gem % 360
    deg3_comb = (c_deg + a_deg) % 360
    teams_sheet_rows.append([
        idx, nm, cd, conf, div, t_gem, t_deg,
        dig_sum_str(t_gem), deg_sign_label(t_deg), st, city, arena, c_gem,
        a_gem, c_deg, a_deg, deg3_comb, dig_sum_str(a_gem), deg_sign_label(deg3_comb),
        lat, lon, tz
    ])

json.dump({"values": teams_sheet_rows, "active32": [r[0] for r in NHL_TEAMS_32_META]},
          open(os.path.join(HERE, "nhl_gem_sheet.json"), "w"), ensure_ascii=False, indent=2)

ESPN_ABBR_TO_CANON = {
    "ANA": ("Anaheim Ducks", "ANA"),
    "ATL": ("Atlanta Thrashers", "ATL"),
    "PHX": ("Phoenix Coyotes", "PHX"),
    "ARI": ("Arizona Coyotes", "ARI"),
    "BOS": ("Boston Bruins", "BOS"),
    "BUF": ("Buffalo Sabres", "BUF"),
    "CAR": ("Carolina Hurricanes", "CAR"),
    "CBJ": ("Columbus Blue Jackets", "CBJ"),
    "CGY": ("Calgary Flames", "CGY"),
    "CHI": ("Chicago Blackhawks", "CHI"),
    "COL": ("Colorado Avalanche", "COL"),
    "DAL": ("Dallas Stars", "DAL"),
    "DET": ("Detroit Red Wings", "DET"),
    "EDM": ("Edmonton Oilers", "EDM"),
    "FLA": ("Florida Panthers", "FLA"),
    "LA":  ("Los Angeles Kings", "LAK"),
    "LAK": ("Los Angeles Kings", "LAK"),
    "MIN": ("Minnesota Wild", "MIN"),
    "MTL": ("Montreal Canadiens", "MTL"),
    "NJ":  ("New Jersey Devils", "NJD"),
    "NJD": ("New Jersey Devils", "NJD"),
    "NSH": ("Nashville Predators", "NSH"),
    "NYI": ("New York Islanders", "NYI"),
    "NYR": ("New York Rangers", "NYR"),
    "OTT": ("Ottawa Senators", "OTT"),
    "PHI": ("Philadelphia Flyers", "PHI"),
    "PIT": ("Pittsburgh Penguins", "PIT"),
    "SEA": ("Seattle Kraken", "SEA"),
    "SJ":  ("San Jose Sharks", "SJS"),
    "SJS": ("San Jose Sharks", "SJS"),
    "STL": ("St. Louis Blues", "STL"),
    "TB":  ("Tampa Bay Lightning", "TBL"),
    "TBL": ("Tampa Bay Lightning", "TBL"),
    "TOR": ("Toronto Maple Leafs", "TOR"),
    "UTAH":("Utah Mammoth", "UTA"),
    "UTA": ("Utah Mammoth", "UTA"),
    "VAN": ("Vancouver Canucks", "VAN"),
    "VGK": ("Vegas Golden Knights", "VGK"),
    "WPG": ("Winnipeg Jets", "WPG"),
    "WSH": ("Washington Capitals", "WSH"),
}

HIST_TEAM_NORM = {
    "Utah Hockey Club": "Utah Mammoth",
    "Montréal Canadiens": "Montreal Canadiens",
    "St Louis Blues": "St. Louis Blues",
}

def norm_team(name):
    s = clean_ascii(name)
    return HIST_TEAM_NORM.get(s, s)

def fetch_json(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=14).read().decode("utf-8")
            return json.loads(raw)
        except Exception:
            if attempt == retries:
                return None
            time.sleep(0.25 * (attempt + 1))
    return None

# 1. Fetch all 32 live NHL team rosters (exact current jersey numbers + injury status)
teams_meta = fetch_json("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams")
espn_teams = [t["team"] for t in teams_meta["sports"][0]["leagues"][0]["teams"]]
print(f"[1/4] Fetching {len(espn_teams)} live NHL rosters...")

live_rosters = {}
player_master = {}

def fetch_one_roster(tm_obj):
    tid = tm_obj["id"]
    abbr = str(tm_obj.get("abbreviation") or "").upper()
    canon_name, canon_code = ESPN_ABBR_TO_CANON.get(abbr, (norm_team(tm_obj.get("displayName", "")), abbr))
    d = fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/{tid}/roster")
    out = []
    for grp in (d or {}).get("athletes", []):
        grp_pos = str(grp.get("position") or "")
        items = grp.get("items") if isinstance(grp.get("items"), list) else ([grp] if grp.get("id") else [])
        for a in items:
            pid = str(a.get("id", ""))
            if not pid:
                continue
            full_name = clean_ascii(a.get("fullName") or a.get("displayName") or "")
            last_name = clean_ascii(a.get("lastName") or "")
            if not last_name and full_name:
                last_name = full_name.split()[-1]
            jersey_str = str(a.get("jersey") or "").strip()
            pos = str((a.get("position") or {}).get("abbreviation") or "").upper()
            if not pos:
                pos = "G" if "goalie" in grp_pos.lower() else ("D" if "defense" in grp_pos.lower() else "F")
            injs = a.get("injuries") or []
            inj_status = str(injs[0].get("status", "Healthy")) if injs else "Healthy"
            inj_detail = str((injs[0].get("details") or {}).get("type", "")) if injs else ""
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

print(f"  Live rosters loaded: {len(live_rosters)} teams, {len(player_master)} active players ({time.time()-t0:.1f}s)")

# 2. Fetch seasonal athlete stats for ESPN seasons 2010..2027 (2009-10 .. 2026-27)
print("[2/4] Fetching seasonal NHL player TOI & stats 2009-10..2026-27 (seasons 2010..2027)...")

def season_label_from_espn_yr(yr):
    return f"{yr-1}-{str(yr)[-2:]}"

def fetch_season_stats(yr):
    s_lbl = season_label_from_espn_yr(yr)
    base_u = f"https://site.web.api.espn.com/apis/common/v3/sports/hockey/nhl/statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false&limit=100&season={yr}&seasontype=2"
    d1 = fetch_json(base_u + "&page=1")
    if not d1:
        return s_lbl, []
    pages = int((d1.get("pagination") or {}).get("pages", 1))
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
        pos = str((ath.get("position") or {}).get("abbreviation") or "").upper()
        gp, mpg, tot_min, pts, wins = 0, 0.0, 0.0, 0.0, 0
        for cat in (item.get("categories") or []):
            vals = cat.get("values") or []
            cname_cat = cat.get("name")
            if cname_cat == "general" and len(vals) >= 8:
                gp = int(round(float(vals[0] or 0)))
                mpg = round(float(vals[2] or 0) / 60.0, 2)
                wins = int(round(float(vals[5] or 0)))
                tot_min = round(float(vals[7] or 0) / 60.0, 1)
            elif cname_cat == "offensive" and len(vals) >= 3:
                pts = round(float(vals[2] or 0), 1)
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
                "pos": pos or "F",
                "gp": gp,
                "mpg": mpg,
                "tot_min": round(tot_min / max(1, len(t_codes)), 1),
                "pts": pts,
                "wins": wins,
            })
    return s_lbl, parsed

season_team_players = defaultdict(list)
all_season_rows = []

with ThreadPoolExecutor(max_workers=9) as ex:
    for s_lbl, rows in ex.map(fetch_season_stats, range(2010, 2028)):
        all_season_rows.extend(rows)
        for r in rows:
            season_team_players[(r["season"], r["team"])].append(r)

# For each (season, team), separate Goalies and Skaters, keep Top 3 Goalies + Top 18 Skaters!
need_jersey_pids = set()
trimmed_stp = {}
for key, lst in season_team_players.items():
    goalies = [x for x in lst if x["pos"] == "G"]
    skaters = [x for x in lst if x["pos"] != "G"]
    goalies.sort(key=lambda x: (x["tot_min"], x["gp"], x["wins"]), reverse=True)
    skaters.sort(key=lambda x: (x["tot_min"], x["mpg"], x["pts"]), reverse=True)
    kept = goalies[:3] + skaters[:18]
    trimmed_stp[key] = kept
    for r in (goalies[:2] + skaters[:15]):
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

print(f"  Seasonal rows: {len(all_season_rows)} across {len(trimmed_stp)} team-seasons. Missing jersey PIDs to fetch: {len(need_jersey_pids)} ({time.time()-t0:.1f}s)")

# 3. Fetch jersey numbers for historical rotation players via ESPN common/v3/sports/hockey/nhl/athletes/{pid}
print(f"[3/4] Fetching jersey numbers for {len(need_jersey_pids)} historical NHL skaters & goalies...")
def fetch_ath_jersey(pid):
    d = fetch_json(f"https://site.web.api.espn.com/apis/common/v3/sports/hockey/nhl/athletes/{pid}", retries=1)
    ath = (d or {}).get("athlete") or {}
    j = str(ath.get("jersey") or "").strip()
    fn = clean_ascii(ath.get("fullName") or ath.get("displayName") or "")
    ln = clean_ascii(ath.get("lastName") or "")
    pos = str((ath.get("position") or {}).get("abbreviation") or "").upper()
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
print(f"  Historical jerseys resolved! Remaining without jersey: {missing_j}/{len(need_jersey_pids)} ({time.time()-t0:.1f}s)")

# 4. Fetch 2026-27 live season scoreboards + boxscores (2026-10-04 through 2026-11-21)
print("[4/4] Fetching 2026-27 NHL game scoreboards & player boxscores...")
start_d = datetime.date(2026, 10, 4)
end_d = datetime.date(2026, 11, 21)
dates_2627 = [(start_d + datetime.timedelta(days=i)) for i in range((end_d - start_d).days + 1)]

def parse_toi_str(raw_s):
    s = str(raw_s or "0").strip()
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
        venue_name = clean_ascii(((comps.get("venue") or {}).get("fullName")) or "")
        competitors = comps.get("competitors") or []
        hc = next((c for c in competitors if c.get("homeAway") == "home"), None)
        ac = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not hc or not ac:
            continue
        hab = str((hc.get("team") or {}).get("abbreviation", "")).upper()
        aab = str((ac.get("team") or {}).get("abbreviation", "")).upper()
        h_name = ESPN_ABBR_TO_CANON.get(hab, (norm_team((hc.get("team") or {}).get("displayName", "")), hab))[0]
        a_name = ESPN_ABBR_TO_CANON.get(aab, (norm_team((ac.get("team") or {}).get("displayName", "")), aab))[0]
        hp = int(hc.get("score") or 0) if completed else 0
        ap = int(ac.get("score") or 0) if completed else 0
        evts.append({
            "eid": eid, "d": d_iso, "completed": completed,
            "h": h_name, "a": a_name, "hp": hp, "ap": ap, "venue": venue_name
        })
    return evts

events_2627 = []
with ThreadPoolExecutor(max_workers=16) as ex:
    for ev_list in ex.map(fetch_sb_day, dates_2627):
        events_2627.extend(ev_list)

completed_evts = [e for e in events_2627 if e["completed"]]
print(f"  Found {len(events_2627)} events in 2026-10-04..11-21 ({len(completed_evts)} completed). Fetching boxscores...")

def fetch_box(ev):
    eid = ev["eid"]
    d = fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event={eid}")
    bx_teams = ((d or {}).get("boxscore") or {}).get("players") or []
    team_players = {}
    for bt in bx_teams:
        ab = str((bt.get("team") or {}).get("abbreviation", "")).upper()
        tname = ESPN_ABBR_TO_CANON.get(ab, (norm_team((bt.get("team") or {}).get("displayName", "")), ab))[0]
        seen_pids = set()
        plist = []
        for sg in (bt.get("statistics") or []):
            gname = str(sg.get("name") or "").lower()
            labels = sg.get("labels") or []
            if "TOI" not in labels:
                continue
            toi_idx = labels.index("TOI")
            g_idx = labels.index("G") if "G" in labels else -1
            a_idx = labels.index("A") if "A" in labels else -1
            is_goalie_grp = ("goalie" in gname)
            for row in (sg.get("athletes") or []):
                if row.get("didNotPlay"):
                    continue
                ath = row.get("athlete") or {}
                pid = str(ath.get("id", ""))
                st_vals = row.get("stats") or []
                if not pid or pid in seen_pids or not st_vals or toi_idx >= len(st_vals):
                    continue
                mins = parse_toi_str(st_vals[toi_idx])
                if mins <= 0:
                    continue
                seen_pids.add(pid)
                pts = 0
                if not is_goalie_grp:
                    try:
                        gv = int(st_vals[g_idx]) if 0 <= g_idx < len(st_vals) else 0
                        av = int(st_vals[a_idx]) if 0 <= a_idx < len(st_vals) else 0
                        pts = gv + av
                    except Exception:
                        pts = 0
                fn = clean_ascii(ath.get("displayName") or ath.get("fullName") or "")
                ln = clean_ascii(ath.get("lastName") or "")
                if not ln and fn:
                    ln = fn.split()[-1]
                j = str(ath.get("jersey") or "").strip()
                pos = "G" if is_goalie_grp else (str((ath.get("position") or {}).get("abbreviation") or "").upper() or "F")
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
                    "starter": False,
                    "min": mins,
                    "pts": pts,
                    "jersey": j or player_master[pid].get("jersey", "")
                })
        # Tag primary goalie + top 5 skaters by TOI as starters
        g_rows = [p for p in plist if p["pos"] == "G"]
        s_rows = [p for p in plist if p["pos"] != "G"]
        g_rows.sort(key=lambda x: x["min"], reverse=True)
        s_rows.sort(key=lambda x: x["min"], reverse=True)
        if g_rows:
            g_rows[0]["starter"] = True
        for sr in s_rows[:5]:
            sr["starter"] = True
        team_players[tname] = g_rows + s_rows
    return eid, {"d": ev["d"], "h": ev["h"], "a": ev["a"], "hp": ev["hp"], "ap": ev["ap"], "box": team_players}

boxscores_2627 = {}
with ThreadPoolExecutor(max_workers=24) as ex:
    for eid, bobj in ex.map(fetch_box, completed_evts):
        boxscores_2627[eid] = bobj

serializable_stp = {}
for (s_lbl, tname), lst in trimmed_stp.items():
    enriched = []
    for r in lst:
        pm = player_master.get(r["pid"], {})
        r2 = dict(r)
        r2["jersey"] = pm.get("jersey", "")
        r2["full_name"] = pm.get("full_name") or r["full_name"]
        r2["jersey_name"] = pm.get("jersey_name") or r["jersey_name"]
        r2["pos"] = pm.get("pos") or r["pos"]
        enriched.append(r2)
    serializable_stp[f"{s_lbl}||{tname}"] = enriched

out_bundle = {
    "player_master": player_master,
    "live_rosters": live_rosters,
    "season_team_players": serializable_stp,
    "events_2627": events_2627,
    "boxscores_2627": boxscores_2627,
}
out_path = os.path.join(HERE, "nhl_players_2010_2027.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out_bundle, f, ensure_ascii=False)
print(f"DONE in {time.time()-t0:.1f}s! Saved nhl_players_2010_2027.json: {len(player_master)} master players, {len(boxscores_2627)} 2026-27 boxscores.")
