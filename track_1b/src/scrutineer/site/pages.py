"""The two HTML pages. Every sentence that states a result is assembled here from results.json.

All interpolated values pass through `esc`. Missing data renders as "n/a" or "not yet run".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from scrutineer.site.charts import directional_chart, gov_lost_chart
from scrutineer.site.common import (
    CORE_LANGS,
    INSTRUMENTS,
    LANG_NAMES,
    LANGS,
    NA,
    count,
    dig,
    esc,
    f1_cell,
    fixed,
    long_date,
    number,
    pct,
    run_label,
)

CLAIM_RUN = "R1"
REPO_URL = "https://github.com/winsznx/scrutineer"
DATASET_URL = "https://huggingface.co/datasets/winsznx/scrutineer"
REPORT_URL = f"{REPO_URL}/blob/main/track_1b/Scrutineer_Report.pdf"
CONTAMINATION_URL = f"{REPO_URL}/blob/main/track_1b/docs/CONTAMINATION.md"
LEDGER_URL = f"{REPO_URL}/blob/main/track_1b/docs/CLAIM_LEDGER.md"
SWISSVOTES_URL = "https://swissvotes.ch"
FONTS_URL = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500"
             "&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=Inter+Tight:wght@500;600;700&display=swap")
AHV_TITLE = re.compile(r"\b13\.?\s*AHV")
TAGLINE = ("A benchmark that asks Apertus 1.5 what the Swiss people decided in every federal vote since 1990, "
           "in four languages, and shows where and why it gets them wrong.")
ERAS = ("1990s", "2000s", "2010s", "2020s")
_CURRENT = ' aria-current="page"'


@dataclass(frozen=True)
class SiteData:
    results: dict[str, Any]
    runs: list[str]
    votes: list[dict[str, Any]]
    results_sha256: str
    en_fallback_titles: int


def _link(href: str, text: str) -> str:
    return f'<a href="{esc(href)}">{esc(text)}</a>'


def _head(title: str, description: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{esc(FONTS_URL)}">
<link rel="stylesheet" href="style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
"""


def _nav(current: str) -> str:
    links = (("index.html#finding", "Finding", "finding"), ("explorer.html", "Explorer", "explorer"),
             (REPORT_URL, "Report", "report"))
    items = "".join(
        f'<li><a href="{esc(href)}"{_CURRENT if key == current else ""}>{esc(text)}</a></li>'
        for href, text, key in links
    )
    return (f'<header class="top"><div class="wrap top-row"><a class="wordmark" href="index.html">Scrutineer</a>'
            f'<nav aria-label="Main"><ul>{items}</ul></nav></div></header>\n')


def _footer(data: SiteData) -> str:
    items_sha = dig(data.results, "items", "sha256") or NA
    schema = dig(data.results, "schema_version") or NA
    return f"""<footer class="foot"><div class="wrap grid">
<div class="foot-col">
<p>Code: Apache-2.0. Dataset: CDLA-Permissive-2.0. Report: CC-BY-4.0.</p>
<p>Vote data: {_link(SWISSVOTES_URL, "Swissvotes")}, CC BY 4.0, Année Politique Suisse, Universität Bern.
Official titles: Federal Chancellery, via LINDAS.</p>
</div>
<div class="foot-col">
<p>Items sha256 <code>{esc(items_sha)}</code></p>
<p>Every result on the finding page is generated from results.json, sha256
<code>{esc(data.results_sha256)}</code>, schema {esc(schema)}. The explorer reads the graded and raw answer files.</p>
</div>
</div></footer>
"""


def _claim_status(results: dict[str, Any]) -> str:
    status = dig(results, "results", CLAIM_RUN, "headline", "status") or dig(results, "claims", "C1") or "pending"
    return str(status).lower()


