from datetime import date, datetime, timedelta
from time import time_ns
from typing import Any

import requests
from waste_collection_schedule import Collection  # type: ignore[attr-defined]


TITLE = "Kirklees Council"
DESCRIPTION = "Source for waste collections for Kirklees Council (my.kirklees.gov.uk)"
URL = "https://www.kirklees.gov.uk"
TEST_CASES = {
    "Midgebottom House": {"uprn": "83074265", "postcode": "HD9 7HA"},
    "HD8 8NA test": {"uprn": "83194785", "postcode": "HD8 8NA"},
}

BASE_URL = "https://my.kirklees.gov.uk"
SERVICE_PATH = "/service/Bins_and_recycling___Manage_your_bins"
FORM_ID = "AF-Form-0d9c96d0-4067-4bea-9a5b-06f32a675be6"

LOOKUP_ADDRESS = "58049013ca4c9"      # postcode → address list (keyed by UPRN)
LOOKUP_COLLECTIONS = "65e5ec5dc4ac6"  # uprnFinal → bin collection dates

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
    "recycling": "mdi:recycle",
    "domestic": "mdi:trash-can",
    "garden": "mdi:leaf",
    "green": "mdi:recycle",
    "grey": "mdi:trash-can",
    "brown": "mdi:leaf",
    "blue": "mdi:recycle",
}


def _icon(waste_type: str) -> str:
    t = waste_type.lower()
    for k, v in ICON_MAP.items():
        if k in t:
            return v
    return "mdi:trash-can"


def _run_lookup(s: requests.Session, sid: str, lookup_id: str, payload: dict) -> dict:
    ts = time_ns() // 1_000_000
    url = (
        f"{BASE_URL}/apibroker/runLookup"
        f"?id={lookup_id}&repeat_against=&noRetry=false"
        f"&getOnlyTokens=undefined&log_id=&app_name=AF-Renderer::Self"
        f"&_={ts}&sid={sid}"
    )
    r = s.post(url, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def _rows(data: dict) -> dict:
    """Normalise rows_data to a dict regardless of whether the API returned a list or dict."""
    raw = data.get("integration", {}).get("transformed", {}).get("rows_data", {})
    if isinstance(raw, dict):
        return raw
    return {str(r.get("name", i)): r for i, r in enumerate(raw)}


class Source:
    def __init__(self, uprn: str | int, postcode: str):
        self._uprn = str(uprn)
        self._postcode = postcode.strip().upper()

    def fetch(self) -> list[Any]:
        s = requests.Session()

        # 1. Init session cookies
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

        # 3. Postcode lookup — validate the UPRN is at this postcode
        addr_data = _run_lookup(s, sid, LOOKUP_ADDRESS, {
            "formId": FORM_ID,
            "formValues": {
                "Section 1": {"Postcode": {"value": self._postcode}}
            },
        })
        addr_rows = _rows(addr_data)
        if self._uprn not in addr_rows:
            raise ValueError(
                f"Kirklees: UPRN {self._uprn} not found for postcode {self._postcode}. "
                f"Found: {list(addr_rows.keys())}"
            )

        # 4. Collection lookup — Search section with uprnFinal + date window
        today = date.today()
        from_date = (today - timedelta(days=7)).strftime("%d/%m/%Y")
        to_date = (today + timedelta(days=28)).strftime("%d/%m/%Y")

        col_data = _run_lookup(s, sid, LOOKUP_COLLECTIONS, {
            "formId": FORM_ID,
            "formValues": {
                "Search": {
                    "uprnFinal":      {"value": self._uprn},
                    "validatedUPRN":  {"value": self._uprn},
                    "suppliedUPRN":   {"value": self._uprn},
                    "uprn2":          {"value": self._uprn},
                },
                "Your bins": {
                    "NextCollectionFromDate": {"value": from_date},
                    "NextCollectionToDate":   {"value": to_date},
                },
            },
        })
        col_rows = _rows(col_data)

        if not col_rows:
            raise ValueError(
                f"Kirklees: no collection data returned for UPRN {self._uprn}."
            )

        entries: list[Any] = []
        for row in col_rows.values():
            date_str  = row.get("nextCollectionDate", "")
            bin_type  = row.get("BinType") or row.get("BinDescription", "")
            if not date_str or not bin_type:
                continue
            # API returns "13/04/2026 00:00:00"
            try:
                col_date = datetime.strptime(date_str.split()[0], "%d/%m/%Y").date()
            except ValueError:
                continue
            entries.append(
                Collection(date=col_date, t=str(bin_type), icon=_icon(str(bin_type)))
            )

        return entries
