"""Option-order robustness items (claim ledger E2).

The F1 questions for de, fr and en with the two answer options swapped in both the
question and the format instruction. Everything else, including the item's gold and
strata, is identical, so answers can be compared item by item with the main run.
"""

from __future__ import annotations

from typing import Any

ORDER_SWAP: dict[str, tuple[str, str]] = {
    "de": ("angenommen oder abgelehnt", "abgelehnt oder angenommen"),
    "fr": ("accepté ou rejeté", "rejeté ou accepté"),
    "en": ("accepted or rejected", "rejected or accepted"),
}
SWAP_SUFFIX = "-swap"


def order_swap_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    swapped: list[dict[str, Any]] = []
    for item in items:
        if item["family"] != "F1" or item["lang"] not in ORDER_SWAP or item["strata"]["gov_lost"] is None:
            continue
        original, replacement = ORDER_SWAP[item["lang"]]
        if item["prompt"].count(original) != 2:
            raise ValueError(f"{item['item_id']}: expected the option pair twice in the prompt")
        swapped.append({
            **item,
            "item_id": item["item_id"] + SWAP_SUFFIX,
            "prompt": item["prompt"].replace(original, replacement),
            "template_id": item["template_id"] + SWAP_SUFFIX,
            "source_item_id": item["item_id"],
        })
    return swapped
