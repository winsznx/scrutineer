"""Assemble `results.json`: the single source for every number in report, README, site and card."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scrutineer.grade.grade import grade_item
from scrutineer.grade.judge import read_judgements
from scrutineer.grade.metrics import (
    CORE_LANGS,
    abstention,
    baselines,
    breakdown,
    coverage,
    directional_by_lang,
    headline,
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
    """Runs with a meta file, in R1, R2, ... order. Smoke runs (prefix `smoke`) are excluded."""
    ids = [p.name.removesuffix(".meta.json") for p in paths.responses.glob("*.meta.json")]
    return sorted((i for i in ids if not i.startswith("smoke")), key=lambda i: (len(i), i))


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
    pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row_id, row in labels.items():
        human = row.get("human_grade", "").strip().lower()
        if human not in {"correct", "incorrect", "not_attempted"}:
            continue
        mapping = key[row_id]
        pairs[mapping["lang"]].append((mapping["judge_grade"], human))
        pairs["all"].append((mapping["judge_grade"], human))
    labelled = len(pairs["all"])
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
        "by_lang": {lang: summarise(group) for lang, group in sorted(pairs.items())},
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
        "judge": judge_summary(paths, graded),
        "human_check": human_agreement(paths),
        "contamination": _optional_json(paths.docs / "contamination.json"),
        "replay": _optional_json(paths.data / "replay" / "agreement.json"),
    }


def serialise(results: dict[str, Any]) -> bytes:
    return (json.dumps(results, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
