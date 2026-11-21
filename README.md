# NHL-PLAYER-SIGNAL (DEG1 = 88)

Player-driven Astrological & Elemental Signal Dashboard for the NHL (2010–2027, Zero Lookahead `r.d < g.d`), ported 1-to-1 from `NBA-PLAYER-SIGNAL`.

## Core Formula & Active Lineup Architecture

- **`DEG1 = 88`** (`EnglishGem("NHL") = 50 + 8 + 30 = 88`)
- **`DEG2 = EnglishGem(Full_Name) mod 360`**
- **Active 13-Player Pre-Game Lineup (Zero Lookahead)**:
  - **1 Primary/Starting Active Goalie** (`G`, effective TOI clamped to `38–60m`)
  - **Top 12 Active Skaters** (`C`, `LW`, `RW`, `D`) ranked by strictly pre-game Time On Ice (`TOI`)
  - Automatic exclusion of injured/unavailable players (`OUT`, `Injured Reserve`, `IR`, `IR-LT`, `Suspended`)
  - Evaluated under both **00:00 UTC** and **Host Arena Local Puck-Drop Sky (`19:30` local IANA timezone)** via Swiss Ephemeris (`pyswisseph`)
- **NHL Sport-Specific Calibration**:
  - **1-Goal Unit Numerical Index** (`min(5, max(1, abs(goal_diff)))`, 1x single-win rule, capped at 5 goals) across 4 channels (`STEP`, `GEO-FIN`, `GEO-DYN`, `GEO-TAB`)
  - **NHL Pythagorean Expectation (`exp = 2.05`) & Log5 Matchup Element** (`FIRE`, `AIR`, `WATER`, `EARTH`) with 32-team seasonal rank tiers (`<=11`, `<=22`)
  - **Kalshi Live NHL Moneyline (`KXNHLGAME`)** integration + 2–4 Leg Multivariate Combo (`KXMVE-NHL`) builder

## Zero-Lookahead 3-Mode `DEG3` Benchmark (22,610 NHL Games • 2010–2027)

| Mode | `DEG3` Formula | 2024–27 Final (`f1_wtp`) | VIP (`vip_idx3`) | 2024–25 | 2025–26 | 2026–27 Live | Recent 50 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mode C (Recommended)** | `Jersey_No_Eff mod 360` | **61.4%** (135/220) | **65.8%** (77/117) | **69.8%** (74/106) | 51.1% (48/94) | **65.0%** (13/20) | **58.0%** (29/50) |
| **Mode A** | `EnglishGem(Jersey_Name) mod 360` | 58.4% (136/233) | 58.7% (74/126) | 64.8% (81/125) | 53.2% (50/94) | 35.7% (5/14) | 50.0% (25/50) |
| **Mode B** | `(EnglishGem(Jersey_Name) + Jersey_No_Eff) mod 360` | 54.5% (126/231) | 58.9% (76/129) | 57.4% (58/101) | **53.6%** (60/112) | 44.4% (8/18) | 54.0% (27/50) |

## Dedicated Google Spreadsheets

- **Input Sheet (`NHL-PLAYERS-GEOMANTIC-INPUT`)**: `https://docs.google.com/spreadsheets/d/1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE/edit`
  - Tabs: `Sheet1`, `NHL-PLAYERS-GEM` (866 active NHL players), `TEAMS` (32 active + historical relocated arenas/timezones), `DECAN_TABLE_36`, `NHL_SCHEDULE_2025_2027`
- **Calculation Sheet (`NHL-PLAYERS-CALCULATION`)**: `https://docs.google.com/spreadsheets/d/16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs/edit`
  - Tabs: `DEG3_Mode_Benchmark`, `Game_Predictions_ModeC`, `Game_Predictions_ModeB`, `Game_Predictions_ModeA`, `Active_Player_Calculations`

## Key Commands

```bash
pnpm install
pnpm run typecheck
pnpm run build

# Refresh ESPN NHL rosters, seasonal TOI, jerseys, and 2026-27 boxscores:
python3 artifacts/api-server/python/fetch_nhl_players_2010_2027.py

# Rebuild all 3 zero-lookahead NHL player modes:
python3 artifacts/api-server/python/build_all_nhl_player_modes.py

# Live ESPN NHL score sync across Mode C / B / A:
python3 artifacts/api-server/python/nhl_live_sync.py
```
