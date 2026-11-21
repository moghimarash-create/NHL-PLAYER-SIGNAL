import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_DIR = path.resolve(__dirname, "..", "python");

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

const INPUT_SHEET_ID = "1DIuN12_G3FRfCThsmhPvtq8nLnU2gJBd0H_635t39FE";
const CALC_SHEET_ID = "16lAFg4a896jWHx4WeDxoLk_RQslyJAHZw51YmjjRABs";

const sheetUrl = (id: string, tab?: string): string =>
  tab
    ? `https://docs.google.com/spreadsheets/d/${id}/edit#gid=0&fvid=${encodeURIComponent(tab)}`
    : `https://docs.google.com/spreadsheets/d/${id}/edit`;

export const STEPS: StepDef[] = [
  {
    id: 1,
    name: "NHL Player Astro-Elemental Calculator (866 Active Players • DEG1=88)",
    description:
      "Player-driven NHL mode: DEG1=88 fixed; 13-man pre-game TOI-weighted lineup (Top 12 Skaters + Primary Goalie, excluding OUT/IR); DEG2=EnglishGem(Full_Name) mod 360; DEG3 tested across 3 modes (Mode C: Jersey_No mod 360 | Mode B: (Jersey_Name + Jersey_No) mod 360 | Mode A: Jersey_Name mod 360) inside Host Arena coordinates & puck-drop sky.",
    runtime: "python",
    implemented: true,
    command: "python3",
    args: [path.join(PYTHON_DIR, "nhl_live_sync.py")],
    inputs: [
      {
        label: "NHL-PLAYERS-GEOMANTIC-INPUT (Sheet1: Active Date Slate & DEG1=88)",
        spreadsheetId: INPUT_SHEET_ID,
        tab: "Sheet1",
        url: sheetUrl(INPUT_SHEET_ID),
      },
      {
        label: "NHL-PLAYERS-GEOMANTIC-INPUT :: NHL-PLAYERS-GEM (866 Players: DEG2 & 3 DEG3 Variants)",
        spreadsheetId: INPUT_SHEET_ID,
        tab: "NHL-PLAYERS-GEM",
        url: sheetUrl(INPUT_SHEET_ID, "NHL-PLAYERS-GEM"),
      },
      {
        label: "NHL-PLAYERS-GEOMANTIC-INPUT :: TEAMS & NHL_SCHEDULE_2025_2027",
        spreadsheetId: INPUT_SHEET_ID,
        tab: "TEAMS",
        url: sheetUrl(INPUT_SHEET_ID, "TEAMS"),
      },
    ],
    outputs: [
      {
        label: "NHL-PLAYERS-CALCULATION :: DEG3_Mode_Benchmark (3-Mode Zero-Lookahead Comparison)",
        spreadsheetId: CALC_SHEET_ID,
        tab: "DEG3_Mode_Benchmark",
        url: sheetUrl(CALC_SHEET_ID, "DEG3_Mode_Benchmark"),
      },
      {
        label: "NHL-PLAYERS-CALCULATION :: Game_Predictions_ModeC / ModeB / ModeA",
        spreadsheetId: CALC_SHEET_ID,
        tab: "Game_Predictions_ModeC",
        url: sheetUrl(CALC_SHEET_ID, "Game_Predictions_ModeC"),
      },
      {
        label: "NHL-PLAYERS-CALCULATION :: Active_Player_Calculations (13 Active Players Per Team: 12S + 1G)",
        spreadsheetId: CALC_SHEET_ID,
        tab: "Active_Player_Calculations",
        url: sheetUrl(CALC_SHEET_ID, "Active_Player_Calculations"),
      },
    ],
  },
];

export function getStep(id: number): StepDef | undefined {
  return STEPS.find((s) => s.id === id);
}
