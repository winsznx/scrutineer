"""Generate the evaluation items from the pinned CSV, stored titles and templates.

The output is a pure function of its inputs: same CSV, titles file and templates give
byte-identical `items.jsonl`. Item order is fixed (vote number, family, language).
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scrutineer.build.swissvotes import Vote
from scrutineer.build.templates import LanguageTemplates, templates_digest
from scrutineer.build.titles import TitleRecord, lindas_id_for
from scrutineer.grade.lexicon import CANONICAL

GENERATOR_VERSION = "1.0.0"
CORE_LANGS = ("de", "fr", "it", "en")
F6_NEGATIVE_SEED = 20260929
FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")

TitleIndex = dict[tuple[int, str], TitleRecord]


@dataclass(frozen=True)
class ResolvedTitle:
    text: str
    source: str
    source_url: str


@dataclass
class BuildLog:
    omitted_titles: list[dict[str, str]]
    fallback_titles: list[dict[str, str]]


def resolve_title(vote: Vote, lang: str, titles: TitleIndex) -> ResolvedTitle | None:
    """Official Chancellery title in `lang`; for English fall back to the Swissvotes short title."""
    record = titles.get((lindas_id_for(vote.anr), lang))
    if record is not None:
        return ResolvedTitle(record.title, "chancellery_lindas", record.title_iri)
    if lang == "en" and vote.title_short_en:
        return ResolvedTitle(vote.title_short_en, "swissvotes_titel_kurz_e", vote.swissvotes_url)
    return None


def _strata(vote: Vote, lang: str) -> dict[str, Any]:
    gov_lost = vote.gov_lost
    return {
        "gov_lost": None if gov_lost is None else int(gov_lost),
        "instrument": vote.instrument,
        "margin_bucket": vote.margin_bucket,
        "era": vote.era,
        "lang": lang,
        "double_majority_split": int(vote.double_majority_split),
    }


def _gold_urls(vote: Vote) -> list[str]:
    return [url for url in (vote.swissvotes_url, vote.chancellery_url_de) if url]


def _outcome(vote: Vote) -> str:
    return "accepted" if vote.accepted else "rejected"


def _cantons_majority(vote: Vote) -> str | None:
    if vote.cantons_yes is None or vote.cantons_no is None:
        return None
    return "yes" if vote.cantons_yes > vote.cantons_no else "no"


def _item(
    vote: Vote,
    family: str,
    lang: str,
    templates: LanguageTemplates,
    prompt: str,
    gold: dict[str, Any],
    gold_key: str,
    title: ResolvedTitle | None,
) -> dict[str, Any]:
    return {
        "item_id": f"{vote.anr}-{family}-{lang}",
        "anr": vote.anr,
        "vote_date": vote.vote_date.isoformat(),
        "family": family,
        "lang": lang,
        "prompt": prompt,
        "gold": gold,
        "gold_answers": list(CANONICAL[lang].get(gold_key, ())),
        "gold_source_url": vote.swissvotes_url,
        "gold_source_urls": _gold_urls(vote),
        "title": title.text if title else None,
        "title_source": title.source if title else None,
        "title_source_url": title.source_url if title else None,
        "strata": _strata(vote, lang),
        "template_id": templates.template_id(family),
        "template_version": templates.version,
        "generator_version": GENERATOR_VERSION,
        "source_row_sha256": vote.row_sha256,
    }


def _recall_fields(vote: Vote, templates: LanguageTemplates, title: ResolvedTitle) -> dict[str, str]:
    return {"date": templates.format_date(vote.vote_date), "title": title.text}


def f6_negatives(universe: list[Vote]) -> list[Vote]:
    """Rejected initiatives/counter-proposals matched by era to the accepted F6 positives.

    F6 asks whether a proposal entered the constitution. Positives alone would reward a
    model that always says yes, so each era gets as many rejected proposals as accepted
    ones, drawn with a fixed seed.
    """
    eligible = [v for v in universe if v.instrument in {"initiative", "counterproposal"}]
    positives = [v for v in eligible if v.accepted]
    rng = random.Random(F6_NEGATIVE_SEED)
    chosen: list[Vote] = []
    for era in sorted({v.era for v in positives}):
        wanted = sum(1 for v in positives if v.era == era)
        pool = [v for v in eligible if not v.accepted and v.era == era]
        chosen.extend(rng.sample(pool, min(wanted, len(pool))))
    return chosen


def generate_items(
    universe: list[Vote],
    post_cutoff: list[Vote],
    titles: TitleIndex,
    templates: dict[str, LanguageTemplates],
) -> tuple[list[dict[str, Any]], BuildLog]:
    log = BuildLog(omitted_titles=[], fallback_titles=[])
    f6_votes = {v.anr for v in universe if v.accepted and v.instrument in {"initiative", "counterproposal"}}
    f6_votes |= {v.anr for v in f6_negatives(universe)}
    items: list[dict[str, Any]] = []

    for vote in [*universe, *post_cutoff]:
        resolved = {lang: resolve_title(vote, lang, titles) for lang in (*CORE_LANGS, "rm")}
        for lang, title in resolved.items():
            if title is None and lang in CORE_LANGS:
                log.omitted_titles.append({"anr": vote.anr, "lang": lang})
            elif title is not None and title.source != "chancellery_lindas":
                log.fallback_titles.append({"anr": vote.anr, "lang": lang, "source": title.source})
        items.extend(_vote_items(vote, resolved, templates, f6_votes))
    return items, log


def _vote_items(
    vote: Vote,
    resolved: dict[str, ResolvedTitle | None],
    templates: dict[str, LanguageTemplates],
    f6_votes: set[str],
) -> Iterator[dict[str, Any]]:
    if not vote.decided:
        for lang in (*CORE_LANGS, "rm"):
            title = resolved[lang]
            if title is None:
                continue
            tpl = templates[lang]
            prompt = tpl.render("F7", **_recall_fields(vote, tpl, title))
            yield _item(vote, "F7", lang, tpl, prompt, {"outcome": "not_decided"}, "not_decided", title)
        return

    assert vote.yes_share is not None and vote.fc_position is not None
    outcome = _outcome(vote)
    cantons = _cantons_majority(vote)

    for lang in (*CORE_LANGS, "rm"):
        title = resolved[lang]
        if title is None:
            continue
        tpl = templates[lang]
        fields = _recall_fields(vote, tpl, title)
        yield _item(vote, "F1", lang, tpl, tpl.render("F1", **fields), {"outcome": outcome}, outcome, title)
        if lang == "rm":
            continue
        yield _item(
            vote, "F2", lang, tpl, tpl.render("F2", **fields),
            {"yes_share": vote.yes_share, "tolerance": 1.0}, "", title,
        )
        yield _item(
            vote, "F3", lang, tpl, tpl.render("F3", **fields),
            {"fc_position": vote.fc_position}, vote.fc_position, title,
        )
        if vote.instrument in {"referendum_obligatory", "initiative"} and cantons is not None:
            yield _item(
                vote, "F4", lang, tpl, tpl.render("F4", **fields),
                {"cantons_majority": cantons, "cantons_yes": vote.cantons_yes,
                 "cantons_no": vote.cantons_no},
                cantons, title,
            )
        if vote.anr in f6_votes:
            in_constitution = "yes" if vote.accepted else "no"
            yield _item(
                vote, "F6", lang, tpl, tpl.render("F6", **fields),
                {"in_constitution": in_constitution, "outcome": outcome}, in_constitution, title,
            )
        yield _item(
            vote, "F8", lang, tpl, tpl.render("F8", **fields),
            {"outcome": outcome, "fc_position": vote.fc_position, "yes_share": vote.yes_share},
            outcome, title,
        )

    if vote.cantons_yes is not None and vote.cantons_no is not None:
        tpl = templates["de"]
        prompt = tpl.render(
            "F5",
            instrument=tpl.instruments[vote.instrument],
            yes_share=tpl.format_number(vote.yes_share, 2),
            cantons_yes=tpl.format_cantons(vote.cantons_yes),
            cantons_no=tpl.format_cantons(vote.cantons_no),
        )
        yield _item(vote, "F5", "de", tpl, prompt, {"outcome": outcome}, outcome, None)


def sort_key(item: dict[str, Any]) -> tuple[int, str, int, int]:
    langs = (*CORE_LANGS, "rm")
    anr = item["anr"]
    return (int(anr.split(".")[0]), anr, FAMILIES.index(item["family"]), langs.index(item["lang"]))


def serialise(items: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in sorted(items, key=sort_key)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def items_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest(payload: bytes, csv_sha256: str, titles_sha256: str, log: BuildLog) -> dict[str, Any]:
    return {
        "generator_version": GENERATOR_VERSION,
        "templates_sha256": templates_digest(),
        "swissvotes_csv_sha256": csv_sha256,
        "titles_sha256": titles_sha256,
        "items_sha256": items_digest(payload),
        "item_count": payload.count(b"\n"),
        "omitted_titles": log.omitted_titles,
        "fallback_titles": log.fallback_titles,
    }


def write_items(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