def _headline(data: SiteData) -> str:
    results = data.results
    head = dig(results, "results", CLAIM_RUN, "headline") or {}
    label = run_label(results, CLAIM_RUN)
    gap = number(head.get("gap_points"))
    direction = ("lower on votes the government lost" if gap is not None and gap >= 0
                 else "higher on votes the government lost" if gap is not None else "")

    def span(key: str, text: str) -> str:
        return f'<span data-headline="{esc(key)}">{esc(text)}</span>'

    big = span("gap_points", NA if gap is None else f"{abs(gap):.1f}")
    unit = f' <span class="unit">points {esc(direction)}</span>' if gap is not None else ""
    accuracies = (f'{span("accuracy_gov_won", pct(head.get("accuracy_gov_won")))} on votes the Federal Council won, '
                  f'{span("accuracy_gov_lost", pct(head.get("accuracy_gov_lost")))} on votes it lost.')
    detail = (f"{esc(label)} was asked whether each vote was accepted or rejected (question F1). German, French, "
              f"Italian and English answers are pooled: {span('n_gov_won', count(head.get('n_gov_won')))} on votes "
              f"the government won, {span('n_gov_lost', count(head.get('n_gov_lost')))} on votes it lost. "
              f"Two-proportion test: z = {span('z', fixed(head.get('z'), 2))}, "
              f"p = {span('p_value', fixed(head.get('p_value'), 2))}.")
    claim = (f"The {_link(LEDGER_URL, 'pre-registered claim')} expected a gap of at least 20 points and counts as "
             f"failed below 10. Status: {esc(_claim_status(results))}.")
    answered = number(dig(results, "runs", CLAIM_RUN, "coverage", "F1", "answered"))
    total = number(dig(results, "runs", CLAIM_RUN, "coverage", "F1", "items"))
    progress = ""
    if answered is not None and total is not None and answered < total:
        progress = (f"<p class=\"note\">So far {count(answered)} of {count(total)} F1 items have an answer in this "
                    "run. The site is rebuilt from the data as runs finish.</p>")
    if not head:
        return f'<p class="big">{big}</p><p class="headline-text">{esc(label)}: not yet run.</p>'
    return (f'<p class="big">{big}{unit}</p><p class="headline-text">{accuracies}</p>'
            f'<p class="detail">{detail} {claim}</p>{progress}')


def _answer_phrase(answer: list[Any] | None) -> str:
    if not answer:
        return "not yet run"
    _, parsed, grade, _, _, status = answer
    if status == "failed":
        return "request failed"
    said = {"accepted": "accepted", "rejected": "rejected", "abstain": "I don't know"}.get(str(parsed), "unreadable")
    verdict = {"correct": "correct", "incorrect": "incorrect", "not_attempted": "abstained"}.get(str(grade),
                                                                                                 "not yet graded")
    return f"{said} ({verdict})"


def _ahv(data: SiteData) -> str:
    vote = next((v for v in data.votes if not v["pc"] and AHV_TITLE.search(v["t"].get("de", ""))), None)
    if vote is None:
        return ""
    yes = number(vote.get("y"))
    outcome = {"accepted": "accepted", "rejected": "rejected"}.get(str(vote.get("o")), NA)
    gold = (f"The 13th AHV pension initiative (vote {esc(vote['a'])}) was {esc(outcome)} on "
            f"{esc(long_date(vote.get('d')))}" + (f" with {esc(fixed(yes, 2))}% yes." if yes is not None else "."))
    answers = dig(vote, "r", CLAIM_RUN, "F1") or {}
    langs = [lang for lang in LANGS if lang in (dig(vote, "k", "F1") or [])]
    if CLAIM_RUN not in data.runs or not answers:
        said = "not yet run"
    else:
        said = ", ".join(f"{LANG_NAMES[lang]} {_answer_phrase(answers.get(lang))}" for lang in langs)
    return (f'<p class="ahv">{gold} Asked in each language whether it was accepted or rejected, '
            f"{esc(run_label(data.results, CLAIM_RUN))} answered: {esc(said)}.</p>")


