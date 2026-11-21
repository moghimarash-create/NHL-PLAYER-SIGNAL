#!/usr/bin/env python3
"""
Build & Benchmark All 3 NHL Player Astrological/Elemental Modes (2010-2027, Zero Lookahead):
  - DEG1 = 88 (EnglishGem("NHL") = 88)
  - Lineup = Top 12 Active Skaters by pre-game TOI + 1 Primary/Starting Goalie (13 players total, TOI-weighted, excluding OUT/IR)
  - mode_a: DEG1=88, DEG2=egem(Full_Name)%360, DEG3=egem(Jersey_Name)%360
  - mode_b: DEG1=88, DEG2=egem(Full_Name)%360, DEG3=(egem(Jersey_Name)+JerseyNoEff)%360
  - mode_c: DEG1=88, DEG2=egem(Full_Name)%360, DEG3=JerseyNoEff%360
"""
import sys, os, json, math, time, datetime, bisect
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PUB_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "calc-dashboard", "public"))
sys.path.insert(0, HERE)
import parity_check as pc
import nhl_live_sync as nls

t0 = time.time()
DEG1_NHL = 88

INACTIVE_STATUSES = {"out", "injured reserve", "ir", "ir-lt", "ir-nr", "suspended"}

def is_inactive_status(st_lbl):
    s = str(st_lbl or "").strip().lower()
    return s in INACTIVE_STATUSES or s.startswith("injured") or s.startswith("out")

# 1. Load NHL player bundle, team metadata, historical games (2010..2026), and 2024..2027 schedule
pb = json.load(open(os.path.join(HERE, "nhl_players_2010_2027.json"), "r", encoding="utf-8"))
player_master = pb["player_master"]
live_rosters = pb["live_rosters"]
season_team_players = pb["season_team_players"]
events_2627 = pb["events_2627"]
boxscores_2627 = pb["boxscores_2627"]

teams_gem_raw = json.load(open(os.path.join(HERE, "nhl_gem_sheet.json"), "r", encoding="utf-8"))["values"]
team_tz_map = {}
team_arena_map = {}
team_code_map = {}
team_lat_map = {}
team_lon_map = {}
for r in teams_gem_raw[1:]:
    if not r or not str(r[1]).strip():
        continue
    tname = str(r[1]).strip()
    team_code_map[tname] = str(r[2]).strip()
    team_arena_map[tname] = str(r[11]).strip()
    team_lat_map[tname] = r[19]
    team_lon_map[tname] = r[20]
    team_tz_map[tname] = str(r[21]).strip() or "America/New_York"

def norm_team(s):
    return nls.norm_team(s)

def season_of_date(d_iso):
    return nls.season_of_date(d_iso)

# Merge all NHL games 2010-01-01 .. 2027-04-10
games_by_key = {}

hist_pack_path = os.path.join(PUB_DIR, "nhl_history_pack_2010_2026.json")
for r in json.load(open(hist_pack_path, "r", encoding="utf-8")):
    if len(r) < 8:
        continue
    d_iso = str(r[0]).strip()
    h = norm_team(r[3])
    a = norm_team(r[4])
    if h not in team_tz_map or a not in team_tz_map:
        continue
    hp, ap = int(r[5]), int(r[6])
    if hp == ap or (hp == 0 and ap == 0):
        continue
    dt = datetime.date(*map(int, d_iso.split("-")))
    games_by_key[(d_iso, h, a)] = {
        "d": d_iso, "day": dt.strftime("%A").upper(), "s": str(r[2]) or season_of_date(d_iso),
        "h": h, "a": a, "hp": hp, "ap": ap, "done": True,
        "arena": team_arena_map.get(h, ""), "tz": team_tz_map.get(h, "America/New_York")
    }

preds_base_path = os.path.join(PUB_DIR, "nhl_predictions_2024_2027.json")
for g0 in json.load(open(preds_base_path, "r", encoding="utf-8")).get("games", []):
    d_iso = str(g0["d"]).strip()
    h = norm_team(g0["h"])
    a = norm_team(g0["a"])
    if h not in team_tz_map or a not in team_tz_map:
        continue
    hp, ap = int(g0.get("hp") or 0), int(g0.get("ap") or 0)
    done = bool(g0.get("done") and hp != ap and (hp > 0 or ap > 0))
    key = (d_iso, h, a)
    dt = datetime.date(*map(int, d_iso.split("-")))
    arena = str(g0.get("venue") or "").strip() or team_arena_map.get(h, "")
    if key not in games_by_key:
        games_by_key[key] = {
            "d": d_iso, "day": dt.strftime("%A").upper(), "s": str(g0.get("s") or season_of_date(d_iso)),
            "h": h, "a": a, "hp": hp if done else 0, "ap": ap if done else 0, "done": done,
            "arena": arena, "tz": team_tz_map.get(h, "America/New_York")
        }
    else:
        if arena:
            games_by_key[key]["arena"] = arena
        if done and not games_by_key[key]["done"]:
            games_by_key[key].update({"hp": hp, "ap": ap, "done": True})

# Apply fresh 2026-27 ESPN scores up through today (2026-11-20)
for ev in events_2627:
    h = norm_team(ev["h"])
    a = norm_team(ev["a"])
    if h not in team_tz_map or a not in team_tz_map:
        continue
    key = (ev["d"], h, a)
    dt = datetime.date(*map(int, ev["d"].split("-")))
    arena = str(ev.get("venue") or "").strip() or team_arena_map.get(h, "")
    if ev["completed"] and ev["hp"] != ev["ap"] and (ev["hp"] > 0 or ev["ap"] > 0):
        if key not in games_by_key:
            games_by_key[key] = {
                "d": ev["d"], "day": dt.strftime("%A").upper(), "s": "2026-27",
                "h": h, "a": a, "hp": ev["hp"], "ap": ev["ap"], "done": True,
                "arena": arena, "tz": team_tz_map.get(h, "America/New_York")
            }
        else:
            games_by_key[key].update({"hp": ev["hp"], "ap": ev["ap"], "done": True})
    elif key not in games_by_key:
        games_by_key[key] = {
            "d": ev["d"], "day": dt.strftime("%A").upper(), "s": "2026-27",
            "h": h, "a": a, "hp": 0, "ap": 0, "done": False,
            "arena": arena, "tz": team_tz_map.get(h, "America/New_York")
        }

