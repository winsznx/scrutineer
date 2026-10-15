"""Blind human check of the judge (PRD section 6.3).

A seeded random 20% of all judged items is written to `human_check.csv` in shuffled
order. That file shows only an opaque row id, the question, the gold facts and the
response. Model, run, language and the judge's verdict live in `human_check_key.csv`,
which the labeller does not open.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from typing import Any

from scrutineer.grade.grade import answer_text
from scrutineer.grade.judge import describe_gold, read_judgements
from scrutineer.grade.results import load_items, run_ids
from scrutineer.paths import Paths
from scrutineer.run.runner import read_records

LABEL_COLUMNS = ("row_id", "question", "gold", "response", "human_grade", "labelled_at", "note")
KEY_COLUMNS = ("row_id", "run_id", "item_id", "family", "lang", "judge_grade")


def _population(paths: Paths, runs: list[str] | None = None) -> list[dict[str, Any]]:
    items = load_items(paths)
    population: list[dict[str, Any]] = []
    for run_id in runs or run_ids(paths):
        records = read_records(paths.responses / f"{run_id}.jsonl")
        for item_id, judgement in sorted(read_judgements(paths.judgements / f"{run_id}.jsonl").items()):
            item = items[item_id]
            population.append({
                "run_id": run_id,
                "item": item,
                "response": answer_text(records[item_id]),
                "judge_grade": judgement["grade"],
            })
    return population


def export_sample(paths: Paths, fraction: float, seed: int, runs: list[str] | None = None) -> tuple[int, int]:
    population = _population(paths, runs)
    rng = random.Random(seed)
    sample = rng.sample(population, round(len(population) * fraction))
    rng.shuffle(sample)

    with paths.human_check.open("w", encoding="utf-8", newline="") as labels, \
            paths.human_check_key.open("w", encoding="utf-8", newline="") as key:
        label_writer = csv.DictWriter(labels, fieldnames=LABEL_COLUMNS)
        key_writer = csv.DictWriter(key, fieldnames=KEY_COLUMNS)
        label_writer.writeheader()
        key_writer.writeheader()
        for entry in sample:
            item = entry["item"]
            row_id = hashlib.sha256(
                json.dumps([seed, entry["run_id"], item["item_id"]]).encode()).hexdigest()[:10]
            label_writer.writerow({
                "row_id": row_id,
                "question": item["prompt"],
                "gold": describe_gold(item),
                "response": entry["response"],
                "human_grade": "",
                "labelled_at": "",
                "note": "",
            })
            key_writer.writerow({
                "row_id": row_id,
                "run_id": entry["run_id"],
                "item_id": item["item_id"],
                "family": item["family"],
                "lang": item["lang"],
                "judge_grade": entry["judge_grade"],
            })
    return len(sample), len(population)


REVIEW_COLUMNS = ("row_id", "question", "gold", "response", "prelabel", "prelabel_note", "human_grade", "labelled_at")


def merge_prelabels(paths: Paths) -> int:
    """Add the blind second rater's labels to human_check.csv and write the review sheet.

    The review sheet carries no judge verdict, run or language, same as the label sheet.
    """
    with paths.prelabels.open(encoding="utf-8") as handle:
        prelabels = {row["row_id"]: row for row in csv.DictReader(handle)}
    with paths.human_check.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if {row["row_id"] for row in rows} != set(prelabels):
        raise SystemExit("prelabel row ids do not match human_check.csv")
    for row in rows:
        row["prelabel"] = prelabels[row["row_id"]]["prelabel"].strip()
        row["prelabel_note"] = prelabels[row["row_id"]].get("prelabel_note", "").strip()
    columns = [*LABEL_COLUMNS, "prelabel", "prelabel_note"]
    with paths.human_check.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row.get(column, "") for column in columns} for row in rows)
    with paths.human_check_review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows({column: row.get(column, "") for column in REVIEW_COLUMNS} for row in rows)
    return len(rows)
