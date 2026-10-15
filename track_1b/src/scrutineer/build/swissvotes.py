"""Load the pinned Swissvotes CSV and derive the vote universe with strata labels."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path

UNIVERSE_START = date(1990, 1, 1)
UNIVERSE_END = date(2026, 9, 27)
POST_CUTOFF_DATE = date(2026, 11, 29)

INSTRUMENTS = {
    "1": "referendum_obligatory",
    "2": "referendum_optional",
    "3": "initiative",
    "4": "counterproposal",
}
FC_POSITIONS = {"1": "accept", "2": "reject"}


@dataclass(frozen=True)
class Vote:
    anr: str
    vote_date: date
    instrument: str
    fc_position: str | None
    parliament_position: str | None
    accepted: bool | None
    yes_share: float | None
    cantons_yes: float | None
    cantons_no: float | None
    popular_majority: bool | None
    cantonal_majority: bool | None
    title_short_de: str
    title_short_fr: str
    title_short_en: str
    title_official_de: str
    title_official_fr: str
    chancellery_url_de: str
    chancellery_url_fr: str
    swissvotes_url: str
    row_sha256: str

    @property
    def decided(self) -> bool:
        return self.accepted is not None

    @property
    def gov_lost(self) -> bool | None:
        if self.accepted is None or self.fc_position is None:
            return None
        return (self.fc_position == "accept") != self.accepted

    @property
    def era(self) -> str:
        return f"{self.vote_date.year // 10 * 10}s"

    @property
    def margin_bucket(self) -> str | None:
        if self.yes_share is None:
            return None
        distance = abs(self.yes_share - 50.0)
        if distance <= 5.0:
            return "within_5"
        if distance <= 15.0:
            return "5_to_15"
        return "over_15"

    @property
    def double_majority_split(self) -> bool:
        if self.popular_majority is None or self.cantonal_majority is None:
            return False
        return self.popular_majority != self.cantonal_majority

    @property
    def requires_cantons(self) -> bool:
        return self.instrument in {"referendum_obligatory", "initiative", "counterproposal"}

    @property
    def vote_number(self) -> int:
        return int(self.anr.split(".")[0])


def _float_or_none(raw: str) -> float | None:
    raw = raw.strip()
    if raw in {"", "."}:
        return None
    return float(raw)


def _bool_or_none(raw: str, true: str = "1", false: str = "0") -> bool | None:
    raw = raw.strip()
    if raw == true:
        return True
    if raw == false:
        return False
    return None


def _parse_row(row: dict[str, str], raw_line: bytes) -> Vote | None:
    instrument = INSTRUMENTS.get(row["rechtsform"])
    if instrument is None:
        return None
    day, month, year = (int(part) for part in row["datum"].split("."))
    return Vote(
        anr=row["anr"],
        vote_date=date(year, month, day),
        instrument=instrument,
        fc_position=FC_POSITIONS.get(row["br-pos"]),
        parliament_position=FC_POSITIONS.get(row["bv-pos"]),
        accepted=_bool_or_none(row["annahme"]),
        yes_share=_float_or_none(row["volkja-proz"]),
        cantons_yes=_float_or_none(row["kt-ja"]),
        cantons_no=_float_or_none(row["kt-nein"]),
        popular_majority=_bool_or_none(row["volk"]),
        cantonal_majority=_bool_or_none(row["stand"]),
        title_short_de=row["titel_kurz_d"].strip(),
        title_short_fr=row["titel_kurz_f"].strip(),
        title_short_en=row["titel_kurz_e"].strip(),
        title_official_de=row["titel_off_d"].strip(),
        title_official_fr=row["titel_off_f"].strip(),
        chancellery_url_de=row["bkchrono-de"].strip(),
        chancellery_url_fr=row["bkchrono-fr"].strip(),
        swissvotes_url=row["swissvoteslink"].strip(),
        row_sha256=hashlib.sha256(raw_line).hexdigest(),
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_votes(path: Path) -> list[Vote]:
    """Parse every vote row. Each row hash covers the exact source bytes of that CSV line."""
    raw = path.read_bytes()
    lines = raw.removeprefix(b"\xef\xbb\xbf").split(b"\r\n")
    lines = [line for line in lines if line]
    header, body = lines[0], lines[1:]
    votes: list[Vote] = []
    for raw_line in body:
        text = (header + b"\n" + raw_line).decode("utf-8")
        row = next(csv.DictReader(io.StringIO(text), delimiter=";"))
        vote = _parse_row(row, raw_line)
        if vote is not None:
            votes.append(vote)
    return votes


def in_universe(vote: Vote) -> bool:
    return (
        UNIVERSE_START <= vote.vote_date <= UNIVERSE_END
        and vote.accepted is not None
        and vote.fc_position is not None
    )


def is_post_cutoff(vote: Vote) -> bool:
    return vote.vote_date == POST_CUTOFF_DATE and vote.accepted is None


def select(votes: list[Vote]) -> tuple[list[Vote], list[Vote]]:
    """Return (decided universe, post-cutoff controls), both ordered by vote number."""
    universe = sorted((v for v in votes if in_universe(v)), key=_sort_key)
    post_cutoff = sorted((v for v in votes if is_post_cutoff(v)), key=_sort_key)
    return universe, post_cutoff


def _sort_key(vote: Vote) -> tuple[int, str]:
    return vote.vote_number, vote.anr
