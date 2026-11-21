import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_DIR = path.resolve(__dirname, "..", "python");

export const NHL_DEG1 = 88;
export const NHL_DEG1_SIGN = "28 GEMINI";
export const NHL_DEG1_ELEMENT = "AIR";

export type SheetLink = {
  label: string;
  spreadsheetId: string;
  tab?: string;
  url: string;
  market?: string;
};

export type StepDef = {
  id: number;
  name: string;
  description: string;
  runtime: "python" | "node";
  implemented: boolean;
  command: string;
  args: string[];
  inputs: SheetLink[];
  outputs: SheetLink[];
};

const INPUT_SHEET_ID = (process.env.NHL_PLAYER_INPUT_SHEET_ID ?? "").trim();
const CALC_SHEET_ID = (process.env.NHL_PLAYER_CALC_SHEET_ID ?? "").trim();

const sheetUrl = (id: string, fallbackApiPath: string, tab?: string): string => {
  if (!id) return fallbackApiPath;
  return tab
    ? `https://docs.google.com/spreadsheets/d/${id}/edit#gid=0&fvid=${encodeURIComponent(tab)}`
    : `https://docs.google.com/spreadsheets/d/${id}/edit`;
};

export const STEPS: StepDef[] = [
  {
    id: 1,
    name: "NHL Player Astro-Elemental Calculator (32 Teams • DEG1=88 • 28 GEMINI / AIR)",
    description:
      "Player-driven NHL mode: DEG1=88 (28 GEMINI / AIR) fixed; DEG2=EnglishGem(Full_Name) mod 360; DEG3 tested across 3 modes (Mode C: Jersey_No mod 360 | Mode B: (Jersey_Name + Jersey_No) mod 360 | Mode A: Jersey_Name mod 360) weighted by pre-game Time On Ice (TOI) with automatic exclusion of injured players (OUT, IR, IR-LT, IR-NR, Suspension) under all 32 NHL Host Arena coordinates & puck-drop sky.",
    runtime: "python",
    implemented: true,
    command: "python3",
    args: [path.join(PYTHON_DIR, "nhl_live_sync.py")],
    inputs: [
      {
        label: "NHL-PLAYERS-GEOMANTIC-INPUT (Sheet1: Active Date Slate & DEG1=88 • 28 GEMINI)",
        spreadsheetId: INPUT_SHEET_ID || "LOCAL_JSON_BACKUP",
        tab: "Sheet1",
        url: sheetUrl(INPUT_SHEET_ID, "/api/nhl/sheet-backup?kind=input"),
      },
      {
        label: "NHL-PLAYERS-GEOMANTIC-INPUT :: NHL-PLAYERS-GEM (32 NHL Teams: TOI, DEG2 & 3 DEG3 Modes)",
        spreadsheetId: INPUT_SHEET_ID || "LOCAL_JSON_BACKUP",
        tab: "NHL-PLAYERS-GEM",
        url: sheetUrl(INPUT_SHEET_ID, "/api/nhl/players-gem", "NHL-PLAYERS-GEM"),
      },
      {
        label: "NHL-PLAYERS-GEOMANTIC-INPUT :: TEAMS (32 NHL Arenas incl. Utah) & NHL_SCHEDULE_2024_2027",
        spreadsheetId: INPUT_SHEET_ID || "LOCAL_JSON_BACKUP",
        tab: "TEAMS",
        url: sheetUrl(INPUT_SHEET_ID, "/api/nhl/teams-gem", "TEAMS"),
      },
    ],
    outputs: [
      {
        label: "NHL-PLAYERS-CALCULATION :: DEG3_Mode_Benchmark (3-Mode Zero-Lookahead Comparison • DEG1=88)",
        spreadsheetId: CALC_SHEET_ID || "LOCAL_JSON_BACKUP",
        tab: "DEG3_Mode_Benchmark",
        url: sheetUrl(CALC_SHEET_ID, "/api/nhl/sheet-backup?kind=calc", "DEG3_Mode_Benchmark"),
      },
      {
        label: "NHL-PLAYERS-CALCULATION :: Game_Predictions_ModeC / ModeB / ModeA",
        spreadsheetId: CALC_SHEET_ID || "LOCAL_JSON_BACKUP",
        tab: "Game_Predictions_ModeC",
        url: sheetUrl(CALC_SHEET_ID, "/api/nhl/predictions?mode=mode_c", "Game_Predictions_ModeC"),
      },
      {
        label: "NHL-PLAYERS-CALCULATION :: Active_Player_Calculations (Top-8 TOI Active Players Per Team)",
        spreadsheetId: CALC_SHEET_ID || "LOCAL_JSON_BACKUP",
        tab: "Active_Player_Calculations",
        url: sheetUrl(CALC_SHEET_ID, "/api/nhl/sheet-backup?kind=calc", "Active_Player_Calculations"),
      },
    ],
  },
];

export function getStep(id: number): StepDef | undefined {
  return STEPS.find((s) => s.id === id);
}