all_games = sorted(games_by_key.values(), key=lambda g: (g["d"], g["h"], g["a"]))
print(f"Unified NHL game universe: {len(all_games)} games ({sum(1 for g in all_games if g['done'])} completed, {sum(1 for g in all_games if not g['done'])} pending)")

# 2. Precompute per-player static metadata (deg2, deg3_a, deg3_b, deg3_c, nam_fawe)
p_static = {}
for pid, pm in player_master.items():
    fn = pc.clean_ascii(pm.get("full_name") or "")
    jn = pc.clean_ascii(pm.get("jersey_name") or (fn.split()[-1] if fn else ""))
    j_str = str(pm.get("jersey") or "").strip()
    deg2 = pc.egem(fn) % 360
    gem_jn = pc.egem(jn)
    j_eff = pc.jersey_eff_num(j_str, zero_rule=True)
    deg3_a = gem_jn % 360
    deg3_b = (gem_jn + j_eff) % 360
    deg3_c = j_eff % 360
    nam_fawe = tuple(pc.s4.word_element_fawe(fn))
    pos_up = str(pm.get("pos") or "F").upper()
    p_static[pid] = {
        "pid": pid,
        "fn": fn,
        "jn": jn,
        "j_str": j_str if j_str != "" else "0",
        "j_eff": j_eff,
        "pos": pos_up,
        "status": pm.get("status", "Healthy"),
        "inj": pm.get("injury_detail", ""),
        "deg2": deg2,
        "deg3": {"mode_a": deg3_a, "mode_b": deg3_b, "mode_c": deg3_c},
        "nam_fawe": nam_fawe,
    }

# Index 2026-27 boxscores chronologically per team for strict pre-game rolling rotation (b.d < g.d)
team_box_2627 = defaultdict(list)
for eid, bobj in boxscores_2627.items():
    d_b = bobj["d"]
    for tname, plist in bobj["box"].items():
        team_box_2627[norm_team(tname)].append((d_b, plist))
for tname in team_box_2627:
    team_box_2627[tname].sort(key=lambda x: x[0])

live_roster_pids = {
    norm_team(tname): {p["pid"]: p for p in plist}
    for tname, plist in live_rosters.items()
}

ADJ_FALLBACK_TEAM = {
    "Utah Mammoth": ["Arizona Coyotes", "Phoenix Coyotes"],
    "Arizona Coyotes": ["Phoenix Coyotes"],
    "Winnipeg Jets": ["Atlanta Thrashers"],
}

def lookup_season_roster(s_lbl, tname):
    lst = season_team_players.get(f"{s_lbl}||{tname}", [])
    if lst:
        return lst
    for alt in ADJ_FALLBACK_TEAM.get(tname, []):
        lst = season_team_players.get(f"{s_lbl}||{alt}", [])
        if lst:
            return lst
    y0 = int(s_lbl[:4])
    prev_lbl = f"{y0-1}-{str(y0)[-2:]}"
    lst = season_team_players.get(f"{prev_lbl}||{tname}", [])
    if lst:
        return lst
    for alt in ADJ_FALLBACK_TEAM.get(tname, []):
        lst = season_team_players.get(f"{prev_lbl}||{alt}", [])
        if lst:
            return lst
    next_lbl = f"{y0+1}-{str(y0+2)[-2:]}"
    return season_team_players.get(f"{next_lbl}||{tname}", [])

