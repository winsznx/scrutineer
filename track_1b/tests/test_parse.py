from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scrutineer.grade.parse import parse_label, parse_percentage, strip_reasoning

FIXTURES = yaml.safe_load((Path(__file__).parent / "fixtures" / "parse_fixtures.yaml").read_text())
CASES = [
    pytest.param(lang, family, response, expected, id=f"{lang}-{i:02d}")
    for lang, rows in FIXTURES.items()
    for i, (family, response, expected) in enumerate(rows)
]


def test_thirty_fixtures_per_language() -> None:
    assert {lang: len(rows) for lang, rows in FIXTURES.items()} == {
        "de": 30, "fr": 30, "it": 30, "en": 30, "rm": 30,
    }


@pytest.mark.parametrize(("lang", "family", "response", "expected"), CASES)
def test_fixture(lang: str, family: str, response: str, expected: str | float) -> None:
    if family == "F2":
        result = parse_percentage(response, lang)
        assert result.label == "number"
        assert result.value == pytest.approx(expected)
    else:
        assert parse_label(response, lang, family) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ich weiss es nicht.", "abstain"),
        ("vom 01.04.1990, kein Wert", "unparseable"),
        ("Im Jahr 2024 waren es 58", "number"),
    ],
)
def test_percentage_edge_cases(text: str, expected: str) -> None:
    assert parse_percentage(text, "de").label == expected


def test_percentage_ignores_dates_and_years() -> None:
    result = parse_percentage("Am 01.04.1990 sagten 28,5 % Ja.", "de")
    assert result.value == pytest.approx(28.5)


def test_reasoning_block_is_ignored() -> None:
    text = "<think>Vielleicht angenommen? Nein, ich erinnere mich.</think>Abgelehnt."
    assert strip_reasoning(text).strip() == "Abgelehnt."
    assert parse_label(text, "de", "F1") == "rejected"


def test_unterminated_reasoning_prefix_is_ignored() -> None:
    assert parse_label("thinking about accepted ...</think> Rejected.", "en", "F1") == "rejected"