def _hero(data: SiteData) -> str:
    chart_runs = [run for run in data.runs if dig(data.results, "results", run)] or data.runs
    links = " ".join(f'<li>{_link(href, text)}</li>' for href, text in
                     ((DATASET_URL, "Dataset"), (REPO_URL, "Repository"), (REPORT_URL, "Report")))
    return f"""<section class="hero wrap">
<h1 class="display">Scrutineer</h1>
<p class="lede">{esc(TAGLINE)}</p>
</section>
<section class="finding wrap grid" id="finding" aria-labelledby="finding-h">
<div class="finding-text">
<h2 class="kicker" id="finding-h">F1 accuracy gap, {esc(run_label(data.results, CLAIM_RUN))}</h2>
{_headline(data)}
{_ahv(data)}
<ul class="links">{links}</ul>
</div>
<figure class="finding-chart">
{gov_lost_chart(data.results, chart_runs)}
<figcaption>Share of F1 answers that named the right outcome, with 95% Wilson intervals. Red marks votes the
Federal Council lost.</figcaption>
</figure>
</section>
"""


def _method(data: SiteData) -> str:
    results = data.results
    items = count(dig(results, "items", "count"))
    decided = count(dig(results, "items", "universe_votes"))
    upcoming = sum(1 for vote in data.votes if vote.get("pc"))
    judged = count(dig(results, "judge", CLAIM_RUN, "judged_items"))
    p1 = (f"Every item is a question about one federal vote. Outcomes, yes shares, canton results and the Federal "
          f"Council's recommendation come from {_link(SWISSVOTES_URL, 'Swissvotes')}. Titles are the official "
          f"Federal Chancellery titles from LINDAS: German, French and Italian for every vote, Romansh where the "
          f"Chancellery publishes it (since 2009), and English where it publishes one. For "
          f"{count(data.en_fallback_titles)} more votes the English title is the Swissvotes short title, and votes "
          f"with neither get no English items. No model translated anything. There are {items} items on "
          f"{decided} decided votes and {upcoming} votes that have not been held yet, where the right answer is "
          f"to say so.")
    p2 = ("A deterministic parser reads each answer in its own language: accepted, rejected, a percentage, or "
          "I don't know. Answers it cannot read, and the two free-text question families, go to a local "
          f"open-weights judge, Qwen2.5-7B-Instruct. Apertus never grades its own answers. In run {CLAIM_RUN} the "
          f"judge has decided {judged} answers so far.")
    p3 = (f"The main claim was {_link(LEDGER_URL, 'written down')} before the first request: on F1, "
          f"{esc(run_label(results, CLAIM_RUN))} would be at least 20 points less accurate on votes the government "
          "lost, and at least 70% of its misses there would match the Federal Council's recommendation. Below 10 "
          "points or 50% it fails. Its status is regenerated from the data, never edited by hand.")
    p4 = ("<code>make run</code> rebuilds the items from the pinned sources, replays grading from the stored "
          "responses, checks results.json against its recorded hash, and regenerates the figures and this site. It "
          "runs in Docker and needs no API key.")
    paragraphs = "".join(f"<p>{p}</p>" for p in (p1, p2, p3, p4))
    return f"""<section class="method wrap grid" id="method" aria-labelledby="method-h">
<h2 class="section-title" id="method-h">Method</h2>
<div class="prose">{paragraphs}</div>
<figure class="method-chart">
<h3 class="figure-title">Which way the wrong answers point, {esc(run_label(results, CLAIM_RUN))}</h3>
{directional_chart(results, CLAIM_RUN)}
<figcaption>Wrong F1 answers per language. Dark: the answer equals the Federal Council's recommendation. Grey: it
opposes it. On a yes-or-no question a wrong answer on a vote the government lost always equals its
recommendation, so this split also shows where the errors fall.</figcaption>
</figure>
</section>
"""


