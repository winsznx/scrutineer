"""The two HTML pages. Every sentence that states a result is assembled here from results.json.

All interpolated values pass through `esc`. Missing data renders as "n/a" or "not yet run".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from scrutineer.site.charts import BIAS_LANGS, directional_chart, gov_lost_chart, language_chart
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
JUDGE_URL = f"{REPO_URL}/blob/main/track_1b/docs/JUDGE.md"
D24_URL = (f"{REPO_URL}/blob/main/track_1b/docs/DECISIONS.md"
           "#d24-public-ais-apertus-v15-8b-id-appears-to-serve-the-70b-no-8b-result-is-reported")
TEMPLATES_URL = f"{REPO_URL}/tree/main/track_1b/src/scrutineer/templates"
SWISSVOTES_URL = "https://swissvotes.ch"
FONTS_URL = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500"
             "&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=Inter+Tight:wght@500;600;700&display=swap")
AHV_TITLE = re.compile(r"\b13\.?\s*AHV")
TAGLINE = ("A benchmark that asks Apertus 1.5 what the Swiss people decided in every federal vote since 1990, "
           "in four languages, and shows where and why it gets them wrong.")
ERAS = ("1990s", "2000s", "2010s", "2020s")
ROUTE_PAIRS = ("R1~R2", "R1~R1_publicai", "R1_publicai~R2", "R3~R4")
DEPLOYER_PAIR = "R1~R1_publicai"
# R1_publicai holds the 287 answers Public AI's 70B gave before R1 moved to Featherless (D19). It is not a run.
ROUTE_NAMES = {"R1_publicai": "70B (Public AI)"}
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
    status = dig(results, "claims", "C1") or dig(results, "results", CLAIM_RUN, "headline", "status") or "pending"
    return str(status).lower()


def _claim(results: dict[str, Any], head: dict[str, Any]) -> str:
    claim = _link(LEDGER_URL, "pre-registered claim")
    status = _claim_status(results)
    if status == "failed":
        gap, share = number(head.get("gap_points")), number(head.get("directional_share"))
        reasons = [reason for failed, reason in (
            (gap is not None and gap < 10, "the gap is under the 10-point falsifier"),
            (share is not None and share < 0.5,
             "fewer than half of the misses on votes the government lost match its recommendation"),
        ) if failed]
        why = f": {' and '.join(reasons)}" if reasons else ""
        return f"The {claim} failed{why}. It predicted at least 20 points."
    if status == "supported":
        return f"The {claim} held: the gap is at least the 20 points it predicted."
    if status == "inconclusive":
        return f"The {claim} is inconclusive: the result is between the 10-point falsifier and the predicted 20."
    return f"The {claim} is not decided yet. It predicts a gap of at least 20 points and fails below 10."


def _within_instrument(results: dict[str, Any]) -> str:
    within = dig(results, "results", CLAIM_RUN, "within_instrument")
    if not within:
        return ""
    base = f"results.{CLAIM_RUN}.within_instrument"
    ref = "referendum_or_counterproposal"

    def acc(instrument: str, stratum: str) -> str:
        key = f"accuracy_gov_{stratum}"
        return _result(f"{base}.{instrument}.{key}", pct(dig(within, instrument, key)))

    label = esc(run_label(results, CLAIM_RUN))
    text = (f"On initiatives the government lost, {label} is right {acc('initiative', 'lost')} of the time, "
            f"against {acc('initiative', 'won')} on initiatives it won. On referendums and counter-proposals the "
            f"government lost it is right {acc(ref, 'lost')}, against {acc(ref, 'won')} when the government won.")
    init_lost, init_won, ref_lost, ref_won = (number(dig(within, instrument, f"accuracy_gov_{stratum}"))
                                              for instrument in ("initiative", ref) for stratum in ("lost", "won"))
    if (init_lost is not None and init_won is not None and ref_lost is not None and ref_won is not None
            and init_lost < init_won and ref_lost > ref_won):
        text += (" A model repeating the government would fail both. Apertus fails the first and does better on "
                 "the second, which fits a default answer of \"rejected\".")
    return text


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
    within = _within_instrument(results)
    answered = number(dig(results, "runs", CLAIM_RUN, "coverage", "F1", "answered"))
    total = number(dig(results, "runs", CLAIM_RUN, "coverage", "F1", "items"))
    progress = ""
    if answered is not None and total is not None and answered < total:
        progress = (f"<p class=\"note\">So far {count(answered)} of {count(total)} F1 items have an answer in this "
                    "run. The site is rebuilt from the data as runs finish.</p>")
    if not head:
        return f'<p class="big">{big}</p><p class="headline-text">{esc(label)}: not yet run.</p>'
    return (f'<p class="big">{big}{unit}</p><p class="headline-text">{accuracies}</p>'
            f'<p class="claim">{_claim(results, head)}</p>'
            + (f'<p class="claim-detail">{within}</p>' if within else "")
            + f'<p class="detail">{detail}</p>{progress}')


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


def _result(path: str, text: str) -> str:
    """A number on the page, tagged with the results.json path it was read from."""
    return f'<span data-result="{esc(path)}">{esc(text)}</span>'


def _derived(op: str, path: str, text: str) -> str:
    """A number computed from a results.json value, tagged with the operation and the path it starts from."""
    return f'<span data-derived="{esc(op)}" data-path="{esc(path)}">{esc(text)}</span>'


def _bias_runs(data: SiteData) -> list[str]:
    return [run for run in data.runs if dig(data.results, "results", run, "language_bias", "by_lang")]


def _truth_run(data: SiteData, runs: list[str]) -> str | None:
    """The run with the most answered F1 items gives the most complete true share."""
    answered = {run: number(dig(data.results, "runs", run, "coverage", "F1", "answered")) or 0 for run in runs}
    return max(runs, key=lambda run: answered[run]) if runs else None


def _language_statement(data: SiteData, runs: list[str]) -> str:
    run = CLAIM_RUN if CLAIM_RUN in runs else runs[0]
    base = f"results.{run}.language_bias.by_lang"
    shares = {lang: number(dig(data.results, "results", run, "language_bias", "by_lang", lang, "says_accepted"))
              for lang in BIAS_LANGS}
    known = {lang: share for lang, share in shares.items() if share is not None}
    if len(known) < 2:
        return f"{esc(run_label(data.results, run))}: not yet run."
    low, high = min(known, key=lambda k: known[k]), max(known, key=lambda k: known[k])
    # Compare like with like: the true share over the same votes this run has answered.
    truth_path = f"{base}.de"
    truth = dig(data.results, "results", run, "language_bias", "by_lang", "de") or {}
    return (f"Asked in {LANG_NAMES[low]}, {esc(run_label(data.results, run))} says a proposal was accepted "
            f"{_result(f'{base}.{low}.says_accepted', pct(known[low]))} of the time. In {LANG_NAMES[high]} it says "
            f"so {_result(f'{base}.{high}.says_accepted', pct(known[high]))} of the time. On the "
            f"{_result(f'{truth_path}.n', count(truth.get('n')))} votes it has answered, the true share is "
            f"{_result(f'{truth_path}.gold_accepted', pct(truth.get('gold_accepted')))}.")


def _agreement(data: SiteData, runs: list[str]) -> str:
    parts = []
    for run in runs:
        path = f"results.{run}.language_bias"
        bias = dig(data.results, "results", run, "language_bias") or {}
        parts.append(f"{_result(f'{path}.all_four_agree', count(bias.get('all_four_agree')))} of "
                     f"{_result(f'{path}.votes_all_four_answered', count(bias.get('votes_all_four_answered')))} "
                     f"votes for {esc(run_label(data.results, run))}")
    return "German, French, Italian and English give the same answer on " + ", ".join(parts) + "."


def _shift(lang: str, entry: dict[str, Any]) -> str:
    path = f"robustness.order_swap.by_lang.{lang}"
    return (f"{_result(f'{path}.shift_points', fixed(entry.get('shift_points')))} points in {LANG_NAMES[lang]} "
            f"(n={_result(f'{path}.n', count(entry.get('n')))})")


def _order_swap(data: SiteData) -> str:
    swap = dig(data.results, "robustness", "order_swap")
    by_lang = dig(swap, "by_lang") or {}
    langs = [lang for lang in ("fr", "en", "de") if number(dig(by_lang, lang, "shift_points")) is not None]
    if not langs:
        return ("A test that asks with the options reversed, \"rejected or accepted\", is still running. It checks "
                "whether the order of the options causes the effect.")
    shifts = ", ".join(_shift(lang, by_lang[lang]) for lang in langs)
    compared = dig(swap, "compared_with")
    model = esc(run_label(data.results, str(compared))) if compared else NA
    sizes = [number(by_lang[lang].get("n")) or 0 for lang in langs]
    universe = number(dig(data.results, "items", "universe_votes")) or 0
    partial = " so far" if min(sizes) < 0.95 * universe else ""
    return (f"Asking \"rejected or accepted\" instead of \"accepted or rejected\" moved the share of accepted "
            f"answers{partial} by {shifts}, with {model}. Registered reading: under 10 points, the option order "
            "does not explain the effect. 20 points or more, it explains a large part.")


def _languages(data: SiteData) -> str:
    runs = _bias_runs(data)
    truth_run = _truth_run(data, runs)
    if truth_run is None:
        body = "<p>Not yet run.</p>"
        chart = ""
    else:
        body = (f'<p class="statement">{_language_statement(data, runs)}</p>'
                f"<p>{_agreement(data, runs)}</p>"
                f"<p>{_order_swap(data)}</p>"
                f'<p class="note">This was noticed after the data came in, so it is exploratory. It is registered as '
                f"E1 in the {_link(LEDGER_URL, 'claim ledger')}.</p>")
        chart = f"""<figure class="lang-chart">
{language_chart(data.results, runs, truth_run)}
<figcaption>Share of F1 answers that say the proposal was accepted. The dark tick is the share that was actually
accepted, from the {esc(run_label(data.results, truth_run))} run, which has answered the most votes.</figcaption>
</figure>"""
    return f"""<section class="languages wrap grid" id="languages" aria-labelledby="languages-h">
