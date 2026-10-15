"""Build the static site: `site/index.html`, `site/explorer.html` and the explorer data.

No build step and no template engine. Pages are Python string templates over results.json;
the explorer is one vanilla script over `data/votes.json`. The output is plain files that any
static host can serve (GitHub Pages included, hence `.nojekyll`).
"""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from scrutineer.grade.results import run_ids
from scrutineer.paths import Paths
from scrutineer.site.common import read_jsonl, run_label
from scrutineer.site.pages import SiteData, explorer, landing
from scrutineer.site.votes import build_votes, load_run, write_votes

ASSETS = ("style.css", "explorer.js")


def _results(paths: Paths) -> tuple[dict[str, Any], str]:
    if not paths.results.exists():
        return {}, "n/a"
    payload = paths.results.read_bytes()
    return json.loads(payload), hashlib.sha256(payload).hexdigest()


def _copy_assets(site: Path) -> None:
    source = files("scrutineer.site") / "assets"
    for name in ASSETS:
        (site / name).write_bytes((source / name).read_bytes())


def build_site(paths: Paths) -> Path:
    results, results_sha256 = _results(paths)
    items = read_jsonl(paths.items)
    runs = run_ids(paths) if paths.responses.exists() else []
    votes = build_votes(items, {run: load_run(paths, run) for run in runs})
    en_fallback = len({item["anr"] for item in items if item["family"] == "F1" and item["lang"] == "en"
                       and item.get("title_source") != "chancellery_lindas"})
    data = SiteData(results, runs, votes, results_sha256, en_fallback)

    site = paths.site
    site.mkdir(parents=True, exist_ok=True)
    write_votes(site / "data", [{"id": run, "label": run_label(results, run)} for run in runs], votes)
    (site / "index.html").write_text(landing(data), encoding="utf-8")
    (site / "explorer.html").write_text(explorer(data), encoding="utf-8")
    _copy_assets(site)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    return site