def _confound(results: dict[str, Any]) -> str:
    base = dig(results, "baselines") or {}
    within = dig(results, "results", CLAIM_RUN, "within_instrument", "initiative") or {}
    text = ("In this set of votes, the government losing always coincides with the less common outcome for that "
            "kind of vote: initiatives usually fail and referendums usually pass. So the data cannot tell a model "
            "that repeats the government apart from one that assumes the usual outcome. Always answering with the "
            f"Federal Council's recommendation scores {pct(dig(base, 'fc_echo', 'gov_won'))} on votes it won and "
            f"{pct(dig(base, 'fc_echo', 'gov_lost'))} on votes it lost. Answering \"initiatives fail, everything "
            f"else passes\" scores {pct(dig(base, 'instrument_prior', 'gov_won'))} and "
            f"{pct(dig(base, 'instrument_prior', 'gov_lost'))}.")
    if number(within.get("accuracy_gov_won")) is not None:
        text += (f" Within initiatives alone, {run_label(results, CLAIM_RUN)} scores "
                 f"{pct(within.get('accuracy_gov_won'))} on votes the government won "
                 f"(n={count(within.get('n_gov_won'))}) and {pct(within.get('accuracy_gov_lost'))} on votes it lost "
                 f"(n={count(within.get('n_gov_lost'))}).")
    return esc(text)


def _templates(results: dict[str, Any]) -> str:
    text = ("Each question family uses one fixed template per language. Different wording could produce different "
            "answers, and some of the gap between languages may come from the templates rather than the language.")
    accuracy = {lang: number(dig(f1_cell(results, CLAIM_RUN, lang, "all", "all"), "accuracy")) for lang in CORE_LANGS}
    known = {lang: acc for lang, acc in accuracy.items() if acc is not None}
    if len(known) >= 2:
        low = min(known, key=lambda lang: known[lang])
        high = max(known, key=lambda lang: known[lang])
        text += (f" F1 accuracy for {run_label(results, CLAIM_RUN)} runs from {pct(known[low])} in "
                 f"{LANG_NAMES[low]} to {pct(known[high])} in {LANG_NAMES[high]}.")
    return esc(text)


def _hosted(results: dict[str, Any]) -> str:
    endpoint = dig(results, "runs", CLAIM_RUN, "endpoint")
    host = urlparse(str(endpoint)).netloc if endpoint else NA
    text = (f"The runs went through a hosted endpoint ({host}), not the official weights on hardware we control. "
            "A hosted deployment can differ in quantisation, chat template or decoding.")
    replay = dig(results, "replay")
    agreement = number(dig(replay, "agreement"))
    if agreement is not None:
        text += f" On the replayed sample, the official checkpoint gave the same label {pct(agreement)} of the time."
    else:
        text += " A replay of a sample against the official checkpoint has not been run yet."
    return esc(text)


def _judge(results: dict[str, Any]) -> str:
    human = dig(results, "human_check") or {}
    status = human.get("status")
    judged = count(dig(results, "judge", CLAIM_RUN, "judged_items"))
    text = (f"Answers the parser cannot read are graded by a 7B judge model, which can be wrong. In run {CLAIM_RUN} "
            f"it decided {judged} answers.")
    overall = dig(human, "by_lang", "all")
    if status in {"partial", "complete"} and overall:
        text += (f" On {count(overall.get('n'))} answers labelled blind by a person, the judge agreed "
                 f"{pct(overall.get('raw_agreement'))} of the time "
                 f"(Cohen's kappa {fixed(overall.get('cohen_kappa'), 2)}).")
    elif status == "awaiting_labels":
        text += f" A blind sample of {count(human.get('sample_size'))} judge decisions is waiting for human labels."
    else:
        text += " The blind human check of the judge has not been done yet."
    return esc(text)