def get_pregame_lineup(tname, s_lbl, d_iso, is_pending=False, top_skaters=12):
    """
    Strictly pre-game 13-man NHL active lineup (NO lookahead!):
      - 1 Primary/Starting Active Goalie (pos == 'G', effective TOI clamped to [35, 60] min)
      - Top 12 Active Skaters by pre-game TOI (pos != 'G')
      - Excludes OUT / Injured Reserve / Suspended players on live/pending games.
    """
    cur_roster = live_roster_pids.get(tname, {})
    if s_lbl == "2026-27":
        prior_games = [plist for (db, plist) in team_box_2627.get(tname, []) if db < d_iso]
        base_mpg = {}
        for ps in lookup_season_roster("2025-26", tname):
            base_mpg[ps["pid"]] = float(ps.get("mpg", 16.0))
        if prior_games:
            min_sums = defaultdict(float)
            gp_cnts = defaultdict(int)
            st_cnts = defaultdict(int)
            recent = prior_games[-10:]
            n_rec = len(recent)
            for plist in recent:
                for pr in plist:
                    min_sums[pr["pid"]] += pr["min"]
                    gp_cnts[pr["pid"]] += 1
                    if pr.get("starter"):
                        st_cnts[pr["pid"]] += 1
            g_cands = []
            s_cands = []
            all_pids = set(min_sums.keys()) | (set(cur_roster.keys()) if is_pending else set())
            for pid in all_pids:
                if pid not in p_static:
                    continue
                if is_pending and cur_roster:
                    if pid not in cur_roster:
                        continue
                    if is_inactive_status(cur_roster[pid].get("status", "Healthy")):
                        continue
                pos = p_static[pid]["pos"]
                g_c = gp_cnts.get(pid, 0)
                obs_m = (min_sums[pid] / g_c) if g_c > 0 else 0.0
                if pos == "G":
                    # Rank goalies by starts/minutes in last 10 team games, blended with prior season
                    prior_g = base_mpg.get(pid, 52.0)
                    share_score = (min_sums[pid] / max(1, n_rec)) + (prior_g * 0.25)
                    eff_toi = round(min(60.0, max(38.0, obs_m if g_c > 0 else prior_g)), 1)
                    g_cands.append((share_score, st_cnts.get(pid, 0), pid, eff_toi))
                else:
                    prior_m = base_mpg.get(pid, 14.0)
                    blend_mpg = (g_c * obs_m + 2.0 * prior_m) / (g_c + 2.0) if g_c > 0 else (prior_m * 0.45)
                    if blend_mpg >= 7.0:
                        is_top_line = st_cnts.get(pid, 0) >= max(1, g_c // 2) if g_c > 0 else False
                        s_cands.append((pid, round(blend_mpg, 1), is_top_line))
            g_cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
            s_cands.sort(key=lambda x: (x[2], x[1]), reverse=True)
            if len(s_cands) >= 8 and len(g_cands) >= 1:
                chosen_g = [(g_cands[0][2], g_cands[0][3], True)]
                return chosen_g + s_cands[:top_skaters]

    # Historical seasons (2009-10..2025-26) or Opening Night fallback
    raw_list = lookup_season_roster(s_lbl, tname)
    goalie_pick = []
    skater_picks = []
    for r in raw_list:
        pid = r["pid"]
        if pid not in p_static:
            continue
        if is_pending and cur_roster:
            if pid not in cur_roster:
                continue
            if is_inactive_status(cur_roster[pid].get("status", "Healthy")):
                continue
        pos = p_static[pid]["pos"]
        if pos == "G":
            if not goalie_pick:
                g_toi = round(min(60.0, max(40.0, float(r.get("mpg") or 56.0))), 1)
                goalie_pick.append((pid, g_toi, True))
        else:
            if len(skater_picks) < top_skaters:
                s_toi = round(max(9.0, float(r.get("mpg") or 15.5)), 1)
                skater_picks.append((pid, s_toi, len(skater_picks) < 5))
        if goalie_pick and len(skater_picks) >= top_skaters:
            break

    # Live roster safety fallback if pending game had all seasonal goalies traded/injured
    if is_pending and not goalie_pick and cur_roster:
        for pid, pr in cur_roster.items():
            if pid in p_static and p_static[pid]["pos"] == "G" and not is_inactive_status(pr.get("status")):
                goalie_pick.append((pid, 55.0, True))
                break

    return goalie_pick + skater_picks

# Precompute 13-man lineups once across all NHL games!
game_lineups = []
for g in all_games:
    is_pend = not g["done"]
    hl = get_pregame_lineup(g["h"], g["s"], g["d"], is_pend, top_skaters=12)
    al = get_pregame_lineup(g["a"], g["s"], g["d"], is_pend, top_skaters=12)
    game_lineups.append((hl, al))

print(f"Precomputed strictly pre-game 13-man NHL lineups (1G + 12S) for {len(all_games)} games in {time.time()-t0:.1f}s")

# Entity memoization cache: (d_iso, jd_key, pid, mode_key) -> (ep, ef, ed, md)
_ent_cache = {}
def cached_eval_player(d_iso, d_ctx, jd_key, pid, mode_key, tbl):
    ck = (d_iso, jd_key, pid, mode_key)
    res = _ent_cache.get(ck)
    if res is not None:
        return res
    ps = p_static[pid]
    res = pc.fast_eval_entity(d_ctx, DEG1_NHL, ps["deg2"], ps["deg3"][mode_key], ps["nam_fawe"], tbl)
    _ent_cache[ck] = res
    return res

def eval_team_lineup(d_iso, d_ctx, jd_key, lineup, mode_key, tbl, emit_cards=False):
    """
    TOI-weighted aggregation of active 13 NHL players (1 Goalie + 12 Skaters) preserving exact Step 4 lattice:
      ele_fin = ele_p + ele_date_sum
      ele_dyn = ele_p + ele_fin
    """
    if not lineup:
        lineup = []
    tot_w = sum(w for _, w, _ in lineup) or 1.0
    ep_acc = [0.0, 0.0, 0.0, 0.0]
    m_keys = ["qdeg", "qfin", "qdec", "qdecf", "qtot", "qp2", "gd", "rul", "qnam"]
    m_acc = {k: [0.0, 0.0] for k in m_keys}
    player_cards = [] if emit_cards else None

    for pid, mpg, is_st in lineup:
        ps = p_static[pid]
        w = mpg / tot_w
        ep, ef, ed, md = cached_eval_player(d_iso, d_ctx, jd_key, pid, mode_key, tbl)
        for j in range(4):
            ep_acc[j] += w * ep[j]
        for k in m_keys:
            m_acc[k][0] += w * md[k][0]
            m_acc[k][1] += w * md[k][1]
        if emit_cards:
            pwr = round(
                (-md["qfin"][1]) * 1.5
                + (abs(md["qdec"][0]) + abs(md["qdec"][1])) * 0.08
                + (ed[0] + ed[1] - ed[2] - ed[3]) * 1.2,
                1
            )
            player_cards.append({
                "pid": pid,
                "fn": ps["fn"],
                "jn": ps["jn"],
                "no": ps["j_str"],
                "pos": ps["pos"],
                "st": is_st,
                "mpg": mpg,
                "d2": ps["deg2"],
                "d3": ps["deg3"][mode_key],
                "ep": f"{ep[0]}-{ep[1]}-{ep[2]}-{ep[3]}",
                "ef": f"{ef[0]}-{ef[1]}-{ef[2]}-{ef[3]}",
                "qf": f"{pc.s4.fmt_hc(md['qfin'][0], False)}/{pc.s4.fmt_md(md['qfin'][1], False)}",
                "dec": md["decan_lbl"],
                "pwr": pwr,
            })

    ele_date_sum = d_ctx[7]
    ep_tm = tuple(min(4, max(0, int(round(ep_acc[j])))) for j in range(4))
    ef_tm = tuple(ep_tm[j] + ele_date_sum[j] for j in range(4))
    ed_tm = tuple(ep_tm[j] + ef_tm[j] for j in range(4))

    c12 = [
        f"{ed_tm[0]} FIRE", f"{ed_tm[1]} AIR", f"{ed_tm[2]} WATER", f"{ed_tm[3]} EARTH",
        f"{ef_tm[0]} FIRE", f"{ef_tm[1]} AIR", f"{ef_tm[2]} WATER", f"{ef_tm[3]} EARTH",
        f"{ep_tm[0]} FIRE", f"{ep_tm[1]} AIR", f"{ep_tm[2]} WATER", f"{ep_tm[3]} EARTH",
    ]
    geo_fin = "".join("1" if (x % 2 == 1) else "0" for x in ef_tm)
    geo_dyn = "".join("1" if (x % 2 == 1) else "0" for x in ed_tm)
    m_tm = {k: (int(round(v[0])), int(round(v[1]))) for k, v in m_acc.items()}
    return c12, geo_fin, geo_dyn, m_tm, player_cards

def score_5_player_fusion(mh_u, ma_u, mh_l, ma_l):
    def sA(hm, am):
        return (1 if hm["qfin"][1]<am["qfin"][1] else (-1 if hm["qfin"][1]>am["qfin"][1] else 0)) + \
               (1 if abs(hm["qdec"][0])+abs(hm["qdec"][1])>abs(am["qdec"][0])+abs(am["qdec"][1]) else (-1 if abs(hm["qdec"][0])+abs(hm["qdec"][1])<abs(am["qdec"][0])+abs(am["qdec"][1]) else 0)) + \
               (1 if hm["qtot"][1]<am["qtot"][1] else (-1 if hm["qtot"][1]>am["qtot"][1] else 0)) + \
               (1 if abs(hm["gd"][1])>abs(am["gd"][1]) else (-1 if abs(hm["gd"][1])<abs(am["gd"][1]) else 0)) + \
               (1 if hm["qp2"][0]<am["qp2"][0] else (-1 if hm["qp2"][0]>am["qp2"][0] else 0)) + \
               (1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])>abs(am["qnam"][0])+abs(am["qnam"][1]) else (-1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])<abs(am["qnam"][0])+abs(am["qnam"][1]) else 0))
    def sB(hm, am):
        return (1 if hm["qfin"][1]<am["qfin"][1] else (-1 if hm["qfin"][1]>am["qfin"][1] else 0)) + \
               (1 if hm["qtot"][1]<am["qtot"][1] else (-1 if hm["qtot"][1]>am["qtot"][1] else 0)) + \
               (1 if hm["qp2"][1]<am["qp2"][1] else (-1 if hm["qp2"][1]>am["qp2"][1] else 0)) + \
               (1 if hm["qdecf"][0]<am["qdecf"][0] else (-1 if hm["qdecf"][0]>am["qdecf"][0] else 0)) + \
               (1 if hm["rul"][0]<am["rul"][0] else (-1 if hm["rul"][0]>am["rul"][0] else 0)) + \
               (1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])>abs(am["qnam"][0])+abs(am["qnam"][1]) else (-1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])<abs(am["qnam"][0])+abs(am["qnam"][1]) else 0))
    def sC(hm, am):
        return (1 if hm["qdeg"][0]>am["qdeg"][0] else (-1 if hm["qdeg"][0]<am["qdeg"][0] else 0)) + \
               (1 if abs(hm["qfin"][0])+abs(hm["qfin"][1])<abs(am["qfin"][0])+abs(am["qfin"][1]) else (-1 if abs(hm["qfin"][0])+abs(hm["qfin"][1])>abs(am["qfin"][0])+abs(am["qfin"][1]) else 0)) + \
               (1 if abs(hm["qdec"][0])+abs(hm["qdec"][1])<abs(am["qdec"][0])+abs(am["qdec"][1]) else (-1 if abs(hm["qdec"][0])+abs(hm["qdec"][1])>abs(am["qdec"][0])+abs(am["qdec"][1]) else 0)) + \
               (1 if hm["qtot"][1]<am["qtot"][1] else (-1 if hm["qtot"][1]>am["qtot"][1] else 0)) + \
               (1 if abs(hm["rul"][1])<abs(am["rul"][1]) else (-1 if abs(hm["rul"][1])>abs(am["rul"][1]) else 0)) + \
               (1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])>abs(am["qnam"][0])+abs(am["qnam"][1]) else (-1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])<abs(am["qnam"][0])+abs(am["qnam"][1]) else 0))
    def sD(hm, am):
        return (1 if hm["qfin"][1]<am["qfin"][1] else (-1 if hm["qfin"][1]>am["qfin"][1] else 0)) + \
               (1 if abs(hm["qdec"][0])+abs(hm["qdec"][1])>abs(am["qdec"][0])+abs(am["qdec"][1]) else (-1 if abs(hm["qdec"][0])+abs(hm["qdec"][1])<abs(am["qdec"][0])+abs(am["qdec"][1]) else 0)) + \
               (1 if hm["qtot"][1]<am["qtot"][1] else (-1 if hm["qtot"][1]>am["qtot"][1] else 0)) + \
               (1 if hm["qp2"][1]<am["qp2"][1] else (-1 if hm["qp2"][1]>am["qp2"][1] else 0)) + \
               (1 if abs(hm["qdecf"][0])<abs(am["qdecf"][0]) else (-1 if abs(hm["qdecf"][0])>abs(am["qdecf"][0]) else 0)) + \
               (1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])>abs(am["qnam"][0])+abs(am["qnam"][1]) else (-1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])<abs(am["qnam"][0])+abs(am["qnam"][1]) else 0))
    def sE(hm, am):
        return (1 if abs(hm["qdec"][1])<abs(am["qdec"][1]) else (-1 if abs(hm["qdec"][1])>abs(am["qdec"][1]) else 0)) + \
               (1 if hm["gd"][1]<am["gd"][1] else (-1 if hm["gd"][1]>am["gd"][1] else 0)) + \
               (1 if abs(hm["qdecf"][0])<abs(am["qdecf"][0]) else (-1 if abs(hm["qdecf"][0])>abs(am["qdecf"][0]) else 0)) + \
               (1 if abs(hm["qfin"][0])+abs(hm["qfin"][1])<abs(am["qfin"][0])+abs(am["qfin"][1]) else (-1 if abs(hm["qfin"][0])+abs(hm["qfin"][1])>abs(am["qfin"][0])+abs(am["qfin"][1]) else 0)) + \
               (1 if hm["qtot"][1]<am["qtot"][1] else (-1 if hm["qtot"][1]>am["qtot"][1] else 0)) + \
               (1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])>abs(am["qnam"][0])+abs(am["qnam"][1]) else (-1 if abs(hm["qnam"][0])+abs(hm["qnam"][1])<abs(am["qnam"][0])+abs(am["qnam"][1]) else 0))
    va, vb, vc, vd, ve = sA(mh_u,ma_u), sB(mh_u,ma_u), sC(mh_l,ma_l), sD(mh_u,ma_u), sE(mh_l,ma_l)
    mv = [va, vb, vc, vd, ve]
    f30 = sum(mv)
    ag5 = sum(1 for v in mv if (v > 0 if f30 >= 0 else v < 0))
    return mv, f30, ag5

