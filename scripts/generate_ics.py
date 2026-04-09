#!/usr/bin/env python3
"""
Generate a .ics file for a single user entry.

Usage:
    python3 scripts/generate_ics.py --council-id kirklees_gov_uk \
        --args '{"door_num": "1", "postcode": "HD9 6RJ"}' \
        --hash a3f9c2d1 \
        --output-dir calendars

Environment:
    WCS_REPO  Path to cloned mampfes/hacs_waste_collection_schedule repo
              (default: ./wcs_repo)
"""

import argparse
import importlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone


def load_source_module(module_id: str, wcs_repo: str):
    source_pkg_dir = os.path.join(
        wcs_repo, "custom_components", "waste_collection_schedule"
    )
    if source_pkg_dir not in sys.path:
        sys.path.append(source_pkg_dir)
    mod = importlib.import_module(f"waste_collection_schedule.source.{module_id}")
    return mod


def fetch_collections(module_id: str, args: dict, wcs_repo: str) -> list:
    mod = load_source_module(module_id, wcs_repo)
    source = mod.Source(**args)
    collections = source.fetch()
    return collections


def escape_ics(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def generate_ics(collections: list, council_title: str, address_hint: str) -> str:
    now = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UK Bin Cal//bin-cal//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics(council_title)} Bin Collections",
        f"X-WR-CALDESC:Bin collection schedule for {escape_ics(address_hint)}",
        "X-WR-TIMEZONE:Europe/London",
        "X-PUBLISHED-TTL:PT12H",
    ]

    for col in collections:
        col_date = col.date  # datetime.date object
        col_type = col.type  # str like "Recycling", "General Waste"

        dtstart = col_date.strftime("%Y%m%d")
        dtend = (col_date + timedelta(days=1)).strftime("%Y%m%d")
        uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{dtstart}-{col_type}-{address_hint}"))

        # Reminder the evening before at 7pm
        alarm_trigger = "PT-17H"  # relative to the start of the event day = 7pm previous day

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{escape_ics(col_type)} collection",
            f"DESCRIPTION:Put out your {escape_ics(col_type)} bin tonight.",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"TRIGGER:{alarm_trigger}",
            f"DESCRIPTION:Bin collection tomorrow: {escape_ics(col_type)}",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--council-id", required=True, help="Module ID e.g. kirklees_gov_uk")
    parser.add_argument("--council-title", default="", help="Human-readable council name")
    parser.add_argument("--args", required=True, help="JSON string of source args")
    parser.add_argument("--hash", required=True, help="8-char hash slug for filename")
    parser.add_argument("--output-dir", default="calendars", help="Output directory")
    parser.add_argument(
        "--wcs-repo",
        default=os.environ.get("WCS_REPO", "wcs_repo"),
        help="Path to cloned mampfes repo",
    )
    opts = parser.parse_args()

    args = json.loads(opts.args)
    council_title = opts.council_title or opts.council_id.replace("_", " ").title()

    # Build a readable address hint from args (no secrets, just postcode)
    address_hint = args.get("postcode", opts.hash)

    print(f"Fetching collections for {council_title} ({address_hint})...")
    collections = fetch_collections(opts.council_id, args, opts.wcs_repo)
    print(f"  Got {len(collections)} collection entries")

    ics_content = generate_ics(collections, council_title, address_hint)

    os.makedirs(opts.output_dir, exist_ok=True)
    out_path = os.path.join(opts.output_dir, f"{opts.hash}.ics")
    with open(out_path, "w", newline="") as f:
        f.write(ics_content)

    print(f"  Written to {out_path}")


if __name__ == "__main__":
    main()
