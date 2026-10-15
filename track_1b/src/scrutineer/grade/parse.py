"""Deterministic response parsers for families F1 to F7.

`parse_polarity` maps free text to positive / negative / abstain / unparseable.
Family-specific meaning is applied by `parse_label`: for F1, F5 and F7 positive means
"accepted", for F3 "the Federal Council recommended acceptance", for F4 and F6 "yes".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from scrutineer.grade.lexicon import (
    ABSTAIN,
    ABSTAIN_PATTERNS,
    DISJUNCTIONS,
    NEGATIVE,
    NEGATORS,
    NO,
    PERCENT_WORDS,
    POSITIVE,
    YES,
)

PARSER_VERSION = "1.0.0"
NEGATION_WINDOW = 3
LEADING_ANSWER_TOKENS = 4

APERTUS_THINK_OPEN = "<|inner_prefix|>"
APERTUS_THINK_CLOSE = "<|inner_suffix|>"
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_OPEN_THINK = re.compile(r"^.*</think>", re.DOTALL | re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NUMBER = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d+)?)(?![\d])(?!\.\d)")
_SENTENCE_END = re.compile(r"[.!?;\n]")


class Polarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ABSTAIN = "abstain"
    UNPARSEABLE = "unparseable"


YES_NO_FAMILIES = frozenset({"F4", "F6"})

FAMILY_LABELS: dict[str, tuple[str, str]] = {
    "F1": ("accepted", "rejected"),
    "F3": ("accept", "reject"),
    "F4": ("yes", "no"),
    "F5": ("accepted", "rejected"),
    "F6": ("yes", "no"),
    "F7": ("accepted", "rejected"),
}


@dataclass(frozen=True)
class ParseResult:
    label: str
    value: float | None = None


def fold(text: str) -> str:
    """Lowercase and strip diacritics so lexicon lookups ignore accent variants."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("ß", "ss"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def strip_reasoning(text: str) -> str:
    """Remove thinking traces: `<think>...</think>` and Apertus' `<|inner_prefix|>...<|inner_suffix|>`.

    A trace that never closes (output cut at `max_tokens`) leaves no visible answer.
    """
    if APERTUS_THINK_OPEN in text:
        _, _, after_open = text.partition(APERTUS_THINK_OPEN)
        _, closed, answer = after_open.partition(APERTUS_THINK_CLOSE)
        return answer if closed else ""
    text = _THINK_BLOCK.sub(" ", text)
    if "</think>" in text.lower():
        text = _OPEN_THINK.sub(" ", text)
    return text


def _normalise(text: str) -> str:
    text = strip_reasoning(text)
    text = text.replace("’", "'").replace("`", "'").replace("ʼ", "'")
    text = re.sub(r"n't\b", " not", text, flags=re.IGNORECASE)
    text = text.replace("*", " ").replace("_", " ")
    return fold(text)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.replace("'", " "))


def _phrase_positions(tokens: list[str], phrase: str) -> list[int]:
    parts = _tokens(fold(phrase))
    width = len(parts)
    return [i for i in range(len(tokens) - width + 1) if tokens[i : i + width] == parts]


def _contains_phrase(tokens: list[str], phrases: tuple[str, ...]) -> bool:
    return any(_phrase_positions(tokens, phrase) for phrase in phrases)


def _abstains(tokens: list[str], lang: str) -> bool:
    if _contains_phrase(tokens, ABSTAIN[lang]):
        return True
    joined = " ".join(tokens)
    return any(re.search(pattern, joined) for pattern in ABSTAIN_PATTERNS[lang])


def _polarity_hits(tokens: list[str], lang: str) -> list[tuple[int, int, Polarity]]:
    """Return (start, end, polarity) for every lexicon hit, before negation is applied."""
    hits: list[tuple[int, int, Polarity]] = []
    for words, polarity in ((POSITIVE[lang], Polarity.POSITIVE), (NEGATIVE[lang], Polarity.NEGATIVE)):
        for word in words:
            width = len(_tokens(fold(word)))
            hits.extend((pos, pos + width, polarity) for pos in _phrase_positions(tokens, word))
    return sorted(set(hits))


