from __future__ import annotations

import math
from typing import Any

import pytest

from scrutineer.grade.grade import grade_item
from scrutineer.grade.metrics import cell, claim_status, headline, reasoning_vs_recall, within_instrument
from scrutineer.grade.stats import bootstrap_mean_ci, cohen_kappa, two_proportion_ztest, wilson_interval


def f1_item(anr: str, lang: str, outcome: str, gov_lost: int, instrument: str = "initiative") -> dict[str, Any]:
    return {
        "item_id": f"{anr}-F1-{lang}", "anr": anr, "family": "F1", "lang": lang,
        "gold": {"outcome": outcome},
        "strata": {"gov_lost": gov_lost, "instrument": instrument, "era": "2020s", "margin_bucket": "over_15",
                   "lang": lang, "double_majority_split": 0},
    }


def graded(item: dict[str, Any], grade: str, parsed: str | None = None) -> dict[str, Any]:
    return {"item_id": item["item_id"], "anr": item["anr"], "family": item["family"], "lang": item["lang"],
            "strata": item["strata"], "status": "ok", "grade": grade, "parsed": parsed, "source": "parser"}


def test_two_proportion_ztest_matches_hand_computation() -> None:
    # p1 = 80/100, p2 = 50/100, pooled 0.65, se = sqrt(0.65*0.35*0.02) = 0.067454
    z, p = two_proportion_ztest(80, 100, 50, 100)
    assert z == pytest.approx(0.30 / math.sqrt(0.65 * 0.35 * 0.02))
    assert p == pytest.approx(math.erfc(z / math.sqrt(2)))
    assert p < 0.001


def test_wilson_interval_known_value() -> None:
    lo, hi = wilson_interval(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-4)
    assert hi == pytest.approx(0.9433, abs=1e-4)


def test_bootstrap_constant_series_has_zero_width() -> None:
    assert bootstrap_mean_ci([1.0] * 20) == (1.0, 1.0)


def test_cohen_kappa_hand_case() -> None:
    a = ["correct", "correct", "incorrect", "incorrect"]
    b = ["correct", "incorrect", "incorrect", "incorrect"]
    # observed 0.75, expected 0.5*0.25 + 0.5*0.75 = 0.5, kappa = 0.5
    assert cohen_kappa(a, b) == pytest.approx(0.5)


def test_cell_rates() -> None:
    item = f1_item("1", "de", "accepted", 0)
    rows = [graded(item, "correct"), graded(item, "incorrect"), graded(item, "not_attempted"),
            {**graded(item, "correct"), "status": "failed", "grade": None}]
    result = cell(rows)
    assert (result["n"], result["correct"], result["failed"]) == (3, 1, 1)
    assert result["accuracy"] == pytest.approx(1 / 3, abs=1e-6)


def test_headline_gap_and_directional_share() -> None:
    items: dict[str, dict[str, Any]] = {}
    rows = []
    # Government won: 4 votes accepted with FC=accept, 3 answered correctly.
    for i, grade in enumerate(["correct", "correct", "correct", "incorrect"]):
        item = f1_item(f"w{i}", "de", "accepted", 0, "referendum_optional")
        items[item["item_id"]] = item
        rows.append(graded(item, grade, "accepted" if grade == "correct" else "rejected"))
    # Government lost: initiatives accepted against FC=reject. 1 correct, 2 say rejected, 1 abstains.
    for i, (grade, parsed) in enumerate([("correct", "accepted"), ("incorrect", "rejected"),
                                         ("incorrect", "rejected"), ("not_attempted", "abstain")]):
        item = f1_item(f"l{i}", "de", "accepted", 1)
        items[item["item_id"]] = item
        rows.append(graded(item, grade, parsed))
    h = headline(rows, items, claim_run="R1", run_id="R1")
    assert h["accuracy_gov_won"] == pytest.approx(0.75)
    assert h["accuracy_gov_lost"] == pytest.approx(0.25)
    assert h["gap_points"] == pytest.approx(50.0)
    # non-correct on lost votes: 2 rejected (FC line) + 1 abstention -> 2/3
    assert h["directional_share"] == pytest.approx(2 / 3, abs=1e-6)
    assert h["literal_clause_share"] == pytest.approx(1.0)
    assert h["status"] == "INCONCLUSIVE"


def test_claim_status_thresholds() -> None:
    assert claim_status(25, 0.8) == "SUPPORTED"
    assert claim_status(9.9, 0.9) == "FAILED"
    assert claim_status(25, 0.49) == "FAILED"
    assert claim_status(15, 0.8) == "INCONCLUSIVE"


def test_within_instrument_splits_groups() -> None:
    rows = [graded(f1_item("a", "de", "rejected", 0), "correct"),
            graded(f1_item("b", "de", "accepted", 1), "incorrect"),
            graded(f1_item("c", "de", "accepted", 0, "referendum_optional"), "correct")]
    result = within_instrument(rows)
    assert result["initiative"]["gap_points"] == pytest.approx(100.0)
    assert result["referendum_or_counterproposal"]["n_gov_lost"] == 0


def test_reasoning_vs_recall_pairs_votes() -> None:
    f1 = f1_item("7", "de", "accepted", 1)
    f5 = {**f1, "item_id": "7-F5-de", "family": "F5"}
    result = reasoning_vs_recall([graded(f1, "incorrect"), graded(f5, "correct")])
    assert result["gov_lost"]["reasoning_only"] == 1
    assert result["gov_lost"]["gap_points"] == pytest.approx(100.0)


def test_grade_item_routes() -> None:
    item = f1_item("9", "fr", "rejected", 0)
    ok = {"status": "ok", "response": "Rejeté."}
    assert grade_item(item, ok, None)["grade"] == "correct"
    unreadable = {"status": "ok", "response": "Hmm."}
    assert grade_item(item, unreadable, None)["status"] == "unjudged"
    assert grade_item(item, unreadable, {"grade": "not_attempted"})["grade"] == "not_attempted"
    assert grade_item(item, {"status": "failed"}, None)["status"] == "failed"
    f7 = {**item, "item_id": "9-F7-fr", "family": "F7", "gold": {"outcome": "not_decided"}}
    assert grade_item(f7, {"status": "ok", "response": "Je ne sais pas."}, None)["grade"] == "correct"
    assert grade_item(f7, ok, None)["grade"] == "incorrect"


def test_f2_tolerance() -> None:
    item = {**f1_item("3", "de", "accepted", 0), "item_id": "3-F2-de", "family": "F2",
            "gold": {"yes_share": 58.25, "tolerance": 1.0}}
    assert grade_item(item, {"status": "ok", "response": "58,2 %"}, None)["grade"] == "correct"
    assert grade_item(item, {"status": "ok", "response": "56 %"}, None)["grade"] == "incorrect"
