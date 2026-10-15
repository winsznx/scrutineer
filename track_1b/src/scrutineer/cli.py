"""Command line entry point: scrutineer build | run | grade | report | site | verify | contamination."""

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

# `scrutineer run` exit codes, used by scripts/supervise_run.sh
EXIT_REMAINING = 3
EXIT_BUDGET = 4
EXIT_ENDPOINT_DOWN = 5
EXIT_SIGNAL = 130


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

    from scrutineer.build.robustness import order_swap_items

    swap_payload = serialise(order_swap_items(items))
    if args.check:
        if paths.order_swap_items.read_bytes() != swap_payload:
            print("robustness items differ from a fresh build", file=sys.stderr)
            return 1
        stored = json.loads(paths.items_manifest.read_text())
        on_disk = hashlib.sha256(paths.items.read_bytes()).hexdigest()
        if stored["items_sha256"] != info["items_sha256"] or on_disk != info["items_sha256"]:
            print(f"items mismatch: rebuilt {info['items_sha256']}, manifest "
                  f"{stored['items_sha256']}, on disk {on_disk}", file=sys.stderr)
            return 1
        print(f"items verified: {info['item_count']} items, sha256 {info['items_sha256']}")
        return 0

    paths.items.write_bytes(payload)
    paths.order_swap_items.parent.mkdir(parents=True, exist_ok=True)
    paths.order_swap_items.write_bytes(swap_payload)
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