done_base_hist = [
    {"d": g["d"], "day": g["day"], "s": g["s"], "h": g["h"], "a": g["a"], "hp": g["hp"], "ap": g["ap"], "mg": g["hp"] - g["ap"]}
    for g in all_games if g["done"]
]
cut_pairs = set()
sched_set = set()
for g in all_games:
    sched_set.add((g["d"], g["h"]))
    sched_set.add((g["d"], g["a"]))
    cut_pairs.add((g["d"], g["s"]))
    if g["d"] >= "2024-10-01":
        dt = datetime.date(*map(int, g["d"].split("-")))
        mon = (dt - datetime.timedelta(days=dt.weekday())).isoformat()
        cut_pairs.add((mon, g["s"]))

all_snaps = nls.build_all_snapshots(done_base_hist, cut_pairs)
print(f"Built {len(all_snaps)} zero-lookahead NHL standings snapshots in {time.time()-t0:.1f}s")

def fast_auto_filter_np(D, lim, t_vec, t_geo, g_key, geo_first, min_gf):
    idx = np.arange(lim, dtype=np.int32)
    m_mat = D["m12"]
    g_arr = D[g_key]
    used_geo = False
    if geo_first and t_geo > 0:
        nxt = idx[g_arr[idx] == t_geo]
        if len(nxt) >= min_gf:
            idx = nxt
            used_geo = True
    used = 0
    while len(idx) > 7:
        bc, bcnt, bnxt = -1, -1, None
        sub = m_mat[idx]
        for c in range(12):
            if (used >> c) & 1:
                continue
            tv = t_vec[c]
            if tv == 0:
                continue
            mask = (sub[:, c] == tv)
            cnt = int(mask.sum())
            if 5 <= cnt < len(idx) and cnt > bcnt:
                bc, bcnt, bnxt = c, cnt, idx[mask]
        if bc < 0:
            break
        used |= (1 << bc)
        idx = bnxt
        if 5 <= len(idx) <= 7:
            break
    if (not geo_first) and (not used_geo) and t_geo > 0 and len(idx) > 7:
        nxt = idx[g_arr[idx] == t_geo]
        if 5 <= len(nxt) <= 7:
            idx = nxt
    nat = (5 <= len(idx) <= 7)
    chosen = idx if len(idx) <= 7 else idx[-7:]
    pool_rows = [D["rows"][int(i)] for i in chosen]
    hw, aw, d_raw, s_delta, eff = nls.pool_idx_ds(pool_rows)
    tot = max(1, hw + aw)
    pct = round(max(hw, aw) * 100.0 / tot, 1)
    return {
        "pool": pool_rows, "hw": hw, "aw": aw, "pct": pct, "mv": abs(hw - aw),
        "nat": nat, "ds": eff, "d_raw": d_raw, "s_delta": s_delta
    }

