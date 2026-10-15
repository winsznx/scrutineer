"""Load the hand-written prompt templates, one YAML file per language."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from importlib import resources
from typing import Any

import yaml

LANGS = ("de", "fr", "it", "en", "rm")


@dataclass(frozen=True)
class LanguageTemplates:
    lang: str
    version: str
    date_format: str
    day_format: str
    first_day: str
    months: tuple[str, ...]
    decimal_separator: str
    instruments: dict[str, str]
    header: str
    families: dict[str, str]

    def format_date(self, value: date) -> str:
        day = self.first_day if value.day == 1 else self.day_format.format(d=value.day)
        return self.date_format.format(day=day, month=self.months[value.month - 1], year=value.year)

    def format_number(self, value: float, decimals: int) -> str:
        return f"{value:.{decimals}f}".replace(".", self.decimal_separator)

    def format_cantons(self, value: float) -> str:
        return str(int(value)) if value.is_integer() else self.format_number(value, 1)

    def template_id(self, family: str) -> str:
        return f"{self.lang}-{family}"

    def render(self, family: str, **fields: str) -> str:
        header = self.header.format(**fields) if "date" in fields else ""
        return self.families[family].format(header=header, **fields)


def _from_mapping(raw: dict[str, Any]) -> LanguageTemplates:
    return LanguageTemplates(
        lang=raw["lang"],
        version=str(raw["version"]),
        date_format=raw["date_format"],
        day_format=raw["day_format"],
        first_day=str(raw["first_day"]),
        months=tuple(raw["months"]),
        decimal_separator=raw["decimal_separator"],
        instruments=dict(raw["instruments"]),
        header=raw["header"],
        families=dict(raw["families"]),
    )


def load_templates() -> dict[str, LanguageTemplates]:
    package = resources.files("scrutineer.templates")
    loaded: dict[str, LanguageTemplates] = {}
    for lang in LANGS:
        raw = yaml.safe_load(package.joinpath(f"{lang}.yaml").read_text(encoding="utf-8"))
        templates = _from_mapping(raw)
        if templates.lang != lang:
            raise ValueError(f"{lang}.yaml declares lang={templates.lang}")
        loaded[lang] = templates
    return loaded


def templates_digest() -> str:
    """Hash of every template file, so items record exactly which wording produced them."""
    package = resources.files("scrutineer.templates")
    digest = hashlib.sha256()
    for lang in LANGS:
        digest.update(package.joinpath(f"{lang}.yaml").read_bytes())
    return digest.hexdigest()
