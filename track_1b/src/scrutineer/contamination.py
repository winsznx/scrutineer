"""Contamination check against the web data behind Apertus.

Two separate questions:

1. Did the sites our gold answers cite opt out of AI crawling? Apertus dropped every
   domain whose robots.txt blocked AI crawlers and published those domain lists. We look
   our source hosts up in the lists and, where the stored robots.txt exists, evaluate it
   for the vote pages we cite.
2. Does our prompt wording occur in the multilingual web text? We scan a seeded sample of
   FineWeb-2 (German, French, Italian) for 13-grams of our prompts and for verbatim vote
   titles. Titles are official text and are expected to occur. The template wording is
   ours and should not.

Corpus shards are read with HTTP range requests (footer plus the `text` and `url` column
chunks of the sampled row groups). Nothing from the corpus is written to disk.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from scrutineer.paths import Paths

USER_AGENT = "scrutineer/1.0 (+https://github.com/winsznx/scrutineer)"
HF = "https://huggingface.co"
NGRAM = 13
EXAMPLE_LIMIT = 20
SOURCE_URL_LIMIT = 10
RANGE_CHUNK = 8 * 1024 * 1024
RETRIES = 6

BLOCKLISTS = (
    ("swiss-ai/robots-txt-blocked-domains-english", "fw1_domains.txt"),
    ("swiss-ai/robots-txt-blocked-domains-multilingual", "fw2_domains.txt"),
)
SOURCE_HOSTS = (
    "swissvotes.ch",
    "www.swissvotes.ch",
    "bk.admin.ch",
    "www.bk.admin.ch",
    "admin.ch",
    "www.admin.ch",
    "fedlex.admin.ch",
)
ROBOTS_REPO = "swiss-ai/fineweb-robots-txt-files-compressed"
ROBOTS_FILE = "fineweb_robots_compressed.parquet"
PROBE_URLS = (
    "https://swissvotes.ch/vote/359.00",
    "https://www.bk.admin.ch/de/details-volksinitiativen?voteNumber=359",
    "https://www.admin.ch/gov/de/start/dokumentation/abstimmungen.html",
)
CRAWLER_AGENTS = ("CCBot", "GPTBot", "Google-Extended", "ClaudeBot", "*")

FINEWEB2_REPO = "HuggingFaceFW/fineweb-2"
CORPUS_CONFIGS = {"de": "deu_Latn", "fr": "fra_Latn", "it": "ita_Latn"}

Gram = tuple[str, ...]
WORD = re.compile(r"\w+")


# Text


def tokenize(text: str) -> list[str]:
    """Unicode `\\w+` tokens, lowercased after matching so spans stay aligned with `text`."""
    return [m.group().lower() for m in WORD.finditer(text)]


def ngrams(tokens: list[str], n: int = NGRAM) -> Iterator[Gram]:
    for start in range(len(tokens) - n + 1):
        yield tuple(tokens[start : start + n])


def normalise(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class PromptGrams:
    item_id: str
    title_only: frozenset[Gram]
    touching_template: frozenset[Gram]
    template_tokens: dict[Gram, int] = field(default_factory=dict, compare=False)
    """For each template-touching n-gram, how many of its tokens lie outside the title."""

    @property
    def grams(self) -> frozenset[Gram]:
        return self.title_only | self.touching_template


def prompt_grams(item_id: str, prompt: str, title: str | None, n: int = NGRAM) -> PromptGrams:
    """Split a prompt's n-grams by whether every token lies inside the vote title."""
    start = prompt.find(title) if title else -1
    stop = start + len(title) if title and start >= 0 else -1
    matches = list(WORD.finditer(prompt))
    tokens = [m.group().lower() for m in matches]
    in_title = [start >= 0 and start <= m.start() and m.end() <= stop for m in matches]
    title_only: set[Gram] = set()
    template_tokens: dict[Gram, int] = {}
    for i, gram in enumerate(ngrams(tokens, n)):
        outside = n - sum(in_title[i : i + n])
        if outside == 0:
            title_only.add(gram)
        else:
            template_tokens[gram] = min(outside, template_tokens.get(gram, n))
    for gram in title_only:
        template_tokens.pop(gram, None)
    return PromptGrams(item_id, frozenset(title_only), frozenset(template_tokens), template_tokens)


