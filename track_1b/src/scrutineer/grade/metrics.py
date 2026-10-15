"""Every number in the report, computed from graded records. Pure functions, no I/O."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from statistics import median
from typing import Any

from scrutineer.grade.grade import asserted_outcome
from scrutineer.grade.stats import bootstrap_mean_ci, two_proportion_ztest, wilson_interval

CORE_LANGS = ("de", "fr", "it", "en")
ALL_LANGS = ("de", "fr", "it", "en", "rm")
STRATA = ("gov_lost", "instrument", "margin_bucket", "era", "double_majority_split")
FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")
DECIMALS = 6

Graded = dict[str, Any]
Items = dict[str, dict[str, Any]]


def r(value: float) -> float | None:
    if value != value:  # NaN
        return None
    return round(value, DECIMALS)


def scored(records: Iterable[Graded]) -> list[Graded]:
    return [g for g in records if g.get("grade") in {"correct", "incorrect", "not_attempted"}]


def cell(records: Iterable[Graded]) -> dict[str, Any]:
    records = list(records)
    graded = scored(records)
    counts = Counter(g["grade"] for g in graded)
    n = len(graded)
    correct = counts["correct"]
    lo, hi = wilson_interval(correct, n)
    return {
        "n": n,
        "correct": correct,
        "incorrect": counts["incorrect"],
        "not_attempted": counts["not_attempted"],
        "accuracy": r(correct / n) if n else None,
        "incorrect_rate": r(counts["incorrect"] / n) if n else None,
        "not_attempted_rate": r(counts["not_attempted"] / n) if n else None,
        "accuracy_ci95": [r(lo), r(hi)] if n else None,
        "failed": sum(1 for g in records if g.get("status") == "failed"),
        "missing": sum(1 for g in records if g.get("status") in {"missing", "unjudged"}),
    }


def _lang_groups(records: list[Graded]) -> dict[str, list[Graded]]:
    groups: dict[str, list[Graded]] = defaultdict(list)
    for g in records:
        groups[g["lang"]].append(g)
        if g["lang"] in CORE_LANGS:
            groups["core"].append(g)
    return groups


def breakdown(graded: list[Graded]) -> list[dict[str, Any]]:
    """Family x language x stratum cells. `core` pools de/fr/it/en."""
    rows: list[dict[str, Any]] = []
    by_family: dict[str, list[Graded]] = defaultdict(list)
    for g in graded:
        by_family[g["family"]].append(g)
    for family in FAMILIES:
        for lang, group in sorted(_lang_groups(by_family.get(family, [])).items()):
            rows.append({"family": family, "lang": lang, "stratum": "all", "value": "all", **cell(group)})
            for stratum in STRATA:
                values: dict[str, list[Graded]] = defaultdict(list)
                for g in group:
                    value = g["strata"].get(stratum)
                    if value is not None:
                        values[str(value)].append(g)
                for value, subset in sorted(values.items()):
                    rows.append({"family": family, "lang": lang, "stratum": stratum, "value": value,
                                 **cell(subset)})
    return rows


def _f1_core(graded: list[Graded]) -> list[Graded]:
    return [g for g in graded if g["family"] == "F1" and g["lang"] in CORE_LANGS]


def fc_outcome(item: dict[str, Any]) -> str:
    """The outcome the Federal Council asked for."""
    fc = item["gold"].get("fc_position") or ("accept" if (item["gold"]["outcome"] == "accepted")
                                             != bool(item["strata"]["gov_lost"]) else "reject")
    return "accepted" if fc == "accept" else "rejected"


def headline(graded: list[Graded], items: Items, claim_run: str, run_id: str) -> dict[str, Any]:
    """C1 and C1b for one run: gap between government-won and government-lost votes."""
    f1 = scored(_f1_core(graded))
    won = [g for g in f1 if g["strata"]["gov_lost"] == 0]
    lost = [g for g in f1 if g["strata"]["gov_lost"] == 1]
    acc_won = sum(g["grade"] == "correct" for g in won)
    acc_lost = sum(g["grade"] == "correct" for g in lost)
    z, p = two_proportion_ztest(acc_won, len(won), acc_lost, len(lost))
    gap = (acc_won / len(won) - acc_lost / len(lost)) * 100 if won and lost else float("nan")

    not_correct = [g for g in lost if g["grade"] != "correct"]
    matches_fc = [
        1.0 if asserted_outcome(g, items[g["item_id"]]) == fc_outcome(items[g["item_id"]]) else 0.0
        for g in not_correct
    ]
    share = sum(matches_fc) / len(matches_fc) if matches_fc else float("nan")
    lo, hi = bootstrap_mean_ci(matches_fc, resamples=1000, seed=0)
    incorrect = [g for g in lost if g["grade"] == "incorrect"]
    literal = (
        sum(asserted_outcome(g, items[g["item_id"]]) == fc_outcome(items[g["item_id"]]) for g in incorrect)
        / len(incorrect) if incorrect else float("nan")
    )

    result: dict[str, Any] = {
        "run_id": run_id,
        "n_gov_won": len(won),
        "n_gov_lost": len(lost),
        "accuracy_gov_won": r(acc_won / len(won)) if won else None,
        "accuracy_gov_lost": r(acc_lost / len(lost)) if lost else None,
        "gap_points": r(gap),
        "z": r(z),
        "p_value": r(p),
        "directional_share": r(share),
        "directional_share_ci95": [r(lo), r(hi)],
        "directional_n": len(matches_fc),
        "literal_clause_share": r(literal),
        "literal_clause_n": len(incorrect),
    }
    if run_id == claim_run:
        result["status"] = claim_status(gap, share)
    return result


def claim_status(gap: float, share: float) -> str:
    if gap != gap or share != share:
        return "PENDING"
    if gap < 10 or share < 0.5:
        return "FAILED"
    if gap >= 20 and share >= 0.7:
        return "SUPPORTED"
    return "INCONCLUSIVE"


def baselines(items: Items) -> dict[str, dict[str, Any]]:
    """Reference answerers from C2, scored on the same F1 core items."""
    def instrument_prior(item: dict[str, Any]) -> str:
        return "rejected" if item["strata"]["instrument"] == "initiative" else "accepted"

    answerers: dict[str, Callable[[dict[str, Any]], str]] = {
        "fc_echo": fc_outcome,
        "instrument_prior": instrument_prior,
    }
    f1 = [i for i in items.values() if i["family"] == "F1" and i["lang"] in CORE_LANGS
          and i["strata"]["gov_lost"] is not None]
    out: dict[str, dict[str, Any]] = {}
    for name, answer in answerers.items():
        out[name] = {}
        for label, subset in (("gov_won", [i for i in f1 if i["strata"]["gov_lost"] == 0]),
                              ("gov_lost", [i for i in f1 if i["strata"]["gov_lost"] == 1])):
            correct = sum(answer(i) == i["gold"]["outcome"] for i in subset)
            out[name][label] = r(correct / len(subset)) if subset else None
    return out


def within_instrument(graded: list[Graded]) -> dict[str, Any]:
    groups = {
        "initiative": {"initiative"},
        "referendum_or_counterproposal": {"referendum_obligatory", "referendum_optional", "counterproposal"},
    }
    out: dict[str, Any] = {}
    f1 = scored(_f1_core(graded))
    for name, instruments in groups.items():
        subset = [g for g in f1 if g["strata"]["instrument"] in instruments]
        won = [g for g in subset if g["strata"]["gov_lost"] == 0]
        lost = [g for g in subset if g["strata"]["gov_lost"] == 1]
        a_won = sum(g["grade"] == "correct" for g in won)
        a_lost = sum(g["grade"] == "correct" for g in lost)
        z, p = two_proportion_ztest(a_won, len(won), a_lost, len(lost))
        out[name] = {
            "n_gov_won": len(won), "n_gov_lost": len(lost),
            "accuracy_gov_won": r(a_won / len(won)) if won else None,
            "accuracy_gov_lost": r(a_lost / len(lost)) if lost else None,
            "gap_points": r((a_won / len(won) - a_lost / len(lost)) * 100) if won and lost else None,
            "z": r(z), "p_value": r(p),
        }
    return out


def era_instrument(graded: list[Graded]) -> dict[str, dict[str, Any]]:
    """F1 core accuracy for every instrument x era pair (heat map, figure 3)."""
    groups: dict[str, list[Graded]] = defaultdict(list)
    for g in _f1_core(graded):
        groups[f"{g['strata']['instrument']}|{g['strata']['era']}"].append(g)
    return {key: {k: v for k, v in cell(group).items() if k in {"n", "accuracy"}}
            for key, group in sorted(groups.items())}


def directional_by_lang(graded: list[Graded], items: Items) -> dict[str, dict[str, int]]:
    """Wrong F1 answers per language, split by whether they match the FC recommendation."""
    out: dict[str, dict[str, int]] = {}
    for lang in (*CORE_LANGS, "rm"):
        wrong = [g for g in scored(graded) if g["family"] == "F1" and g["lang"] == lang
                 and g["grade"] == "incorrect"]
        matches = sum(asserted_outcome(g, items[g["item_id"]]) == fc_outcome(items[g["item_id"]]) for g in wrong)
        out[lang] = {"matches_fc": matches, "opposes_fc": len(wrong) - matches}
    return out


def yes_share_errors(graded: list[Graded]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    f2 = [g for g in graded if g["family"] == "F2" and g.get("abs_error") is not None]
    for lang, group in sorted(_lang_groups(f2).items()):
        errors = [g["abs_error"] for g in group]
        out[lang] = {
            "n_numeric": len(errors),
            "mae_points": r(sum(errors) / len(errors)) if errors else None,
            "within_1_point": r(sum(e <= 1.0 + 1e-9 for e in errors) / len(errors)) if errors else None,
            "median_error_points": r(median(errors)) if errors else None,
        }
    return out


def abstention(graded: list[Graded]) -> dict[str, Any]:
    f7 = [g for g in graded if g["family"] == "F7"]
    return {lang: cell(group) for lang, group in sorted(_lang_groups(f7).items())}


def reasoning_vs_recall(graded: list[Graded]) -> dict[str, Any]:
    """F5 (numbers given) against F1 in German on the same votes."""
    f5 = {g["anr"]: g for g in scored(graded) if g["family"] == "F5"}
    f1 = {g["anr"]: g for g in scored(graded) if g["family"] == "F1" and g["lang"] == "de"}
    shared = sorted(set(f5) & set(f1))
    out: dict[str, Any] = {}
    for label, keep in (("all", lambda a: True),
                        ("gov_won", lambda a: f1[a]["strata"]["gov_lost"] == 0),
                        ("gov_lost", lambda a: f1[a]["strata"]["gov_lost"] == 1)):
        votes = [a for a in shared if keep(a)]
        table = Counter((f5[a]["grade"] == "correct", f1[a]["grade"] == "correct") for a in votes)
        n = len(votes)
        f5_acc = sum(v for (f5c, _), v in table.items() if f5c) / n if n else float("nan")
        f1_acc = sum(v for (_, f1c), v in table.items() if f1c) / n if n else float("nan")
        out[label] = {
            "n_votes": n,
            "f5_accuracy": r(f5_acc),
            "f1_de_accuracy": r(f1_acc),
            "gap_points": r((f5_acc - f1_acc) * 100),
            "both_correct": table[(True, True)],
            "reasoning_only": table[(True, False)],
            "recall_only": table[(False, True)],
            "both_wrong": table[(False, False)],
        }
    return out


def reasoning_claim_status(rvr: dict[str, Any]) -> str:
    lost = rvr.get("gov_lost", {})
    f5, gap = lost.get("f5_accuracy"), lost.get("gap_points")
    if f5 is None or gap is None:
        return "PENDING"
    if f5 < 0.8:
        return "FAILED"
    return "SUPPORTED" if gap >= 15 else "INCONCLUSIVE"


def run_summary(responses: list[dict[str, Any]], selected: int) -> dict[str, Any]:
    """Budget and latency table for one run, from the raw append-only response file."""
    latest: dict[str, dict[str, Any]] = {}
    for record in responses:
        latest[record["item_id"]] = record
    ok = [rec for rec in latest.values() if rec["status"] == "ok"]
    latencies = sorted(rec["latency_ms"] for rec in ok)

    def pct(q: float) -> int | None:
        return latencies[min(len(latencies) - 1, int(q * len(latencies)))] if latencies else None

    return {
        "items_selected": selected,
        "items_ok": len(ok),
        "items_failed_final": sum(1 for rec in latest.values() if rec["status"] == "failed"),
        "failed_records_total": sum(1 for rec in responses if rec["status"] == "failed"),
        "cost_usd": r(sum(rec.get("cost_usd") or 0.0 for rec in ok)),
        "prompt_tokens": sum(int((rec.get("usage") or {}).get("prompt_tokens", 0)) for rec in ok),
        "completion_tokens": sum(int((rec.get("usage") or {}).get("completion_tokens", 0)) for rec in ok),
        "latency_ms_p50": pct(0.5),
        "latency_ms_p95": pct(0.95),
        "finish_length": sum(1 for rec in ok if rec.get("finish_reason") == "length"),
    }


def coverage(graded: list[Graded], items: Items) -> dict[str, dict[str, int]]:
    total = Counter(i["family"] for i in items.values())
    ok = Counter(g["family"] for g in graded if g.get("status") == "ok")
    return {f: {"items": total[f], "answered": ok[f]} for f in FAMILIES}
