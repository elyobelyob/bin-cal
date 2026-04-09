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
    "Midgebottom House": {"uprn": "83074265", "postcode": "HD9 7HA"},
}

BASE_URL = "https://my.kirklees.gov.uk"
SERVICE_PATH = "/service/Bins_and_recycling___Manage_your_bins"
FORM_ID = "AF-Form-0d9c96d0-4067-4bea-9a5b-06f32a675be6"

# Step 1: postcode → address list (UPRN → PropertyReference)
LOOKUP_ADDRESS = "58049013ca4c9"
# Steps 2+: called after address selection; collection dates expected in the later two
LOOKUP_IDS_STEP2 = [
    "699d8de6a7183",
    "631615c4bd3b7",
    "659c2c2386104",
    "661d3dbd48355",
    "65e08e60b299d",
    "65e5ec5dc4ac6",
]

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


class Source:
    def __init__(self, uprn: str | int, postcode: str):
        self._uprn = str(uprn)
        self._postcode = postcode.strip().upper()

    def fetch(self) -> list[Any]:
        s = requests.Session()

        # 1. Init session
        ts = time_ns() // 1_000_000
        s.get(
            f"{BASE_URL}/apibroker/domain/my.kirklees.gov.uk?_={ts}",
            headers=HEADERS,
            timeout=30,
        ).raise_for_status()

        # 2. Get SID
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

        # 3. Step 1: postcode lookup → get PropertyReference for our UPRN
        # Try common section/field name combinations
        step1_candidates = [
            ("Section 1", "postcode"),
            ("Section 1", "Postcode"),
            ("Section 1", "PostCode"),
            ("Section 1", "searchPostcode"),
            ("Section 1", "addressSearch"),
            ("Your address", "postcode"),
            ("Your address", "Postcode"),
            ("Address", "postcode"),
            ("Search", "postcode"),
        ]
        rows1_raw: Any = {}
        for section, field in step1_candidates:
            payload_step1: dict[str, Any] = {
                "formId": FORM_ID,
                "formValues": {section: {field: {"value": self._postcode}}},
            }
            d = _run_lookup(s, sid, LOOKUP_ADDRESS, payload_step1)
            r = d.get("integration", {}).get("transformed", {}).get("rows_data", {})
            print(f"DEBUG step1 [{section}/{field}]: rows={len(r) if r else 0}")
            if r:
                rows1_raw = r
                print(f"DEBUG step1 MATCH: section='{section}' field='{field}'")
                break

        # rows_data may be a dict keyed by UPRN or a list of dicts
        if isinstance(rows1_raw, dict):
            rows1 = rows1_raw  # keyed by UPRN ("name" field)
        else:
            # list → build dict keyed by "name" (UPRN)
            rows1 = {str(r.get("name", i)): r for i, r in enumerate(rows1_raw)}

        print(f"DEBUG step1 rows keys: {list(rows1.keys())[:5]}")

        # Find our property by UPRN
        if self._uprn not in rows1:
            raise ValueError(
                f"Kirklees: UPRN {self._uprn} not found in postcode {self._postcode} results. "
                f"Found: {list(rows1.keys())}"
            )

        prop_ref = rows1[self._uprn]["PropertyReference"]
        print(f"DEBUG PropertyReference for UPRN {self._uprn}: {prop_ref}")

        # 4. Step 2: try each subsequent lookup with PropertyReference + UPRN
        # Include all plausible field names from the form; extra fields are ignored by the API
        payload_step2: dict[str, Any] = {
            "formId": FORM_ID,
            "formValues": {
                "Section 1": {
                    "Postcode": {"value": self._postcode},
                    "PropertyReference": {"value": prop_ref},
                    "propertyReference": {"value": prop_ref},
                    "suppliedUPRN": {"value": self._uprn},
                    "uprn": {"value": self._uprn},
                    "UPRN": {"value": self._uprn},
                }
            },
        }

        for lid in LOOKUP_IDS_STEP2:
            try:
                data = _run_lookup(s, sid, lid, payload_step2)
                transformed = data.get("integration", {}).get("transformed", {})
                rows_raw = transformed.get("rows_data", {})
                fields_raw = transformed.get("fields_data", {})
                field_keys = list(fields_raw.keys()) if isinstance(fields_raw, dict) else list(fields_raw) if isinstance(fields_raw, list) else []
                if isinstance(rows_raw, dict):
                    rows_list = list(rows_raw.values())
                elif isinstance(rows_raw, list):
                    rows_list = rows_raw
                else:
                    rows_list = []
                print(f"DEBUG lookup {lid}: fields={field_keys}, rows_count={len(rows_list)}")
                for i, row in enumerate(rows_list[:3]):
                    print(f"DEBUG lookup {lid} row[{i}]: {json.dumps(row)}")
            except Exception as exc:
                print(f"DEBUG lookup {lid} error: {exc}")

        raise ValueError(
            "Kirklees DEBUG: check output above to identify which lookup contains collection dates"
        )
