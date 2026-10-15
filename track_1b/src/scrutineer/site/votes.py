"""Explorer data: one compact record per vote, carrying every run's answer to every item of that vote.

Keys are short to keep the download small. The schema is documented once, at the top of
`assets/explorer.js`, and the two must change together.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scrutineer.paths import Paths
from scrutineer.site.common import LANGS, read_jsonl

SPLIT_BYTES = 8_000_000
FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")


@dataclass(frozen=True)
class RunRecords:
    graded: dict[str, dict[str, Any]]
    responses: dict[str, dict[str, Any]]


def load_run(paths: Paths, run: str) -> RunRecords:
    """Graded records and the last raw response per item (the response file is append-only)."""
    graded = {g["item_id"]: g for g in read_jsonl(paths.data / "graded" / f"{run}.jsonl")}
    responses = {rec["item_id"]: rec for rec in read_jsonl(paths.responses / f"{run}.jsonl")}
    return RunRecords(graded, responses)


def anr_key(anr: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", anr))


def _gold_value(group: list[dict[str, Any]], family: str, key: str) -> Any:
    for item in group:
        if item["family"] == family and key in item["gold"]:
            return item["gold"][key]
    return None


def _answer(item_id: str, run: RunRecords) -> list[Any] | None:
    """[verbatim response, parser label, grade, grade source, judge reason, status], or None if never asked."""
    graded, record = run.graded.get(item_id), run.responses.get(item_id)
    if graded is None and record is None:
        return None
    response = record.get("response") if record and record.get("status") == "ok" else None
    if graded is None:
        return [response, None, None, None, None, "ungraded"]
    return [response, graded.get("parsed"), graded.get("grade"), graded.get("source"), graded.get("judge_reason"),
            graded.get("status")]


def _verdict(answer: list[Any] | None) -> str | None:
    if answer is None:
        return None
    grade, status = answer[2], answer[5]
    return str(grade) if grade else str(status)


def _vote(anr: str, group: list[dict[str, Any]], runs: dict[str, RunRecords]) -> dict[str, Any]:
    post_cutoff = all(item["family"] == "F7" for item in group if item["family"] in {"F1", "F7"})
    table_family = "F7" if post_cutoff else "F1"
    by_family: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for item in group:
        by_family[item["family"]][item["lang"]] = item
    base_group = by_family[table_family]
    base = base_group.get("de") or next(iter(base_group.values()), group[0])
    strata = base["strata"]
    details: dict[str, dict[str, dict[str, list[Any]]]] = {}
    for run, records in runs.items():
        per_family: dict[str, dict[str, list[Any]]] = {}
        for family in FAMILIES:
            answers = {lang: _answer(item["item_id"], records) for lang, item in by_family.get(family, {}).items()}
            kept = {lang: answer for lang, answer in answers.items() if answer is not None}
            if kept:
                per_family[family] = kept
        details[run] = per_family
    return {
        "a": anr,
        "d": base.get("vote_date"),
        "t": {lang: base_group[lang]["title"] for lang in LANGS if lang in base_group and base_group[lang]["title"]},
        "g": strata.get("gov_lost"),
        "i": strata.get("instrument"),
        "e": strata.get("era"),
        "m": strata.get("margin_bucket"),
        "s": strata.get("double_majority_split"),
        "pc": 1 if post_cutoff else 0,
        "o": base["gold"].get("outcome"),
        "f": _gold_value(group, "F3", "fc_position"),
        "y": _gold_value(group, "F2", "yes_share"),
        "cy": _gold_value(group, "F4", "cantons_yes"),
        "cn": _gold_value(group, "F4", "cantons_no"),
        "ic": _gold_value(group, "F6", "in_constitution"),
        "u": base.get("gold_source_urls") or [base.get("gold_source_url")],
        "k": {family: [lang for lang in LANGS if lang in by_family[family]] for family in FAMILIES
              if family in by_family},
        "v": {run: {lang: _verdict(answer) for lang, answer in by_lang.items()}
              for run, family_answers in details.items() if (by_lang := family_answers.get(table_family))},
        "r": details,
    }


def build_votes(items: list[dict[str, Any]], runs: dict[str, RunRecords]) -> list[dict[str, Any]]:
    """Every vote that has an F1 item (the decided universe) or an F7 item (not yet held), newest first."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[item["anr"]].append(item)
    votes = [_vote(anr, group, runs) for anr, group in groups.items()
             if any(item["family"] in {"F1", "F7"} for item in group)]
    return sorted(votes, key=lambda v: (v["d"] or "", anr_key(v["a"])), reverse=True)


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def write_votes(data_dir: Path, runs: list[dict[str, str]], votes: list[dict[str, Any]]) -> list[Path]:
    """Write `votes.json`. Above SPLIT_BYTES the per-run answers move to `votes/<anr>.json`, fetched on expand."""
    data_dir.mkdir(parents=True, exist_ok=True)
    split_dir = data_dir / "votes"
    if split_dir.exists():
        shutil.rmtree(split_dir)
    index = data_dir / "votes.json"
    blob = _dump({"runs": runs, "split": False, "votes": votes})
    if len(blob.encode("utf-8")) <= SPLIT_BYTES:
        index.write_text(blob, encoding="utf-8")
        return [index]
    split_dir.mkdir()
    written = [index]
    for vote in votes:
        path = split_dir / f"{vote['a']}.json"
        path.write_text(_dump({"r": vote["r"]}), encoding="utf-8")
        written.append(path)
    slim = [{key: value for key, value in vote.items() if key != "r"} for vote in votes]
    index.write_text(_dump({"runs": runs, "split": True, "votes": slim}), encoding="utf-8")
    return written
