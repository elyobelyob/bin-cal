#!/usr/bin/env python3
"""
Parse the mampfes/hacs_waste_collection_schedule repo to generate councils.json.
Run from the repo root: python3 scripts/generate_councils.py

Requires the repo to be cloned at /tmp/wcs (or set WCS_REPO env var).
"""

import json
import os
import re
import sys

WCS_REPO = os.environ.get("WCS_REPO", "/tmp/wcs")
SOURCES_JSON = os.path.join(WCS_REPO, "custom_components/waste_collection_schedule/sources.json")
DOC_DIR = os.path.join(WCS_REPO, "doc/source")
OUT = os.path.join(os.path.dirname(__file__), "..", "councils.json")


def parse_args_from_doc(module_id: str) -> list[dict]:
    """Extract configuration variables from the markdown doc for a source module."""
    doc_path = os.path.join(DOC_DIR, f"{module_id}.md")
    if not os.path.exists(doc_path):
        return []

    with open(doc_path) as f:
        content = f.read()

    args = []
    # Match configuration variables section entries like:
    # **field_name**
    # *(type) (required/optional)*
    pattern = re.compile(
        r'\*\*(\w+)\*\*\s*[<br>]*\s*\n\s*\*\(([^)]+)\)\s*(\([^)]*\))?\s*(\([^)]*\))?\*',
        re.IGNORECASE
    )

    # Also try alternative pattern
    pattern2 = re.compile(
        r'\*\*(\w+)\*\*\s*\n\s*\*\(([^)]+)\)\s*\(?(required|optional)?\)?\*',
        re.IGNORECASE
    )

    seen = set()
    for m in pattern.findall(content):
        name, type_str, qual1, qual2 = m
        name = name.strip()
        if name in seen:
            continue
        seen.add(name)
        qualifiers = f"{qual1} {qual2}".lower()
        required = "optional" not in qualifiers
        args.append({"name": name, "type": type_str.strip(), "required": required})

    if not args:
        for m in pattern2.findall(content):
            name, type_str, required_str = m
            name = name.strip()
            if name in seen:
                continue
            seen.add(name)
            required = required_str.lower() != "optional" if required_str else True
            args.append({"name": name, "type": type_str.strip(), "required": required})

    # Fallback: look for yaml example block and infer args
    if not args:
        yaml_match = re.search(r'```yaml.*?args:\s*\n(.*?)```', content, re.DOTALL)
        if yaml_match:
            for line in yaml_match.group(1).splitlines():
                m = re.match(r'\s+(\w+):', line)
                if m:
                    name = m.group(1).strip()
                    if name not in seen and name not in ('name', 'sources', 'waste_collection_schedule'):
                        seen.add(name)
                        args.append({"name": name, "type": "string", "required": True})

    return args


def main():
    with open(SOURCES_JSON) as f:
        sources = json.load(f)

    uk_sources = sources.get("United Kingdom", [])

    councils = []
    seen_ids = set()

    for entry in uk_sources:
        module = entry["module"]
        title = entry["title"]
        source_id = entry["id"]
        default_params = entry.get("default_params", {})

        # Deduplicate by source_id (some modules serve multiple councils)
        if source_id in seen_ids:
            # If there are default_params differentiating, keep it
            if not default_params:
                continue
        seen_ids.add(source_id)

        args = parse_args_from_doc(module)

        # For the generic ICS module, only expose the url field — all other
        # parameters (regex, split_at, headers, etc.) are developer knobs that
        # no end-user can meaningfully fill in.
        ics_hint = None
        if module == "ics":
            args = [{"name": "url", "type": "string", "required": True}]
            ics_hint = (
                "To get your calendar URL: visit your council\u2019s website, search for your address, "
                "and look for a \u201cSubscribe\u201d or \u201cAdd to calendar\u201d option on your bin collection page. "
                "Right-click or copy the link \u2014 it should end in <code>.ics</code> \u2014 and paste it above."
            )

        # Merge default_params into args as hidden fixed fields
        council = {
            "id": source_id,
            "module": module,
            "title": title,
            "args": args,
        }
        if default_params:
            council["default_params"] = default_params
        if ics_hint:
            council["hint"] = ics_hint

        councils.append(council)

    councils.sort(key=lambda c: c["title"])

    with open(OUT, "w") as f:
        json.dump(councils, f, indent=2)

    print(f"Generated {len(councils)} UK councils -> {OUT}")


if __name__ == "__main__":
    main()