<div class="lang-text">
<h2 class="section-title" id="languages-h">The answer depends on the language you ask in</h2>
{body}
</div>
{chart}
</section>
"""


def _route_name(results: dict[str, Any], route: str) -> str:
    return ROUTE_NAMES.get(route) or run_label(results, route)


def _route_sentence(results: dict[str, Any], pair: str, entry: dict[str, Any]) -> str:
    first, _, second = pair.partition("~")
    path = f"route_identity.{pair}"
    return (f"{esc(_route_name(results, first))} and {esc(_route_name(results, second))} give word-for-word "
            f"identical answers on {_result(f'{path}.identical_text', pct(entry.get('identical_text')))} of "
            f"{_result(f'{path}.n', count(entry.get('n')))} items.")


def _serving(data: SiteData) -> str:
    identity = dig(data.results, "route_identity") or {}
    pairs = [pair for pair in ROUTE_PAIRS if isinstance(identity.get(pair), dict)]
    sentences = [_route_sentence(data.results, pair, identity[pair]) for pair in pairs]
    if not sentences:
        sentences = ["The routes have not been compared yet."]
    body = "".join(f"<p>{sentence}</p>" for sentence in sentences)
    d24 = ("Public AI's <code>apertus-v1.5-8b</code> id answers like the 70B, so no 8B result is reported. "
           f"{_link(D24_URL, 'Decision D24')} has the evidence.")
    return f"""<section class="serving wrap grid" id="serving" aria-labelledby="serving-h">
