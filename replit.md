# NHL-PLAYER-SIGNAL Workspace

## Overview

pnpm workspace monorepo using TypeScript + Python (`pyswisseph`, `numpy`, `pytz`) for the **NHL Player Astrological & Elemental Signal Dashboard (`DEG1 = 88`)**.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Frontend (`artifacts/calc-dashboard`)**: React 19 + Vite + Tailwind CSS v4 (Persian RTL UI, 3-Mode `DEG3` switcher, 13-Player active lineup drawer, 12-column manual Elemental Twins filter, Kalshi `KXNHLGAME` auto-betting & MVE combo panel)
- **API Server (`artifacts/api-server`)**: Express 5 (`/api/nhl/sync`, `/api/nhl/predictions`, `/api/nhl/history-pack`, `/api/kalshi/nhl-markets`, `/api/kalshi/execute`, `/api/kalshi/combo`)
- **Python Astro-Elemental Engine (`artifacts/api-server/python`)**: Swiss Ephemeris (`pyswisseph`), zero-lookahead (`r.d < g.d`) 22,610-game NHL twin search & 5-method 30-vote fusion

## NHL Player Signal Architecture (`DEG1 = 88`)

- **Fixed League Degree**: `DEG1 = 88` (`EnglishGem("NHL") = 88`)
- **Player Full Name Degree**: `DEG2 = EnglishGem(Full_Name) mod 360`
- **3 `DEG3` Player Variants (Zero-Lookahead 2010–2027 Benchmark)**:
  - **`mode_c` (Recommended — 61.4% 2024–27, 65.8% VIP, 65.0% 2026–27 Live)**: `DEG3 = Jersey_No_Eff mod 360`
  - **`mode_a` (58.4% 2024–27)**: `DEG3 = EnglishGem(Jersey_Name) mod 360`
  - **`mode_b` (54.5% 2024–27)**: `DEG3 = (EnglishGem(Jersey_Name) + Jersey_No_Eff) mod 360`
- **Pre-Game Active 13-Player Lineup**:
  - **1 Primary/Starting Active Goalie** (`pos == "G"`, effective TOI `38–60m`)
  - **Top 12 Active Skaters** (`C`, `LW`, `RW`, `D`) ranked by strictly pre-game Time On Ice (`TOI`)
  - Automatically excludes injured/unavailable players (`OUT`, `Injured Reserve`, `IR`, `IR-LT`, `Suspended`) on pending slates
- **Dedicated Google Spreadsheets**:
  - `NHL-PLAYERS-GEOMANTIC-INPUT`: `1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE` (`Sheet1`, `NHL-PLAYERS-GEM`, `TEAMS`, `DECAN_TABLE_36`, `NHL_SCHEDULE_2025_2027`)
  - `NHL-PLAYERS-CALCULATION`: `16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs` (`DEG3_Mode_Benchmark`, `Game_Predictions_ModeC`, `Game_Predictions_ModeB`, `Game_Predictions_ModeA`, `Active_Player_Calculations`)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `python3 artifacts/api-server/python/fetch_nhl_players_2010_2027.py` — refresh 32 live NHL rosters, injuries, 2009–2027 TOI stats, jerseys, and 2026–27 boxscores
- `python3 artifacts/api-server/python/build_all_nhl_player_modes.py` — recompute all 3 zero-lookahead NHL player modes
- `python3 artifacts/api-server/python/nhl_live_sync.py` — live ESPN NHL score sync across Mode C / B / A
