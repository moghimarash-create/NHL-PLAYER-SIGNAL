"""Shared Google Sheets client with hard safety guard against live NBA spreadsheets."""
import json
import os
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Hard blocklist of live NBA Google Sheet IDs so NHL-PLAYER-SIGNAL can NEVER touch or overwrite them.
FORBIDDEN_NBA_SHEET_IDS = frozenset({
    "1YVnrJxI8zVztJM9e5hGVBxRps4LblfxBFzAN7i20nqs",  # NBA-PLAYERS-GEOMANTIC-INPUT
    "1Lasp4OwUsO3CZ86jzAXykJWTJll-mIDXRWtKQpIcntM",  # NBA-PLAYERS-CALCULATION
    "1lFQgTDURItuY0LeIjcTeRRsAZDBHqXQ9j013qNq45o8",  # NBA-GEOMANTIC-INPUT
    "1yi4rNBwT4iktcZms_lEJNJ-SPNQ9Kc0d-6AeX9KzikA",  # NBA-Calculation
    "1MqZL-5y7k5aQOYjfHdtnsRrBPviF811gnVGp8IggdtQ",  # NBA-Result-Degree
    "1GCTMMwmOPpc6d3rVhY8_Tnr6lbJxiYqy62C3N2MUvBI",  # NBA-Aspects
    "1CewQkD-FFuE6RAtAtosIvC2sLHmAywA4cCx1CSgVvHI",  # NBA-Astro_Header_Input
    "1jw2UuFCyQLWCiPZimAmlCInu4Iq-ec149wyI6dJpK-U",  # NBA-Astro_Input
    "1YYAe9PqsxDLfMAMC5UyDz8Ihh3lLUz7UNwVUjWs5-fo",  # NBA-FUSION-INPUT
    "1OOSLnGUdNiuSNSKzzkT6Q_UqI0dcj7J4AMkLwH4A24Q",  # NBA-FUSION-CALCULATION
    "1HSscf2X7yeE7_Wi74Svam9QcVZOVQqi25r5DhlyP5PQ",  # NBA-Twin-History-2010-2026
})


def _load_service_account_info() -> dict[str, Any]:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set."
        )
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}."
        ) from e


_client: gspread.Client | None = None


def get_client() -> gspread.Client:
    global _client
    if _client is None:
        info = _load_service_account_info()
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client


def open_sheet(spreadsheet_id: str) -> gspread.Spreadsheet:
    sid = str(spreadsheet_id or "").strip()
    if not sid:
        raise RuntimeError("Spreadsheet ID is empty. Set NHL_PLAYER_INPUT_SHEET_ID / NHL_PLAYER_CALC_SHEET_ID.")
    if sid in FORBIDDEN_NBA_SHEET_IDS:
        raise RuntimeError(
            f"Refusing to open protected live NBA spreadsheet ({sid}) from NHL-PLAYER-SIGNAL."
        )
    return get_client().open_by_key(sid)
