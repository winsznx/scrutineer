"""Command line entry point: scrutineer build | run | grade | report | site | verify."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable

from scrutineer.paths import Paths, default_paths

Handler = Callable[[argparse.Namespace, Paths], int]


def cmd_fetch_titles(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.build.swissvotes import UNIVERSE_START, load_votes
    from scrutineer.build.titles import fetch_titles, write_titles

    votes = load_votes(paths.csv)
    first = min(v.vote_number for v in votes if v.vote_date >= UNIVERSE_START)
    records = fetch_titles(first)
    write_titles(records, paths.titles)
    print(f"wrote {len(records)} title records to {paths.titles}")
    return 0


def cmd_build(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.build.items import generate_items, manifest, serialise
    from scrutineer.build.swissvotes import file_sha256, load_votes, select
    from scrutineer.build.templates import load_templates
    from scrutineer.build.titles import read_titles

    universe, post_cutoff = select(load_votes(paths.csv))
    items, log = generate_items(universe, post_cutoff, read_titles(paths.titles), load_templates())
    payload = serialise(items)
    info = manifest(payload, file_sha256(paths.csv), file_sha256(paths.titles), log)

    if args.check:
        stored = json.loads(paths.items_manifest.read_text())
        on_disk = hashlib.sha256(paths.items.read_bytes()).hexdigest()
        if stored["items_sha256"] != info["items_sha256"] or on_disk != info["items_sha256"]:
            print(f"items mismatch: rebuilt {info['items_sha256']}, manifest "
                  f"{stored['items_sha256']}, on disk {on_disk}", file=sys.stderr)
            return 1
        print(f"items verified: {info['item_count']} items, sha256 {info['items_sha256']}")
        return 0

    paths.items.write_bytes(payload)
    paths.items_manifest.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n")
    print(f"universe {len(universe)} votes, post-cutoff {len(post_cutoff)}, "
          f"{info['item_count']} items, sha256 {info['items_sha256']}")
    print(f"titles omitted: {len(log.omitted_titles)}, fallbacks: {len(log.fallback_titles)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrutineer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch-titles", help="fetch official titles from the Chancellery (LINDAS)")

    build = sub.add_parser("build", help="generate data/items.jsonl from the pinned sources")
    build.add_argument("--check", action="store_true", help="verify instead of writing")

    return parser


HANDLERS: dict[str, Handler] = {
    "fetch-titles": cmd_fetch_titles,
    "build": cmd_build,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args, default_paths())


if __name__ == "__main__":
    raise SystemExit(main())
