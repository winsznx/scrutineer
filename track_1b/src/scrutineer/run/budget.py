"""Spend accounting that keeps every run inside the starter credit.

Public AI exposes no API-key endpoint for the wallet balance, so the guard keeps its own
ledger: each paid request is logged with its estimated cost, and `reconcile` replaces
estimates with the billed cost from `POST /v1/developer/billing`. Before a request is
sent, its worst-case cost (prompt estimate plus `max_tokens` of output) is reserved, so
eight concurrent workers can never jointly overshoot. The server's own HTTP 402
`insufficient_balance` is the final backstop and stops the run immediately.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_CREDIT_USD = 2.00
DEFAULT_FLOOR_USD = 0.05
CHARS_PER_TOKEN_LOWER_BOUND = 2.5


class BudgetExhausted(Exception):
    """Raised when the next request could take the balance below the floor."""


def estimate_prompt_tokens(prompt: str) -> int:
    """Deliberately high estimate so reservations err on the side of stopping early."""
    return int(len(prompt) / CHARS_PER_TOKEN_LOWER_BOUND) + 16


def cost_usd(prompt_tokens: int, completion_tokens: int, price: tuple[float, float]) -> float:
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000


@dataclass
class SpendLedger:
    """Append-only JSONL. `spend` records come from the runner, `billed` from reconcile."""

    path: Path
    _estimates: dict[str, float] = field(default_factory=dict)
    _billed: dict[str, float] = field(default_factory=dict)
    _unidentified: float = 0.0

    def __post_init__(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["kind"] == "spend":
                if record.get("request_id"):
                    self._estimates[record["request_id"]] = record["cost_usd"]
                else:
                    self._unidentified += record["cost_usd"]
            elif record["kind"] == "billed":
                self._billed[record["request_id"]] = record["cost_usd"]

    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def record_spend(self, run_id: str, item_id: str, request_id: str | None, cost: float) -> None:
        self._append({
            "kind": "spend", "run_id": run_id, "item_id": item_id, "request_id": request_id,
            "cost_usd": cost, "timestamp": _now(),
        })
        if request_id:
            self._estimates[request_id] = cost
        else:
            self._unidentified += cost

    def record_billed(self, request_id: str, cost: float) -> None:
        self._append({"kind": "billed", "request_id": request_id, "cost_usd": cost, "timestamp": _now()})
        self._billed[request_id] = cost

    def unbilled_request_ids(self) -> list[str]:
        return [rid for rid in self._estimates if rid not in self._billed]

    @property
    def total_usd(self) -> float:
        total = self._unidentified
        for request_id, estimate in self._estimates.items():
            total += self._billed.get(request_id, estimate)
        return total


@dataclass
class BudgetGuard:
    ledger: SpendLedger
    credit_usd: float = DEFAULT_CREDIT_USD
    floor_usd: float = DEFAULT_FLOOR_USD
    run_cap_usd: float | None = None
    run_spent_usd: float = 0.0
    _reserved: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def remaining_usd(self) -> float:
        return self.credit_usd - self.ledger.total_usd

    async def reserve(self, worst_case: float) -> None:
        async with self._lock:
            projected = self.ledger.total_usd + self._reserved + worst_case
            if self.credit_usd - projected < self.floor_usd:
                raise BudgetExhausted(
                    f"balance would drop below ${self.floor_usd:.2f} "
                    f"(estimated remaining ${self.remaining_usd:.4f})"
                )
            if self.run_cap_usd is not None:
                run_projected = self.run_spent_usd + self._reserved + worst_case
                if run_projected > self.run_cap_usd:
                    raise BudgetExhausted(f"run cap ${self.run_cap_usd:.2f} reached")
            self._reserved += worst_case

    async def settle(
        self, worst_case: float, run_id: str, item_id: str, request_id: str | None, actual: float | None
    ) -> None:
        async with self._lock:
            self._reserved -= worst_case
            if actual is not None:
                self.ledger.record_spend(run_id, item_id, request_id, actual)
                self.run_spent_usd += actual


def reconcile(ledger: SpendLedger, billing_url: str, api_key: str, user_agent: str) -> int:
    """Replace estimates with billed costs. Returns how many requests were updated."""
    pending = ledger.unbilled_request_ids()
    updated = 0
    with httpx.Client(timeout=60, headers={"User-Agent": user_agent}) as client:
        for start in range(0, len(pending), 100):
            batch = pending[start : start + 100]
            response = client.post(
                billing_url,
                json={"requestIds": batch},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            for row in response.json().get("requests", []):
                nano = row.get("costNanoUsd") or 0
                if nano > 0:
                    ledger.record_billed(row["requestId"], nano / 1e9)
                    updated += 1
    return updated


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
