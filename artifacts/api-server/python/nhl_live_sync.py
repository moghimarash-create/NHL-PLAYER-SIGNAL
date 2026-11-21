#!/usr/bin/env python3
"""
Live ESPN Score + Injury + Google Sheets Sync for NHL-PLAYER-SIGNAL (DEG1 = 88)
Updates all 3 DEG3 player modes (mode_c, mode_b, mode_a) in:
  - artifacts/calc-dashboard/public/player_nhl_preds_{mode}.json
  - artifacts/calc-dashboard/public/player_nhl_hist_{mode}.json
And syncs completed game scores & predictions to the dedicated Google Sheets:
  - NHL-PLAYERS-GEOMANTIC-INPUT (1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE)
  - NHL-PLAYERS-CALCULATION     (16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs)
"""
import argparse, json, math, os, sys, unicodedata, urllib.request
from datetime import datetime, timezone, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PUB_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "calc-dashboard", "public"))

INPUT_SHEET_ID = "1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE"
CALC_SHEET_ID  = "16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs"

NHL_TEAMS_32 = [
    "Anaheim Ducks", "Boston Bruins", "Buffalo Sabres", "Calgary Flames",
    "Carolina Hurricanes", "Chicago Blackhawks", "Colorado Avalanche", "Columbus Blue Jackets",
    "Dallas Stars", "Detroit Red Wings", "Edmonton Oilers", "Florida Panthers",
    "Los Angeles Kings", "Minnesota Wild", "Montreal Canadiens", "Nashville Predators",
    "New Jersey Devils", "New York Islanders", "New York Rangers", "Ottawa Senators",
    "Philadelphia Flyers", "Pittsburgh Penguins", "San Jose Sharks", "Seattle Kraken",
    "St. Louis Blues", "Tampa Bay Lightning", "Toronto Maple Leafs", "Utah Mammoth",
    "Vancouver Canucks", "Vegas Golden Knights", "Washington Capitals", "Winnipeg Jets"
]

FRANCHISE_CONTINUITY = {
    "Atlanta Thrashers": "Winnipeg Jets",
    "Phoenix Coyotes": "Utah Mammoth",
    "Arizona Coyotes": "Utah Mammoth",
    "Utah Hockey Club": "Utah Mammoth",
    "Montréal Canadiens": "Montreal Canadiens",
    "St Louis Blues": "St. Louis Blues",
}