@dataclass(frozen=True)
class TitlePattern:
    title: str
    anchor: str
    verbatim: re.Pattern[str]
    token_sequence: str


def title_pattern(title: str) -> TitlePattern | None:
    """Verbatim means case-insensitive, whitespace-normalised, and bounded by non-word characters."""
    tokens = tokenize(title)
    if not tokens:
        return None
    return TitlePattern(
        title=title,
        anchor=max(tokens, key=len),
        verbatim=re.compile(rf"(?<!\w){re.escape(normalise(title))}(?!\w)"),
        token_sequence=f" {' '.join(tokens)} ",
    )


def is_source_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == base or host.endswith(f".{base}") for base in ("admin.ch", "swissvotes.ch"))


@dataclass
class TitleHits:
    docs: int = 0
    first_url: str = ""


@dataclass
class CorpusScan:
    """Single pass over a corpus sample, matching prompt n-grams and vote titles."""

    grams: frozenset[Gram]
    titles: list[TitlePattern]
    n: int = NGRAM
    docs: int = 0
    tokens: int = 0
    gram_docs: dict[Gram, int] = field(default_factory=dict)
    gram_url: dict[Gram, str] = field(default_factory=dict)
    verbatim: dict[str, TitleHits] = field(default_factory=dict)
    token_sequence: dict[str, TitleHits] = field(default_factory=dict)
    source_urls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._heads = {gram[0] for gram in self.grams}
        self._anchors: dict[str, list[TitlePattern]] = {}
        for pattern in self.titles:
            self._anchors.setdefault(pattern.anchor, []).append(pattern)

    def add(self, text: str, url: str) -> None:
        tokens = tokenize(text)
        self.docs += 1
        self.tokens += len(tokens)
        n = self.n
        hits = {
            gram
            for i in range(len(tokens) - n + 1)
            if tokens[i] in self._heads and (gram := tuple(tokens[i : i + n])) in self.grams
        }
        for gram in sorted(hits):
            self.gram_docs[gram] = self.gram_docs.get(gram, 0) + 1
            self.gram_url.setdefault(gram, url)

        anchors = sorted(self._anchors.keys() & set(tokens))
        if anchors:
            flat = normalise(text)
            joined = f" {' '.join(tokens)} "
            for anchor in anchors:
                for pattern in self._anchors[anchor]:
                    if pattern.verbatim.search(flat):
                        _record(self.verbatim, pattern.title, url)
                    if pattern.token_sequence in joined:
                        _record(self.token_sequence, pattern.title, url)

        host = urlsplit(url).hostname or ""
        if is_source_host(host):
            self.source_urls.append(url)


def _record(hits: dict[str, TitleHits], title: str, url: str) -> None:
    entry = hits.setdefault(title, TitleHits(first_url=url))
    entry.docs += 1


