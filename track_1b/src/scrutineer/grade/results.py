"""Assemble `results.json`: the single source for every number in report, README, site and card."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scrutineer.grade.grade import grade_item
from scrutineer.grade.judge import JUDGE_PROMPT_VERSION, read_judgements
from scrutineer.grade.metrics import (
    CORE_LANGS,
    abstention,
    baselines,
    breakdown,
    coverage,
    directional_by_lang,
    era_instrument,
    headline,
    language_bias,
    order_swap,
    r,
    reasoning_claim_status,
    reasoning_vs_recall,
    run_summary,
    within_instrument,
    yes_share_errors,
)
from scrutineer.grade.stats import cohen_kappa
from scrutineer.paths import Paths
from scrutineer.run.runner import read_records

SCHEMA_VERSION = "1.0.0"
CLAIM_RUN = "R1"
RUN_LABELS = {
    "R1": "Apertus 1.5 70B",
    "R2": "Apertus 1.5 8B",
    "R3": "Apertus 1.5 8B thinking",
    "R4": "Apertus 1.5 70B thinking",
}


def load_items(paths: Paths) -> dict[str, dict[str, Any]]:
    items = (json.loads(line) for line in paths.items.read_text(encoding="utf-8").splitlines())
    return {item["item_id"]: item for item in items}


def run_ids(paths: Paths) -> list[str]:
    """Main runs over items.jsonl, in R1, R2, ... order. Smoke runs and runs over other item
    files (robustness checks) are excluded."""
    ids = []
    for meta_path in paths.responses.glob("*.meta.json"):
        run_id = meta_path.name.removesuffix(".meta.json")
        meta = json.loads(meta_path.read_text())
        if run_id.startswith("smoke") or "items_path" in meta or "comparison_of" in meta:
            continue
        ids.append(run_id)
    return sorted(ids, key=lambda i: (len(i), i))


def graded_run(paths: Paths, run_id: str, items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records = read_records(paths.responses / f"{run_id}.jsonl")
    judgements = read_judgements(paths.judgements / f"{run_id}.jsonl")
    selected = [i for i in items.values() if i["item_id"] in records]
    return [grade_item(i, records.get(i["item_id"]), judgements.get(i["item_id"])) for i in selected]


def write_graded(path: Path, graded: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(g, ensure_ascii=False, sort_keys=True) for g in sorted(graded, key=lambda g: g["item_id"])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def human_agreement(paths: Paths) -> dict[str, Any]:
    """Judge versus the blind human labels, overall and per language."""
    if not paths.human_check.exists() or not paths.human_check_key.exists():
        return {"status": "not_exported"}
    with paths.human_check_key.open(encoding="utf-8") as handle:
        key = {row["row_id"]: row for row in csv.DictReader(handle)}
    with paths.human_check.open(encoding="utf-8") as handle:
        labels = {row["row_id"]: row for row in csv.DictReader(handle)}
    current = _current_judge_grades(paths, key)
    pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    pairs_v1_0: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row_id, row in labels.items():
        human = row.get("human_grade", "").strip().lower()
        if human not in {"correct", "incorrect", "not_attempted"}:
            continue
        mapping = key[row_id]
        # The key holds the verdict shown at export time (judge 1.0.0).
        pairs_v1_0[mapping["lang"]].append((mapping["judge_grade"], human))
        pairs_v1_0["all"].append((mapping["judge_grade"], human))
        if row_id in current:
            pairs[mapping["lang"]].append((current[row_id], human))
            pairs["all"].append((current[row_id], human))
    labelled = len(pairs_v1_0["all"])
    if labelled == 0:
        return {"status": "awaiting_labels", "sample_size": len(key)}

    def summarise(group: list[tuple[str, str]]) -> dict[str, Any]:
        judge, human = [p[0] for p in group], [p[1] for p in group]
        return {
            "n": len(group),
            "raw_agreement": r(sum(a == b for a, b in group) / len(group)),
            "cohen_kappa": r(cohen_kappa(judge, human)),
            "confusion": {f"{a}->{b}": c for (a, b), c in sorted(Counter(group).items())},
        }

    return {
        "status": "complete" if labelled == len(key) else "partial",
        "sample_size": len(key),
        "labelled": labelled,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "by_lang": {lang: summarise(group) for lang, group in sorted(pairs.items())},
        "judge_v1_0_by_lang": {lang: summarise(group) for lang, group in sorted(pairs_v1_0.items())},
    }


def _current_judge_grades(paths: Paths, key: dict[str, dict[str, str]]) -> dict[str, str]:
    """Verdicts of the current judge version for the sampled rows, from the live judgement files."""
    by_run: dict[str, dict[str, Any]] = {}
    grades: dict[str, str] = {}
    for row_id, mapping in key.items():
        run = mapping["run_id"]
        if run not in by_run:
            by_run[run] = read_judgements(paths.judgements / f"{run}.jsonl")
        judgement = by_run[run].get(mapping["item_id"])
        if judgement is not None:
            grades[row_id] = judgement["grade"]
    return grades


def second_rater_agreement(paths: Paths) -> dict[str, Any]:
    """Judge versus the blind Claude pre-labels (and versus the human, once labelled)."""
    if not paths.prelabels.exists() or not paths.human_check_key.exists():
        return {"status": "not_available"}
    with paths.human_check_key.open(encoding="utf-8") as handle:
        key = {row["row_id"]: row for row in csv.DictReader(handle)}
    with paths.prelabels.open(encoding="utf-8") as handle:
        claude = {row["row_id"]: row["prelabel"].strip() for row in csv.DictReader(handle)}
    human: dict[str, str] = {}
    if paths.human_check.exists():
        with paths.human_check.open(encoding="utf-8") as handle:
            human = {row["row_id"]: row.get("human_grade", "").strip().lower() for row in csv.DictReader(handle)}

    def summarise(pairs: list[tuple[str, str]]) -> dict[str, Any]:
        return {
            "n": len(pairs),
            "raw_agreement": r(sum(a == b for a, b in pairs) / len(pairs)) if pairs else None,
            "cohen_kappa": r(cohen_kappa([p[0] for p in pairs], [p[1] for p in pairs])) if pairs else None,
        }

    def by_group(pairs: list[tuple[str, str, str, str]], index: int) -> dict[str, Any]:
        groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for pair in pairs:
            groups[pair[index]].append((pair[0], pair[1]))
            groups["all"].append((pair[0], pair[1]))
        return {name: summarise(group) for name, group in sorted(groups.items())}

    current = _current_judge_grades(paths, key)
    rated = [i for i in key if i in claude]
    judge_claude = [(current[i], claude[i], key[i]["family"], key[i]["lang"]) for i in rated if i in current]
    judge_v1_0_claude = [(key[i]["judge_grade"], claude[i], key[i]["family"], key[i]["lang"]) for i in rated]
    valid = {"correct", "incorrect", "not_attempted"}
    claude_human = [(claude[i], human[i], key[i]["family"], key[i]["lang"]) for i in key if human.get(i) in valid]
    return {
        "rater": "Claude (Fable 5.1), blind to judge verdicts, run and language",
        "judge_vs_claude": {"by_family": by_group(judge_claude, 2), "by_lang": by_group(judge_claude, 3)},
        "judge_v1_0_vs_claude": {
            "by_family": by_group(judge_v1_0_claude, 2),
            "by_lang": by_group(judge_v1_0_claude, 3),
        },
        "claude_vs_human": by_group(claude_human, 2) if claude_human else {"status": "awaiting_labels"},
    }


def judge_summary(paths: Paths, graded: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for run_id, records in graded.items():
        judged = [g for g in records if g.get("source") == "judge" and g.get("grade")]
        out[run_id] = {
            "judged_items": len(judged),
            "by_reason": dict(sorted(Counter(g["family"] if g["family"] in {"F6", "F8"} else "unparseable"
                                              for g in judged).items())),
            "unjudged_pending": sum(1 for g in records if g.get("status") == "unjudged"),
        }
    meta_path = paths.docs / "judge_meta.json"
    if meta_path.exists():
        out["_judge"] = json.loads(meta_path.read_text())
    return out


def f6_parser_judge_agreement(
    graded: list[dict[str, Any]], items: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """On F6 the parser label implies a grade too; report how often it equals the judge's."""
    pairs = []
    for g in graded:
        if g["family"] != "F6" or g.get("source") != "judge" or g.get("grade") is None:
            continue
        parsed = g.get("parsed")
        if parsed in {"yes", "no"}:
            implied = "correct" if parsed == items[g["item_id"]]["gold"]["in_constitution"] else "incorrect"
        elif parsed == "abstain":
            implied = "not_attempted"
        else:
            continue
        pairs.append((implied, g["grade"]))
    if not pairs:
        return {"n": 0}
    return {"n": len(pairs), "agreement": r(sum(a == b for a, b in pairs) / len(pairs)),
            "cohen_kappa": r(cohen_kappa([p[0] for p in pairs], [p[1] for p in pairs]))}