def clean_ascii(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip()

def norm_team(s):
    t = clean_ascii(s)
    if t == "Utah Hockey Club":
        return "Utah Mammoth"
    if t == "St Louis Blues":
        return "St. Louis Blues"
    return t

def franchise_canon(s):
    t = clean_ascii(s)
    return FRANCHISE_CONTINUITY.get(t, t)

def active_teams_for_season(s_lbl):
    y0 = int(str(s_lbl or "2024-25")[:4])
    out = [t for t in NHL_TEAMS_32 if not (t == "Vegas Golden Knights" and y0 < 2017) and not (t == "Seattle Kraken" and y0 < 2021)]
    return out

def season_of_date(d_iso):
    if "2019-10-01" <= d_iso <= "2020-10-15": return "2019-20"
    if "2020-12-15" <= d_iso <= "2021-08-15": return "2020-21"
    if "2013-01-01" <= d_iso <= "2013-07-01": return "2012-13"
    y, m, _ = map(int, d_iso.split("-"))
    return f"{y}-{(y+1)%100:02d}" if m >= 9 else f"{y-1}-{y%100:02d}"

def pyth_nhl(gf, ga, exp=2.05):
    if gf <= 0 or ga <= 0:
        return 0.5
    r = ga / gf
    try:
        return 1.0 / (1.0 + (r ** exp))
    except OverflowError:
        return 0.0 if r > 1 else 1.0

def log5_prob(p_h, p_a, ha=0.50):
    p_h = min(0.92, max(0.08, p_h))
    p_a = min(0.92, max(0.08, p_a))
    num = p_h * (1.0 - p_a) * ha
    den = num + (1.0 - p_h) * p_a * (1.0 - ha)
    return num / den if den > 0 else 0.5

def team_elem(p_tm):
    if p_tm >= 0.56: return "FIRE"
    if p_tm >= 0.50: return "AIR"
    if p_tm >= 0.44: return "WATER"
    return "EARTH"

def matchup_elem(p_pick_pct):
    if p_pick_pct >= 56.0: return "FIRE"
    if p_pick_pct >= 50.5: return "AIR"
    if p_pick_pct >= 44.0: return "WATER"
    return "EARTH"

def geo_tab_pair(snap, h_tm, a_tm):
    hc = franchise_canon(h_tm)
    ac = franchise_canon(a_tm)
    hrk = snap["rk"].get(hc, 16)
    ark = snap["rk"].get(ac, 16)
    h_tab = f"{int(hrk<=11)}{int(hrk<=22)}{int(ark<=11)}{int(ark<=22)}"
    a_tab = f"{int(ark<=11)}{int(ark<=22)}{int(hrk<=11)}{int(hrk<=22)}"
    return h_tab, a_tab

def elem_fin(el12):
    if not el12 or len(el12) < 8:
        return ""
    out = []
    for x in el12[4:8]:
        try:
            n = int(str(x).strip().split()[0])
        except Exception:
            n = 0
        out.append("1" if abs(n) % 2 == 1 else "0")
    return "".join(out)

def fetch_espn_date(d_iso):
    ds = d_iso.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={ds}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
    finals = {}
    for ev in data.get("events", []):
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        comps = ev.get("competitions", [{}])[0].get("competitors", [])
        hc = next((c for c in comps if c.get("homeAway") == "home"), None)
        ac = next((c for c in comps if c.get("homeAway") == "away"), None)
        if not hc or not ac:
            continue
        h = norm_team(hc.get("team", {}).get("displayName", ""))
        a = norm_team(ac.get("team", {}).get("displayName", ""))
        try:
            hp = int(hc.get("score", 0))
            ap = int(ac.get("score", 0))
        except Exception:
            continue
        if (hp > 0 or ap > 0) and hp != ap:
            finals[(h, a)] = (hp, ap)
    return finals

def build_all_snapshots(hist, cut_pairs):
    out = {}
    th = {tm: [] for tm in NHL_TEAMS_32}
    ptr = 0
    n = len(hist)
    for cut_iso, s_cur in sorted(set(cut_pairs)):
        while ptr < n and hist[ptr]["d"] < cut_iso:
            r = hist[ptr]
            if r["mg"] != 0:
                hf = franchise_canon(r["h"])
                af = franchise_canon(r["a"])
                th.setdefault(hf, []).append((r["s"], r["mg"] > 0, r["mg"], r["hp"], r["ap"]))
                th.setdefault(af, []).append((r["s"], r["mg"] < 0, -r["mg"], r["ap"], r["hp"]))
            ptr += 1
        active_set = active_teams_for_season(s_cur)
        tp, wl, pstr = {}, {}, {}
        for tm in active_set:
            arr = th.get(tm, [])
            sp = [x for x in arr if x[0] == s_cur]
            l20 = arr[-20:]
            gp = len(sp)
            w = sum(1 for x in sp if x[1])
            gds = sum(x[2] for x in sp)
            gf = sum(x[3] for x in sp)
            ga = sum(x[4] for x in sp)
            l20_wp = sum(1 for x in l20 if x[1]) / len(l20) if l20 else 0.5
            l20_gd = sum(x[2] for x in l20) / len(l20) if l20 else 0.0
            b_wp = (w + 10.0 * l20_wp) / (gp + 10.0)
            b_gd = (gds + 10.0 * l20_gd) / (gp + 10.0)
            tp[tm] = round(50.0 + 60.0 * (b_wp - 0.5) + 8.0 * b_gd, 1)
            wl[tm] = f"{w}-{gp - w}"
            prior_p = (0.5 * (0.4 * l20_wp + 0.6 * pyth_nhl(sum(x[3] for x in l20), sum(x[4] for x in l20))) + 0.25) if l20 else 0.5
            p_wl = (w + 10.0 * prior_p) / (gp + 10.0)
            p_py = (gp * (pyth_nhl(gf, ga) if gp > 0 else prior_p) + 10.0 * prior_p) / (gp + 10.0)
            pstr[tm] = 0.35 * p_wl + 0.65 * p_py
        ranked = sorted(pstr.keys(), key=lambda t: pstr[t], reverse=True)
        rk = {t: i + 1 for i, t in enumerate(ranked)}
        out[(cut_iso, s_cur)] = {"tp": tp, "rk": rk, "wl": wl, "p": pstr}
    return out

def make_wtp_obj(snap, label_date, h_tm, a_tm, hfav):
    hc = franchise_canon(h_tm)
    ac = franchise_canon(a_tm)
    htp = snap["tp"].get(hc, 50.0)
    atp = snap["tp"].get(ac, 50.0)
    dtp = round((htp - atp) if hfav else (atp - htp), 1)
    ph = snap["p"].get(hc, 0.5)
    pa = snap["p"].get(ac, 0.5)
    l5h = round(log5_prob(ph, pa, 0.50) * 100.0, 1)
    l5pick = l5h if hfav else round(100.0 - l5h, 1)
    mel = matchup_elem(l5pick)
    pfair_h = log5_prob(ph, pa, 0.535)
    hodds = round(1.0 / max(0.05, pfair_h), 2)
    aodds = round(1.0 / max(0.05, 1.0 - pfair_h), 2)
    return {
        "mon": label_date,
        "htp": htp, "atp": atp, "dtp": dtp,
        "hrk": snap["rk"].get(hc, 16),
        "ark": snap["rk"].get(ac, 16),
        "hwl": snap["wl"].get(hc, "0-0"),
        "awl": snap["wl"].get(ac, "0-0"),
        "hpct": round(ph * 100.0, 1),
        "apct": round(pa * 100.0, 1),
        "hel": team_elem(ph),
        "ael": team_elem(pa),
        "l5h": l5h,
        "hodds": hodds,
        "aodds": aodds,
        "mel": mel,
    }

def pool_idx_ds(pool):
    """NHL 1-goal unit numerical index (1x single-win rule, capped at 5 goals to suppress blowouts)."""
    ch = [min(5, max(1, int(abs(x["mg"])))) for x in pool if x["mg"] > 0]
    ca = [min(5, max(1, int(abs(x["mg"])))) for x in pool if x["mg"] < 0]
    hw, aw = len(ch), len(ca)
    ih = 0 if not ch else (ch[0] if hw == 1 else max(ch) + min(ch))
    ia = 0 if not ca else (ca[0] if aw == 1 else max(ca) + min(ca))
    d = ih - ia
    s_delta = (2 * hw + ih) - (2 * aw + ia)
    if d > 0 and s_delta > 0:
        eff = d
    elif d < 0 and s_delta < 0:
        eff = d
    elif d == 0 and abs(s_delta) >= 2:
        eff = 1 if s_delta > 0 else -1
    else:
        eff = 0
    return hw, aw, d, s_delta, eff

def auto_filter(t12, tgeo, dpool, geo_first, geo_kind, min_gf):
    pool = list(dpool)
    used = set()
    used_geo = False
    gk = "h_fin" if geo_kind == "fin" else ("h_tab" if geo_kind == "tab" else "h_dyn")
    if geo_first and tgeo:
        nxt = [x for x in pool if x[gk] == tgeo]
        if len(nxt) >= min_gf:
            pool = nxt
            used_geo = True
    while len(pool) > 7:
        bc, bcnt, bnxt = None, -1, None
        for c in range(12):
            if c in used:
                continue
            tv = t12[c] if c < len(t12) else ""
            if not tv:
                continue
            nxt = [x for x in pool if len(x["h12"]) > c and x["h12"][c] == tv]
            if 5 <= len(nxt) < len(pool) and len(nxt) > bcnt:
                bc, bcnt, bnxt = c, len(nxt), nxt
        if bc is None:
            break
        used.add(bc)
        pool = bnxt
        if 5 <= len(pool) <= 7:
            break
    if (not geo_first) and (not used_geo) and tgeo and len(pool) > 7:
        nxt = [x for x in pool if x[gk] == tgeo]
        if 5 <= len(nxt) <= 7:
            pool = nxt
    unsliced = list(pool)
    nat = 5 <= len(unsliced) <= 7
    if len(pool) > 7:
        pool = pool[-7:]
    hw, aw, d_raw, s_delta, eff = pool_idx_ds(pool)
    tot = max(1, hw + aw)
    pct = round(max(hw, aw) * 100.0 / tot, 1)
    return {
        "pool": pool, "hw": hw, "aw": aw, "pct": pct, "mv": abs(hw - aw),
        "nat": nat, "ds": eff, "d_raw": d_raw, "s_delta": s_delta
    }

def sync_single_mode(pub_dir, mk, finals_by_date):
    p_path = os.path.join(pub_dir, f"player_nhl_preds_{mk}.json")
    h_path = os.path.join(pub_dir, f"player_nhl_hist_{mk}.json")
    if not os.path.exists(p_path) or not os.path.exists(h_path):
        return 0, None

    pd = json.load(open(p_path, "r", encoding="utf-8"))
    hist_raw = json.load(open(h_path, "r", encoding="utf-8"))
    hist_keys = {(str(r[0]), norm_team(r[3]), norm_team(r[4])) for r in hist_raw}

    updated_scores = 0
    earliest_new_date = None

    for d_iso, finals in sorted(finals_by_date.items()):
        if not finals:
            continue
        for g in pd["games"]:
            if g["d"] != d_iso:
                continue
            h_norm, a_norm = norm_team(g["h"]), norm_team(g["a"])
            if (h_norm, a_norm) not in finals:
                continue
            hp, ap_pts = finals[(h_norm, a_norm)]
            aw = h_norm if hp > ap_pts else a_norm
            new_sc = f"{hp}-{ap_pts}"
            was_done = bool(g.get("done") and g.get("sc") == new_sc and g.get("aw") == aw)
            g["h"], g["a"] = h_norm, a_norm
            g["hp"], g["ap"] = hp, ap_pts
            g["sc"] = new_sc
            g["aw"] = aw
            g["done"] = True
            g["hw"] = bool(hp > ap_pts)
            g["st"] = "WIN" if norm_team(g.get("pw")) == aw else "LOSS"
            if g.get("fpw"):
                g["fst"] = "WIN" if norm_team(g["fpw"]) == aw else "LOSS"
            if not was_done:
                updated_scores += 1
                if earliest_new_date is None or d_iso < earliest_new_date:
                    earliest_new_date = d_iso
            if (d_iso, h_norm, a_norm) not in hist_keys:
                hist_raw.append([
                    d_iso, g["day"], g.get("s", season_of_date(d_iso)), h_norm, a_norm,
                    hp, ap_pts, hp - ap_pts,
                    g.get("h_12", []), g.get("h_geo_dyn") or g.get("h_geo", ""),
                    g.get("a_12", []), g.get("a_geo_dyn") or g.get("a_geo", ""),
                    g.get("f30", 0), "", "", ""
                ])
                hist_keys.add((d_iso, h_norm, a_norm))
                if earliest_new_date is None or d_iso < earliest_new_date:
                    earliest_new_date = d_iso

    if earliest_new_date is not None:
        hist = []
        cut_pairs = set()
        for idx_r, arr in enumerate(hist_raw):
            d_iso = str(arr[0])
            s_cur = str(arr[2] or season_of_date(d_iso))
            h12 = [str(x) for x in (arr[8] if isinstance(arr[8], list) else [])]
            h_dyn = str(arr[9] or "")
            hist.append({
                "raw_idx": idx_r,
                "d": d_iso, "day": str(arr[1]), "s": s_cur,
                "h": norm_team(arr[3]), "a": norm_team(arr[4]),
                "hp": int(arr[5]), "ap": int(arr[6]), "mg": int(arr[7]),
                "h12": h12, "h_fin": elem_fin(h12), "h_dyn": h_dyn,
            })
            cut_pairs.add((d_iso, s_cur))
        hist.sort(key=lambda r: r["d"])

        sched = set()
        for r in hist:
            sched.add((r["d"], r["h"]))
            sched.add((r["d"], r["a"]))
        for g in pd["games"]:
            sched.add((g["d"], norm_team(g["h"])))
            sched.add((g["d"], norm_team(g["a"])))
            dt = date(*map(int, g["d"].split("-")))
            mon = (dt - timedelta(days=dt.weekday())).isoformat()
            s_cur = g.get("s") or season_of_date(g["d"])
            cut_pairs.add((mon, s_cur))
            cut_pairs.add((g["d"], s_cur))

        all_snaps = build_all_snapshots(hist, cut_pairs)
        by_day = {}
        for r in hist:
            raw_arr = hist_raw[r["raw_idx"]]
            ht, at = geo_tab_pair(all_snaps[(r["d"], r["s"])], r["h"], r["a"])
            while len(raw_arr) < 16:
                raw_arr.append("")
            raw_arr[14] = ht
            raw_arr[15] = at
            r["h_tab"] = ht
            r["a_tab"] = at
            by_day.setdefault(r["day"], []).append(r)

        hist_raw.sort(key=lambda r: str(r[0]))
        json.dump(hist_raw, open(h_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

        for g in pd["games"]:
            if g["d"] <= earliest_new_date:
                continue
            y, m, d = map(int, g["d"].split("-"))
            dt = date(y, m, d)
            mon = (dt - timedelta(days=dt.weekday())).isoformat()
            yest = (dt - timedelta(days=1)).isoformat()
            s_cur = g.get("s") or season_of_date(g["d"])
            snap_dy = all_snaps[(g["d"], s_cur)]
            snap_wk = all_snaps[(mon, s_cur)]
            h_tab, a_tab = geo_tab_pair(snap_dy, g["h"], g["a"])
            g["h_geo_tab"] = h_tab
            g["a_geo_tab"] = a_tab

            h12 = [str(x) for x in g.get("h_12", [])]
            h_dyn = str(g.get("h_geo_dyn") or g.get("h_geo") or "")
            h_fin = elem_fin(h12)
            arr = by_day.get(g["day"], [])
            lo, hi = 0, len(arr)
            while lo < hi:
                mid = (lo + hi) // 2
                if arr[mid]["d"] < g["d"]:
                    lo = mid + 1
                else:
                    hi = mid
            dpool = arr[:lo]
            sd = auto_filter(h12, h_dyn, dpool, False, "dyn", 3)
            gd3 = auto_filter(h12, h_dyn, dpool, True, "dyn", 3)
            f30 = int(g.get("f30") if g.get("f30") is not None else g.get("vm6", 0))
            ag5 = int(g.get("ag5", 3))
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
            opp = g["a"] if hfav else g["h"]
            g["pw"] = pred
            g["fpw"] = pred
            g["sys_win"] = pred
            g["twWin"] = pred
            g["twVotes"] = f"{hw}H-{aw}A"
            g["twPct"] = f"{pct_int}%"
            g["twins"] = [[x["d"], x["h"], x["a"], x["hp"], x["ap"], x["mg"]] for x in ch["pool"]]
            f30_o = f30 * sgn
            agree = (hfav and f30 > 0) or (not hfav and f30 < 0)
            both100 = sd["pct"] == 100.0 and gd3["pct"] == 100.0 and ((sd["hw"] > 0) == (gd3["hw"] > 0))
            v71 = 5 <= tot <= 7 and pct_int >= 71 and abs(hw - aw) >= 3
            bcombo = v71 and (agree or both100)

            c1 = auto_filter(h12, h_fin, dpool, False, "fin", 5)
            c2 = auto_filter(h12, h_fin, dpool, True, "fin", 5)
            c3 = auto_filter(h12, h_dyn, dpool, True, "dyn", 5)
            c4 = auto_filter(h12, h_tab, dpool, True, "tab", 5)
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

            pb2b = (yest, pred) in sched and (yest, opp) not in sched
            ob2b = (yest, opp) in sched and (yest, pred) not in sched
            is_playoff = (g["d"][5:10] >= "04-18" and m <= 6)
            c4_vote_opp = ((c4["hw"] - c4["aw"]) * sgn < 0)

            t1 = (not hfav) and (f30_o < 10 or (fav_v3 < 2 and fav_v4 < 3))
            t2 = (opp_v3 >= 2 and f30_o < 8) or (opp_v4 >= 2 and f30_o < 10)
            t3 = pb2b and f30_o < 12 and ((not hfav) or (not nat))
            t4 = (not nat) and fav_v3 < 3 and fav_v4 < 3 and f30_o < 12
            t5 = (fav_v4 == 0) or (c4_vote_opp and f30_o < 12) or (is_playoff and (ag5 < 4 or not nat))
            htrap = t1 or t2 or t3 or t4 or t5
            g["b2b_tag"] = "B2B_PICK" if pb2b else ("B2B_OPP" if ob2b else "")
            g["is_nat"] = bool(nat)
            g["f1"] = bool(bcombo)
            g["f1_idx"] = bool(bcombo and (ch["ds"] * sgn > 0))
            g["f1_guard"] = bool(bcombo and not htrap)
            g["idx3"] = {
                "st": [c1["hw"], c1["aw"], c1["ds"]],
                "gf": [c2["hw"], c2["aw"], c2["ds"]],
                "gd": [c3["hw"], c3["aw"], c3["ds"]],
                "gt": [c4["hw"], c4["aw"], c4["ds"]],
                "tw": [hw, aw, ch["ds"]],
                "vh": vh4, "va": va4, "nat": nat4, "minD": min_o4,
            }
            wtp_wk = make_wtp_obj(snap_wk, mon, g["h"], g["a"], hfav)
            wtp_dy = make_wtp_obj(snap_dy, yest, g["h"], g["a"], hfav)
            wtrap_wk = (wtp_wk["mel"] == "EARTH")
            wtrap_dy = (wtp_dy["mel"] == "EARTH")
            g4 = bool(g.get("f1_guard"))
            g["wtp"] = wtp_wk
            g["f1_wtp"] = bool(g4 and not wtrap_wk)
            g["vip_idx3"] = bool(g4 and not wtrap_wk and (wtp_wk["mel"] == "FIRE" or (nat and fav_v4 == 4 and min_o4 >= 2)))
            g["wtp_day"] = wtp_dy
            g["f1_wtp_day"] = bool(g4 and not wtrap_dy)
            g["vip_idx3_day"] = bool(g4 and not wtrap_dy and (wtp_dy["mel"] == "FIRE" or (nat and fav_v4 == 4 and min_o4 >= 2)))

    if updated_scores > 0 or earliest_new_date is not None:
        json.dump(pd, open(p_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return updated_scores, pd

def sync_google_sheets(pd_best, target_iso):
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        return False
    try:
        sys.path.insert(0, HERE)
        from _lib.sheets import open_sheet
        sh_in = open_sheet(INPUT_SHEET_ID)
        ws1 = sh_in.sheet1
        today_games = [g for g in pd_best["games"] if g["d"] == target_iso]
        if today_games:
            rows = [["DATE", "WEEKDAY", "DEG1", "HOME_TEAM", "AWAY_TEAM", "ARENA", "PUCKDROP_LOCAL", "DEG3_MODE"]]
            for g in today_games:
                rows.append([g["d"], g["day"], 88, g["h"], g["a"], g.get("venue", ""), "19:30:00", "MODE_C_JERSEY_NO"])
            ws1.clear()
            ws1.update(values=rows, range_name="A1", value_input_option="RAW")
        return True
    except Exception:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", default="")
    ap.add_argument("--end-date", default="")
    ap.add_argument("--target-date", default="")
    ap.add_argument("--pub-dir", default="")
    args = ap.parse_args()

    pub_dir = args.pub_dir or DEFAULT_PUB_DIR
    base_c = json.load(open(os.path.join(pub_dir, "player_nhl_preds_mode_c.json"), "r", encoding="utf-8"))

    today_utc = datetime.now(timezone.utc).date()
    max_check_iso = (today_utc + timedelta(days=1)).isoformat()
    min_recent_iso = (today_utc - timedelta(days=5)).isoformat()

    dates_to_check = set()
    for g in base_c["games"]:
        d_iso = g["d"]
        if d_iso <= max_check_iso and (not g.get("done") or g.get("aw") in (None, "", "PENDING") or d_iso >= min_recent_iso):
            if d_iso >= "2026-10-04":
                dates_to_check.add(d_iso)
    if args.target_date and len(args.target_date) == 10 and args.target_date <= max_check_iso:
        dates_to_check.add(args.target_date)
    if args.start_date and args.end_date:
        for g in base_c["games"]:
            if args.start_date <= g["d"] <= args.end_date:
                dates_to_check.add(g["d"])

    sorted_dates = sorted(dates_to_check)[-20:]
    finals_by_date = {}
    for d_iso in sorted_dates:
        try:
            finals_by_date[d_iso] = fetch_espn_date(d_iso)
        except Exception:
            continue

    upd_c, pd_c = sync_single_mode(pub_dir, "mode_c", finals_by_date)
    sync_single_mode(pub_dir, "mode_b", finals_by_date)
    sync_single_mode(pub_dir, "mode_a", finals_by_date)

    sheet_synced = sync_google_sheets(pd_c or base_c, args.target_date or today_utc.isoformat())

    pd_use = pd_c or base_c
    done_all = [g for g in pd_use["games"] if g.get("done")]
    oos = [g for g in done_all if g.get("f1_wtp")]
    oos_w = sum(1 for g in oos if g.get("sys_win") == g.get("aw"))
    s26 = [g for g in oos if g.get("s") == "2026-27"]
    s26_w = sum(1 for g in s26 if g.get("sys_win") == g.get("aw"))

    payload = {
        "ok": True,
        "updatedScores": upd_c,
        "checkedDates": sorted_dates,
        "sheetSynced": sheet_synced,
        "totalDone": len(done_all),
        "oosF1": {"w": oos_w, "n": len(oos), "pct": round(100.0 * oos_w / max(1, len(oos)), 1)},
        "s2627": {"w": s26_w, "n": len(s26), "pct": round(100.0 * s26_w / max(1, len(s26)), 1)},
    }
    print("__NHL_SYNC__ " + json.dumps(payload, ensure_ascii=False))
    print("__RESULT__ " + json.dumps({"ok": True, "rowsWritten": upd_c, "message": f"Synced {upd_c} NHL games across all 3 DEG3 modes"}, ensure_ascii=False))

if __name__ == "__main__":
    main()
