"""Fetch official vote titles from the Federal Chancellery's linked-data store (LINDAS).

The Chancellery's vote pages (bk.admin.ch/<lang>/details-...?voteNumber=N) are rendered
client-side from this exact SPARQL cube, so querying it returns the same titles the
pages display, in all five official languages. Titles are stored verbatim, typos
included. Nothing is ever translated.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

SPARQL_ENDPOINT = "https://cached.lindas.admin.ch/query"
POPULAR_VOTE_CUBE = "https://politics.ld.admin.ch/political-rights/popular-vote/1"
LANGS = ("de", "fr", "it", "en", "rm")
USER_AGENT = "scrutineer/1.0 (+https://github.com/winsznx/scrutineer)"

TITLE_QUERY = """
PREFIX schema: <http://schema.org/>
PREFIX vote: <https://politics.ld.admin.ch/political-rights/popular-vote/>
SELECT DISTINCT ?nr ?id ?t ?title ?lang WHERE {
  <https://politics.ld.admin.ch/political-rights/popular-vote/1> <https://cube.link/observationSet> ?obsSet .
  ?obsSet <https://cube.link/observation> ?obs .
  ?obs vote:abstimmungsNummerBk ?nr .
  ?obs vote:id ?id .
  ?obs vote:abstimmungstitel ?t .
  ?t schema:name ?title .
  BIND(LANG(?title) AS ?lang)
  FILTER(?nr >= %(min_nr)d)
}
"""


@dataclass(frozen=True)
class TitleRecord:
    vote_number: int
    lindas_id: int
    lang: str
    title: str
    source_url: str
    title_iri: str
    fetched_at: str


def lindas_id_for(anr: str) -> int:
    """Map a Swissvotes anr ("359", "465.1") to the LINDAS observation id (3590, 4651)."""
    number, _, sub = anr.partition(".")
    return int(number) * 10 + (int(sub) if sub else 0)


def fetch_titles(min_vote_number: int, client: httpx.Client | None = None) -> list[TitleRecord]:
    owns_client = client is None
    http = client or httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT})
    try:
        response = http.post(
            f"{SPARQL_ENDPOINT}/{POPULAR_VOTE_CUBE}",
            content=TITLE_QUERY % {"min_nr": min_vote_number},
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        response.raise_for_status()
        bindings = response.json()["results"]["bindings"]
    finally:
        if owns_client:
            http.close()

    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    records = {
        (int(b["id"]["value"]), b["lang"]["value"]): TitleRecord(
            vote_number=int(b["nr"]["value"]),
            lindas_id=int(b["id"]["value"]),
            lang=b["lang"]["value"],
            title=b["title"]["value"].strip(),
            source_url=f"{SPARQL_ENDPOINT}/{POPULAR_VOTE_CUBE}",
            title_iri=b["t"]["value"],
            fetched_at=fetched_at,
        )
        for b in bindings
        if b["lang"]["value"] in LANGS
    }
    return sorted(records.values(), key=lambda r: (r.lindas_id, LANGS.index(r.lang)))


def write_titles(records: Iterable[TitleRecord], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_titles(path: Path) -> dict[tuple[int, str], TitleRecord]:
    """Index stored titles by (lindas_id, lang). Empty titles count as missing."""
    index: dict[tuple[int, str], TitleRecord] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = TitleRecord(**json.loads(line))
            if record.title:
                index[(record.lindas_id, record.lang)] = record
    return index
