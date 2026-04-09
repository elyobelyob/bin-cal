import json
from datetime import datetime
from time import time_ns
from typing import Any

import requests
from waste_collection_schedule import Collection  # type: ignore[attr-defined]


TITLE = "Kirklees Council"
DESCRIPTION = "Source for waste collections for Kirklees Council (my.kirklees.gov.uk)"
URL = "https://www.kirklees.gov.uk"
TEST_CASES = {
    "Midgebottom House": {"uprn": "83074265"},
    "HD9 6LW 20": {"uprn": "83194785"},
}

BASE_URL = "https://my.kirklees.gov.uk"
SERVICE_PATH = "/service/Bins_and_recycling___Manage_your_bins"
LOOKUP_ID = "58049013ca4c9"
FORM_ID = "AF-Form-0d9c96d0-4067-4bea-9a5b-06f32a675be6"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE_URL}{SERVICE_PATH}",
}

ICON_MAP = {
    "green": "mdi:recycle",
    "grey": "mdi:trash-can",
    "brown": "mdi:leaf",
    "blue": "mdi:recycle",
    "recycling": "mdi:recycle",
    "domestic": "mdi:trash-can",
    "garden": "mdi:leaf",
}


def _icon(waste_type: str) -> str:
    t = waste_type.lower()
    for k, v in ICON_MAP.items():
        if k in t:
            return v
    return "mdi:trash-can"


class Source:
    def __init__(self, uprn: str | int):
        self._uprn = str(uprn)

    def fetch(self) -> list[Any]:
        s = requests.Session()

        # 1. Hit domain endpoint to initialise session cookies
        ts = time_ns() // 1_000_000
        s.get(
            f"{BASE_URL}/apibroker/domain/my.kirklees.gov.uk?_={ts}",
            headers=HEADERS,
            timeout=30,
        ).raise_for_status()

        # 2. Obtain auth-session SID
        auth_url = (
            f"{BASE_URL}/authapi/isauthenticated"
            f"?uri=https%3A%2F%2Fmy.kirklees.gov.uk%2Fservice%2FBins_and_recycling___Manage_your_bins"
            f"&hostname=my.kirklees.gov.uk&withCredentials=true"
        )
        sid_r = s.get(auth_url, headers=HEADERS, timeout=30)
        sid_r.raise_for_status()
        sid = sid_r.json().get("auth-session")
        if not sid:
            raise ValueError("Kirklees API: failed to obtain session ID")

        # 3. POST to runLookup with UPRN
        ts = time_ns() // 1_000_000
        lookup_url = (
            f"{BASE_URL}/apibroker/runLookup"
            f"?id={LOOKUP_ID}&repeat_against=&noRetry=false"
            f"&getOnlyTokens=undefined&log_id=&app_name=AF-Renderer::Self"
            f"&_={ts}&sid={sid}"
        )
        payload: dict[str, Any] = {
            "formId": FORM_ID,
            "formValues": {
                "Section 1": {
                    "uprn": {"value": self._uprn},
                }
            },
        }
        r = s.post(lookup_url, headers=HEADERS, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()

        rows_data: dict[str, Any] = (
            data.get("integration", {})
            .get("transformed", {})
            .get("rows_data", {})
        )

        if not rows_data:
            raise ValueError(
                f"Kirklees API: no collection data returned for UPRN {self._uprn}. "
                f"Raw response: {json.dumps(data)[:500]}"
            )

        entries: list[Any] = []
        for _row_key, row in rows_data.items():
            # Each row is one collection event; field names TBC from live response
            # Common Firmstep patterns tried in order
            date_str = (
                row.get("date")
                or row.get("collectionDate")
                or row.get("nextDate")
                or row.get("NextCollectionDate")
            )
            waste_type = (
                row.get("type")
                or row.get("wasteType")
                or row.get("collectionType")
                or row.get("BinType")
                or row.get("service")
            )

            if not date_str or not waste_type:
                # Log unknown structure to help iteration
                print(f"DEBUG row {_row_key}: {json.dumps(row)}")
                continue

            # Parse dates — Firmstep commonly uses ISO or UK formats
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"):
                try:
                    col_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                print(f"DEBUG: unrecognised date format '{date_str}'")
                continue

            entries.append(
                Collection(date=col_date, t=str(waste_type), icon=_icon(str(waste_type)))
            )

        return entries
