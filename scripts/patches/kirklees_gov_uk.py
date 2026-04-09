import logging
import re
from datetime import datetime
from typing import Any

from curl_cffi import requests
from bs4 import BeautifulSoup
from waste_collection_schedule import Collection  # type: ignore[attr-defined]

_LOGGER = logging.getLogger(__name__)

TITLE = "Kirklees Council"
DESCRIPTION = "Source for waste collections for Kirklees Council"
URL = "https://www.kirklees.gov.uk"
TEST_CASES = {
    "Test_001": {"door_num": 20, "postcode": "HD9 6LW"},
    "test_002": {"door_num": "6", "postcode": "hd9 1js"},
    "HD8 8NA, 1": {"door_num": "1", "postcode": "HD8 8NA", "uprn": "83194785"},
}

BASE_URL = "https://www.kirklees.gov.uk/beta/your-property-bins-recycling/your-bins/"

PARAMS = {
    "__EVENTTARGET": "",
    "__EVENTARGUMENT": "",
    "__LASTFOCUS": "",
    "__VIEWSTATE": "",
    "__VIEWSTATEGENERATOR": "",
    "__SCROLLPOSITIONX": "0",
    "__SCROLLPOSITIONY": "0",
    "__EVENTVALIDATION": "",
    "ctl00$ctl00$cphPageBody$cphContent$hdnBinUPRN": "",
}

COLLECTION_REGEX = (
    "(Recycling|Domestic|Garden Waste).*collection date ([0-3][0-9] [a-zA-Z]* [0-9]{4})"
)

ICON_MAP = {
    "DOMESTIC": "mdi:trash-can",
    "RECYCLING": "mdi:recycle",
    "GARDEN WASTE": "mdi:leaf",
}

# Matches any calendar download link regardless of bin size (180, 240, etc.)
CAL_LINK_RE = re.compile(r"cphPageBody_cphContent_wtc\w+_LnkCalendar")


