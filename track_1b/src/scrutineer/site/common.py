"""Lookup and formatting helpers shared by the site modules. Missing values render as "n/a"."""

from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path
from typing import Any

NA = "n/a"
RUN_ORDER = ("R1", "R2", "R3", "R4")
CORE_LANGS = ("de", "fr", "it", "en")
LANGS = ("de", "fr", "it", "en", "rm")
LANG_NAMES = {"de": "German", "fr": "French", "it": "Italian", "en": "English", "rm": "Romansh"}
INSTRUMENTS = {
    "initiative": "Popular initiative",
    "counterproposal": "Counter-proposal",
    "referendum_obligatory": "Mandatory referendum",
    "referendum_optional": "Optional referendum",
}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def dig(obj: Any, *keys: str) -> Any:
    """Nested dict lookup that returns None instead of raising when any level is missing."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


def pct(value: Any, digits: int = 1) -> str:
    v = number(value)
    return NA if v is None else f"{v * 100:.{digits}f}%"


def fixed(value: Any, digits: int = 1) -> str:
    v = number(value)
    return NA if v is None else f"{v:,.{digits}f}"


def count(value: Any) -> str:
    v = number(value)
    return NA if v is None else f"{int(v):,}"


def long_date(iso: str | None) -> str:
    """`2024-03-03` -> `3 March 2024`."""
    try:
        year, month, day = (int(part) for part in str(iso).split("-"))
        return f"{day} {MONTHS[month - 1]} {year}"
    except (ValueError, IndexError):
        return NA


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # Runs append to these files while the site is built; a half-written last line is expected.
            if index == len(lines) - 1:
                break
            raise
    return records


def run_label(results: dict[str, Any], run: str) -> str:
    return str(dig(results, "runs", run, "label") or run)


def f1_cell(results: dict[str, Any], run: str, lang: str, stratum: str, value: str) -> dict[str, Any] | None:
    cells = dig(results, "results", run, "cells")
    for row in cells if isinstance(cells, list) else []:
        if (row.get("family"), row.get("lang"), row.get("stratum"), row.get("value")) == ("F1", lang, stratum, value):
            return dict(row)
    return None
