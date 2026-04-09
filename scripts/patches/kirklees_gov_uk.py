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

        print(f"DEBUG full response: {json.dumps(data)}")

        # Kirklees returns {"status": "done", "data": "<xml>"}
        xml_str = data.get("data", "")
        if not xml_str:
            raise ValueError(
                f"Kirklees API: empty response for UPRN {self._uprn}. "
                f"Response keys: {list(data.keys())}"
            )

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_str)

        # Print full structure for debugging
        print(f"DEBUG XML root tag: {root.tag}")
        for child in root:
            print(f"DEBUG child: {child.tag}")
            for grandchild in child:
                print(f"DEBUG  grandchild: {grandchild.tag} attribs={grandchild.attrib} text={grandchild.text!r}")
                for field in grandchild:
                    print(f"DEBUG   field: tag={field.tag} attribs={field.attrib} text={field.text!r}")

        raise ValueError(
            "Kirklees DEBUG: inspect the output above to determine field names, then update the scraper"
        )
