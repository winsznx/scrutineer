from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from scrutineer.run.budget import BudgetExhausted, BudgetGuard, SpendLedger
from scrutineer.run.providers import Provider
from scrutineer.run.runner import (
    RunConfig,
    Runner,
    body_sha256,
    order_items,
    pending_items,
    read_records,
    request_body,
)

PROVIDER = Provider(name="fake", base_url="http://fake.test/v1", api_key="k")


def make_items(n: int) -> list[dict[str, Any]]:
    return [
        {"item_id": f"{400 + i}-F1-de", "anr": str(400 + i), "family": "F1", "lang": "de",
         "prompt": f"Frage {i}"}
        for i in range(n)
    ]


def ok_payload(request: httpx.Request) -> dict[str, Any]:
    body = json.loads(request.content)
    return {
        "id": f"chatcmpl-{body['messages'][0]['content'][-1]}",
        "model": body["model"],
        "choices": [{"message": {"content": "Abgelehnt."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 5},
    }


class FakeServer:
    def __init__(self, script: list[int] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body["messages"][0]["content"])
        assert request.headers["user-agent"].startswith("scrutineer/")
        status = self.script.pop(0) if self.script else 200
        if status == 200:
            return httpx.Response(200, json=ok_payload(request))
        if status == 402:
            return httpx.Response(402, json={"error": {"type": "insufficient_balance"}})
        return httpx.Response(status, text="boom")


def run(tmp_path: Path, server: FakeServer, items: list[dict[str, Any]], credit: float = 2.0,
        price: tuple[float, float] | None = (1.0, 1.0)) -> Runner:
    config = RunConfig(run_id="T", model="m", provider=PROVIDER, price=price, workers=2, rpm=60_000)
    guard = BudgetGuard(SpendLedger(tmp_path / "ledger.jsonl"), credit_usd=credit, floor_usd=0.05)
    runner = Runner(config, guard, tmp_path / "T.jsonl", httpx.MockTransport(server), sleep_base_s=0)
    asyncio.run(runner.run(items))
    return runner


def test_records_every_item_with_request_hash(tmp_path: Path) -> None:
    items = make_items(3)
    run(tmp_path, FakeServer(), items)
    records = read_records(tmp_path / "T.jsonl")
    assert set(records) == {i["item_id"] for i in items}
    config = RunConfig(run_id="T", model="m", provider=PROVIDER, price=None)
    for item in items:
        record = records[item["item_id"]]
        assert record["status"] == "ok"
        assert record["response"] == "Abgelehnt."
        assert record["request_sha256"] == body_sha256(request_body(config, item))


def test_resume_never_resends_completed_items(tmp_path: Path) -> None:
    items = make_items(4)
    run(tmp_path, FakeServer(), items[:2])
    existing = read_records(tmp_path / "T.jsonl")
    todo = pending_items(items, existing, retry_failed=False)
    assert [i["item_id"] for i in todo] == [items[2]["item_id"], items[3]["item_id"]]
    server = FakeServer()
    run(tmp_path, server, todo)
    assert sorted(server.calls) == ["Frage 2", "Frage 3"]
    assert len((tmp_path / "T.jsonl").read_text().splitlines()) == 4


def test_retries_then_records_failure(tmp_path: Path) -> None:
    server = FakeServer([503, 503, 503, 503, 503])
    runner = run(tmp_path, server, make_items(1))
    record = read_records(tmp_path / "T.jsonl")["400-F1-de"]
    assert record["status"] == "failed"
    assert record["attempts"] == 5
    assert record["response"] is None
    assert len(server.calls) == 5
    assert runner.state.failed == {"400-F1-de"}


def test_transient_error_then_success(tmp_path: Path) -> None:
    run(tmp_path, FakeServer([429, 200]), make_items(1))
    record = read_records(tmp_path / "T.jsonl")["400-F1-de"]
    assert record["status"] == "ok"
    assert record["attempts"] == 2


def test_failed_items_are_retried_only_on_request(tmp_path: Path) -> None:
    items = make_items(1)
    run(tmp_path, FakeServer([500] * 5), items)
    existing = read_records(tmp_path / "T.jsonl")
    assert pending_items(items, existing, retry_failed=False) == []
    assert pending_items(items, existing, retry_failed=True) == items


def test_insufficient_balance_stops_without_writing(tmp_path: Path) -> None:
    runner = run(tmp_path, FakeServer([402] * 10), make_items(5))
    assert runner.state.stop_reason is not None and "402" in runner.state.stop_reason
    assert not (tmp_path / "T.jsonl").exists()


def test_budget_guard_stops_before_overspending(tmp_path: Path) -> None:
    # Each request reserves (prompt estimate + 60 output tokens) at $1/1M tokens, about $0.0001.
    runner = run(tmp_path, FakeServer(), make_items(20), credit=0.05 + 0.00035)
    assert runner.state.stop_reason is not None
    assert 0 < len(runner.state.done) < 20
    ledger = SpendLedger(tmp_path / "ledger.jsonl")
    assert ledger.total_usd <= 0.00035


def test_reserve_raises_below_floor(tmp_path: Path) -> None:
    guard = BudgetGuard(SpendLedger(tmp_path / "l.jsonl"), credit_usd=0.10, floor_usd=0.05)
    asyncio.run(guard.reserve(0.04))
    with pytest.raises(BudgetExhausted):
        asyncio.run(guard.reserve(0.02))


def test_ledger_prefers_billed_cost(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "l.jsonl")
    ledger.record_spend("R", "a", "req-1", 0.010)
    ledger.record_spend("R", "b", "req-2", 0.020)
    ledger.record_billed("req-1", 0.012)
    reloaded = SpendLedger(tmp_path / "l.jsonl")
    assert reloaded.total_usd == pytest.approx(0.032)
    assert reloaded.unbilled_request_ids() == ["req-2"]


def test_priority_order_puts_headline_family_first() -> None:
    items = [
        {"item_id": "1-F8-de", "anr": "1", "family": "F8", "lang": "de"},
        {"item_id": "2-F1-fr", "anr": "2", "family": "F1", "lang": "fr"},
        {"item_id": "2-F1-de", "anr": "2", "family": "F1", "lang": "de"},
        {"item_id": "1-F7-de", "anr": "1", "family": "F7", "lang": "de"},
    ]
    assert [i["item_id"] for i in order_items(items)] == ["2-F1-de", "2-F1-fr", "1-F7-de", "1-F8-de"]


def test_circuit_breaker_stops_a_dead_endpoint(tmp_path: Path) -> None:
    runner = run(tmp_path, FakeServer([503] * 1000), make_items(40))
    assert runner.state.stop_reason is not None and "consecutive" in runner.state.stop_reason
    assert len(runner.state.failed) < 40


def test_billed_cost_header_wins_over_estimate(tmp_path: Path) -> None:
    def server(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok_payload(request), headers={"x-litellm-response-cost": "0.00042"})

    config = RunConfig(run_id="T", model="m", provider=PROVIDER, price=(1.0, 1.0), workers=1, rpm=60_000)
    guard = BudgetGuard(SpendLedger(tmp_path / "ledger.jsonl"), credit_usd=2.0)
    runner = Runner(config, guard, tmp_path / "T.jsonl", httpx.MockTransport(server), sleep_base_s=0)
    asyncio.run(runner.run(make_items(1)))
    assert read_records(tmp_path / "T.jsonl")["400-F1-de"]["cost_usd"] == pytest.approx(0.00042)


def test_upstream_capacity_400_is_retried(tmp_path: Path) -> None:
    calls = {"n": 0}

    def server(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(400, text='{"error":{"message":"Unsupported model or no available clients"}}')
        return httpx.Response(200, json=ok_payload(request))

    config = RunConfig(run_id="T", model="m", provider=PROVIDER, price=(1.0, 1.0), workers=1, rpm=60_000)
    guard = BudgetGuard(SpendLedger(tmp_path / "ledger.jsonl"), credit_usd=2.0)
    runner = Runner(config, guard, tmp_path / "T.jsonl", httpx.MockTransport(server), sleep_base_s=0)
    asyncio.run(runner.run(make_items(1)))
    assert read_records(tmp_path / "T.jsonl")["400-F1-de"]["attempts"] == 2
