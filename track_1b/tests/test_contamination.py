from __future__ import annotations

import random

from scrutineer.contamination import (
    CorpusScan,
    choose_row_groups,
    is_source_host,
    ngrams,
    prompt_grams,
    robots_verdicts,
    summarise,
    title_pattern,
    tokenize,
)

PROMPT = "Abstimmung vom 1. April 1990\nVorlage: Volksinitiative 'Stopp dem Beton'\n\nAngenommen oder abgelehnt?"
TITLE = "Volksinitiative 'Stopp dem Beton'"


def test_tokenize_lowercases_unicode_words() -> None:
    assert tokenize("Für die Ständeräte, l'État 1990!") == ["für", "die", "ständeräte", "l", "état", "1990"]


def test_ngrams_window_count() -> None:
    tokens = ["a", "b", "c", "d"]
    assert list(ngrams(tokens, 3)) == [("a", "b", "c"), ("b", "c", "d")]
    assert list(ngrams(tokens, 5)) == []


def test_prompt_grams_split_title_and_template() -> None:
    grams = prompt_grams("x", PROMPT, TITLE, n=3)
    assert grams.title_only == {("volksinitiative", "stopp", "dem"), ("stopp", "dem", "beton")}
    assert ("vorlage", "volksinitiative", "stopp") in grams.touching_template
    assert ("dem", "beton", "angenommen") in grams.touching_template
    assert grams.template_tokens[("dem", "beton", "angenommen")] == 1
    assert grams.template_tokens[("1990", "vorlage", "volksinitiative")] == 2
    assert not grams.title_only & grams.touching_template
    assert len(grams.grams) == len(list(ngrams(tokenize(PROMPT), 3)))


def test_prompt_grams_without_title_are_all_template() -> None:
    grams = prompt_grams("x", PROMPT, None, n=3)
    assert grams.title_only == frozenset()
    assert len(grams.touching_template) == len(list(ngrams(tokenize(PROMPT), 3)))


def test_scan_and_summary_separate_title_and_template_hits() -> None:
    prompts = [prompt_grams("a", PROMPT, TITLE, n=3), prompt_grams("b", "Vorlage: Stopp dem Beton jetzt", None, n=3)]
    pattern = title_pattern(TITLE)
    assert pattern is not None
    scan = CorpusScan(frozenset[tuple[str, ...]]().union(*(p.grams for p in prompts)), [pattern], n=3)
    scan.add("Die volksinitiative  'Stopp dem BETON' scheiterte.", "https://example.ch/1")
    scan.add("Volksinitiative «Stopp dem Beton»", "https://www.admin.ch/2")
    scan.add("Nichts davon.", "https://example.ch/3")

    summary = summarise(prompts, scan)
    assert summary["prompts_with_hit"] == 2
    assert summary["prompts_with_title_only_hits"] == 1
    assert summary["prompts_with_template_hits"] == 1
    assert summary["hit_ngrams_title_only"] == 2
    assert summary["titles_verbatim"]["titles"] == 1
    assert summary["titles_verbatim"]["examples"][0] == {"title": TITLE, "docs": 1, "url": "https://example.ch/1"}
    assert summary["titles_token_sequence"]["examples"][0]["docs"] == 2
    assert summary["source_host_docs"] == {"docs": 1, "urls": ["https://www.admin.ch/2"]}


def test_verbatim_title_needs_word_boundaries() -> None:
    pattern = title_pattern("Asylgesetz")
    assert pattern is not None
    assert pattern.verbatim.search("das asylgesetz wurde")
    assert not pattern.verbatim.search("das asylgesetzes wurde")


def test_choose_row_groups_is_seeded_and_exact() -> None:
    sizes = [1000] * 50
    first = choose_row_groups(sizes, 2500, random.Random("0:deu_Latn"))
    again = choose_row_groups(sizes, 2500, random.Random("0:deu_Latn"))
    assert first == again
    assert sum(rows for _, rows in first) == 2500
    assert [index for index, _ in first] == sorted(index for index, _ in first)


def test_robots_verdicts() -> None:
    robots = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private/\n"
    verdicts = robots_verdicts(robots, "https://example.ch/vote/1", ("GPTBot", "CCBot", "*"))
    assert verdicts == {"GPTBot": False, "CCBot": True, "*": True}


def test_is_source_host() -> None:
    assert is_source_host("www.bk.admin.ch")
    assert is_source_host("swissvotes.ch")
    assert not is_source_host("notadmin.ch")
