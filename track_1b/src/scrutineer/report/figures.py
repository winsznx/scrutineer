"""The four report figures, drawn from results.json with matplotlib.

Style follows the site: near-black ink, grey for everything ordinary, Swiss red only for
the government-lost stratum. Values are labelled directly on the marks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.figure import Figure

RED = "#D52B1E"
GREY = "#8A8A8A"
INK = "#1A1A1A"
MUTED = "#6B6B6B"
RULE = "#D9D9D6"
LANG_NAMES = {"de": "German", "fr": "French", "it": "Italian", "en": "English", "rm": "Romansh"}
ERAS = ("1990s", "2000s", "2010s", "2020s")
INSTRUMENTS = {
    "initiative": "Initiative",
    "counterproposal": "Counter-proposal",
    "referendum_obligatory": "Mandatory ref.",
    "referendum_optional": "Optional ref.",
}


FONTS = Path(__file__).with_name("fonts")


def _style() -> None:
    """Register the bundled IBM Plex Sans so figures look the same on every machine."""
    for font in sorted(FONTS.glob("*.ttf")):
        font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({
        "font.family": "IBM Plex Sans",
        "font.size": 9,
        "axes.edgecolor": RULE,
        "axes.linewidth": 0.8,
        "axes.labelcolor": MUTED,
        "axes.titlesize": 10,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlecolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "figure.facecolor": "white",
    })


def _cell(results: dict[str, Any], run: str, family: str, lang: str, stratum: str, value: str) -> dict[str, Any] | None:
    for row in results["results"][run]["cells"]:
        if (row["family"], row["lang"], row["stratum"], row["value"]) == (family, lang, stratum, value):
            return dict(row)
    return None


def _runs(results: dict[str, Any]) -> list[str]:
    return [run for run in ("R1", "R2", "R3", "R4") if run in results["results"]]


def _save(fig: Figure, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_accuracy_by_gov_lost(results: dict[str, Any], out_dir: Path) -> Path:
    runs = _runs(results)
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    width = 0.36
    for i, run in enumerate(runs):
        for offset, value, colour, label in ((-width / 2, "0", GREY, "Government won"),
                                             (width / 2, "1", RED, "Government lost")):
            row = _cell(results, run, "F1", "core", "gov_lost", value)
            if not row or row["accuracy"] is None:
                continue
            acc = row["accuracy"] * 100
            lo, hi = (v * 100 for v in row["accuracy_ci95"])
            ax.bar(i + offset, acc, width * 0.9, color=colour, label=label if i == 0 else None, zorder=2)
            ax.errorbar(i + offset, acc, yerr=[[acc - lo], [hi - acc]], color=INK, lw=0.8, capsize=2, zorder=3)
            ax.text(i + offset, hi + 2, f"{acc:.0f}%", ha="center", va="bottom", color=INK, fontsize=8)
    ax.set_xticks(range(len(runs)), [results["runs"][r]["label"].replace(", ", ",\n").replace(" (", "\n(")
                                     for r in runs])
    ax.set_ylim(0, 125)
    ax.set_yticks([0, 25, 50, 75, 100], ["0", "25", "50", "75", "100%"])
    ax.yaxis.grid(True, color=RULE, lw=0.6, zorder=0)
    ax.legend(frameon=False, loc="upper left", ncols=2, fontsize=8)
    ax.set_title("F1 outcome accuracy, de/fr/it/en pooled, 95% Wilson CI")
    return _save(fig, out_dir, "fig1_accuracy_gov_lost.png")


def fig_directional(results: dict[str, Any], out_dir: Path, run: str = "R1") -> Path:
    data = results["results"][run]["directional_by_lang"]
    langs = [lang for lang in ("de", "fr", "it", "en", "rm") if sum(data.get(lang, {}).values())]
    fig, ax = plt.subplots(figsize=(6.4, 0.45 * len(langs) + 0.9))
    for y, lang in enumerate(reversed(langs)):
        matches, opposes = data[lang]["matches_fc"], data[lang]["opposes_fc"]
        ax.barh(y, matches, color=RED, height=0.55, zorder=2, edgecolor="white", linewidth=1.5)
        ax.barh(y, opposes, left=matches, color=GREY, height=0.55, zorder=2, edgecolor="white", linewidth=1.5)
        total = matches + opposes
        ax.text(total + 0.5, y, f"{matches} of {total} match the Federal Council", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(langs)), [LANG_NAMES[lang] for lang in reversed(langs)])
    ax.set_xlabel("Wrong F1 answers. Red: the answer equals the Federal Council's recommendation. Grey: it opposes it.")
    ax.xaxis.grid(True, color=RULE, lw=0.6, zorder=0)
    ax.set_xlim(0, max(sum(data[lang].values()) for lang in langs) * 1.6 if langs else 1)
    ax.set_title(f"Which way the wrong answers point, {results['runs'][run]['label']}")
    return _save(fig, out_dir, "fig2_directional_error.png")


def fig_era_instrument(results: dict[str, Any], out_dir: Path, run: str = "R1") -> Path:
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    grid = [[float("nan")] * len(ERAS) for _ in INSTRUMENTS]
    era_instrument = results["results"][run]["era_instrument"]
    for i, instrument in enumerate(INSTRUMENTS):
        for j, era in enumerate(ERAS):
            entry = era_instrument.get(f"{instrument}|{era}")
            if entry and entry["accuracy"] is not None:
                grid[i][j] = entry["accuracy"] * 100
                ax.text(j, i, f"{entry['accuracy'] * 100:.0f}%\nn={entry['n']}", ha="center", va="center",
                        fontsize=7.5, color="white" if grid[i][j] < 55 else INK)
    image = ax.imshow(grid, cmap="Greys_r", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(ERAS)), list(ERAS))
    ax.set_yticks(range(len(INSTRUMENTS)), list(INSTRUMENTS.values()))
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=7, colors=MUTED)
    ax.set_title(f"F1 accuracy by era and instrument, {results['runs'][run]['label']}")
    return _save(fig, out_dir, "fig3_era_instrument.png")


def fig_reasoning_vs_recall(results: dict[str, Any], out_dir: Path) -> Path:
    runs = _runs(results)
    fig, ax = plt.subplots(figsize=(6.4, 0.55 * len(runs) * 2 + 0.8))
    labels: list[str] = []
    y = 0
    for run in runs:
        rvr = results["results"][run]["reasoning_vs_recall"]
        for stratum, colour in (("gov_won", GREY), ("gov_lost", RED)):
            entry = rvr.get(stratum, {})
            f1, f5 = entry.get("f1_de_accuracy"), entry.get("f5_accuracy")
            if f1 is None or f5 is None:
                continue
            ax.plot([f1 * 100, f5 * 100], [y, y], color=RULE, lw=2, zorder=1)
            ax.scatter([f1 * 100], [y], s=36, color="white", edgecolors=colour, linewidths=1.6, zorder=2)
            ax.scatter([f5 * 100], [y], s=36, color=colour, zorder=3)
            ax.text(102, y, f"recall {f1 * 100:.0f}%  ·  reasoning {f5 * 100:.0f}%", va="center", fontsize=7.5,
                    color=INK)
            labels.append(f"{results['runs'][run]['label']}, gov. {'lost' if stratum == 'gov_lost' else 'won'}")
            y += 1
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 150)
    ax.set_xticks([0, 25, 50, 75, 100], ["0", "25", "50", "75", "100%"])
    ax.xaxis.grid(True, color=RULE, lw=0.6, zorder=0)
    ax.set_title("Same votes, German: recall (F1, open ring) vs reasoning from numbers (F5, dot)")
    return _save(fig, out_dir, "fig4_reasoning_vs_recall.png")


def fig_language_bias(results: dict[str, Any], out_dir: Path) -> Path:
    runs = _runs(results)
    langs = ("de", "it", "fr", "en")
    fig, ax = plt.subplots(figsize=(6.4, 2.7))
    width = 0.8 / max(len(runs), 1)
    shades = ("#1A1A1A", "#6B6B6B", "#AFAFAF", "#D0D0CE")
    for i, run in enumerate(runs):
        bias = results["results"][run]["language_bias"]["by_lang"]
        for j, lang in enumerate(langs):
            value = bias.get(lang, {}).get("says_accepted")
            if value is None:
                continue
            x = j + (i - (len(runs) - 1) / 2) * width
            label = results["runs"][run]["label"] if j == 0 else None
            ax.bar(x, value * 100, width * 0.9, color=shades[i], label=label, zorder=2)
            ax.text(x, value * 100 + 1.5, f"{value * 100:.0f}", ha="center", va="bottom", fontsize=7, color=INK)
    # The gold share comes from the run that answered the most items, i.e. the full universe once complete.
    fullest = max(runs, key=lambda run: results["results"][run]["language_bias"]["by_lang"].get("de", {}).get("n", 0))
    by_lang = results["results"][fullest]["language_bias"]["by_lang"]
    gold = [by_lang.get(lang, {}).get("gold_accepted") for lang in langs]
    for j, value in enumerate(gold):
        if value is not None:
            ax.plot([j - 0.45, j + 0.45], [value * 100] * 2, color=INK, lw=1.0, zorder=3)
    ax.text(len(langs) - 0.5, (gold[-1] or 0) * 100 + 2, "true share", color=INK, fontsize=7, ha="right")
    ax.set_xticks(range(len(langs)), [LANG_NAMES[lang] for lang in langs])
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100], ["0", "25", "50", "75", "100%"])
    ax.yaxis.grid(True, color=RULE, lw=0.6, zorder=0)
    ax.legend(frameon=False, fontsize=7.5, loc="upper right")
    ax.set_title("Share of F1 answers saying \"accepted\", by question language")
    return _save(fig, out_dir, "fig5_language_bias.png")


def render_all(results: dict[str, Any], out_dir: Path) -> list[Path]:
    _style()
    if "R1" not in results["results"]:
        return []
    return [
        fig_accuracy_by_gov_lost(results, out_dir),
        fig_directional(results, out_dir),
        fig_era_instrument(results, out_dir),
        fig_reasoning_vs_recall(results, out_dir),
        fig_language_bias(results, out_dir),
    ]