class Source:
    def __init__(
        self, door_num: str | int, postcode: str, uprn: str | int | None = None
    ):
        self._door_num = door_num
        self._postcode = postcode
        self._uprn = uprn
        self._session = requests.Session(impersonate="chrome124")
        self._params: dict[str, Any] = PARAMS

    def _update_params(self, soup: BeautifulSoup) -> None:
        self._params = {k: v for k, v in PARAMS.items()}

        self._params["__VIEWSTATE"] = (
            soup.select_one("input#__VIEWSTATE") or dict[str, str]()
        ).get("value")
        self._params["__VIEWSTATEGENERATOR"] = (
            soup.select_one("input#__VIEWSTATEGENERATOR") or dict[str, str]()
        ).get("value")
        self._params["__EVENTVALIDATION"] = (
            soup.select_one("input#__EVENTVALIDATION") or dict[str, str]()
        ).get("value")

        if soup.find(
            "input",
            {"name": "ctl00$ctl00$cphPageBody$cphContent$thisGeoSearch$txtGeoPremises"},
        ):
            self._params[
                "ctl00$ctl00$cphPageBody$cphContent$thisGeoSearch$txtGeoPremises"
            ] = self._door_num
            self._params[
                "ctl00$ctl00$cphPageBody$cphContent$thisGeoSearch$txtGeoSearch"
            ] = self._postcode
            self._params[
                "ctl00$ctl00$cphPageBody$cphContent$thisGeoSearch$butGeoSearch"
            ] = (soup.select_one("input#butGeoSearch") or dict[str, str]()).get("value")

        if soup.select_one("table#dagAddressList"):
            self._params["ctl00$ctl00$cphPageBody$cphContent$hdnBinUPRN"] = self._uprn
            self._params["UPRN"] = self._uprn
            self._params[
                "ctl00$ctl00$cphPageBody$cphContent$thisGeoSearch$butSelectAddress"
            ] = (soup.select_one("input#butSelectAddress") or dict[str, str]()).get(
                "value"
            )

    def _find_cal_link(self, soup: BeautifulSoup):
        """Find the calendar download link, tolerating any bin size in the element ID."""
        return soup.find("a", {"id": CAL_LINK_RE})

    def fetch(self):
        entries = []
        self._session.cookies.set(
            "cookiesacceptedGDPR", "true", domain=".kirklees.gov.uk"
        )

        r0 = self._session.get(f"{BASE_URL}/default.aspx")
        r0.raise_for_status()
        r0_bs4 = BeautifulSoup(r0.text, features="html.parser")
        print(f"DEBUG r0: title={r0_bs4.title}, status={r0.status_code}, url={r0.url}")
        print(f"DEBUG r0 html[:3000]: {r0.text[:3000]}")
        self._update_params(r0_bs4)
        search_url = f"{BASE_URL}/default.aspx"
        r1 = self._session.post(
            search_url,
            data=self._params,
            headers={"Referer": r0.url},
        )
        r1.raise_for_status()
        r1_bs4 = BeautifulSoup(r1.text, features="html.parser")
        print(f"DEBUG r1: title={r1_bs4.title}, status={r1.status_code}")
        print(f"DEBUG r1 params keys: {list(self._params.keys())}")

        if r1_bs4.select_one("table#dagAddressList"):
            # Multiple addresses returned — need UPRN to select one
            if not self._uprn:
                raise ValueError("UPRN required: multiple properties found for this address")
            self._update_params(r1_bs4)
            r1 = self._session.post(
                f"{BASE_URL}/default.aspx",
                data=self._params,
                headers={"Referer": r1.url},
            )
            r1.raise_for_status()
            r1_bs4 = BeautifulSoup(r1.text, features="html.parser")

        cal_link_el = self._find_cal_link(r1_bs4)

        if cal_link_el is None and self._uprn:
            # Named property: the door-number search returned no usable results.
            # Re-run the search with an empty door number so the council returns ALL
            # properties in the postcode as a dagAddressList, then select with UPRN.
            print("DEBUG: cal_link not found after normal search, trying postcode-only fallback")
            print(f"DEBUG: page title after normal search: {r1_bs4.title}")
            print(f"DEBUG: dagAddressList present: {bool(r1_bs4.select_one('table#dagAddressList'))}")
            print(f"DEBUG: all <a> ids on page: {[a.get('id') for a in r1_bs4.find_all('a') if a.get('id')]}")

            saved_door_num = self._door_num
            self._door_num = ""
            self._update_params(r0_bs4)  # fresh params from initial page
            r1 = self._session.post(
                f"{BASE_URL}/default.aspx",
                data=self._params,
                headers={"Referer": r0.url},
            )
            r1.raise_for_status()
            r1_bs4 = BeautifulSoup(r1.text, features="html.parser")
            self._door_num = saved_door_num

            print(f"DEBUG: page title after postcode-only search: {r1_bs4.title}")
            print(f"DEBUG: dagAddressList present: {bool(r1_bs4.select_one('table#dagAddressList'))}")
            print(f"DEBUG: all <a> ids on page: {[a.get('id') for a in r1_bs4.find_all('a') if a.get('id')]}")

            if r1_bs4.select_one("table#dagAddressList"):
                self._update_params(r1_bs4)
                r1 = self._session.post(f"{BASE_URL}/default.aspx", data=self._params)
                r1.raise_for_status()
                r1_bs4 = BeautifulSoup(r1.text, features="html.parser")
                print(f"DEBUG: page title after UPRN POST: {r1_bs4.title}")
                print(f"DEBUG: all <a> ids on page: {[a.get('id') for a in r1_bs4.find_all('a') if a.get('id')]}")

            cal_link_el = self._find_cal_link(r1_bs4)

        if cal_link_el is None:
            raise ValueError(
                f"Could not find collection calendar for '{self._door_num}', {self._postcode}. "
                "Check your door number / postcode, or provide a UPRN."
            )

        cal_link = cal_link_el["href"]

        r2 = self._session.get(f"{BASE_URL}/{cal_link}")
        r2.raise_for_status()
        r2_bs4 = BeautifulSoup(r2.text, features="html.parser")

        for collection in r2_bs4.find_all(
            "img",
            {
                "id": re.compile(
                    r"^cphPageBody_cphContent_rptr_Sticker_rptr_Collections_[0-9]_rptr_Bins_[0-9]_img_binType_[0-9]"
                )
            },
        ):
            matches = re.findall(COLLECTION_REGEX, collection["alt"])
            if matches:
                entries.append(
                    Collection(
                        date=datetime.strptime(matches[0][1], "%d %B %Y").date(),
                        t=matches[0][0],
                        icon=ICON_MAP.get(matches[0][0].upper()),
                    )
                )
        return entries
