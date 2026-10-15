"""Stage the Hugging Face dataset: items, per-item metadata with licences, responses, card."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from scrutineer.grade.results import load_items, run_ids
from scrutineer.paths import Paths

LICENCES = {
    "item_license": "CDLA-Permissive-2.0",
    "gold_source": "Swissvotes, Année Politique Suisse, Universität Bern",
    "gold_source_license": "CC-BY-4.0",
    "title_source_license_chancellery": "Swiss Federal Chancellery official text, open government data (attribution)",
    "title_source_license_swissvotes": "CC-BY-4.0",
    "response_license": "CDLA-Permissive-2.0",
}


def metadata_row(item: dict[str, Any]) -> dict[str, Any]:
    from_chancellery = item["title_source"] in {None, "chancellery_lindas"}
    return {
        "item_id": item["item_id"],
        "anr": item["anr"],
        "family": item["family"],
        "lang": item["lang"],
        "item_license": LICENCES["item_license"],
        "gold_source": LICENCES["gold_source"],
        "gold_source_license": LICENCES["gold_source_license"],
        "gold_source_urls": item["gold_source_urls"],
        "source_row_sha256": item["source_row_sha256"],
        "title_source": item["title_source"],
        "title_source_url": item["title_source_url"],
        "title_license": (LICENCES["title_source_license_chancellery"] if from_chancellery
                          else LICENCES["title_source_license_swissvotes"]),
        "template_id": item["template_id"],
        "template_version": item["template_version"],
        "generator_version": item["generator_version"],
        "contains_pii": False,
        "human_subjects": False,
    }


def export_hf(paths: Paths, out_dir: Path) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "responses").mkdir(parents=True)
    shutil.copy(paths.items, out_dir / "items.jsonl")
    items = load_items(paths)
    with (out_dir / "metadata.jsonl").open("w", encoding="utf-8") as handle:
        for item in items.values():
            handle.write(json.dumps(metadata_row(item), ensure_ascii=False, sort_keys=True) + "\n")
    for run_id in run_ids(paths):
        shutil.copy(paths.responses / f"{run_id}.jsonl", out_dir / "responses" / f"{run_id}.jsonl")
        shutil.copy(paths.responses / f"{run_id}.meta.json", out_dir / "responses" / f"{run_id}.meta.json")
    graded = paths.data / "graded"
    if graded.exists():
        shutil.copytree(graded, out_dir / "graded")
    shutil.copy(paths.docs / "DATA_CARD.md", out_dir / "README.md")
    shutil.copy(paths.results, out_dir / "results.json")
    return out_dir
