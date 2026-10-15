"""Inline SVG charts for the landing page.

Horizontal coordinates are percentages of the chart width and text sizes come from CSS, so a
chart reflows to any column width without scaling its labels. Colours are CSS classes, so dark
mode needs no second drawing. Each chart ships with a data table for screen readers.
"""

from __future__ import annotations

from typing import Any

from scrutineer.site.common import LANG_NAMES, LANGS, NA, count, dig, esc, f1_cell, number, pct, run_label

PLOT = 75.0
BAR = 12
LABEL = 18
GAP = 12
STRATA = (("0", "Government won", "bar-won"), ("1", "Government lost", "bar-lost"))


def _x(fraction: float, width: float = PLOT) -> str:
    return f"{max(0.0, min(1.0, fraction)) * width:.3f}%"


def _svg(chart_id: str, title: str, desc: str, height: int, body: list[str]) -> str:
    return (
        f'<svg class="chart" width="100%" height="{height}" role="img" '
        f'aria-labelledby="{chart_id}-title {chart_id}-desc">'
        f'<title id="{chart_id}-title">{esc(title)}</title><desc id="{chart_id}-desc">{esc(desc)}</desc>'
        + "".join(body) + "</svg>"
    )


def _table(caption: str, head: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    th = "".join(f'<th scope="col">{esc(h)}</th>' for h in head)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
    return (f'<details class="chart-table"><summary>Show the numbers</summary><table class="data">'
            f"<caption>{esc(caption)}</caption><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></details>")


def _gridlines(top: int, bottom: int) -> list[str]:
    parts = []
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        label = f"{tick * 100:.0f}" + ("%" if tick == 1.0 else "")
        anchor = "start" if tick == 0.0 else "middle"
        parts.append(f'<line class="grid" x1="{_x(tick)}" x2="{_x(tick)}" y1="{top}" y2="{bottom}"/>')
        parts.append(f'<text class="tick" x="{_x(tick)}" y="{bottom + 16}" text-anchor="{anchor}">{label}</text>')
    return parts


def _accuracy_bar(y: int, label: str, cell: dict[str, Any] | None, css: str) -> list[str]:
    acc = number(cell.get("accuracy")) if cell else None
    n = cell.get("n") if cell else None
    parts = [f'<text class="label" x="0" y="{y + 12}">{esc(label)}{esc(f", n={count(n)}" if acc is not None else "")}'
             "</text>"]
    top = y + LABEL
    if acc is None:
        parts.append(f'<text class="value" x="0" y="{top + 10}">{NA}</text>')
        return parts
    ci = cell.get("accuracy_ci95") if cell else None
    lo, hi = (number(ci[0]), number(ci[1])) if isinstance(ci, list) and len(ci) == 2 else (None, None)
    lo, hi = (acc if lo is None else lo), (acc if hi is None else hi)
    mid = top + BAR / 2
    tip = f"{label}: {pct(acc)} correct, 95% CI {pct(lo)} to {pct(hi)}, n={count(n)}"
    parts += [
        f'<rect class="{css}" x="0" y="{top}" width="{_x(acc)}" height="{BAR}"><title>{esc(tip)}</title></rect>',
        f'<line class="ci" x1="{_x(lo)}" x2="{_x(hi)}" y1="{mid}" y2="{mid}"/>',
        f'<line class="ci" x1="{_x(lo)}" x2="{_x(lo)}" y1="{top + 2}" y2="{top + BAR - 2}"/>',
        f'<line class="ci" x1="{_x(hi)}" x2="{_x(hi)}" y1="{top + 2}" y2="{top + BAR - 2}"/>',
        f'<text class="value" x="{_x(hi)}" dx="6" y="{top + 10}">{pct(acc, 0)}</text>',
    ]
    return parts


def gov_lost_chart(results: dict[str, Any], runs: list[str]) -> str:
    """F1 accuracy on government-won versus government-lost votes, one pair of bars per run."""
    body: list[str] = []
    rows: list[tuple[str, ...]] = []
    y = 0
    for run in runs:
        body.append(f'<text class="group" x="0" y="{y + 14}">{esc(run_label(results, run))}</text>')
        y += 22
        for value, label, css in STRATA:
            cell = f1_cell(results, run, "core", "gov_lost", value)
            body += _accuracy_bar(y, label, cell, css)
            y += LABEL + BAR + GAP
            ci = cell.get("accuracy_ci95") if cell else None
            lo, hi = (ci[0], ci[1]) if isinstance(ci, list) and len(ci) == 2 else (None, None)
            rows.append((run_label(results, run), label, pct(cell.get("accuracy") if cell else None),
                         f"{pct(lo)} to {pct(hi)}", count(cell.get("n") if cell else None)))
        y += 6
    plot_bottom = max(y, 1)
    chart = _svg(
        "gov-chart",
        "F1 accuracy when the government won and when it lost",
        "Share of correct answers to 'was this vote accepted or rejected', German, French, Italian and English "
        "pooled, with 95% Wilson confidence intervals.",
        plot_bottom + 22,
        _gridlines(0, plot_bottom) + body,
    )
    table = _table("F1 accuracy by government result", ("Run", "Votes", "Accuracy", "95% CI", "Answers"), rows)
    return chart + table


def directional_chart(results: dict[str, Any], run: str) -> str:
    """Wrong F1 answers per language, split by whether they match the Federal Council's recommendation."""
    data = dig(results, "results", run, "directional_by_lang") or {}
    totals = {lang: (int(number(dig(data, lang, "matches_fc")) or 0), int(number(dig(data, lang, "opposes_fc")) or 0))
              for lang in LANGS}
    widest = max((m + o for m, o in totals.values()), default=0) or 1
    body: list[str] = []
    rows: list[tuple[str, ...]] = []
    y = 0
    for lang in LANGS:
        matches, opposes = totals[lang]
        answered = number(dig(f1_cell(results, run, lang, "all", "all"), "n"))
        if not answered:
            note = "not yet run"
        elif matches + opposes == 0:
            note = "no wrong answers"
        else:
            note = f"{matches} match, {opposes} oppose"
        body.append(f'<text class="label" x="0" y="{y + 12}">{esc(LANG_NAMES[lang])}</text>')
        body.append(f'<text class="value" x="100%" y="{y + 12}" text-anchor="end">{esc(note)}</text>')
        top = y + LABEL
        if matches:
            body.append(f'<rect class="seg-match" x="0" y="{top}" width="{_x(matches / widest, 100)}" '
                        f'height="{BAR}"><title>{esc(LANG_NAMES[lang])}: {matches} match the recommendation</title>'
                        "</rect>")
        if opposes:
            body.append(f'<rect class="seg-oppose" x="{_x(matches / widest, 100)}" y="{top}" '
                        f'width="{_x(opposes / widest, 100)}" height="{BAR}"><title>{esc(LANG_NAMES[lang])}: '
                        f"{opposes} oppose the recommendation</title></rect>")
        if not matches + opposes:
            body.append(f'<line class="grid" x1="0" x2="100%" y1="{top + BAR / 2}" y2="{top + BAR / 2}"/>')
        rows.append((LANG_NAMES[lang], str(matches), str(opposes)) if answered else (LANG_NAMES[lang], NA, NA))
        y += LABEL + BAR + GAP
    chart = _svg(
        "dir-chart",
        f"Which way the wrong answers point, {run_label(results, run)}",
        "For each language, the wrong F1 answers split into those that match the Federal Council's "
        "recommendation (dark) and those that oppose it (grey).",
        max(y, 1),
        body,
    )
    table = _table("Wrong F1 answers by language", ("Language", "Match the recommendation", "Oppose it"), rows)
    return chart + table


BIAS_LANGS = ("de", "it", "fr", "en")


def language_chart(results: dict[str, Any], runs: list[str], truth_run: str) -> str:
    """Share of F1 answers saying "accepted", per language and run, with a tick at the true share."""
    body: list[str] = []
    rows: list[tuple[str, ...]] = []
    y = 0
    for lang in BIAS_LANGS:
        truth = number(dig(results, "results", truth_run, "language_bias", "by_lang", lang, "gold_accepted"))
        body.append(f'<text class="group" x="0" y="{y + 14}">{esc(LANG_NAMES[lang])}</text>')
        if truth is not None:
            body.append(f'<text class="truth-label" x="{_x(truth)}" dx="6" y="{y + 14}">true {pct(truth, 0)}</text>')
            rows.append((LANG_NAMES[lang], "True share", pct(truth), ""))
        y += 22
        for run in runs:
            entry = dig(results, "results", run, "language_bias", "by_lang", lang) or {}
            share, n = number(entry.get("says_accepted")), entry.get("n")
            label = f"{run_label(results, run)}, n={count(n)}" if share is not None else run_label(results, run)
            body.append(f'<text class="label" x="0" y="{y + 12}">{esc(label)}</text>')
            bar_top = y + LABEL
            if share is None:
                body.append(f'<text class="value" x="0" y="{bar_top + 10}">{NA}</text>')
            else:
                tip = f"{LANG_NAMES[lang]}, {run_label(results, run)}: says accepted {pct(share)} of the time"
                body += [
                    f'<rect class="bar-run" x="0" y="{bar_top}" width="{_x(share)}" height="{BAR}">'
                    f"<title>{esc(tip)}</title></rect>",
                    f'<text class="value" x="{_x(share)}" dx="6" y="{bar_top + 10}">{pct(share, 0)}</text>',
                ]
            if truth is not None:
                body.append(f'<line class="truth" x1="{_x(truth)}" x2="{_x(truth)}" y1="{bar_top - 3}" '
                            f'y2="{bar_top + BAR + 3}"/>')
            rows.append((LANG_NAMES[lang], run_label(results, run), pct(share), count(n)))
            y += LABEL + BAR + GAP
        y += 6
    chart = _svg(
        "lang-chart",
        "How often each language's answer says the vote was accepted",
        "Share of F1 answers that say accepted, per language and run. The dark tick marks the share of votes "
        "that were actually accepted.",
        max(y, 1) + 22,
        _gridlines(0, max(y, 1)) + body,
    )
    table = _table("Share of F1 answers saying accepted", ("Language", "Run", "Says accepted", "Answers"), rows)
    return chart + table