def summarise(prompts: list[PromptGrams], scan: CorpusScan) -> dict[str, Any]:
    found = scan.gram_docs.keys()
    title_only_prompts = template_prompts = 0
    title_hits: set[Gram] = set()
    template_hits: dict[Gram, int] = {}
    for prompt in prompts:
        in_title = prompt.title_only & found
        in_template = prompt.touching_template & found
        title_hits |= in_title
        for gram in in_template:
            template_hits[gram] = min(prompt.template_tokens[gram], template_hits.get(gram, NGRAM))
        if in_template:
            template_prompts += 1
        elif in_title:
            title_only_prompts += 1

    def ranked(grams: Iterable[Gram]) -> list[Gram]:
        return sorted(grams, key=lambda g: (-scan.gram_docs[g], g))[:EXAMPLE_LIMIT]

    def example(gram: Gram) -> dict[str, Any]:
        return {"ngram": " ".join(gram), "docs": scan.gram_docs[gram], "url": scan.gram_url[gram]}

    def title_summary(hits: dict[str, TitleHits]) -> dict[str, Any]:
        return {
            "titles": len(hits),
            "examples": [
                {"title": title, "docs": hits[title].docs, "url": hits[title].first_url}
                for title in sorted(hits, key=lambda t: (-hits[t].docs, t))[:EXAMPLE_LIMIT]
            ],
        }

    return {
        "prompts": len(prompts),
        "prompt_ngrams": len(scan.grams),
        "prompts_with_hit": title_only_prompts + template_prompts,
        "prompts_with_title_only_hits": title_only_prompts,
        "prompts_with_template_hits": template_prompts,
        "hit_ngrams_title_only": len(title_hits),
        "hit_ngrams_touching_template": len(template_hits),
        "title_only_examples": [example(g) for g in ranked(title_hits)],
        "template_examples": [{**example(g), "template_tokens": template_hits[g]} for g in ranked(template_hits)],
        "max_template_tokens_in_hit": max(template_hits.values(), default=0),
        "distinct_titles": len(scan.titles),
        "titles_verbatim": title_summary(scan.verbatim),
        "titles_token_sequence": title_summary(scan.token_sequence),
        "source_host_docs": {"docs": len(scan.source_urls), "urls": sorted(scan.source_urls)[:EXAMPLE_LIMIT]},
        "sample_docs": scan.docs,
        "sample_tokens": scan.tokens,
    }


def robots_verdicts(content: str, url: str, agents: Iterable[str] = CRAWLER_AGENTS) -> dict[str, bool]:
    """True means the robots.txt allows `agent` to fetch `url`."""
    parser = RobotFileParser()
    parser.parse(content.splitlines())
    return {agent: parser.can_fetch(agent, url) for agent in agents}


def choose_row_groups(sizes: list[int], docs: int, rng: random.Random) -> list[tuple[int, int]]:
    """Seeded row groups covering `docs` rows, as (row_group, rows_taken), in file order."""
    taken: list[tuple[int, int]] = []
    remaining = docs
    for index in rng.sample(range(len(sizes)), len(sizes)):
        if remaining <= 0:
            break
        rows = min(sizes[index], remaining)
        taken.append((index, rows))
        remaining -= rows
    return sorted(taken)


# Hugging Face access


@dataclass(frozen=True)
class RepoFile:
    path: str
    size: int
    sha256: str | None


def hf_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(60, read=180),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def resolve_url(repo: str, revision: str, path: str) -> str:
    return f"{HF}/datasets/{repo}/resolve/{revision}/{path}"


def resolve_revision(client: httpx.Client, repo: str) -> str:
    response = client.get(f"{HF}/api/datasets/{repo}")
    response.raise_for_status()
    sha: str = response.json()["sha"]
    return sha


