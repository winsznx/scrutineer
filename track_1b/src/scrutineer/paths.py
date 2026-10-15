"""Canonical file locations, relative to the project root (the `track_1b/` directory)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def csv(self) -> Path:
        return self.data / "swissvotes_dataset.csv"

    @property
    def titles(self) -> Path:
        return self.data / "titles_chancellery.jsonl"

    @property
    def items(self) -> Path:
        return self.data / "items.jsonl"

    @property
    def items_manifest(self) -> Path:
        return self.data / "items.manifest.json"

    @property
    def responses(self) -> Path:
        return self.data / "responses"

    @property
    def judgements(self) -> Path:
        return self.data / "judgements"

    @property
    def spend_ledger(self) -> Path:
        return self.data / "spend_ledger.jsonl"

    @property
    def human_check(self) -> Path:
        return self.data / "human_check.csv"

    @property
    def human_check_key(self) -> Path:
        return self.data / "human_check_key.csv"

    @property
    def results(self) -> Path:
        return self.data / "results.json"

    @property
    def results_hash(self) -> Path:
        return self.data / "results.sha256"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def figures(self) -> Path:
        return self.docs / "figures"

    @property
    def site(self) -> Path:
        return self.root / "site"


def default_paths() -> Paths:
    return Paths(Path(os.environ.get("SCRUTINEER_ROOT", Path.cwd())).resolve())