summary_comparison = {}

for mode_key, mode_label in [
    ("mode_a", "A: فقط نام روی پیراهن (DEG3 = Jersey Name)"),
    ("mode_b", "B: جمع نام و شماره پیراهن (DEG3 = Jersey Name + No)"),
    ("mode_c", "C: جایگزینی کامل با شماره پیراهن (DEG3 = Jersey No)"),
]:
    tm_m = time.time()
    _ent_cache.clear()
    vocab = {}
    def vid(s):
        if not s:
            return 0
        v = vocab.get(s)
        if v is None:
            v = len(vocab) + 1
            vocab[s] = v
        return v

    mode_rows = []
    for idx_g, g in enumerate(all_games):
        d_ctx = pc.get_date_ctx(g["d"])
        hl, al = game_lineups[idx_g]
        tbl_u = d_ctx[8]
        need_target = (g["d"] >= "2024-10-01")
        emit_pc = (g["d"] >= "2026-10-01")
        h12, h_fin, h_dyn, mh_u, h_pcards = eval_team_lineup(g["d"], d_ctx, "UTC", hl, mode_key, tbl_u, emit_pc)
        a12, a_fin, a_dyn, ma_u, a_pcards = eval_team_lineup(g["d"], d_ctx, "UTC", al, mode_key, tbl_u, emit_pc)

        snap_dy = all_snaps[(g["d"], g["s"])]
        h_tab, a_tab = nls.geo_tab_pair(snap_dy, g["h"], g["a"])

        mv, f30, ag5 = [0, 0, 0, 0, 0], 0, 3
        if need_target:
            y, m, d = map(int, g["d"].split("-"))
            jd_l = pc.get_jd_local(y, m, d, g["tz"], 19, 30)
            tbl_l = pc.get_deg_table(jd_l)
            _, _, _, mh_l, _ = eval_team_lineup(g["d"], d_ctx, g["tz"], hl, mode_key, tbl_l, False)
            _, _, _, ma_l, _ = eval_team_lineup(g["d"], d_ctx, g["tz"], al, mode_key, tbl_l, False)
            mv, f30, ag5 = score_5_player_fusion(mh_u, ma_u, mh_l, ma_l)

        mode_rows.append({
            "g": g,
            "h12": h12, "a12": a12,
            "h_fin": h_fin, "h_dyn": h_dyn, "h_tab": h_tab,
            "a_fin": a_fin, "a_dyn": a_dyn, "a_tab": a_tab,
            "v_h12": [vid(x) for x in h12],
            "v_hfin": vid(h_fin), "v_hdyn": vid(h_dyn), "v_htab": vid(h_tab),
            "mv": mv, "f30": f30, "ag5": ag5,
            "mh_u": mh_u,
            "h_pcards": h_pcards,
            "a_pcards": a_pcards,
        })

    by_day = defaultdict(list)
    hist_pack_out = []
    for mr in mode_rows:
        g = mr["g"]
        if g["done"]:
            mg = g["hp"] - g["ap"]
            rec_h = {
                "d": g["d"], "day": g["day"], "s": g["s"],
                "h": g["h"], "a": g["a"], "hp": g["hp"], "ap": g["ap"], "mg": mg,
                "h12": mr["h12"], "h_fin": mr["h_fin"], "h_dyn": mr["h_dyn"], "h_tab": mr["h_tab"],
                "v_h12": mr["v_h12"], "v_hfin": mr["v_hfin"], "v_hdyn": mr["v_hdyn"], "v_htab": mr["v_htab"],
            }
            by_day[g["day"]].append(rec_h)
            hist_pack_out.append([
                g["d"], g["day"], g["s"], g["h"], g["a"], g["hp"], g["ap"], mg,
                mr["h12"], mr["h_dyn"], mr["a12"], mr["a_dyn"],
                mr["f30"], "", mr["h_tab"], mr["a_tab"]
            ])

    day_np = {}
    for wd_k, lst in by_day.items():
        day_np[wd_k] = {
            "dates": [x["d"] for x in lst],
            "rows": lst,
            "m12": np.array([x["v_h12"] for x in lst], dtype=np.int32),
            "fin": np.array([x["v_hfin"] for x in lst], dtype=np.int32),
            "dyn": np.array([x["v_hdyn"] for x in lst], dtype=np.int32),
            "tab": np.array([x["v_htab"] for x in lst], dtype=np.int32),
        }

    preds_out = []
    game_num = 0
    for mr in mode_rows:
        g = mr["g"]
        if g["d"] < "2024-10-01":
            continue
        game_num += 1
        D = day_np[g["day"]]
        lim = bisect.bisect_left(D["dates"], g["d"])

        sd  = fast_auto_filter_np(D, lim, mr["v_h12"], mr["v_hdyn"], "dyn", False, 3)
        gd3 = fast_auto_filter_np(D, lim, mr["v_h12"], mr["v_hdyn"], "dyn", True,  3)
        f30 = mr["f30"]
        ag5 = mr["ag5"]
        sa = (sd["hw"] >= sd["aw"]) == (f30 >= 0)
        ga = (gd3["hw"] >= gd3["aw"]) == (f30 >= 0)
        pick_geo = (
            False if (sd["pct"] < 60 or (sa and not ga and sd["pct"] >= 55))
            else True if (not sa and ga and gd3["pct"] >= 55)
            else (gd3["pct"] > sd["pct"] or (gd3["pct"] == sd["pct"] and gd3["mv"] > sd["mv"]))
        )
        ch = gd3 if pick_geo else sd
        hw, aw, nat = ch["hw"], ch["aw"], ch["nat"]
        tot = hw + aw
        pct_int = round(max(hw, aw) * 100 / tot) if tot else 50
        hfav = True if hw > aw else (False if aw > hw else f30 >= 0)
        sgn = 1 if hfav else -1
        pred = g["h"] if hfav else g["a"]
        opp  = g["a"] if hfav else g["h"]
        f30_o = f30 * sgn
        agree = (hfav and f30 > 0) or (not hfav and f30 < 0)
        both100 = sd["pct"] == 100.0 and gd3["pct"] == 100.0 and ((sd["hw"] > 0) == (gd3["hw"] > 0))
        v71 = 5 <= tot <= 7 and pct_int >= 71 and abs(hw - aw) >= 3
        bcombo = v71 and (agree or both100)

        c1 = fast_auto_filter_np(D, lim, mr["v_h12"], mr["v_hfin"], "fin", False, 5)
        c2 = fast_auto_filter_np(D, lim, mr["v_h12"], mr["v_hfin"], "fin", True,  5)
        c3 = fast_auto_filter_np(D, lim, mr["v_h12"], mr["v_hdyn"], "dyn", True,  5)
        c4 = fast_auto_filter_np(D, lim, mr["v_h12"], mr["v_htab"], "tab", True,  5)

        ds4 = [c1["ds"], c2["ds"], c3["ds"], c4["ds"]]
        ds4_o = [v * sgn for v in ds4]
        ds3_o = ds4_o[:3]
        vh4 = sum(1 for v in ds4 if v > 0)
        va4 = sum(1 for v in ds4 if v < 0)
        nat4 = sum(1 for cx in (c1, c2, c3, c4) if cx["nat"])
        fav_v4 = vh4 if hfav else va4
        opp_v4 = va4 if hfav else vh4
        fav_v3 = sum(1 for v in ds3_o if v > 0)
        opp_v3 = sum(1 for v in ds3_o if v < 0)
        min_o4 = min(ds4_o)
        min_o3 = min(ds3_o)

        y, m, d = map(int, g["d"].split("-"))
        dt = datetime.date(y, m, d)
        mon = (dt - datetime.timedelta(days=dt.weekday())).isoformat()
        yest = (dt - datetime.timedelta(days=1)).isoformat()
        pb2b = (yest, pred) in sched_set and (yest, opp) not in sched_set
        ob2b = (yest, opp) in sched_set and (yest, pred) not in sched_set
        is_playoff = (g["d"][5:10] >= "04-18" and m <= 6)
        c4_vote_opp = ((c4["hw"] - c4["aw"]) * sgn < 0)

        t1 = (not hfav) and (f30_o < 10 or (fav_v3 < 2 and fav_v4 < 3))
        t2 = (opp_v3 >= 2 and f30_o < 8) or (opp_v4 >= 2 and f30_o < 10)
        t3 = pb2b and f30_o < 12 and ((not hfav) or (not nat))
        t4 = (not nat) and fav_v3 < 3 and fav_v4 < 3 and f30_o < 12
        t5 = (fav_v4 == 0) or (c4_vote_opp and f30_o < 12) or (is_playoff and (ag5 < 4 or not nat))
        htrap = t1 or t2 or t3 or t4 or t5
        trap_tag = (
            "تله میهمان ضعیف" if t1
            else "مخالفت شاخص ۴ کاناله Δ+S" if t2
            else "تله خستگی B2B" if t3
            else "تله CAP7 بدون پشتوانه" if t4
            else "مخالفت شکل رمل جدول روزانه (GEO-TAB)" if (c4_vote_opp and f30_o < 12)
            else "تله پلی‌آف غیرطبیعی" if (is_playoff and (ag5 < 4 or not nat))
            else "تساوی/مخالفت شاخص Δ+S" if t5
            else ""
        )
        g4 = bool(bcombo and not htrap)
        c4_hfav = c4["hw"] > c4["aw"]
        c4_resc = (
            (not bcombo)
            and 5 <= (c4["hw"] + c4["aw"]) <= 7
            and c4["nat"] and c4["pct"] >= 83
            and c4_hfav == hfav and f30_o >= 10 and c4["ds"] * sgn >= 2
            and not is_playoff and not pb2b
        )
        resc = bool(((not bcombo) and v71 and fav_v4 >= 3 and min_o3 >= 1 and not htrap) or c4_resc)

        snap_wk = all_snaps[(mon, g["s"])]
        snap_dy = all_snaps[(g["d"], g["s"])]
        wtp_wk = nls.make_wtp_obj(snap_wk, mon, g["h"], g["a"], hfav)
        wtp_dy = nls.make_wtp_obj(snap_dy, yest, g["h"], g["a"], hfav)
        wtrap_wk = (wtp_wk["mel"] == "EARTH")
        wtrap_dy = (wtp_dy["mel"] == "EARTH")

        f1_wtp = bool(g4 and not wtrap_wk)
        vip_idx3 = bool(g4 and not wtrap_wk and (wtp_wk["mel"] == "FIRE" or (nat and fav_v4 == 4 and min_o4 >= 2)))
        f1_union = bool((g4 or resc) and not wtrap_wk)

        f1_wtp_day = bool(g4 and not wtrap_dy)
        vip_idx3_day = bool(g4 and not wtrap_dy and (wtp_dy["mel"] == "FIRE" or (nat and fav_v4 == 4 and min_o4 >= 2)))
        f1_union_day = bool((g4 or resc) and not wtrap_dy)

        aw_team = (g["h"] if g["hp"] > g["ap"] else g["a"]) if g["done"] else "PENDING"
        st_lbl = ("WIN" if pred == aw_team else "LOSS") if g["done"] else "PENDING"
        sc_lbl = f"{g['hp']}-{g['ap']}" if g["done"] else "PENDING"

        dir_mgs = sorted([abs(x["mg"]) for x in ch["pool"] if (x["mg"] > 0) == hfav])
        if dir_mgs:
            tp_arr = [
                int(dir_mgs[max(0, len(dir_mgs)//4)]),
                int(dir_mgs[len(dir_mgs)//2]),
                int(dir_mgs[min(len(dir_mgs)-1, (3*len(dir_mgs))//4)])
            ]
        else:
            tp_arr = [1, 2, 3]

        h_out, a_out = [], []
        if g["d"] >= "2026-11-12":
            h_out = [f"{p['full_name']} (#{p['jersey']})" for p in live_rosters.get(g["h"], []) if is_inactive_status(p.get("status", ""))]
            a_out = [f"{p['full_name']} (#{p['jersey']})" for p in live_rosters.get(g["a"], []) if is_inactive_status(p.get("status", ""))]

        pred_obj = {
            "n": game_num,
            "day": g["day"], "d": g["d"], "ym": g["d"][:7], "s": g["s"],
            "h": g["h"], "a": g["a"],
            "hc": team_code_map.get(g["h"], ""), "ac": team_code_map.get(g["a"], ""),
            "venue": g["arena"],
            "hp": g["hp"], "ap": g["ap"],
            "sc": sc_lbl, "pw": pred, "fpw": pred, "sys_win": pred, "twWin": pred,
            "aw": aw_team, "st": st_lbl, "fst": st_lbl,
            "done": g["done"], "hw": (g["hp"] > g["ap"]) if g["done"] else None,
            "ph": hfav, "vm6": f30, "f30": f30, "a25": f30, "ag5": ag5, "mv": mv,
            "v": mv, "nd": abs(f30),
            "b137": False, "n80": False, "e80": False, "q80": False, "g83": False,
            "tier": "VIP" if vip_idx3 else ("QUALIFIED" if f1_wtp else "FILTERED"),
            "twMode": "GEO" if pick_geo else "STEP",
            "twVotes": f"{hw}H-{aw}A", "twPct": f"{pct_int}%",
            "tp": tp_arr, "twAgree": agree,
            "twins": [[x["d"], x["h"], x["a"], x["hp"], x["ap"], x["mg"]] for x in ch["pool"]],
            "twPeers": [f"{x['d']} | {x['h']} {x['hp']}-{x['ap']} {x['a']}" for x in ch["pool"]],
            "h_12": mr["h12"], "h_geo": mr["h_fin"], "h_geo_dyn": mr["h_dyn"], "h_geo_tab": mr["h_tab"],
            "a_12": mr["a12"], "a_geo": mr["a_fin"], "a_geo_dyn": mr["a_dyn"], "a_geo_tab": mr["a_tab"],
            "b2b_tag": "B2B_PICK" if pb2b else ("B2B_OPP" if ob2b else ""),
            "is_nat": bool(nat),
            "trap_tag": trap_tag,
            "f1": bool(bcombo),
            "f1_idx": bool(bcombo and (ch["ds"] * sgn > 0)),
            "f1_guard": g4,
            "idx_rescue": resc,
            "f1_wtp": f1_wtp, "vip_idx3": vip_idx3, "f1_union": f1_union,
            "f1_wtp_day": f1_wtp_day, "vip_idx3_day": vip_idx3_day, "f1_union_day": f1_union_day,
            "idx3": {
                "st": [c1["hw"], c1["aw"], c1["ds"]],
                "gf": [c2["hw"], c2["aw"], c2["ds"]],
                "gd": [c3["hw"], c3["aw"], c3["ds"]],
                "gt": [c4["hw"], c4["aw"], c4["ds"]],
                "tw": [hw, aw, ch["ds"]],
                "vh": vh4, "va": va4, "nat": nat4, "minD": min_o4,
            },
            "wtp": wtp_wk,
            "wtp_day": wtp_dy,
            "p_mode": mode_key,
            "h_players": mr["h_pcards"],
            "a_players": mr["a_pcards"],
            "h_out": h_out,
            "a_out": a_out,
        }
        preds_out.append(pred_obj)

    done_p = [x for x in preds_out if x["done"]]
    def calc_metric(sub, flag_k):
        sel = [x for x in sub if x.get(flag_k)]
        w = sum(1 for x in sel if x["sys_win"] == x["aw"])
        n = len(sel)
        return {"w": w, "n": n, "pct": round(100.0 * w / max(1, n), 1)}

    sel_all = [x for x in done_p if x["f1_wtp"]]
    last50 = sel_all[-50:]
    l50_w = sum(1 for x in last50 if x["sys_win"] == x["aw"])

    stats_obj = {
        "mode": mode_key,
        "label": mode_label,
        "total_2427": calc_metric(done_p, "f1_wtp"),
        "vip_2427": calc_metric(done_p, "vip_idx3"),
        "union_2427": calc_metric(done_p, "f1_union"),
        "guard_only": calc_metric(done_p, "f1_guard"),
        "s2425": calc_metric([x for x in done_p if x["s"] == "2024-25"], "f1_wtp"),
        "s2526": calc_metric([x for x in done_p if x["s"] == "2025-26"], "f1_wtp"),
        "s2627": calc_metric([x for x in done_p if x["s"] == "2026-27"], "f1_wtp"),
        "last50": {"w": l50_w, "n": len(last50), "pct": round(100.0 * l50_w / max(1, len(last50)), 1)},
    }
    summary_comparison[mode_key] = stats_obj
    print(f"\n=== {mode_label} ({time.time()-tm_m:.1f}s) ===")
    print("  2024-27 Final (f1_wtp):", stats_obj["total_2427"])
    print("  2024-27 VIP           :", stats_obj["vip_2427"])
    print("  2024-25 Season        :", stats_obj["s2425"])
    print("  2025-26 Season        :", stats_obj["s2526"])
    print("  2026-27 Live Season   :", stats_obj["s2627"])
    print("  Recent 50 Signals     :", stats_obj["last50"])

    SHAMSI_MONTHS = ["", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    def _g2j(gy, gm, gd):
        g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        gy2 = gy + 1 if gm > 2 else gy
        days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
        jy = -1595 + (33 * (days // 12053)); days %= 12053
        jy += 4 * (days // 1461); days %= 1461
        if days > 365: jy += (days - 1) // 365; days = (days - 1) % 365
        if days < 186: jm = 1 + (days // 31); jd = 1 + (days % 31)
        else: jm = 7 + ((days - 186) // 30); jd = 1 + ((days - 186) % 30)
        return jy, jm, jd
    for _g in preds_out:
        _y, _m, _d = map(int, _g["d"].split("-"))
        _jy, _jm, _jd = _g2j(_y, _m, _d)
        _g["sh_d"] = f"{_jy}/{_jm:02d}/{_jd:02d}"
        _g["sh_m"] = f"{_jy}-{_jm:02d} ({SHAMSI_MONTHS[_jm]})"
        _hp = _g.get("h_players") or []
        _ap = _g.get("a_players") or []
        _hd2 = _hp[0]["d2"] if _hp else DEG1_NHL
        _hd3 = _hp[0]["d3"] if _hp else 0
        _ad2 = _ap[0]["d2"] if _ap else DEG1_NHL
        _ad3 = _ap[0]["d3"] if _ap else 0
        _g["deg"] = [DEG1_NHL, _hd2, _hd3, _ad2, _ad3, _hd2, _ad2, _hd3]

    json.dump(
        {"games": preds_out, "modeStats": stats_obj},
        open(os.path.join(PUB_DIR, f"player_nhl_preds_{mode_key}.json"), "w", encoding="utf-8"),
        ensure_ascii=False, separators=(",", ":")
    )
    json.dump(
        hist_pack_out,
        open(os.path.join(PUB_DIR, f"player_nhl_hist_{mode_key}.json"), "w", encoding="utf-8"),
        ensure_ascii=False, separators=(",", ":")
    )

json.dump(summary_comparison, open(os.path.join(PUB_DIR, "player_modes_comparison.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\nALL 3 NHL PLAYER MODES BUILT & SAVED in {time.time()-t0:.1f}s!")