def _drop_disjunctions(
    hits: list[tuple[int, int, Polarity]], tokens: list[str], lang: str
) -> list[tuple[int, int, Polarity]]:
    """Remove "accepted or rejected" style pairs, which restate the question."""
    joiners = {fold(word) for word in DISJUNCTIONS[lang]}
    dropped: set[int] = set()
    for i in range(len(hits) - 1):
        _, end, first = hits[i]
        start, _, second = hits[i + 1]
        if first != second and start - end == 1 and tokens[end] in joiners:
            dropped.update({i, i + 1})
    return [hit for i, hit in enumerate(hits) if i not in dropped]


def _negated(tokens: list[str], start: int, lang: str) -> bool:
    negators = {fold(word) for word in NEGATORS[lang]}
    window = tokens[max(0, start - NEGATION_WINDOW) : start]
    return sum(token in negators for token in window) % 2 == 1


def _flip(polarity: Polarity) -> Polarity:
    return Polarity.NEGATIVE if polarity is Polarity.POSITIVE else Polarity.POSITIVE


def _leading_particle(tokens: list[str], lang: str) -> Polarity | None:
    if not tokens:
        return None
    first = tokens[0]
    if first in {fold(word) for word in YES[lang]}:
        return Polarity.POSITIVE
    if first in {fold(word) for word in NO[lang]}:
        return Polarity.NEGATIVE
    return None


def parse_polarity(response: str, lang: str, *, yes_no_question: bool = False) -> Polarity:
    """Classify a response. For yes/no questions a leading yes/no particle decides;
    otherwise explicit outcome words win and a particle is only the fallback."""
    text = _normalise(response)
    tokens = _tokens(text)
    if not tokens:
        return Polarity.UNPARSEABLE

    first_sentence_end = _SENTENCE_END.search(text)
    first_sentence = _tokens(text[: first_sentence_end.start()] if first_sentence_end else text)
    if _abstains(first_sentence, lang) and not _polarity_hits(first_sentence, lang):
        return Polarity.ABSTAIN

    particle = _leading_particle(tokens, lang)
    if yes_no_question and particle is not None:
        return particle

    hits = _drop_disjunctions(_polarity_hits(tokens, lang), tokens, lang)
    resolved = [
        (start, _flip(polarity) if _negated(tokens, start, lang) else polarity)
        for start, _, polarity in hits
    ]
    if resolved:
        if len({polarity for _, polarity in resolved}) == 1:
            return resolved[0][1]
        opening = {polarity for start, polarity in resolved if start < len(first_sentence)}
        if len(opening) == 1 and resolved[0][0] < LEADING_ANSWER_TOKENS:
            return opening.pop()
        return Polarity.UNPARSEABLE

    if particle is not None:
        return particle
    if _abstains(tokens, lang):
        return Polarity.ABSTAIN
    return Polarity.UNPARSEABLE


def parse_label(response: str, lang: str, family: str) -> str:
    """Map a response to a family label, "abstain" or "unparseable"."""
    positive, negative = FAMILY_LABELS[family]
    polarity = parse_polarity(response, lang, yes_no_question=family in YES_NO_FAMILIES)
    if polarity is Polarity.POSITIVE:
        return positive
    if polarity is Polarity.NEGATIVE:
        return negative
    return polarity.value


def parse_percentage(response: str, lang: str) -> ParseResult:
    """Extract the first plausible yes-share from an F2 answer.

    Prefers a number directly followed by a percent sign or word. Accepts comma or
    point decimals. Years and dates are skipped because the pattern caps the integer
    part at three digits and refuses numbers followed by another `.digit` group.
    """
    text = _normalise(response)
    percent_words = tuple(fold(word) for word in PERCENT_WORDS[lang])
    candidates: list[tuple[bool, float]] = []
    for match in _NUMBER.finditer(text):
        value = float(match.group(1).replace(",", "."))
        if not 0.0 <= value <= 100.0:
            continue
        tail = text[match.end() : match.end() + 14].lstrip()
        marked = tail.startswith("%") or tail.startswith(percent_words)
        candidates.append((marked, value))
    marked_values = [value for marked, value in candidates if marked]
    if marked_values:
        return ParseResult("number", marked_values[0])
    if candidates:
        return ParseResult("number", candidates[0][1])
    if _abstains(_tokens(text), lang):
        return ParseResult("abstain")
    return ParseResult("unparseable")