def robustness(paths: Paths, graded: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """E2: order-swapped F1 items against the matching R2 answers."""
    swapped_path = paths.responses / "E2.jsonl"
    if not swapped_path.exists() or "R2" not in graded:
        return {"order_swap": None}
    swap_items = {i["item_id"]: i for i in
                  (json.loads(line) for line in paths.order_swap_items.read_text(encoding="utf-8").splitlines())}
    records = read_records(swapped_path)
    swapped = []
    for item_id, record in records.items():
        g = grade_item(swap_items[item_id], record, None)
        swapped.append({**g, "source_item_id": swap_items[item_id]["source_item_id"]})
    original = {g["item_id"]: g for g in graded["R2"]}
    meta = json.loads((paths.responses / "E2.meta.json").read_text())
    return {"order_swap": {"model": meta["model"], "compared_with": "R2", "by_lang": order_swap(swapped, original)}}


def deployer_agreement(paths: Paths, items: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """R1 on Featherless against R1's first route (Public AI) on the items both answered."""
    first = paths.responses / "R1_publicai.jsonl"
    if not first.exists() or not (paths.responses / "R1.jsonl").exists():
        return None
    a, b = read_records(first), read_records(paths.responses / "R1.jsonl")
    shared = sorted(k for k in a if a[k]["status"] == "ok" and b.get(k, {}).get("status") == "ok")
    labels = [(grade_item(items[k], a[k], None).get("parsed"), grade_item(items[k], b[k], None).get("parsed"))
              for k in shared]
    return {
        "first_route": "publicai", "second_route": "hf/featherless-ai", "n": len(shared),
        "parsed_agreement": r(sum(x == y for x, y in labels) / len(labels)) if labels else None,
        "exact_text_agreement": r(sum(a[k]["response"].strip() == b[k]["response"].strip() for k in shared)
                                  / len(shared)) if shared else None,
    }


def thinking_traces(paths: Paths, run: str) -> dict[str, Any]:
    """Length of the reasoning trace per language, and how often max_tokens cut it off."""
    records = [rec for rec in read_records(paths.responses / f"{run}.jsonl").values() if rec["status"] == "ok"]
    out: dict[str, Any] = {}
    for lang in ("de", "fr", "it", "en", "rm"):
        subset = [rec for rec in records if rec["item_id"].split("-")[-1] == lang]
        if not subset:
            continue
        traced = [len(rec.get("reasoning") or "") for rec in subset]
        tokens = [int((rec.get("usage") or {}).get("completion_tokens", 0)) for rec in subset]
        out[lang] = {
            "n": len(subset),
            "share_with_trace": r(sum(t > 0 for t in traced) / len(subset)),
            "mean_completion_tokens": r(sum(tokens) / len(tokens)),
            "truncated_at_max_tokens": sum(rec.get("finish_reason") == "length" for rec in subset),
        }
    return out


def paired_runs(graded: dict[str, list[dict[str, Any]]], left: str, right: str) -> dict[str, Any] | None:
    """Accuracy of two runs on exactly the F1/F3 items both answered, split by gov_lost."""
    if left not in graded or right not in graded:
        return None
    a = {g["item_id"]: g for g in graded[left] if g.get("grade")}
    b = {g["item_id"]: g for g in graded[right] if g.get("grade")}
    shared = [k for k in a if k in b and a[k]["family"] in {"F1", "F3"} and a[k]["strata"]["gov_lost"] is not None]
    out: dict[str, Any] = {"left": left, "right": right}
    for label, value in (("gov_won", 0), ("gov_lost", 1)):
        keys = [k for k in shared if a[k]["strata"]["gov_lost"] == value]
        n = len(keys)
        out[label] = {
            "n": n,
            f"{left}_accuracy": r(sum(a[k]["grade"] == "correct" for k in keys) / n) if n else None,
            f"{right}_accuracy": r(sum(b[k]["grade"] == "correct" for k in keys) / n) if n else None,
            "only_left_correct": sum(a[k]["grade"] == "correct" and b[k]["grade"] != "correct" for k in keys),
            "only_right_correct": sum(b[k]["grade"] == "correct" and a[k]["grade"] != "correct" for k in keys),
        }
    return out


def judge_versions(paths: Paths, items: dict[str, dict[str, Any]], run: str) -> dict[str, Any]:
    """F6 and F8 accuracy under the archived judge 1.0.0 verdicts and the current ones."""
    records = read_records(paths.responses / f"{run}.jsonl")
    versions = {"1.0.0": paths.judgements / "v1.0" / f"{run}.jsonl", "current": paths.judgements / f"{run}.jsonl"}
    out: dict[str, Any] = {}
    for name, path in versions.items():
        judgements = read_judgements(path)
        for family in ("F6", "F8"):
            graded = [grade_item(items[k], rec, judgements.get(k)) for k, rec in records.items()
                      if rec["status"] == "ok" and items[k]["family"] == family]
            scored = [g for g in graded if g.get("grade")]
            out.setdefault(family, {})[name] = {
                "n": len(scored),
                "accuracy": r(sum(g["grade"] == "correct" for g in scored) / len(scored)) if scored else None,
            }
    return out


def _optional_json(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def assemble(paths: Paths) -> dict[str, Any]:
    items = load_items(paths)
    manifest = json.loads(paths.items_manifest.read_text())
    graded: dict[str, list[dict[str, Any]]] = {}
    runs: dict[str, Any] = {}
    for run_id in run_ids(paths):
        meta = json.loads((paths.responses / f"{run_id}.meta.json").read_text())
        records = [json.loads(line) for line in
                   (paths.responses / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines() if line]
        graded[run_id] = graded_run(paths, run_id, items)
        runs[run_id] = {
            "label": RUN_LABELS.get(run_id, meta["model"]),
            "model": meta["model"],
            "provider": meta["provider"],
            "endpoint": meta["endpoint"],
            "thinking": meta["thinking"],
            "started_at": meta.get("started_at"),
            "summary": run_summary(records, len(items)),
            "coverage": coverage(graded[run_id], items),
        }

    per_run: dict[str, Any] = {}
    for run_id, records in graded.items():
        per_run[run_id] = {
            "headline": headline(records, items, CLAIM_RUN, run_id),
            "within_instrument": within_instrument(records),
            "era_instrument": era_instrument(records),
            "language_bias": language_bias(records, items),
            "directional_by_lang": directional_by_lang(records, items),
            "yes_share": yes_share_errors(records),
            "post_cutoff": abstention(records),
            "reasoning_vs_recall": reasoning_vs_recall(records),
            "f6_parser_judge": f6_parser_judge_agreement(records, items),
            "cells": breakdown(records),
        }

    claim = per_run.get(CLAIM_RUN, {})
    claims = {
        "C1": claim.get("headline", {}).get("status", "PENDING"),
        "C3": reasoning_claim_status(claim.get("reasoning_vs_recall", {})) if claim else "PENDING",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "items": {
            "count": len(items),
            "sha256": manifest["items_sha256"],
            "swissvotes_csv_sha256": manifest["swissvotes_csv_sha256"],
            "titles_sha256": manifest["titles_sha256"],
            "templates_sha256": manifest["templates_sha256"],
            "by_family": dict(sorted(Counter(i["family"] for i in items.values()).items())),
            "by_lang": dict(sorted(Counter(i["lang"] for i in items.values()).items())),
            "universe_votes": len({i["anr"] for i in items.values() if i["family"] == "F1"
                                   and i["strata"]["gov_lost"] is not None}),
            "gov_lost_votes": len({i["anr"] for i in items.values() if i["family"] == "F1"
                                   and i["strata"]["gov_lost"] == 1}),
            "core_langs": list(CORE_LANGS),
        },
        "runs": runs,
        "results": per_run,
        "claims": claims,
        "baselines": baselines(items),
        "robustness": robustness(paths, graded),
        "deployer_agreement": deployer_agreement(paths, items),
        "thinking_traces": {run: thinking_traces(paths, run) for run in graded if runs[run]["thinking"]},
        "r4_vs_r1": paired_runs(graded, "R4", "R1"),
        "judge_versions": {run: judge_versions(paths, items, run) for run in graded},
        "judge": judge_summary(paths, graded),
        "human_check": human_agreement(paths),
        "second_rater_agreement": second_rater_agreement(paths),
        "contamination": _optional_json(paths.docs / "contamination.json"),
        "replay": _optional_json(paths.data / "replay" / "agreement.json"),
    }


def serialise(results: dict[str, Any]) -> bytes:
    return (json.dumps(results, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