<h2 class="section-title" id="serving-h">Same weights, different answers</h2>
<div class="prose">{body}<p>{d24}</p></div>
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


def _serving_noise(results: dict[str, Any]) -> str:
    path = f"route_identity.{DEPLOYER_PAIR}"
    entry = dig(results, "route_identity", DEPLOYER_PAIR) or {}
    same = number(entry.get("identical_text"))
    if same is None:
        return esc("The two deployers of the official 70B have not been compared yet.")
    differ = 1 - same
    share = _derived("complement", f"{path}.identical_text", pct(differ))
    rate = (f", about 1 in {_derived('one_in', f'{path}.identical_text', str(round(1 / differ)))}"
            if differ > 0 else "")
    first, _, second = DEPLOYER_PAIR.partition("~")
    return (f"The same weights at temperature 0 give a different answer on {share} of items{rate}, depending on "
            f"who serves them. That is {esc(_route_name(results, first))} against "
            f"{esc(_route_name(results, second))} on the {_result(f'{path}.n', count(entry.get('n')))} items both "
            "answered. A single run of a hosted Apertus carries that much serving noise.")


def _judge(results: dict[str, Any]) -> str:
    judged = count(dig(results, "judge", CLAIM_RUN, "judged_items"))
    return esc(f"Answers the parser cannot read are graded by a 7B judge model, which can be wrong. In run "
               f"{CLAIM_RUN} it decided {judged} answers.")


