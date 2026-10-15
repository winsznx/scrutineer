from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from scrutineer.grade.results import run_ids
from scrutineer.paths import Paths
from scrutineer.site.generate import build_site

ROOT = Path(__file__).resolve().parents[1]
REAL_DATA = ROOT / "data"
VOTE_KEYS = {"a", "d", "t", "g", "i", "e", "m", "s", "pc", "o", "f", "y", "cy", "cn", "ic", "u", "k", "v"}
BANNED = ("\u2014", "!", "robust", "seamless", "groundbreaking", "delve", "crucial", "pivotal")
HEADLINE_SPAN = re.compile(r'<span data-headline="(?P<key>[a-z_]+)">(?P<text>[^<]*)</span>')
RESULT_SPAN = re.compile(r'<span data-result="(?P<path>[A-Za-z0-9_.]+)">(?P<text>[^<]*)</span>')


VOID_TAGS = frozenset({"meta", "link", "br", "img", "input", "hr", "source", "wbr"})


class _Checker(HTMLParser):
    """Fails on unbalanced tags, which is what a broken template usually produces."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pass

    def handle_endtag(self, tag: str) -> None:
        assert self.stack and self.stack[-1] == tag, f"unexpected </{tag}>, open: {self.stack[-3:]}"
        self.stack.pop()


def _assert_well_formed(html: str) -> None:
    checker = _Checker()
    checker.feed(html)
    checker.close()
    assert checker.stack == []


@pytest.fixture(scope="module")
def real_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not (REAL_DATA / "results.json").exists() or not (REAL_DATA / "items.jsonl").exists():
        pytest.skip("benchmark data not present")
    root = tmp_path_factory.mktemp("site-root")
    (root / "data").symlink_to(REAL_DATA, target_is_directory=True)
    return build_site(Paths(root))


def test_outputs_exist(real_site: Path) -> None:
    for name in ("index.html", "explorer.html", "style.css", "explorer.js", "data/votes.json", ".nojekyll"):
        assert (real_site / name).exists(), name


def test_headline_numbers_match_results(real_site: Path) -> None:
    head = json.loads((REAL_DATA / "results.json").read_text())["results"]["R1"]["headline"]
    spans = {m["key"]: m["text"] for m in HEADLINE_SPAN.finditer((real_site / "index.html").read_text())}
    assert {"gap_points", "accuracy_gov_won", "accuracy_gov_lost", "n_gov_won", "n_gov_lost"} <= spans.keys()
    for key, text in spans.items():
        expected = head[key]
        if expected is None:
            assert text == "n/a"
            continue
        shown = float(text.rstrip("%").replace(",", ""))
        if text.endswith("%"):
            assert shown == pytest.approx(expected * 100, abs=0.05), key
        elif key == "gap_points":
            assert shown == pytest.approx(abs(expected), abs=0.05), key
        else:
            decimals = len(text.partition(".")[2])
            assert shown == pytest.approx(expected, abs=0.5 * 10 ** -decimals), key


def _shown_matches(text: str, expected: float | None) -> bool:
    if expected is None:
        return text == "n/a"
    shown = float(text.rstrip("%").replace(",", ""))
    if text.endswith("%"):
        return bool(shown == pytest.approx(expected * 100, abs=0.05))
    decimals = len(text.partition(".")[2])
    return bool(shown == pytest.approx(expected, abs=0.5 * 10 ** -decimals))


def test_language_section_numbers_match_results(real_site: Path) -> None:
    results = json.loads((REAL_DATA / "results.json").read_text())
    html = (real_site / "index.html").read_text()
    assert "The answer depends on the language you ask in" in html
    section = html.partition('id="languages"')[2].partition("</section>")[0]
    spans = list(RESULT_SPAN.finditer(section))
    runs_with_bias = [run for run, body in results["results"].items() if body.get("language_bias")]
    if not runs_with_bias:
        pytest.skip("no language_bias in results.json yet")
    assert any(m["path"].endswith(".says_accepted") for m in spans)
    assert any(m["path"].endswith(".gold_accepted") for m in spans)
    assert sum(m["path"].endswith(".all_four_agree") for m in spans) == len(runs_with_bias)
    for match in spans:
        value: Any = results
        for key in match["path"].split("."):
            value = value[key]
        assert _shown_matches(match["text"], value), (match["path"], match["text"], value)
    claim_run = "R1" if "R1" in runs_with_bias else runs_with_bias[0]
    assert f"results.{claim_run}.language_bias.by_lang.de.gold_accepted" in section
    assert 'class="truth"' in section and "bar-lost" not in section


def test_one_vote_entry_per_vote(real_site: Path) -> None:
    items = [json.loads(line) for line in (REAL_DATA / "items.jsonl").read_text().splitlines() if line]
    expected = {i["anr"] for i in items if i["family"] in {"F1", "F7"}}
    payload = json.loads((real_site / "data" / "votes.json").read_text())
    anrs = [vote["a"] for vote in payload["votes"]]
    assert len(anrs) == len(set(anrs))
    assert set(anrs) == expected
    for vote in payload["votes"]:
        assert vote.keys() >= VOTE_KEYS
        assert ("r" in vote) != payload["split"]
    assert [run["id"] for run in payload["runs"]] == run_ids(Paths(REAL_DATA.parent))


def test_pages_are_static_and_clean(real_site: Path) -> None:
    for name in ("index.html", "explorer.html"):
        html = (real_site / name).read_text()
        assert "<script src=\"http" not in html and "<script src='http" not in html
        _assert_well_formed(html)
        text = re.sub(r"<[^>]+>", " ", html).lower()
        for word in BANNED:
            assert word not in text, (name, word)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _item(anr: str, family: str, gold: dict[str, Any], gov_lost: int | None, title: str) -> dict[str, Any]:
    return {
        "item_id": f"{anr}-{family}-de", "anr": anr, "family": family, "lang": "de", "vote_date": "2024-03-03",
        "title": title, "title_source": "chancellery_lindas", "gold": gold,
        "gold_source_url": f"https://swissvotes.ch/vote/{anr}.00", "gold_source_urls": [],
        "strata": {"gov_lost": gov_lost, "instrument": "initiative", "era": "2020s", "margin_bucket": None,
                   "double_majority_split": 0, "lang": "de"},
    }


def test_partial_data_renders_without_crashing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_jsonl(data / "items.jsonl", [
        _item("665", "F1", {"outcome": "accepted"}, 1, "Volksinitiative für eine 13. AHV-Rente"),
        _item("690", "F7", {"outcome": "not_decided"}, None, "Bundesbeschluss über die Finanzierung der 13. AHV-Rente"),
    ])
    by_lang = {"de": {"n": 1, "says_accepted": 1.0, "gold_accepted": 1.0}, "fr": {"n": 1, "says_accepted": None}}
    bias = {"by_lang": by_lang, "all_four_agree": None, "votes_all_four_answered": 0}
    results = {"results": {"R1": {"headline": {"gap_points": None}, "language_bias": bias}}, "robustness": None}
    (data / "results.json").write_text(json.dumps(results))
    (data / "responses").mkdir()
    (data / "responses" / "R1.meta.json").write_text("{}")
    (data / "responses" / "smoke1.meta.json").write_text("{}")
    _write_jsonl(data / "responses" / "R1.jsonl", [{"item_id": "665-F1-de", "status": "ok", "response": "Ja"}])
    with (data / "responses" / "R1.jsonl").open("a") as handle:
        handle.write('{"item_id": "690-F7')

    site = build_site(Paths(tmp_path))

    index = (site / "index.html").read_text()
    assert '<span data-headline="gap_points">n/a</span>' in index
    assert "accepted on 3 March 2024" in index
    assert "Not yet run." not in index and "is still running" in index
    _assert_well_formed(index)
    _assert_well_formed((site / "explorer.html").read_text())
    payload = json.loads((site / "data" / "votes.json").read_text())
    assert [run["id"] for run in payload["runs"]] == ["R1"]
    votes = {vote["a"]: vote for vote in payload["votes"]}
    assert votes["665"]["r"]["R1"]["F1"]["de"][5] == "ungraded"
    assert votes["690"]["pc"] == 1 and votes["690"]["g"] is None


def test_large_payload_splits_per_vote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scrutineer.site.votes.SPLIT_BYTES", 0)
    data = tmp_path / "data"
    _write_jsonl(data / "items.jsonl", [_item("465.1", "F1", {"outcome": "rejected"}, 0, "Bundesgesetz")])
    (data / "responses").mkdir()
    (data / "responses" / "R1.meta.json").write_text("{}")
    _write_jsonl(data / "responses" / "R1.jsonl", [{"item_id": "465.1-F1-de", "status": "ok", "response": "Nein"}])

    site = build_site(Paths(tmp_path))

    payload = json.loads((site / "data" / "votes.json").read_text())
    assert payload["split"] is True and "r" not in payload["votes"][0]
    detail = json.loads((site / "data" / "votes" / "465.1.json").read_text())
    assert detail["r"]["R1"]["F1"]["de"][0] == "Nein"
