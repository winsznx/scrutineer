"""Generated markdown blocks. Every number quoted in a document comes from here.

A document opts in with a marker pair:

    <!-- scrutineer:begin headline -->
    (generated, do not edit)
    <!-- scrutineer:end headline -->

`sync_file` replaces the text between markers with the named block rendered from
results.json. Prose outside markers is never touched.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

LANG_NAMES = {"de": "German", "fr": "French", "it": "Italian", "en": "English", "rm": "Romansh", "core": "de/fr/it/en"}
FAMILY_NAMES = {
    "F1": "Outcome", "F2": "Yes share", "F3": "FC recommendation", "F4": "Cantons majority",
    "F5": "Reasoning control", "F6": "In the constitution", "F7": "Post-cutoff", "F8": "Free recall",
}
MARKER = re.compile(
    r"(<!-- scrutineer:begin (?P<name>[a-z0-9_]+) -->\n)(?P<body>.*?)(<!-- scrutineer:end (?P=name) -->)",
    re.DOTALL,
)

Results = dict[str, Any]


def pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def num(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _cell(
    results: Results, run: str, family: str, lang: str, stratum: str = "all", value: str = "all"
) -> dict[str, Any]:
    for row in results["results"].get(run, {}).get("cells", []):
        if (row["family"], row["lang"], row["stratum"], row["value"]) == (family, lang, stratum, value):
            return dict(row)
    return {}


def _runs(results: Results) -> list[str]:
    return [run for run in ("R1", "R2", "R3", "R4") if run in results["results"]]


def headline(results: Results) -> str:
    h = results["results"].get("R1", {}).get("headline")
    if not h or h.get("accuracy_gov_won") is None:
        return "_R1 has not been graded yet._\n"
    return (
        f"On F1 (did the vote pass?) in German, French, Italian and English, Apertus 1.5 70B is right on "
        f"**{pct(h['accuracy_gov_won'])}** of votes the Federal Council won and **{pct(h['accuracy_gov_lost'])}** "
        f"of votes it lost, a gap of **{num(h['gap_points'])} points** (z = {num(h['z'], 2)}, "
        f"p = {num(h['p_value'], 4)}; n = {h['n_gov_won']} and {h['n_gov_lost']} answers). "
        f"Pre-registered claim C1: **{h.get('status', 'PENDING')}**.\n"
    )


def claims(results: Results) -> str:
    h = results["results"].get("R1", {}).get("headline", {})
    rvr = results["results"].get("R1", {}).get("reasoning_vs_recall", {}).get("gov_lost", {})
    rows = [
        "| Claim | Test | Result | Status |",
        "|---|---|---|---|",
        f"| C1 gap | accuracy(gov won) − accuracy(gov lost) ≥ 20 pts, falsified < 10 | "
        f"{num(h.get('gap_points'))} pts, p = {num(h.get('p_value'), 4)} | {results['claims'].get('C1', 'PENDING')} |",
        f"| C1b direction | FC-matching share of non-correct answers on gov-lost votes ≥ 70%, falsified < 50% | "
        f"{pct(h.get('directional_share'))} (95% CI {pct((h.get('directional_share_ci95') or [None])[0])}–"
        f"{pct((h.get('directional_share_ci95') or [None, None])[1])}, n = {h.get('directional_n', 0)}) | "
        f"part of C1 |",
        f"| C1 literal clause | FC-matching share of incorrect answers on gov-lost votes | "
        f"{pct(h.get('literal_clause_share'))} (n = {h.get('literal_clause_n', 0)}), 100% by construction | n/a |",
        f"| C3 reasoning | F5 on gov-lost votes ≥ 80% and ≥ 15 pts above F1 (de) | "
        f"F5 {pct(rvr.get('f5_accuracy'))}, F1 {pct(rvr.get('f1_de_accuracy'))} | "
        f"{results['claims'].get('C3', 'PENDING')} |",
    ]
    return "\n".join(rows) + "\n"


def f1_table(results: Results) -> str:
    rows = ["| Model | Language | Gov. won | Gov. lost | Gap (pts) | Not attempted |", "|---|---|--:|--:|--:|--:|"]
    for run in _runs(results):
        for lang in ("core", "de", "fr", "it", "en", "rm"):
            won = _cell(results, run, "F1", lang, "gov_lost", "0")
            lost = _cell(results, run, "F1", lang, "gov_lost", "1")
            overall = _cell(results, run, "F1", lang)
            if not overall.get("n"):
                continue
            gap = ((won["accuracy"] - lost["accuracy"]) * 100
                   if won.get("accuracy") is not None and lost.get("accuracy") is not None else None)
            rows.append(f"| {results['runs'][run]['label']} | {LANG_NAMES[lang]} | {pct(won.get('accuracy'))} "
                        f"(n={won.get('n', 0)}) | {pct(lost.get('accuracy'))} (n={lost.get('n', 0)}) | {num(gap)} | "
                        f"{pct(overall.get('not_attempted_rate'))} |")
    return "\n".join(rows) + "\n"


def family_table(results: Results) -> str:
    runs = _runs(results)
    rows = ["| Family | " + " | ".join(results["runs"][r]["label"] for r in runs) + " |",
            "|---|" + "--:|" * len(runs)]
    for family, name in FAMILY_NAMES.items():
        lang = "de" if family == "F5" else "core"
        values = []
        for run in runs:
            c = _cell(results, run, family, lang)
            values.append(f"{pct(c.get('accuracy'))} (n={c.get('n', 0)})" if c.get("n") else "not run")
        rows.append(f"| {family} {name} | " + " | ".join(values) + " |")
    return "\n".join(rows) + "\n"


def within_instrument(results: Results) -> str:
    rows = ["| Model | Instruments | Gov. won | Gov. lost | Gap (pts) | p |", "|---|---|--:|--:|--:|--:|"]
    for run in _runs(results):
        for name, w in results["results"][run]["within_instrument"].items():
            rows.append(f"| {results['runs'][run]['label']} | {name.replace('_', ' ')} | {pct(w['accuracy_gov_won'])} "
                        f"(n={w['n_gov_won']}) | {pct(w['accuracy_gov_lost'])} (n={w['n_gov_lost']}) | "
                        f"{num(w['gap_points'])} | {num(w['p_value'], 4)} |")
    b = results["baselines"]
    rows.append(f"| Baseline: always the FC's line | all | {pct(b['fc_echo']['gov_won'])} | "
                f"{pct(b['fc_echo']['gov_lost'])} | | |")
    rows.append(f"| Baseline: initiatives fail, all else passes | all | {pct(b['instrument_prior']['gov_won'])} | "
                f"{pct(b['instrument_prior']['gov_lost'])} | | |")
    return "\n".join(rows) + "\n"


def secondary_table(results: Results) -> str:
    rows = ["| Model | F2 MAE (pts) | F2 within 1 pt | F7 abstains (correct) | F5 − F1 de, gov. lost |",
            "|---|--:|--:|--:|--:|"]
    for run in _runs(results):
        f2 = results["results"][run]["yes_share"].get("core", {})
        f7 = results["results"][run]["post_cutoff"].get("core", {})
        rvr = results["results"][run]["reasoning_vs_recall"].get("gov_lost", {})
        rows.append(f"| {results['runs'][run]['label']} | {num(f2.get('mae_points'))} | "
                    f"{pct(f2.get('within_1_point'))} | {pct(f7.get('accuracy'))} (n={f7.get('n', 0)}) | "
                    f"{num(rvr.get('gap_points'))} pts |")
    return "\n".join(rows) + "\n"


def runs_table(results: Results) -> str:
    rows = ["| Run | Model id | Answered | Failed (final) | Failed attempts logged | Cost (USD) | Tokens in / out | "
            "Latency p50 / p95 (ms) |", "|---|---|--:|--:|--:|--:|--:|--:|"]
    for run in _runs(results):
        info = results["runs"][run]
        s = info["summary"]
        rows.append(f"| {run} | `{info['model']}` | {s['items_ok']:,} / {s['items_selected']:,} | "
                    f"{s['items_failed_final']} | {s['failed_records_total']} | {s['cost_usd']:.4f} | "
                    f"{s['prompt_tokens']:,} / {s['completion_tokens']:,} | "
                    f"{s['latency_ms_p50']} / {s['latency_ms_p95']} |")
    return "\n".join(rows) + "\n"


def dataset_stats(results: Results) -> str:
    items = results["items"]
    fams = " · ".join(f"{f} {n:,}" for f, n in items["by_family"].items())
    langs = " · ".join(f"{LANG_NAMES[lang]} {n:,}" for lang, n in items["by_lang"].items())
    return (f"{items['count']:,} items over {items['universe_votes']} decided federal votes "
            f"(1 Jan 1990 to 27 Sep 2026, {items['gov_lost_votes']} of them lost by the Federal Council) "
            f"plus the 4 votes of 29 Nov 2026.\n\nBy family: {fams}.\n\nBy language: {langs}.\n\n"
            f"`items.jsonl` sha256 `{items['sha256'][:16]}…` (full hash in `data/items.manifest.json`).\n")


def human_table(results: Results) -> str:
    human = results["human_check"]
    if human.get("status") in {"not_exported", "awaiting_labels"}:
        return f"_Human check status: {human['status'].replace('_', ' ')}._\n"
    second = results.get("second_rater_agreement", {})
    claude_human = second.get("claude_vs_human", {}).get("all", {})
    rows = [f"Labelled {human['labelled']} of {human['sample_size']} sampled judgements ({human['status']}). "
            f"The labeller saw a blind Claude pre-label; human and Claude agree on "
            f"{pct(claude_human.get('raw_agreement'))} of rows, so judge versus human is close to judge versus "
            "Claude and is not an independent second annotation.", "",
            f"| Language | n | Judge {human.get('judge_prompt_version', '')} vs human | κ | Judge 1.0.0 vs human | κ |",
            "|---|--:|--:|--:|--:|--:|"]
    for lang, s in human["by_lang"].items():
        old = human.get("judge_v1_0_by_lang", {}).get(lang, {})
        rows.append(f"| {LANG_NAMES.get(lang, lang)} | {s['n']} | {pct(s['raw_agreement'])} | "
                    f"{num(s['cohen_kappa'], 3)} | {pct(old.get('raw_agreement'))} | "
                    f"{num(old.get('cohen_kappa'), 3)} |")
    return "\n".join(rows) + "\n"


def judge_versions_table(results: Results) -> str:
    rows = ["| Run | F6 judge 1.0.0 | F6 judge 1.1.0 | F8 judge 1.0.0 | F8 judge 1.1.0 |", "|---|--:|--:|--:|--:|"]
    for run in _runs(results):
        v = results.get("judge_versions", {}).get(run, {})
        cells = [pct(v.get(f, {}).get(ver, {}).get("accuracy")) for f in ("F6", "F8") for ver in ("1.0.0", "current")]
        rows.append(f"| {results['runs'][run]['label']} | " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"


def thinking_table(results: Results) -> str:
    rows = ["| Run | Language | Answers with a trace | Mean output tokens | Cut off at 2,000 |",
            "|---|---|--:|--:|--:|"]
    for run, by_lang in results.get("thinking_traces", {}).items():
        for lang, t in by_lang.items():
            rows.append(f"| {results['runs'][run]['label']} | {LANG_NAMES.get(lang, lang)} | "
                        f"{pct(t['share_with_trace'])} | {num(t['mean_completion_tokens'], 0)} | "
                        f"{t['truncated_at_max_tokens']} |")
    return "\n".join(rows) + "\n"


def deployer_text(results: Results) -> str:
    d = results.get("deployer_agreement")
    if not d:
        return "_No deployer comparison available._\n"
    return (f"The same official 70B weights, asked the same {d['n']} F1 questions at temperature 0 on two "
            f"deployers (Public AI, then Featherless through the Hugging Face router), gave the same parsed "
            f"answer {pct(d['parsed_agreement'])} of the time. The rest flip between accepted and rejected.\n")


def route_identity_text(results: Results) -> str:
    ri = results.get("route_identity", {})
    pairs = {
        "R1~R2": "the official 70B (Featherless) and Public AI's \"8B\" route",
        "R1~R1_publicai": "the official 70B on Featherless and on Public AI",
        "R1_publicai~R2": "Public AI's 70B and \"8B\" routes",
        "R3~R4": "Public AI's \"8B\" route with thinking and the 70B with thinking (Featherless)",
    }
    lines = [f"- {label}: identical text on {pct(ri[key]['identical_text'])} of {ri[key]['n']:,} items"
             for key, label in pairs.items() if key in ri]
    return "\n".join(lines) + "\n" if lines else "_No route comparison available._\n"


def claim_status(results: Results) -> str:
    h = results["results"].get("R1", {}).get("headline", {})
    rvr = results["results"].get("R1", {}).get("reasoning_vs_recall", {}).get("gov_lost", {})
    within = results["results"].get("R1", {}).get("within_instrument", {})
    initiative_gap = within.get("initiative", {}).get("gap_points")
    referendum_gap = within.get("referendum_or_counterproposal", {}).get("gap_points")
    return (
        f"- C1: **{results['claims'].get('C1', 'PENDING')}**. Gap {num(h.get('gap_points'))} points "
        f"(falsifier: under 10), p = {num(h.get('p_value'), 4)}, R1 on Featherless (D19).\n"
        f"- C1b: directional share {pct(h.get('directional_share'))}, above the 70% threshold; reported as part "
        "of C1, which fails on the gap.\n"
        f"- C2: within initiatives the gap is {num(initiative_gap)} points; within "
        f"referendums and counter-proposals it is {num(referendum_gap)} points. "
        "The errors follow a default \"rejected\" answer, not the Federal Council.\n"
        f"- C3: **{results['claims'].get('C3', 'PENDING')}**. F5 {pct(rvr.get('f5_accuracy'))} against "
        f"F1 (de) {pct(rvr.get('f1_de_accuracy'))} on government-lost votes.\n"
    )


def flip_rate(results: Results) -> str:
    """Share of answers that change between two deployers of the same 70B weights."""
    pair = results.get("route_identity", {}).get("R1~R1_publicai")
    if not pair:
        return "_No deployer comparison available._\n"
    flipped = 1 - pair["identical_text"]
    rate = f", about 1 in {round(1 / flipped)}" if flipped else ""
    return (f"The same official 70B weights at temperature 0, served by Public AI and by Featherless, give a "
            f"different answer on {pct(flipped)} of the {pair['n']} items both answered{rate}.\n")


def r4_table(results: Results) -> str:
    pr = results.get("r4_vs_r1")
    if not pr:
        return "_R4 not run._\n"
    rows = ["| F1 items (answered by both) | n | 70B | 70B thinking | Only 70B right | Only thinking right |",
            "|---|--:|--:|--:|--:|--:|"]
    for label in ("gov_won", "gov_lost"):
        c = pr[label]
        side = "won" if label == "gov_won" else "lost"
        rows.append(f"| Government {side} | {c['n']} | {pct(c.get('R1_accuracy'))} | "
                    f"{pct(c.get('R4_accuracy'))} | {c['only_right_correct']} | {c['only_left_correct']} |")
    return "\n".join(rows) + "\n"


def judge_table(results: Results) -> str:
    rows = ["| Run | Judged items | By reason | F6 parser vs judge agreement |", "|---|--:|---|--:|"]
    for run in _runs(results):
        j = results["judge"].get(run, {})
        f6 = results["results"][run]["f6_parser_judge"]
        reasons = ", ".join(f"{k} {v}" for k, v in j.get("by_reason", {}).items())
        rows.append(f"| {run} | {j.get('judged_items', 0)} | {reasons} | "
                    f"{pct(f6.get('agreement'))} (n={f6.get('n', 0)}) |")
    return "\n".join(rows) + "\n"


def contamination(results: Results) -> str:
    c = results.get("contamination")
    if not c:
        return "_Contamination check not run yet._\n"
    lists = "; ".join(f"`{b['file']}` ({b['lines']:,} hosts): "
                      f"{', '.join(b['source_hosts_listed']) or 'no swissvotes.ch or admin.ch host'}"
                      for b in c["domains"]["blocklists"])
    rows = ["| Language | Prompts | With a 13-gram hit | Inside the title only | Touching template | "
            "Titles found verbatim |", "|---|--:|--:|--:|--:|--:|"]
    corpus = c.get("corpus") or {}
    for lang, s in corpus.get("languages", {}).items():
        rows.append(f"| {LANG_NAMES.get(lang, lang)} | {s['prompts']:,} | {s['prompts_with_hit']} | "
                    f"{s['prompts_with_title_only_hits']} | {s['prompts_with_template_hits']} | "
                    f"{s['titles_verbatim']['titles']} of {s['distinct_titles']} |")
    sample = (f"Sample: {corpus.get('docs_per_lang', 0):,} FineWeb-2 documents per language "
              f"(revision `{str(corpus.get('revision', ''))[:8]}`, seed {corpus.get('seed')}).") if corpus else ""
    return (f"Apertus robots.txt opt-out lists: {lists}.\n\n" + "\n".join(rows) + f"\n\n{sample} "
            "Details in `docs/CONTAMINATION.md`.\n")


def replay(results: Results) -> str:
    rep = results.get("replay")
    if not rep:
        return ("_Local replay against the official `swiss-ai/Apertus-v1.5-8B` weights has not run: the checkpoint "
                "is gated and needs a Hugging Face token. See docs/DECISIONS.md._\n")
    return (f"Local official checkpoint `{rep['model']}` vs hosted R2 on {rep['n']} F1 items: parsed outcome "
            f"agreement {pct(rep['label_agreement'])}, exact text agreement {pct(rep['exact_agreement'])}.\n")


def language_table(results: Results) -> str:
    rows = ["| Model | Language | Says accepted | Gold accepted | Accuracy | Abstained |",
            "|---|---|--:|--:|--:|--:|"]
    agree = []
    for run in _runs(results):
        bias = results["results"][run]["language_bias"]
        for lang, b in bias["by_lang"].items():
            rows.append(f"| {results['runs'][run]['label']} | {LANG_NAMES[lang]} | {pct(b['says_accepted'])} | "
                        f"{pct(b['gold_accepted'])} | {pct(b['accuracy'])} (n={b['n']}) | {pct(b['abstained'])} |")
        agree.append(f"{results['runs'][run]['label']}: {bias['all_four_agree']} of "
                     f"{bias['votes_all_four_answered']} ({pct(bias['all_four_agree_share'])})")
    return ("\n".join(rows) + "\n\nVotes where German, French, Italian and English give the same answer: "
            + "; ".join(agree) + ".\n")


def order_swap_table(results: Results) -> str:
    swap = results.get("robustness", {}).get("order_swap")
    if not swap:
        return "_Option-order test (E2) not run yet._\n"
    rows = [f"Same F1 items, options reversed (\"rejected or accepted\"), `{swap['model']}`, compared with "
            f"{swap['compared_with']}:", "",
            "| Language | n | Says accepted, original order | Says accepted, reversed | Shift (pts) | Answer changed |",
            "|---|--:|--:|--:|--:|--:|"]
    for lang, b in swap["by_lang"].items():
        rows.append(f"| {LANG_NAMES[lang]} | {b['n']} | {pct(b['says_accepted_original_order'])} | "
                    f"{pct(b['says_accepted_swapped_order'])} | {num(b['shift_points'])} | "
                    f"{pct(b['answer_changed'])} |")
    return "\n".join(rows) + "\n"


BLOCKS: dict[str, Callable[[Results], str]] = {
    "headline": headline,
    "claims": claims,
    "f1_table": f1_table,
    "family_table": family_table,
    "within_instrument": within_instrument,
    "secondary_table": secondary_table,
    "runs_table": runs_table,
    "dataset_stats": dataset_stats,
    "human_table": human_table,
    "judge_table": judge_table,
    "contamination": contamination,
    "replay": replay,
    "language_table": language_table,
    "order_swap_table": order_swap_table,
    "judge_versions_table": judge_versions_table,
    "thinking_table": thinking_table,
    "deployer_text": deployer_text,
    "r4_table": r4_table,
    "route_identity_text": route_identity_text,
    "claim_status": claim_status,
    "flip_rate": flip_rate,
}


def sync_text(text: str, results: Results) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in BLOCKS:
            raise KeyError(f"unknown scrutineer block {name!r}")
        return f"{match.group(1)}{BLOCKS[name](results)}{match.group(4)}"

    return MARKER.sub(replace, text)


def sync_file(path: Path, results: Results) -> bool:
    """Rewrite the generated blocks in `path`. Returns True if the file changed."""
    original = path.read_text(encoding="utf-8")
    updated = sync_text(original, results)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False
