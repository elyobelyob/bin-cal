"""
Unit tests for generate_ics.py and kirklees_gov_uk.py helpers.
Run with: python3 -m pytest tests/
"""

import sys
import os
from datetime import date
from types import SimpleNamespace

# ── Path setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_ics


# ── escape_ics ───────────────────────────────────────────────────────────────

def test_escape_ics_passthrough():
    assert generate_ics.escape_ics("hello world") == "hello world"

def test_escape_ics_backslash():
    assert generate_ics.escape_ics("a\\b") == "a\\\\b"

def test_escape_ics_semicolon():
    assert generate_ics.escape_ics("a;b") == "a\\;b"

def test_escape_ics_comma():
    assert generate_ics.escape_ics("a,b") == "a\\,b"

def test_escape_ics_newline():
    assert generate_ics.escape_ics("a\nb") == "a\\nb"

def test_escape_ics_combined():
    assert generate_ics.escape_ics("semi;colon,back\\slash\nnewline") == \
        "semi\\;colon\\,back\\\\slash\\nnewline"


# ── generate_ics ─────────────────────────────────────────────────────────────

def _make_collection(d: date, t: str):
    return SimpleNamespace(date=d, type=t)


def test_generate_ics_structure():
    cols = [_make_collection(date(2026, 4, 20), "Grey wheelie bin")]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.strip().endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in ics
    assert "END:VEVENT" in ics


def test_generate_ics_event_fields():
    cols = [_make_collection(date(2026, 4, 20), "Grey wheelie bin")]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert "DTSTART;VALUE=DATE:20260420" in ics
    assert "DTEND;VALUE=DATE:20260421" in ics
    assert "SUMMARY:Grey wheelie bin collection" in ics


def test_generate_ics_dtend_is_dtstart_plus_one():
    cols = [_make_collection(date(2026, 12, 31), "Green wheelie bin")]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert "DTSTART;VALUE=DATE:20261231" in ics
    assert "DTEND;VALUE=DATE:20270101" in ics


def test_generate_ics_valarm_present():
    cols = [_make_collection(date(2026, 4, 20), "Grey wheelie bin")]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert "BEGIN:VALARM" in ics
    assert "END:VALARM" in ics
    assert "ACTION:DISPLAY" in ics
    assert "TRIGGER:PT-17H" in ics


def test_generate_ics_multiple_events():
    cols = [
        _make_collection(date(2026, 4, 13), "Green wheelie bin"),
        _make_collection(date(2026, 4, 20), "Grey wheelie bin"),
    ]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert ics.count("BEGIN:VEVENT") == 2


def test_generate_ics_escapes_special_chars_in_summary():
    cols = [_make_collection(date(2026, 4, 20), "Bin, Type; Special")]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert "SUMMARY:Bin\\, Type\\; Special collection" in ics


def test_generate_ics_empty_collections():
    ics = generate_ics.generate_ics([], "Test Council", "HD9 7HA")
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" not in ics


def test_generate_ics_crlf_line_endings():
    cols = [_make_collection(date(2026, 4, 20), "Grey wheelie bin")]
    ics = generate_ics.generate_ics(cols, "Test Council", "HD9 7HA")
    assert "\r\n" in ics


# ── _rows (kirklees) ─────────────────────────────────────────────────────────

# Import without triggering the WCS import (which isn't installed locally)
import importlib, types

