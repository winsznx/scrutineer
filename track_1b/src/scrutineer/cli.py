"""Command line entry point: scrutineer build | run | grade | report | site | verify."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


def load_env_files(paths: Paths) -> None:
    """Read KEY=VALUE lines from .env files without overriding the real environment."""
    for candidate in (paths.root / ".env", paths.root.parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_items(paths: Paths) -> list[dict[str, Any]]:
    return [json.loads(line) for line in paths.items.read_text(encoding="utf-8").splitlines()]


def _select(items: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = items
    if args.families:
        selected = [i for i in selected if i["family"] in set(args.families.split(","))]
    if args.langs:
        selected = [i for i in selected if i["lang"] in set(args.langs.split(","))]
    if args.item_ids:
        wanted = set(Path(args.item_ids).read_text().split())
        selected = [i for i in selected if i["item_id"] in wanted]
    return selected


def cmd_run(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.run.budget import BudgetGuard, SpendLedger, reconcile
    from scrutineer.run.providers import USER_AGENT, price_for, resolve_provider
    from scrutineer.run.runner import (
        Runner,
        RunConfig,
        order_items,
        pending_items,
        read_records,
        report_remaining,
        write_meta,
    )

    provider = resolve_provider(args.provider)
    if not provider.api_key:
        print(f"no API key for provider {provider.name}", file=sys.stderr)
        return 2
    thinking = args.thinking or args.model.endswith("-thinking")
    config = RunConfig(
        run_id=args.run_id,
        model=args.model,
        provider=provider,
        price=price_for(args.model),
        thinking=thinking,
        workers=args.workers,
        rpm=args.rpm,
        retry_failed=args.retry_failed,
    )
    if config.price is None and provider.name == "publicai":
        print(f"no list price known for {args.model}; refusing to run unguarded", file=sys.stderr)
        return 2

    paths.responses.mkdir(parents=True, exist_ok=True)
    out = paths.responses / f"{args.run_id}.jsonl"
    items_sha = hashlib.sha256(paths.items.read_bytes()).hexdigest()
    write_meta(paths.responses / f"{args.run_id}.meta.json", config, items_sha)

    selected = order_items(_select(_load_items(paths), args))
    if args.limit:
        selected = selected[: args.limit]
    todo = pending_items(selected, read_records(out), args.retry_failed)
    ledger = SpendLedger(paths.spend_ledger)
    guard = BudgetGuard(
        ledger, credit_usd=args.credit_usd, floor_usd=args.floor_usd, run_cap_usd=args.max_usd
    )
    print(f"{args.run_id}: {len(selected)} selected, {len(todo)} to send, "
          f"ledger spend ${ledger.total_usd:.4f}, est. remaining ${guard.remaining_usd:.4f}")

    state = asyncio.run(Runner(config, guard, out).run(todo))

    if provider.billing_url and provider.api_key:
        try:
            updated = reconcile(ledger, provider.billing_url, provider.api_key, USER_AGENT)
            print(f"reconciled {updated} request costs against /developer/billing")
        except Exception as exc:  # reconciliation is advisory; the run itself is complete
            print(f"billing reconciliation failed: {exc}", file=sys.stderr)

    records = read_records(out)
    remaining = [i["item_id"] for i in selected if records.get(i["item_id"], {}).get("status") != "ok"]
    failed = [i for i in remaining if records.get(i, {}).get("status") == "failed"]
    print(f"{args.run_id}: ok {len(selected) - len(remaining)}, failed {len(failed)}, "
          f"unsent {len(remaining) - len(failed)}; run spend ${guard.run_spent_usd:.4f}, "
          f"ledger total ${ledger.total_usd:.4f}")
    if state.stop_reason:
        print(f"stopped: {state.stop_reason}", file=sys.stderr)
    report_remaining(remaining, paths.responses / f"{args.run_id}.remaining.txt")
    return 0 if not remaining else 3


def cmd_budget(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.run.budget import DEFAULT_CREDIT_USD, SpendLedger, reconcile
    from scrutineer.run.providers import USER_AGENT, resolve_provider

    ledger = SpendLedger(paths.spend_ledger)
    if args.reconcile:
        provider = resolve_provider("publicai")
        assert provider.billing_url and provider.api_key
        print(f"reconciled {reconcile(ledger, provider.billing_url, provider.api_key, USER_AGENT)}")
    print(f"ledger spend ${ledger.total_usd:.4f}; "
          f"estimated remaining ${DEFAULT_CREDIT_USD - ledger.total_usd:.4f} of ${DEFAULT_CREDIT_USD:.2f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrutineer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch-titles", help="fetch official titles from the Chancellery (LINDAS)")

    build = sub.add_parser("build", help="generate data/items.jsonl from the pinned sources")
    build.add_argument("--check", action="store_true", help="verify instead of writing")

    run = sub.add_parser("run", help="query a model for every pending item")
    run.add_argument("--run-id", required=True)
    run.add_argument("--model", default=os.environ.get("LLM_NAME"), required="LLM_NAME" not in os.environ)
    run.add_argument("--provider", default="publicai", choices=["publicai", "hf", "env"])
    run.add_argument("--thinking", action="store_true", help="thinking variant (2,000 max tokens)")
    run.add_argument("--families", help="comma separated, e.g. F1,F7")
    run.add_argument("--langs", help="comma separated, e.g. de,fr")
    run.add_argument("--item-ids", help="file with item ids to restrict to")
    run.add_argument("--limit", type=int, help="first N items in priority order")
    run.add_argument("--retry-failed", action="store_true")
    run.add_argument("--workers", type=int, default=8)
    run.add_argument("--rpm", type=int, default=100)
    run.add_argument("--max-usd", type=float, help="cap on this run's spend")
    run.add_argument("--credit-usd", type=float, default=2.00, help="starting wallet credit")
    run.add_argument("--floor-usd", type=float, default=0.05, help="stop before going below")

    budget = sub.add_parser("budget", help="show ledger spend, optionally reconcile with billing")
    budget.add_argument("--reconcile", action="store_true")

    return parser


HANDLERS: dict[str, Handler] = {
    "fetch-titles": cmd_fetch_titles,
    "build": cmd_build,
    "run": cmd_run,
    "budget": cmd_budget,
}


def main(argv: list[str] | None = None) -> int:
    paths = default_paths()
    load_env_files(paths)
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args, paths)


if __name__ == "__main__":
    raise SystemExit(main())