def _contamination(results: dict[str, Any]) -> str:
    text = ("The questions are built from public sources that are likely in the training data, which is the point "
            "of a recall test. The risk is that the exact question text or the gold answers leaked too. ")
    done = "The check and its result are" if dig(results, "contamination") else "The planned check is"
    return f'{esc(text)}{done} in {_link(CONTAMINATION_URL, "CONTAMINATION.md")}.'


def _caveats(data: SiteData) -> str:
    results = data.results
    entries = (
        ("Government lost or usual outcome", _confound(results)),
        ("Contamination", _contamination(results)),
        ("Template phrasing", _templates(results)),
        ("Hosted endpoint, not official weights", _hosted(results)),
        ("Judge disagreement", _judge(results)),
    )
    body = "".join(f'<li><h3>{esc(title)}</h3><p>{text}</p></li>' for title, text in entries)
    return f"""<section class="caveats wrap grid" id="caveats" aria-labelledby="caveats-h">
<h2 class="section-title" id="caveats-h">How could this be misleading</h2>
<ul class="caveat-list">{body}</ul>
</section>
"""


def landing(data: SiteData) -> str:
    description = TAGLINE
    return (_head("Scrutineer", description) + _nav("finding") + '<main id="main">\n' + _hero(data) + _method(data)
            + _caveats(data) + "</main>\n" + _footer(data) + "</body>\n</html>\n")


def _options(name: str, label: str, choices: list[tuple[str, str]]) -> str:
    options = "".join(f'<option value="{esc(value)}">{esc(text)}</option>' for value, text in choices)
    return (f'<div class="field"><label for="f-{esc(name)}">{esc(label)}</label>'
            f'<select id="f-{esc(name)}" name="{esc(name)}">{options}</select></div>')


def _filters() -> str:
    return ('<form class="filters" role="search" aria-label="Filter votes">'
            + _options("lang", "Language", [(lang, LANG_NAMES[lang]) for lang in LANGS])
            + _options("gov", "Government", [("all", "Won or lost"), ("won", "Won"), ("lost", "Lost")])
            + _options("inst", "Instrument", [("all", "All instruments"), *INSTRUMENTS.items()])
            + _options("era", "Era", [("all", "All years"), *((era, era) for era in ERAS)])
            + '<div class="field field-search"><label for="f-q">Search titles</label>'
            '<input id="f-q" name="q" type="search" autocomplete="off" spellcheck="false"></div>'
            "</form>")


def explorer(data: SiteData) -> str:
    run_heads = "".join(f'<th scope="col" class="verdict-col">{esc(run_label(data.results, run))}</th>'
                        for run in data.runs)
    description = "Every vote in the Scrutineer benchmark with each model's verbatim answers and verdicts."
    return (_head("Scrutineer explorer", description) + _nav("explorer") + f"""<main id="main" class="explorer">
<section class="wrap grid explorer-intro">
<h1 class="page-title">Explorer</h1>
<p class="lede">Every vote in the benchmark. Choose a language to read titles and verdicts in it, and open a vote
to see the gold answers, the sources and every answer each model gave.</p>
</section>
<div class="wrap">
{_filters()}
<p class="count" id="count" aria-live="polite">Loading votes</p>
<table class="votes" id="votes">
<caption class="visually-hidden">Votes, with each run's verdict on the outcome question in the selected
language</caption>
<thead><tr><th scope="col" class="date-col">Date</th><th scope="col">Vote</th><th scope="col">Instrument</th>
<th scope="col">Government</th><th scope="col">Outcome</th>{run_heads}</tr></thead>
<tbody id="votes-body"></tbody>
</table>
<p class="table-note">Run columns show the verdict on the outcome question (F1) in the selected language. For the
votes not yet held it is F7, where the right answer is that the vote has not happened.</p>
<noscript><p>The explorer needs JavaScript. The raw data is in <a href="data/votes.json">data/votes.json</a>.
</p></noscript>
</div>
</main>
""" + _footer(data) + '<script src="explorer.js" defer></script>\n</body>\n</html>\n')