def _load_kirklees():
    """Load kirklees_gov_uk.py with the WCS import stubbed out."""
    stub = types.ModuleType("waste_collection_schedule")
    stub.Collection = SimpleNamespace
    sys.modules.setdefault("waste_collection_schedule", stub)
    spec = importlib.util.spec_from_file_location(
        "kirklees_gov_uk",
        os.path.join(os.path.dirname(__file__), "..", "scripts", "patches", "kirklees_gov_uk.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kirklees = _load_kirklees()


def test_rows_dict_passthrough():
    data = {"integration": {"transformed": {"rows_data": {"A": {"x": 1}, "B": {"x": 2}}}}}
    result = kirklees._rows(data)
    assert result == {"A": {"x": 1}, "B": {"x": 2}}


def test_rows_list_to_dict():
    data = {"integration": {"transformed": {"rows_data": [
        {"name": "240G", "label": "Green"},
        {"name": "240D", "label": "Grey"},
    ]}}}
    result = kirklees._rows(data)
    assert "240G" in result
    assert result["240G"]["label"] == "Green"


def test_rows_empty_dict():
    data = {"integration": {"transformed": {"rows_data": {}}}}
    assert kirklees._rows(data) == {}


def test_rows_empty_list():
    data = {"integration": {"transformed": {"rows_data": []}}}
    assert kirklees._rows(data) == {}


def test_rows_missing_key():
    assert kirklees._rows({}) == {}


def test_rows_list_without_name_uses_index():
    data = {"integration": {"transformed": {"rows_data": [{"label": "Grey"}, {"label": "Green"}]}}}
    result = kirklees._rows(data)
    assert "0" in result
    assert "1" in result


# ── _icon (kirklees) ─────────────────────────────────────────────────────────

def test_icon_grey():
    assert kirklees._icon("Grey wheelie bin") == "mdi:trash-can"

def test_icon_green():
    assert kirklees._icon("Green wheelie bin") == "mdi:recycle"

def test_icon_recycling():
    assert kirklees._icon("Recycling") == "mdi:recycle"

def test_icon_garden():
    assert kirklees._icon("Garden waste") == "mdi:leaf"

def test_icon_brown():
    assert kirklees._icon("Brown bin") == "mdi:leaf"

def test_icon_domestic():
    assert kirklees._icon("Domestic waste") == "mdi:trash-can"

def test_icon_unknown_fallback():
    assert kirklees._icon("Mystery bin") == "mdi:trash-can"

def test_icon_case_insensitive():
    assert kirklees._icon("RECYCLING") == "mdi:recycle"


# ── councils.json schema ─────────────────────────────────────────────────────

import json

COUNCILS_PATH = os.path.join(os.path.dirname(__file__), "..", "councils.json")
VALID_TYPES = {"string", "String", "int", "integer", "Integer", "boolean", "Boolean",
               "bool", "dict", "String | Integer", "string | Integer", "string | integer",
               "string | int", "int | string", "int |string", "integer | string",
               "integrer | string", "string|integer", "int|string", "int or string", "str"}


def test_councils_json_loads():
    with open(COUNCILS_PATH) as f:
        councils = json.load(f)
    assert isinstance(councils, list)
    assert len(councils) > 0


def test_councils_required_fields():
    with open(COUNCILS_PATH) as f:
        councils = json.load(f)
    for c in councils:
        assert "id" in c, f"Missing id: {c}"
        assert "title" in c, f"Missing title: {c}"
        assert "module" in c, f"Missing module: {c}"
        assert "args" in c, f"Missing args: {c}"
        assert isinstance(c["args"], list), f"args not a list: {c['id']}"


def test_councils_no_duplicate_titles():
    # IDs may be shared (one module serves multiple councils) but titles must be unique
    with open(COUNCILS_PATH) as f:
        councils = json.load(f)
    titles = [c["title"] for c in councils]
    assert len(titles) == len(set(titles)), "Duplicate council titles found"


def test_councils_args_have_required_fields():
    with open(COUNCILS_PATH) as f:
        councils = json.load(f)
    for c in councils:
        for arg in c["args"]:
            assert "name" in arg, f"arg missing name in {c['id']}: {arg}"
            assert "type" in arg, f"arg missing type in {c['id']}: {arg}"
            assert "required" in arg, f"arg missing required in {c['id']}: {arg}"
            assert isinstance(arg["required"], bool), \
                f"arg.required not bool in {c['id']}.{arg['name']}: {arg['required']!r}"


def test_councils_broken_has_reason():
    with open(COUNCILS_PATH) as f:
        councils = json.load(f)
    for c in councils:
        if c.get("broken"):
            assert "broken_reason" in c or "hint" in c, \
                f"broken council {c['id']} has no broken_reason or hint"
