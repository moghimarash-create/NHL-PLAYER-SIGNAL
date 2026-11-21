"""Shared Google Sheets client. Reads service account JSON from env."""
import json
import os
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _load_service_account_info() -> dict[str, Any]:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON secret is not set in this Replit project. "
            "Add it under Tools -> Secrets."
        )
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}. "
            "Paste the entire service-account JSON file contents as the secret value."
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
    return get_client().open_by_key(spreadsheet_id)