def _judge_vs_human(human: dict[str, Any]) -> str:
    version = str(human.get("judge_prompt_version") or "")
    current = dig(human, "by_lang", "all")
    earlier = dig(human, "judge_v1_0_by_lang", "all")
    path, entry = (("human_check.by_lang.all", current) if current
                   else ("human_check.judge_v1_0_by_lang.all", earlier) if earlier else ("", None))
    if entry is None:
        return ""
    shown, verb = (esc(version), "agrees") if current and version else ("1.0.0", "agreed")
    text = (f" Judge prompt {shown} {verb} with the reviewed labels on "
            f"{_result(f'{path}.raw_agreement', pct(entry.get('raw_agreement')))} of them, Cohen's kappa "
            f"{_result(f'{path}.cohen_kappa', fixed(entry.get('cohen_kappa'), 2))}.")
    if current and version != "1.0.0":
        text += " That prompt was corrected using these rows, so the number is optimistic."
    elif version and version != "1.0.0":
        text += f" Re-judging the sample with prompt {esc(version)} is not finished."
    return text


def _human_check(results: dict[str, Any]) -> str:
    human = dig(results, "human_check") or {}
    status = human.get("status")
    path = "second_rater_agreement.claude_vs_human.all"
    second = dig(results, *path.split(".")) or {}
    rows, agreement = number(second.get("n")), number(second.get("raw_agreement"))
    guide = f" {_link(JUDGE_URL, 'JUDGE.md')} describes how the labels were made."
    if status == "awaiting_labels":
        sample_size = count(human.get("sample_size"))
        return esc(f"A blind sample of {sample_size} judge decisions is waiting for review.") + guide
    if status not in {"partial", "complete"} or rows is None:
        return esc("The check of the judge against human labels has not been done yet.") + guide
    kept = NA if agreement is None else count(round(rows * agreement))
    sample = _result(f"{path}.n", count(rows))
    text = ("A second AI rater labelled a blind sample of judge decisions without seeing the judge's verdict, the run "
            f"or the language. A person then reviewed those labels and kept {_derived('agreed', path, kept)} of "
            f"{sample}. So judge-human agreement is close to judge-AI agreement and is not an independent human "
            "annotation.")
    return text + _judge_vs_human(human) + guide


def _contamination(results: dict[str, Any]) -> str:
    text = ("The questions are built from public sources that are likely in the training data, which is the point "
            "of a recall test. The risk is that the exact question text or the gold answers leaked too. ")
    done = "The check and its result are" if dig(results, "contamination") else "The planned check is"
    return f'{esc(text)}{done} in {_link(CONTAMINATION_URL, "CONTAMINATION.md")}.'


def _language_templates() -> str:
    text = ("Every language has its own question template, so the language effect could come from how each "
            "template is worded rather than from the language itself. The option-order test above checks one part "
            "of that. The templates are in ")
    return f'{esc(text)}{_link(TEMPLATES_URL, "src/scrutineer/templates/")}.'


def _caveats(data: SiteData) -> str:
    results = data.results
    entries = (
        ("Government lost or usual outcome", _confound(results)),
        ("Contamination", _contamination(results)),
        ("Template phrasing", _templates(results)),
        ("Language or template wording", _language_templates()),
        ("Hosted endpoint, not official weights", _hosted(results)),
        ("Serving", _serving_noise(results)),
        ("Judge disagreement", _judge(results)),
        ("Human check", _human_check(results)),
    )
    body = "".join(f'<li><h3>{esc(title)}</h3><p>{text}</p></li>' for title, text in entries)
    return f"""<section class="caveats wrap grid" id="caveats" aria-labelledby="caveats-h">
<h2 class="section-title" id="caveats-h">How could this be misleading</h2>
<ul class="caveat-list">{body}</ul>
</section>
"""


def landing(data: SiteData) -> str:
    description = TAGLINE
    return (_head("Scrutineer", description) + _nav("finding") + '<main id="main">\n' + _hero(data) + _languages(data)
            + _serving(data) + _method(data) + _caveats(data) + "</main>\n" + _footer(data) + "</body>\n</html>\n")


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
