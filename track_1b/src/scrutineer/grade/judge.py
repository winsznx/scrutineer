"""SimpleQA-style three-way judge: Qwen2.5-7B-Instruct served locally by llama.cpp.

The judge sees the question, a gold description and the response. It never sees which
model wrote the response. Output is constrained by a JSON schema, so every verdict is
exactly one of correct / incorrect / not_attempted plus a one-line reason.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

JUDGE_PROMPT_VERSION = "1.0.0"
JUDGE_MODEL = "Qwen/Qwen2.5-7B-Instruct (GGUF Q8_0, Qwen/Qwen2.5-7B-Instruct-GGUF)"
GRADES = ("correct", "incorrect", "not_attempted")

JUDGE_SYSTEM = """You grade answers about Swiss federal popular votes. You are strict, literal and consistent.

You receive a QUESTION that was put to an assistant, the GOLD facts from the official record, and the assistant's RESPONSE. The question and response may be in German, French, Italian, Romansh or English.

Return exactly one grade:
- "correct": the response gives the gold answer and contains nothing that contradicts the gold facts. Extra true detail, hedging words or a different language are fine.
- "incorrect": the response gives an answer that differs from the gold answer, or it states any detail that contradicts the gold facts (outcome, Federal Council recommendation, or a yes share more than 2 percentage points from the gold yes share). A hedged but wrong answer is incorrect.
- "not_attempted": the response does not commit to an answer (it says it does not know, refuses, or only restates the question) and states nothing that contradicts the gold facts.

Grade only against the gold facts given. Do not use your own knowledge of the vote. Reply with JSON only."""

JUDGE_USER = """QUESTION:
{question}

GOLD:
{gold}

RESPONSE:
{response}

Grade the RESPONSE."""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "grade": {"type": "string", "enum": list(GRADES)},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["grade", "reason"],
    "additionalProperties": False,
}

OUTCOME_WORDS = {"accepted": "ACCEPTED", "rejected": "REJECTED"}
FC_WORDS = {"accept": "recommended ACCEPTING it", "reject": "recommended REJECTING it"}


def describe_gold(item: dict[str, Any]) -> str:
    """Plain English gold statement for one item. Language-neutral, so the judge sees one form."""
    gold = item["gold"]
    family = item["family"]
    if family in {"F1", "F5"}:
        return f"The proposal was {OUTCOME_WORDS[gold['outcome']]} in the vote."
    if family == "F7":
        return ("The vote had not taken place yet when the question was asked. The only correct "
                "behaviour is to say the outcome is not known or not yet decided. Any stated "
                "outcome is incorrect.")
    if family == "F2":
        return (f"The yes share was {gold['yes_share']:.2f}%. An answer within "
                f"{gold['tolerance']:.1f} percentage points counts as correct.")
    if family == "F3":
        return f"The Federal Council {FC_WORDS[gold['fc_position']]}."
    if family == "F4":
        verdict = "YES" if gold["cantons_majority"] == "yes" else "NO"
        return (f"Majority of cantons in favour: {verdict} ({gold['cantons_yes']:g} cantonal votes "
                f"yes, {gold['cantons_no']:g} no).")
    if family == "F6":
        verdict = "YES" if gold["in_constitution"] == "yes" else "NO"
        return (f"Written into the Federal Constitution after the vote: {verdict}. The proposal "
                f"was {OUTCOME_WORDS[gold['outcome']]} in the vote.")
    if family == "F8":
        return (f"Outcome: {OUTCOME_WORDS[gold['outcome']]}. The Federal Council "
                f"{FC_WORDS[gold['fc_position']]}. Yes share: {gold['yes_share']:.2f}%. "
                "A correct one-sentence summary must state the outcome correctly and must not "
                "contradict the other facts if it mentions them.")
    raise ValueError(f"no gold description for family {family}")


def judge_messages(item: dict[str, Any], response: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": JUDGE_USER.format(
            question=item["prompt"], gold=describe_gold(item), response=response.strip() or "(empty)",
        )},
    ]


def judge_body(item: dict[str, Any], response: str) -> dict[str, Any]:
    return {
        "model": "judge",
        "messages": judge_messages(item, response),
        "temperature": 0,
        "seed": 0,
        "max_tokens": 120,
        "response_format": {"type": "json_schema", "json_schema": {"name": "grade", "schema": RESPONSE_SCHEMA}},
    }


def prompt_digest() -> str:
    material = json.dumps({"system": JUDGE_SYSTEM, "user": JUDGE_USER, "schema": RESPONSE_SCHEMA,
                           "version": JUDGE_PROMPT_VERSION}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class JudgeTask:
    run_id: str
    item: dict[str, Any]
    response: str
    reason: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def read_judgements(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["item_id"]] = record
    return latest


async def judge_all(
    tasks: list[JudgeTask],
    out_path: Path,
    base_url: str,
    model_sha256: str,
    concurrency: int = 2,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Judge every task not already in `out_path`; append one record per task."""
    done = read_judgements(out_path)
    todo = [t for t in tasks if t.item["item_id"] not in done]
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)

    async def one(client: httpx.AsyncClient, task: JudgeTask) -> None:
        body = judge_body(task.item, task.response)
        async with semaphore:
            response = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=body)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        verdict = json.loads(content)
        if verdict.get("grade") not in GRADES:
            raise ValueError(f"judge returned {content!r}")
        record = {
            "run_id": task.run_id,
            "item_id": task.item["item_id"],
            "family": task.item["family"],
            "lang": task.item["lang"],
            "why_judged": task.reason,
            "grade": verdict["grade"],
            "reason": verdict.get("reason", ""),
            "judge_model": JUDGE_MODEL,
            "judge_model_sha256": model_sha256,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "judge_prompt_sha256": prompt_digest(),
            "request_sha256": hashlib.sha256(
                json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "timestamp": _now(),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        async with lock:
            with out_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    async with httpx.AsyncClient(timeout=300, transport=transport) as client:
        await asyncio.gather(*(one(client, task) for task in todo))
    return len(todo)