def _load_items(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


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
        RunConfig,
        Runner,
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
    items_path = Path(args.items).resolve() if args.items else paths.items
    items_sha = hashlib.sha256(items_path.read_bytes()).hexdigest()
    extra_meta = {"items_path": str(items_path.relative_to(paths.root))} if args.items else {}
    write_meta(paths.responses / f"{args.run_id}.meta.json", config, items_sha, extra_meta)

    selected = order_items(_select(_load_items(items_path), args))
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
    if not remaining:
        return 0
    return {"budget": EXIT_BUDGET, "endpoint": EXIT_ENDPOINT_DOWN, "signal": EXIT_SIGNAL}.get(
        state.stop_kind or "", EXIT_REMAINING)


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


def cmd_judge(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.grade.grade import answer_text, needs_judge
    from scrutineer.grade.judge import JudgeTask, judge_all
    from scrutineer.grade.results import load_items, run_ids
    from scrutineer.run.runner import read_records

    meta = json.loads((paths.docs / "judge_meta.json").read_text())
    items = load_items(paths)
    paths.judgements.mkdir(parents=True, exist_ok=True)
    for run_id in args.run_id or run_ids(paths):
        records = read_records(paths.responses / f"{run_id}.jsonl")
        tasks = []
        for item_id, record in records.items():
            if record["status"] != "ok":
                continue
            item = items[item_id]
            response = answer_text(record)
            reason = needs_judge(item, response)
            if reason:
                tasks.append(JudgeTask(run_id, item, response, reason))
        sent = asyncio.run(judge_all(
            tasks, paths.judgements / f"{run_id}.jsonl", args.base_url,
            meta["gguf_sha256"], concurrency=args.concurrency,
        ))
        print(f"{run_id}: {len(tasks)} items need the judge, {sent} judged now")
    return 0


def _write_results(paths: Paths) -> bytes:
    from scrutineer.grade.results import assemble, graded_run, load_items, run_ids, serialise, write_graded

    items = load_items(paths)
    for run_id in run_ids(paths):
        write_graded(paths.data / "graded" / f"{run_id}.jsonl", graded_run(paths, run_id, items))
    payload = serialise(assemble(paths))
    paths.results.write_bytes(payload)
    return payload


def cmd_grade(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.grade.results import digest

    payload = _write_results(paths)
    sha = digest(payload)
    if args.update_hash:
        paths.results_hash.write_text(f"{sha}  results.json\n")
    print(f"results.json sha256 {sha}")
    return 0


def cmd_verify(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.grade.results import digest

    expected = paths.results_hash.read_text().split()[0]
    actual = digest(_write_results(paths))
    if actual != expected:
        print(f"VERIFY FAILED: results.json sha256 {actual}, expected {expected}", file=sys.stderr)
        return 1
    print(f"verified: results.json sha256 {actual} matches results.sha256")
    return 0


SYNCED_DOCS = ("README.md", "technical_report.md", "docs/DATA_CARD.md", "docs/CLAIM_LEDGER.md", "docs/JUDGE.md")


def cmd_report(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.report.blocks import sync_text
    from scrutineer.report.figures import render_all

    results = json.loads(paths.results.read_text(encoding="utf-8"))
    figures = render_all(results, paths.figures)
    print(f"rendered {len(figures)} figures into {paths.figures}")
    stale = []
    for name in SYNCED_DOCS:
        path = paths.root / name
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = sync_text(original, results)
        if updated == original:
            continue
        if args.check:
            stale.append(name)
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"updated generated numbers in {name}")
    if args.pdf:
        from scrutineer.report.pdf import export_pdf

        print(f"wrote {export_pdf(paths.root / 'technical_report.md', paths.root / 'Scrutineer_Report.pdf')}")
    if stale:
        print(f"REPORT CHECK FAILED: generated numbers are stale in {', '.join(stale)}; run `make report`",
              file=sys.stderr)
        return 1
    return 0


def cmd_export_human_check(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.grade.human import export_sample

    if paths.human_check.exists() and not args.force:
        print(f"{paths.human_check} exists; refusing to overwrite labels (use --force)", file=sys.stderr)
        return 1
    count, population = export_sample(paths, fraction=args.fraction, seed=args.seed)
    print(f"exported {count} of {population} judged items to {paths.human_check}")
    return 0


def cmd_contamination(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.contamination import run, write_report

    report = run(paths, docs_per_lang=args.docs_per_lang, seed=args.seed, skip_corpus=args.skip_corpus)
    write_report(report, paths.docs / "contamination.json", paths.docs / "CONTAMINATION.md")
    for blocklist in report["domains"]["blocklists"]:
        listed = [host for host, hit in blocklist["exact_matches"].items() if hit]
        print(f"{blocklist['file']}: {blocklist['lines']} lines, exact source hosts listed: {listed or 'none'}, "
              f"related hosts listed: {blocklist['source_hosts_listed'] or 'none'}")
    for lang, summary in (report["corpus"] or {}).get("languages", {}).items():
        print(f"{lang}: {summary['sample_docs']} docs, {summary['prompts_with_hit']}/{summary['prompts']} prompts "
              f"with a 13-gram hit ({summary['prompts_with_template_hits']} touching template), "
              f"{summary['titles_verbatim']['titles']}/{summary['distinct_titles']} titles verbatim")
    print(f"wrote {paths.docs / 'contamination.json'} and {paths.docs / 'CONTAMINATION.md'}")
    return 0


def cmd_site(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.site.generate import build_site

    print(f"site written to {build_site(paths)}")
    return 0


def cmd_export_hf(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.export import export_hf

    print(f"Hugging Face dataset staged in {export_hf(paths, paths.root / 'hf')}")
    return 0


def cmd_replay(args: argparse.Namespace, paths: Paths) -> int:
    from scrutineer.grade.results import load_items
    from scrutineer.replay import agreement, generate, sample_items
    from scrutineer.run.runner import read_records

    hosted = read_records(paths.responses / f"{args.hosted_run}.jsonl")
    items = sample_items(list(load_items(paths).values()), hosted)
    out_dir = paths.data / "replay"
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / "local_8b.jsonl"
    if not args.compare_only:
        generate(items, local_path, device=args.device)
    result = agreement(items, read_records(local_path), hosted)
    (out_dir / "agreement.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"label agreement {result['label_agreement']} on {result['n']} items")
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
    run.add_argument("--items", help="alternative item file, e.g. data/robustness/order_swap_items.jsonl")
    run.add_argument("--limit", type=int, help="first N items in priority order")
    run.add_argument("--retry-failed", action="store_true")
    run.add_argument("--workers", type=int, default=8)
    run.add_argument("--rpm", type=int, default=100)
    run.add_argument("--max-usd", type=float, help="cap on this run's spend")
    run.add_argument("--credit-usd", type=float, default=2.00, help="starting wallet credit")
    run.add_argument("--floor-usd", type=float, default=0.05, help="stop before going below")

    budget = sub.add_parser("budget", help="show ledger spend, optionally reconcile with billing")
    budget.add_argument("--reconcile", action="store_true")

    judge = sub.add_parser("judge", help="grade F6, F8 and unparseable answers with the local judge")
    judge.add_argument("--run-id", action="append", help="repeatable; default all runs")
    judge.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    judge.add_argument("--concurrency", type=int, default=2)

    grade = sub.add_parser("grade", help="grade all runs and write data/results.json")
    grade.add_argument("--update-hash", action="store_true", help="also rewrite results.sha256")

    sub.add_parser("verify", help="recompute results.json and check it against results.sha256")

    report = sub.add_parser("report", help="render figures and sync generated numbers into the docs")
    report.add_argument("--check", action="store_true", help="fail instead of writing if docs are stale")
    report.add_argument("--pdf", action="store_true", help="also export Scrutineer_Report.pdf (pandoc + typst)")

    human = sub.add_parser("export-human-check", help="blind 20%% sample of judgements for labelling")
    human.add_argument("--fraction", type=float, default=0.2)
    human.add_argument("--seed", type=int, default=0)
    human.add_argument("--force", action="store_true")

    contamination = sub.add_parser("contamination", help="robots.txt opt-outs and 13-gram overlap with FineWeb-2")
    contamination.add_argument("--docs-per-lang", type=int, default=100_000)
    contamination.add_argument("--seed", type=int, default=0)
    contamination.add_argument("--skip-corpus", action="store_true", help="domain check only")

    sub.add_parser("site", help="build the static site into site/")
    sub.add_parser("export-hf", help="stage the Hugging Face dataset (items, metadata, responses, card) in hf/")

    replay = sub.add_parser("replay", help="replay 100 F1 items on the official 8B weights, compare with R2")
    replay.add_argument("--hosted-run", default="R2")
    replay.add_argument("--device", help="torch device; default mps if available, else cpu")
    replay.add_argument("--compare-only", action="store_true", help="skip generation, recompute agreement")

    return parser


HANDLERS: dict[str, Handler] = {
    "fetch-titles": cmd_fetch_titles,
    "build": cmd_build,
    "run": cmd_run,
    "budget": cmd_budget,
    "judge": cmd_judge,
    "grade": cmd_grade,
    "verify": cmd_verify,
    "export-human-check": cmd_export_human_check,
    "report": cmd_report,
    "contamination": cmd_contamination,
    "site": cmd_site,
    "export-hf": cmd_export_hf,
    "replay": cmd_replay,
}


def main(argv: list[str] | None = None) -> int:
    paths = default_paths()
    load_env_files(paths)
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args, paths)


if __name__ == "__main__":
    raise SystemExit(main())