def list_files(client: httpx.Client, repo: str, revision: str, folder: str = "") -> list[RepoFile]:
    """Files in a dataset folder. `sha256` is the LFS object id, which is the file's sha256."""
    url: str | None = f"{HF}/api/datasets/{repo}/tree/{revision}" + (f"/{folder}" if folder else "")
    files: list[RepoFile] = []
    while url:
        response = client.get(url)
        response.raise_for_status()
        for entry in response.json():
            if entry["type"] == "file":
                files.append(RepoFile(entry["path"], entry["size"], (entry.get("lfs") or {}).get("oid")))
        url = response.links.get("next", {}).get("url")
    return sorted(files, key=lambda f: f.path)


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable view of a remote file backed by HTTP range requests.

    The first request follows the Hub's redirect to the storage CDN, and later requests
    go straight to the signed CDN URL. When that URL expires the Hub URL is resolved again.
    """

    def __init__(self, client: httpx.Client, url: str, size: int) -> None:
        super().__init__()
        self._client = client
        self._url = url
        self._direct: str | None = None
        self._size = size
        self._pos = 0
        self.bytes_fetched = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = base + offset
        return self._pos

    def read(self, size: int = -1) -> bytes:
        stop = self._size if size < 0 else min(self._pos + size, self._size)
        if stop <= self._pos:
            return b""
        data = b"".join(self._fetch(s, min(s + RANGE_CHUNK, stop)) for s in range(self._pos, stop, RANGE_CHUNK))
        self._pos = stop
        return data

    def _fetch(self, start: int, stop: int) -> bytes:
        problem = ""
        for attempt in range(RETRIES):
            try:
                response = self._client.get(self._direct or self._url, headers={"Range": f"bytes={start}-{stop - 1}"})
            except httpx.TransportError as exc:
                problem = repr(exc)
            else:
                if response.status_code == 206 and len(response.content) == stop - start:
                    self._direct = str(response.url)
                    self.bytes_fetched += stop - start
                    return response.content
                problem = f"HTTP {response.status_code}, {len(response.content)} bytes"
            self._direct = None
            time.sleep(2**attempt)
        raise OSError(f"range {start}-{stop - 1} of {self._url} failed after {RETRIES} attempts: {problem}")


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# Check 1: robots.txt opt-outs


def check_blocklists(client: httpx.Client) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for repo, filename in BLOCKLISTS:
        revision = resolve_revision(client, repo)
        _log(f"downloading {repo}/{filename} at {revision}")
        response = client.get(resolve_url(repo, revision, filename))
        response.raise_for_status()
        body = response.content
        lines = body.decode("utf-8").splitlines()
        hosts = {line.strip().lower() for line in lines if line.strip()}
        results.append({
            "repo": repo,
            "file": filename,
            "revision": revision,
            "url": f"{HF}/datasets/{repo}/resolve/main/{filename}",
            "sha256": hashlib.sha256(body).hexdigest(),
            "lines": len(lines),
            "distinct_hosts": len(hosts),
            "exact_matches": {host: host in hosts for host in SOURCE_HOSTS},
            "source_hosts_listed": sorted(h for h in hosts if is_source_host(h)),
        })
    return results


def _host_variants(host: str) -> list[str]:
    return [host, host.removeprefix("www.") if host.startswith("www.") else f"www.{host}"]


def check_robots(client: httpx.Client) -> dict[str, Any]:
    import pyarrow.parquet as pq

    revision = resolve_revision(client, ROBOTS_REPO)
    entry = next(f for f in list_files(client, ROBOTS_REPO, revision) if f.path == ROBOTS_FILE)
    _log(f"reading domain column of {ROBOTS_REPO}/{ROBOTS_FILE} at {revision}")
    source = HttpRangeFile(client, resolve_url(ROBOTS_REPO, revision, ROBOTS_FILE), entry.size)
    parquet = pq.ParquetFile(source)
    domains: list[str] = parquet.read(columns=["domain"]).column("domain").to_pylist()
    wanted = set(SOURCE_HOSTS) | {v for url in PROBE_URLS for v in _host_variants(urlsplit(url).hostname or "")}
    rows = [i for i, d in enumerate(domains) if d.lower() in wanted or is_source_host(d)]

    stored: dict[str, list[dict[str, str]]] = {}
    if rows:
        _log(f"{len(rows)} matching domains; reading content column")
        table = parquet.read(columns=["protocol", "content"])
        protocols: list[str] = table.column("protocol").to_pylist()
        contents: list[str] = table.column("content").to_pylist()
        for i in rows:
            stored.setdefault(domains[i].lower(), []).append({"protocol": protocols[i], "content": contents[i]})

    probes: list[dict[str, Any]] = []
    for url in PROBE_URLS:
        host = urlsplit(url).hostname or ""
        used = next((v for v in _host_variants(host) if v in stored), None)
        probe: dict[str, Any] = {"url": url, "host": host, "robots_domain": used}
        if used is None:
            probe["note"] = "no stored robots.txt for this host or its www variant"
        else:
            probe["verdicts"] = [
                {"protocol": row["protocol"], "allowed": robots_verdicts(row["content"], url)} for row in stored[used]
            ]
        probes.append(probe)

    return {
        "repo": ROBOTS_REPO,
        "file": ROBOTS_FILE,
        "revision": revision,
        "sha256": entry.sha256,
        "domains_in_file": len(domains),
        "bytes_fetched": source.bytes_fetched,
        "source_hosts_stored": {
            domain: [
                {
                    "protocol": row["protocol"],
                    "sha256": hashlib.sha256(row["content"].encode()).hexdigest(),
                    "content": row["content"],
                    "root_allowed": robots_verdicts(row["content"], f"{row['protocol']}://{domain}/"),
                }
                for row in rows_
            ]
            for domain, rows_ in sorted(stored.items())
        },
        "hosts_checked": {host: host in stored for host in sorted(wanted)},
        "probes": probes,
        "agents": list(CRAWLER_AGENTS),
    }


# Check 2: n-gram overlap with FineWeb-2


def _sample_language(
    client: httpx.Client, revision: str, lang: str, config: str, items: list[dict[str, Any]], docs: int, seed: int
) -> dict[str, Any]:
    import pyarrow.parquet as pq

    listing = list_files(client, FINEWEB2_REPO, revision, f"data/{config}/train")
    shards = [f for f in listing if f.path.endswith(".parquet")]
    rng = random.Random(f"{seed}:{config}")
    shard = shards[rng.randrange(len(shards))]
    source = HttpRangeFile(client, resolve_url(FINEWEB2_REPO, revision, shard.path), shard.size)
    parquet = pq.ParquetFile(source)
    sizes = [parquet.metadata.row_group(i).num_rows for i in range(parquet.metadata.num_row_groups)]
    starts = [sum(sizes[:i]) for i in range(len(sizes))]
    picks = choose_row_groups(sizes, docs, rng)

    prompts = [prompt_grams(item["item_id"], item["prompt"], item.get("title")) for item in items]
    titles = sorted({item["title"] for item in items if item.get("title")})
    patterns = [p for p in (title_pattern(t) for t in titles) if p is not None]
    scan = CorpusScan(frozenset[Gram]().union(*(p.grams for p in prompts)), patterns)

    _log(f"{lang}: {shard.path}, {len(picks)} of {len(sizes)} row groups, target {docs} docs")
    began = time.monotonic()
    for done, (index, take) in enumerate(picks, start=1):
        table = parquet.read_row_group(index, columns=["text", "url"])
        texts: list[str] = table.column("text").to_pylist()[:take]
        urls: list[str] = table.column("url").to_pylist()[:take]
        for text, url in zip(texts, urls, strict=True):
            scan.add(text, url)
        if done % 10 == 0 or done == len(picks):
            _log(f"{lang}: {done}/{len(picks)} row groups, {scan.docs} docs, "
                 f"{source.bytes_fetched / 1e6:.0f} MB, {time.monotonic() - began:.0f}s")

    return {
        **summarise(prompts, scan),
        "sample": {
            "config": config,
            "shard": shard.path,
            "shard_url": resolve_url(FINEWEB2_REPO, revision, shard.path),
            "shard_sha256": shard.sha256,
            "shard_rows": sum(sizes),
            "shard_row_groups": len(sizes),
            "shards_in_config": len(shards),
            "row_groups": [index for index, _ in picks],
            "row_ranges": [[starts[index], starts[index] + take] for index, take in picks],
            "bytes_fetched": source.bytes_fetched,
        },
    }


def check_corpus(client: httpx.Client, items: list[dict[str, Any]], docs: int, seed: int) -> dict[str, Any]:
    revision = resolve_revision(client, FINEWEB2_REPO)
    languages = {
        lang: _sample_language(client, revision, lang, config, [i for i in items if i["lang"] == lang], docs, seed)
        for lang, config in CORPUS_CONFIGS.items()
    }
    return {
        "dataset": FINEWEB2_REPO,
        "revision": revision,
        "docs_per_lang": docs,
        "seed": seed,
        "ngram": NGRAM,
        "tokeniser": "Python re \\w+ (Unicode), each match lowercased",
        "languages": languages,
    }


def run(paths: Paths, docs_per_lang: int, seed: int, skip_corpus: bool) -> dict[str, Any]:
    items = [json.loads(line) for line in paths.items.read_text(encoding="utf-8").splitlines()]
    with hf_client() as client:
        return {
            "fetched_on": datetime.now(UTC).date().isoformat(),
            "items_sha256": hashlib.sha256(paths.items.read_bytes()).hexdigest(),
            "user_agent": USER_AGENT,
            "domains": {"blocklists": check_blocklists(client), "robots_txt": check_robots(client)},
            "corpus": None if skip_corpus else check_corpus(client, items, docs_per_lang, seed),
        }


def write_report(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


# Report


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _blocklist_section(blocklists: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Host | " + " | ".join(f"`{b['file']}`" for b in blocklists) + " |",
        "|---|" + "---|" * len(blocklists),
    ]
    lines += [
        f"| `{host}` | " + " | ".join(_yes(b["exact_matches"][host]) for b in blocklists) + " |"
        for host in SOURCE_HOSTS
    ]
    lines.append("")
    for b in blocklists:
        listed = b["source_hosts_listed"]
        found = ", ".join(f"`{h}`" for h in listed) if listed else "none"
        lines.append(f"Hosts under `admin.ch` or `swissvotes.ch` in `{b['file']}`: {found}.")
    return lines


def _robots_section(robots: dict[str, Any]) -> list[str]:
    stored = robots["source_hosts_stored"]
    lines = [
        f"The robots.txt dataset holds {robots['domains_in_file']:,} domains. "
        f"Hosts under `admin.ch` or `swissvotes.ch` with a stored robots.txt: "
        + (", ".join(f"`{d}`" for d in stored) if stored else "none") + ".",
        "",
        "| URL | robots.txt used | " + " | ".join(f"`{a}`" for a in robots["agents"]) + " |",
        "|---|---|" + "---|" * len(robots["agents"]),
    ]
    for probe in robots["probes"]:
        if probe["robots_domain"] is None:
            lines.append(f"| {probe['url']} | none stored | " + " | ".join("n/a" for _ in robots["agents"]) + " |")
            continue
        for verdict in probe["verdicts"]:
            cells = " | ".join("allowed" if verdict["allowed"][a] else "disallowed" for a in robots["agents"])
            lines.append(f"| {probe['url']} | `{probe['robots_domain']}` ({verdict['protocol']}) | {cells} |")
    if stored:
        lines += [
            "",
            "The stored files that do exist, evaluated for each host's root URL:",
            "",
            "| Host | " + " | ".join(f"`{a}`" for a in robots["agents"]) + " |",
            "|---|" + "---|" * len(robots["agents"]),
        ]
        for domain, rows in stored.items():
            for row in rows:
                cells = " | ".join("allowed" if row["root_allowed"][a] else "disallowed" for a in robots["agents"])
                lines.append(f"| `{domain}` ({row['protocol']}) | {cells} |")
    return lines


def _corpus_section(corpus: dict[str, Any]) -> list[str]:
    langs = corpus["languages"]
    lines = [
        "| Lang | Docs scanned | Prompts | Prompts with a 13-gram hit | Hits inside title only "
        "| Hits touching template | Distinct titles | Titles verbatim | Titles as token sequence "
        "| Docs from admin.ch / swissvotes.ch |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lang, s in langs.items():
        lines.append(
            f"| {lang} | {s['sample_docs']:,} | {s['prompts']:,} | {s['prompts_with_hit']:,} "
            f"| {s['prompts_with_title_only_hits']:,} | {s['prompts_with_template_hits']:,} "
            f"| {s['distinct_titles']} | {s['titles_verbatim']['titles']} "
            f"| {s['titles_token_sequence']['titles']} | {s['source_host_docs']['docs']} |"
        )
    lines += [
        "",
        "Distinct hit 13-grams per language, by where they sit in the prompt:",
        "",
        "| Lang | Distinct prompt 13-grams | Found, inside title | Found, touching template "
        "| Most template tokens in one found 13-gram |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {lang} | {s['prompt_ngrams']:,} | {s['hit_ngrams_title_only']:,} | {s['hit_ngrams_touching_template']:,} "
        f"| {s['max_template_tokens_in_hit']} |"
        for lang, s in langs.items()
    ]
    for lang, s in langs.items():
        lines += ["", f"### {lang}", "", "13-grams touching the template:", ""]
        if s["template_examples"]:
            lines += [
                f"- `{e['ngram']}` ({e['template_tokens']} template token(s), {e['docs']} docs), e.g. {e['url']}"
                for e in s["template_examples"]
            ]
        else:
            lines.append("- none")
        lines += ["", "13-grams inside a title:", ""]
        if s["title_only_examples"]:
            lines += [f"- `{e['ngram']}` ({e['docs']} docs), e.g. {e['url']}" for e in s["title_only_examples"]]
        else:
            lines.append("- none")
        lines += ["", f"Titles found verbatim (up to {EXAMPLE_LIMIT}):", ""]
        if s["titles_verbatim"]["examples"]:
            lines += [f"- {e['title']} ({e['docs']} docs), e.g. {e['url']}" for e in s["titles_verbatim"]["examples"]]
        else:
            lines.append("- none")
        lines += ["", f"Sampled documents from `admin.ch` or `swissvotes.ch` hosts (up to {SOURCE_URL_LIMIT}):", ""]
        urls = s["source_host_docs"]["urls"][:SOURCE_URL_LIMIT]
        lines += [f"- {url}" for url in urls] if urls else ["- none"]
    return lines


def _sources_section(report: dict[str, Any]) -> list[str]:
    robots = report["domains"]["robots_txt"]
    lines = ["| Source | Revision | sha256 | Size |", "|---|---|---|---|"]
    for b in report["domains"]["blocklists"]:
        lines.append(f"| [{b['repo']}/{b['file']}]({b['url']}) | `{b['revision'][:12]}` | `{b['sha256']}` "
                     f"| {b['lines']:,} lines |")
    lines.append(f"| [{robots['repo']}/{robots['file']}]({HF}/datasets/{robots['repo']}) "
                 f"| `{robots['revision'][:12]}` | `{robots['sha256']}` | {robots['domains_in_file']:,} rows |")
    corpus = report["corpus"]
    if corpus:
        for lang, s in corpus["languages"].items():
            sample = s["sample"]
            lines.append(f"| [{corpus['dataset']}/{sample['shard']}]({sample['shard_url']}) "
                         f"| `{corpus['revision'][:12]}` | `{sample['shard_sha256']}` "
                         f"| {sample['shard_rows']:,} rows, {len(sample['row_groups'])} row groups sampled ({lang}) |")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    corpus = report["corpus"]
    docs = f"{corpus['docs_per_lang']:,}" if corpus else "n/a"
    out = [
        "# Contamination check",
        "",
        f"Generated by `scrutineer contamination` on {report['fetched_on']}. Machine-readable results are in "
        "`docs/contamination.json`. Items file sha256 `" + report["items_sha256"] + "`.",
        "",
        "The benchmark asks about public facts: official vote titles, dates and results. Those facts are on "
        "swissvotes.ch and admin.ch and are almost certainly in any large web crawl, so this check does not try to "
        "show that the facts are absent. It asks two narrower questions. First, did the source sites opt out of "
        "AI crawling, which would have removed them from the Apertus pretraining data? Second, does the wording "
        "of our prompts, which we wrote for this benchmark, appear in the multilingual web text Apertus draws on?",
        "",
        "## 1. robots.txt opt-outs",
        "",
        "Apertus removed web pages from domains whose robots.txt disallowed AI crawlers and published the removed "
        "domains as two lists, one per FineWeb release (`fw1` for English FineWeb, `fw2` for FineWeb-2). Each line "
        "is one hostname. We match hostnames exactly, then list every entry that is `admin.ch`, `swissvotes.ch`, "
        "or a subdomain of either.",
        "",
        *_blocklist_section(report["domains"]["blocklists"]),
        "",
        "We also read the robots.txt files Apertus stored for the FineWeb domains (crawled in January 2025) and "
        "evaluated the vote pages we cite with Python's `urllib.robotparser`, for each crawler user agent. When a "
        "host has no stored file we try its `www.` variant and otherwise report it as missing.",
        "",
        *_robots_section(report["domains"]["robots_txt"]),
        "",
        "## 2. Prompt overlap with FineWeb-2",
        "",
    ]
    if corpus:
        out += [
            f"Every prompt in German, French and Italian is split into lowercase word tokens (Unicode `\\w+`) and "
            f"cut into {corpus['ngram']}-grams. A 13-gram counts as inside the title when all 13 tokens fall within "
            "the item's `title` field as it appears in the prompt. Any 13-gram that includes a token of the date "
            "line, the `Vorlage:` label or the question counts as touching the template. Items without a title "
            "(German F5, which describes the vote by its result) are all template. We then scan the FineWeb-2 "
            "sample once per language and record every prompt 13-gram that occurs in at least one document.",
            "",
            "Titles are matched in two ways. Verbatim: the title, lowercased and with whitespace collapsed, occurs "
            "in the lowercased, whitespace-collapsed document text with no word character on either side. Token "
            "sequence: the title's word tokens occur as a contiguous run of document tokens, which ignores "
            "punctuation and so also catches titles quoted with «» or typographic quotes instead of the straight "
            "quotes the Chancellery uses.",
            "",
            *_corpus_section(corpus),
            "",
            "How to read these numbers. A prompt counts as a title-only hit when some 13-token stretch of its title "
            "occurs in a sampled document, so long titles can match without the whole title appearing verbatim. "
            "That is why the title-only prompt counts can exceed the verbatim title counts. A 13-gram touching the "
            "template with only one or two template tokens is a title whose last words are followed by a common "
            "word such as an article, and says nothing about our question wording. The template wording itself "
            "(the date line, the question and the answer-format instruction) would show up as found 13-grams "
            "with many template tokens.",
            "",
            "## Sample design and deviation from the PRD",
            "",
            "The PRD asked for a 1% sample of FineWeb-2 per language. The German, French and Italian configs are "
            "roughly 770, 540 and 360 GB of Parquet, so 1% is about 17 GB of downloads. This check ran on a "
            "laptop with about 12 GB of free disk and under 1 MB/s of bandwidth, so we scanned a fixed "
            f"sample of {docs} documents per language instead. That is a small fraction of a percent of each "
            "config. A zero in the template column is therefore evidence about this sample, and an upper bound on "
            "overlap elsewhere only in the loose sense that template text found nowhere here is unlikely to be "
            "common in the full corpus.",
            "",
            f"The sample is reproducible from the seed ({corpus['seed']}). For each language a "
            "`random.Random(f\"{seed}:{config}\")` generator picks one train shard, then picks whole 1,000-row "
            "row groups from that shard in random order until the target is reached (the last group is truncated). "
            "Shards are read at a pinned dataset revision with HTTP range requests, so only the Parquet footer and "
            "the `text` and `url` column chunks of the chosen row groups are transferred, and nothing is written to "
            "disk. Shard paths, row group indices and global row ranges are in `contamination.json` under "
            "`corpus.languages.<lang>.sample`.",
            "",
            "FineWeb-2 is a proxy for the Apertus multilingual data. Apertus filtered it further (the opt-out "
            "lists above, among other steps), so documents in our sample may not have been seen by the model, and "
            "the model saw documents we did not sample.",
        ]
    else:
        out += ["Skipped (`--skip-corpus`)."]
    out += ["", "## Sources", "", *_sources_section(report), ""]
    return "\n".join(out)
