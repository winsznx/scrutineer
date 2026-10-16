"""Pre-specified item order for budget-limited runs (R4, 70B thinking).

When a run cannot afford every item, the order decides what it measures. The order is fixed
before the first request, written to disk, and registered in the claim ledger:

1. matched pairs: every government-lost F1 and F3 item, each paired with a government-won
   item drawn at random from the same (family, language, era, instrument) cell, or the
   same (family, language, era) cell where that runs short. Pairs come in random order, lost
   item first, so a run stopped at any point has as many lost as won items;
2. every F8 item, in random order;
3. every remaining item, in random order.

The run then goes through this list until its budget guard or its time limit stops it.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

PHASES = ("matched_pairs_f1_f3", "f8", "rest")


def _cell(item: dict[str, Any], *, instrument: bool = True) -> tuple[str, ...]:
    strata = item["strata"]
    base = (item["family"], item["lang"], strata["era"])
    return (*base, strata["instrument"]) if instrument else base


def stratified_order(items: list[dict[str, Any]], seed: int) -> list[tuple[str, str]]:
    """Return (item_id, phase) pairs in the order a budget-limited run must follow."""
    rng = random.Random(seed)
    ordered = sorted(items, key=lambda i: i["item_id"])
    core = [i for i in ordered if i["family"] in {"F1", "F3"} and i["strata"]["gov_lost"] is not None]
    lost = [i for i in core if i["strata"]["gov_lost"] == 1]
    won = [i for i in core if i["strata"]["gov_lost"] == 0]

    won_by_cell: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    won_by_coarse: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in won:
        won_by_cell[_cell(item)].append(item)
        won_by_coarse[_cell(item, instrument=False)].append(item)
    taken: set[str] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in lost:
        pool = [w for w in won_by_cell[_cell(item)] if w["item_id"] not in taken]
        if not pool:
            pool = [w for w in won_by_coarse[_cell(item, instrument=False)] if w["item_id"] not in taken]
        if pool:
            choice = rng.choice(pool)
            taken.add(choice["item_id"])
            pairs.append((item, choice))
    rng.shuffle(pairs)

    used = {i["item_id"] for pair in pairs for i in pair}
    f8 = [i for i in ordered if i["family"] == "F8"]
    rng.shuffle(f8)
    rest = [i for i in ordered if i["item_id"] not in used and i["family"] != "F8"]
    rng.shuffle(rest)
    paired = [(i["item_id"], PHASES[0]) for pair in pairs for i in pair]
    return paired + [(i["item_id"], PHASES[1]) for i in f8] + [(i["item_id"], PHASES[2]) for i in rest]


def write_plan(plan: list[tuple[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for rank, (item_id, phase) in enumerate(plan, 1):
            handle.write(json.dumps({"rank": rank, "item_id": item_id, "phase": phase}) + "\n")


def read_plan(path: Path) -> list[str]:
    return [json.loads(line)["item_id"] for line in path.read_text(encoding="utf-8").splitlines() if line]
