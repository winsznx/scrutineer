"""Stream model responses for a set of items into `responses/<run_id>.jsonl`.

The response file is append-only and is the run's source of truth. On restart every
item that already has an `ok` record is skipped, so no item is ever paid for twice.
Records are fsynced one by one, so a crash loses at most the in-flight requests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import signal
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scrutineer.grade.parse import APERTUS_THINK_CLOSE, APERTUS_THINK_OPEN
from scrutineer.run.budget import BudgetExhausted, BudgetGuard, cost_usd, estimate_prompt_tokens
from scrutineer.run.providers import USER_AGENT, Provider

FAMILY_PRIORITY = ("F1", "F7", "F5", "F3", "F4", "F2", "F6", "F8")
MAX_TOKENS = {"F8": 120}
DEFAULT_MAX_TOKENS = 60
THINKING_MAX_TOKENS = 2000
MAX_ATTEMPTS = 5
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}
# Upstream capacity errors that LiteLLM forwards with a non-retryable status code.
TRANSIENT_MARKERS = ("no available clients", "ratelimiterror", "too many requests", "overloaded")
# Consecutive failed items after which the endpoint is treated as down and the run stops.
CIRCUIT_BREAKER = 16


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    model: str
    provider: Provider
    price: tuple[float, float] | None
    thinking: bool = False
    workers: int = 8
    rpm: int = 100
    temperature: float = 0.0
    seed: int = 0
    timeout_s: float = 180.0
    retry_failed: bool = False

    def max_tokens(self, family: str) -> int:
        if self.thinking:
            return THINKING_MAX_TOKENS
        return MAX_TOKENS.get(family, DEFAULT_MAX_TOKENS)

    def meta(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "wire_model": self.provider.wire_model(self.model),
            "provider": self.provider.name,
            "endpoint": self.provider.chat_url,
            "thinking": self.thinking,
            "thinking_switch": (
                "chat_template_kwargs.enable_thinking" if self.thinking and not self.model.endswith("-thinking")
                else ("model id" if self.thinking else None)
            ),
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": {f: self.max_tokens(f) for f in FAMILY_PRIORITY},
            "system_prompt": None,
            "price_usd_per_mtok": list(self.price) if self.price else None,
            "workers": self.workers,
            "rpm": self.rpm,
        }


class TokenBucket:
    """At most `rpm` requests in any 60 s window, with no initial burst."""

    def __init__(self, rpm: int) -> None:
        self.interval = 60.0 / rpm
        self._next = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)


class StopRun(Exception):
    """The server refused for lack of balance; nothing more may be sent."""


class EndpointDown(StopRun):
    """Too many consecutive failures; the endpoint is treated as unavailable."""


@dataclass
class RunState:
    done: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    stop_reason: str | None = None
    stop_kind: str | None = None  # "budget", "endpoint", "signal" or "deadline"
    consecutive_failures: int = 0


def request_body(config: RunConfig, item: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": config.provider.wire_model(config.model),
        "messages": [{"role": "user", "content": item["prompt"]}],
        "temperature": config.temperature,
        "seed": config.seed,
        "max_tokens": config.max_tokens(item["family"]),
    }
    if config.thinking and not config.model.endswith("-thinking"):
        # Apertus' chat template switch; the hosted `-thinking` ids set the same flag server-side.
        body["chat_template_kwargs"] = {"enable_thinking": True}
    return body


def body_sha256(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_records(path: Path) -> dict[str, dict[str, Any]]:
    """Last record per item id. Later lines supersede earlier ones (retries append)."""
    latest: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["item_id"]] = record
    return latest


def order_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Headline families first, so a run cut short by the budget still answers the claim."""
    langs = ("de", "fr", "it", "en", "rm")
    return sorted(
        items,
        key=lambda i: (
            FAMILY_PRIORITY.index(i["family"]),
            int(i["anr"].split(".")[0]),
            i["anr"],
            langs.index(i["lang"]),
        ),
    )


