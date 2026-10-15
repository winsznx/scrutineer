"""Turn raw responses plus stored judgements into one graded record per item.

Routing (PRD section 6): F1-F5 and F7 go through the deterministic parser. Anything the
parser marks `unparseable`, and every F6 and F8 item, is decided by the judge. F6 keeps
its parser label alongside the judge grade so parser-judge agreement can be reported.
"""

from __future__ import annotations

from typing import Any

from scrutineer.grade.parse import PARSER_VERSION, parse_label, parse_percentage, strip_reasoning

JUDGED_FAMILIES = frozenset({"F6", "F8"})
GOLD_KEY = {"F1": "outcome", "F3": "fc_position", "F4": "cantons_majority", "F5": "outcome",
            "F6": "in_constitution"}


def needs_judge(item: dict[str, Any], response: str) -> str | None:
    """Return why an item must be judged, or None if the parser decides it."""
    family = str(item["family"])
    if family in JUDGED_FAMILIES:
        return family
    if family == "F2":
        return "unparseable" if parse_percentage(response, item["lang"]).label == "unparseable" else None
    return "unparseable" if parse_label(response, item["lang"], family) == "unparseable" else None


def answer_text(record: dict[str, Any]) -> str:
    """Visible answer only. Thinking traces are kept in the record but never graded."""
    return strip_reasoning(record.get("response") or "")


def grade_item(
    item: dict[str, Any], record: dict[str, Any] | None, judgement: dict[str, Any] | None
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_id": item["item_id"],
        "anr": item["anr"],
        "family": item["family"],
        "lang": item["lang"],
        "strata": item["strata"],
        "parser_version": PARSER_VERSION,
    }
    if record is None:
        return {**base, "status": "missing", "grade": None}
    if record["status"] != "ok":
        return {**base, "status": "failed", "grade": None}

    response = answer_text(record)
    family = item["family"]
    gold = item["gold"]
    graded: dict[str, Any] = {**base, "status": "ok", "parsed": None, "value": None, "source": "parser"}

    if family == "F2":
        parsed = parse_percentage(response, item["lang"])
        graded["parsed"] = parsed.label
        graded["value"] = parsed.value
        if parsed.label == "number" and parsed.value is not None:
            error = abs(parsed.value - gold["yes_share"])
            graded["abs_error"] = round(error, 4)
            graded["grade"] = "correct" if error <= gold["tolerance"] + 1e-9 else "incorrect"
            return graded
        if parsed.label == "abstain":
            graded["grade"] = "not_attempted"
            return graded
    elif family != "F8":
        label = parse_label(response, item["lang"], family)
        graded["parsed"] = label
        if family == "F7":
            if label == "abstain":
                graded["grade"] = "correct"
                return graded
            if label in {"accepted", "rejected"}:
                graded["grade"] = "incorrect"
                return graded
        elif label == "abstain" and family not in JUDGED_FAMILIES:
            graded["grade"] = "not_attempted"
            return graded
        elif label not in {"unparseable", "abstain"} and family not in JUDGED_FAMILIES:
            graded["grade"] = "correct" if label == gold[GOLD_KEY[family]] else "incorrect"
            return graded

    if judgement is None:
        return {**graded, "status": "unjudged", "grade": None, "source": "judge"}
    return {**graded, "grade": judgement["grade"], "source": "judge",
            "judge_reason": judgement.get("reason", "")}


def asserted_outcome(graded: dict[str, Any], item: dict[str, Any]) -> str | None:
    """The outcome an F1 answer commits to, recovered for judge-graded items too."""
    if graded.get("parsed") in {"accepted", "rejected"}:
        return str(graded["parsed"])
    if graded.get("grade") == "correct":
        return str(item["gold"]["outcome"])
    if graded.get("grade") == "incorrect":
        return "rejected" if item["gold"]["outcome"] == "accepted" else "accepted"
    return None
