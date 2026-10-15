from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scrutineer.build.items import generate_items, items_digest, serialise
from scrutineer.build.swissvotes import load_votes, select
from scrutineer.build.templates import load_templates
from scrutineer.build.titles import lindas_id_for, read_titles

DATA = Path(__file__).resolve().parents[1] / "data"


def build_payload() -> bytes:
    universe, post_cutoff = select(load_votes(DATA / "swissvotes_dataset.csv"))
    items, _ = generate_items(universe, post_cutoff, read_titles(DATA / "titles_chancellery.jsonl"), load_templates())
    return serialise(items)


def test_same_inputs_give_identical_items() -> None:
    first, second = build_payload(), build_payload()
    assert first == second
    manifest = json.loads((DATA / "items.manifest.json").read_text())
    assert items_digest(first) == manifest["items_sha256"]


def test_universe_counts() -> None:
    universe, post_cutoff = select(load_votes(DATA / "swissvotes_dataset.csv"))
    assert len(universe) == 334
    assert sum(1 for v in universe if v.gov_lost) == 66
    assert [v.vote_date for v in post_cutoff] == [date(2026, 11, 29)] * 4


def test_lindas_id_mapping() -> None:
    assert lindas_id_for("359") == 3590
    assert lindas_id_for("465.2") == 4652


def test_date_formatting_per_language() -> None:
    templates = load_templates()
    assert templates["de"].format_date(date(1990, 4, 1)) == "1. April 1990"
    assert templates["fr"].format_date(date(1990, 4, 1)) == "1er avril 1990"
    assert templates["it"].format_date(date(2024, 3, 3)) == "3 marzo 2024"
    assert templates["rm"].format_date(date(2026, 11, 29)) == "29 da november 2026"


def test_every_prompt_ends_with_an_instruction() -> None:
    for line in (DATA / "items.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        assert item["prompt"].rstrip().endswith((".", ".»")), item["item_id"]
        assert "{" not in item["prompt"], item["item_id"]