def pending_items(
    items: list[dict[str, Any]], existing: dict[str, dict[str, Any]], retry_failed: bool
) -> list[dict[str, Any]]:
    def needs_request(item_id: str) -> bool:
        record = existing.get(item_id)
        if record is None:
            return True
        return record["status"] == "failed" and retry_failed

    return [item for item in order_items(items) if needs_request(item["item_id"])]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _extract(payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Verbatim content, the thinking trace if the server or the template exposes one, finish reason."""
    choice = payload["choices"][0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    extra = message.get("provider_specific_fields") or {}
    reasoning = message.get("reasoning_content") or message.get("reasoning") or extra.get("reasoning")
    if reasoning is None and APERTUS_THINK_OPEN in content:
        trace = content.partition(APERTUS_THINK_OPEN)[2]
        reasoning = trace.partition(APERTUS_THINK_CLOSE)[0]
    return content, reasoning, choice.get("finish_reason")


def _is_transient(response: httpx.Response) -> bool:
    body = response.text[:500].lower()
    return response.status_code == 400 and any(marker in body for marker in TRANSIENT_MARKERS)


def _billed_cost(response: httpx.Response) -> float | None:
    """LiteLLM reports the exact charge per request in a response header."""
    raw = response.headers.get("x-litellm-response-cost")
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


class Runner:
    def __init__(
        self,
        config: RunConfig,
        guard: BudgetGuard,
        out_path: Path,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep_base_s: float = 2.0,
        stop_at: datetime | None = None,
    ) -> None:
        self.stop_at = stop_at
        self.config = config
        self.guard = guard
        self.out_path = out_path
        self.transport = transport
        self.sleep_base_s = sleep_base_s
        self.state = RunState()
        self._write_lock = asyncio.Lock()

    async def _write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        async with self._write_lock:
            with self.out_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def _worst_case(self, item: dict[str, Any]) -> float:
        if self.config.price is None:
            return 0.0
        return cost_usd(
            estimate_prompt_tokens(item["prompt"]),
            self.config.max_tokens(item["family"]),
            self.config.price,
        )

    async def _call(self, client: httpx.AsyncClient, bucket: TokenBucket, item: dict[str, Any]) -> None:
        body = request_body(self.config, item)
        base = {
            "run_id": self.config.run_id,
            "item_id": item["item_id"],
            "model": self.config.model,
            "provider": self.config.provider.name,
            "endpoint": self.config.provider.chat_url,
            "request_sha256": body_sha256(body),
        }
        worst = self._worst_case(item)
        await self.guard.reserve(worst)
        actual: float | None = None
        request_id: str | None = None
        last_error = ""
        last_status: int | None = None
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                await bucket.acquire()
                started = time.perf_counter()
                try:
                    response = await client.post(self.config.provider.chat_url, json=body)
                except httpx.TransportError as exc:
                    last_error, last_status = f"{type(exc).__name__}: {exc}", None
                    await self._backoff(attempt)
                    continue
                latency_ms = round((time.perf_counter() - started) * 1000)
                last_status = response.status_code
                if response.status_code == 402:
                    raise StopRun(f"HTTP 402 from server: {response.text[:300]}")
                if response.status_code in RETRYABLE or _is_transient(response):
                    last_error = response.text[:300]
                    print(f"{_now()} retry {item['item_id']} attempt {attempt} HTTP "
                          f"{response.status_code} after {latency_ms} ms: {last_error[:90]!r}",
                          file=sys.stderr)
                    await self._backoff(attempt, response.headers.get("retry-after"))
                    continue
                if response.status_code >= 400:
                    last_error = response.text[:300]
                    break
                try:
                    payload = response.json()
                    content, reasoning, finish = _extract(payload)
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    # A 200 with a malformed body is a transport fault, not an answer: retry it.
                    last_error = f"malformed 200 response ({type(exc).__name__}): {response.text[:200]}"
                    print(f"{_now()} retry {item['item_id']} attempt {attempt}: {last_error[:120]!r}", file=sys.stderr)
                    await self._backoff(attempt)
                    continue
                usage = payload.get("usage") or {}
                request_id = payload.get("id") or response.headers.get("inference-id")
                actual = _billed_cost(response)
                if actual is None and self.config.price is not None:
                    actual = cost_usd(
                        int(usage.get("prompt_tokens", 0)),
                        int(usage.get("completion_tokens", 0)),
                        self.config.price,
                    )
                await self._write({
                    **base,
                    "status": "ok",
                    "response": content,
                    "reasoning": reasoning,
                    "finish_reason": finish,
                    "usage": usage,
                    "cost_usd": actual,
                    "request_id": request_id,
                    "served_model": payload.get("model"),
                    "latency_ms": latency_ms,
                    "attempts": attempt,
                    "http_status": response.status_code,
                    "timestamp": _now(),
                })
                self.state.done.add(item["item_id"])
                self.state.consecutive_failures = 0
                return
            await self._write({
                **base,
                "status": "failed",
                "response": None,
                "error": last_error,
                "http_status": last_status,
                "attempts": attempt,
                "timestamp": _now(),
            })
            self.state.failed.add(item["item_id"])
            self.state.consecutive_failures += 1
            if self.state.consecutive_failures >= CIRCUIT_BREAKER:
                raise EndpointDown(f"{CIRCUIT_BREAKER} consecutive failures, last: HTTP {last_status}")
        finally:
            await self.guard.settle(worst, self.config.run_id, item["item_id"], request_id, actual)

    async def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        if attempt >= MAX_ATTEMPTS:
            return
        delay = self.sleep_base_s * 2 ** (attempt - 1) + random.uniform(0, self.sleep_base_s)
        if retry_after and retry_after.replace(".", "", 1).isdigit():
            delay = max(delay, float(retry_after))
        await asyncio.sleep(min(delay, 60.0))

    async def run(self, items: list[dict[str, Any]]) -> RunState:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for item in items:
            queue.put_nowait(item)
        bucket = TokenBucket(self.config.rpm)
        headers = {"User-Agent": USER_AGENT}
        if self.config.provider.api_key:
            headers["Authorization"] = f"Bearer {self.config.provider.api_key}"
        stop = asyncio.Event()

        def request_stop(signum: int) -> None:
            if self.state.stop_reason is None:
                self.state.stop_reason = f"signal {signal.Signals(signum).name}; in-flight requests finished"
                self.state.stop_kind = "signal"
            stop.set()

        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, request_stop, signum)

        async def worker(client: httpx.AsyncClient) -> None:
            while not stop.is_set():
                if self.stop_at is not None and datetime.now(UTC) >= self.stop_at:
                    if self.state.stop_reason is None:
                        self.state.stop_reason = f"time limit {self.stop_at.isoformat()} reached"
                        self.state.stop_kind = "deadline"
                    stop.set()
                    return
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await self._call(client, bucket, item)
                except (BudgetExhausted, StopRun) as exc:
                    if self.state.stop_reason is None:
                        self.state.stop_reason = str(exc)
                        self.state.stop_kind = "endpoint" if isinstance(exc, EndpointDown) else "budget"
                    stop.set()

        async with httpx.AsyncClient(
            headers=headers, timeout=self.config.timeout_s, transport=self.transport
        ) as client:
            await asyncio.gather(*(worker(client) for _ in range(self.config.workers)))
        return self.state


def write_meta(path: Path, config: RunConfig, items_sha256: str, extra: dict[str, Any] | None = None) -> None:
    """Record run parameters once; refuse to resume a file made with different ones."""
    meta = {**config.meta(), "items_sha256": items_sha256, **(extra or {})}
    if path.exists():
        stored = json.loads(path.read_text())
        mismatched = {
            key for key in meta
            if key not in {"started_at", "workers", "rpm"} and stored.get(key) != meta[key]
        }
        if mismatched:
            raise SystemExit(f"{path} was written with different settings: {sorted(mismatched)}")
        return
    meta["started_at"] = _now()
    path.write_text(json.dumps(meta, indent=2) + "\n")


def report_remaining(remaining: list[str], path: Path) -> None:
    path.write_text("\n".join(remaining) + ("\n" if remaining else ""))
    print(f"{len(remaining)} items remain; ids written to {path}", file=sys.stderr)
    if remaining:
        print(" ".join(remaining), file=sys.stderr)
