from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from scrutineer.grade.judge import JudgeTask, describe_gold, judge_all, judge_messages, read_judgements

ITEM = {
    "item_id": "665-F8-de", "family": "F8", "lang": "de", "prompt": "Beschreiben Sie ...",
    "gold": {"outcome": "accepted", "fc_position": "reject", "yes_share": 58.25},
}


def test_gold_description_states_all_facts() -> None:
    text = describe_gold(ITEM)
    assert "ACCEPTED" in text and "REJECTING" in text and "58.25%" in text


def test_judge_never_sees_the_model_name() -> None:
    messages = judge_messages(ITEM, "Die Initiative wurde abgelehnt.")
    blob = json.dumps(messages).lower()
    assert "apertus" not in blob and "swiss-ai" not in blob


def test_judge_all_appends_and_resumes(tmp_path: Path) -> None:
    calls = []

    def server(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        verdict = json.dumps({"grade": "incorrect", "reason": "says rejected"})
        return httpx.Response(200, json={"choices": [{"message": {"content": verdict}}]})

    out = tmp_path / "R1.jsonl"
    task = JudgeTask("R1", ITEM, "abgelehnt", "F8")
    sent = asyncio.run(judge_all([task], out, "http://judge.test/v1", "abc", transport=httpx.MockTransport(server)))
    assert sent == 1
    assert read_judgements(out)["665-F8-de"]["grade"] == "incorrect"
    assert calls[0]["temperature"] == 0
    assert calls[0]["response_format"]["type"] == "json_schema"
    again = asyncio.run(judge_all([task], out, "http://judge.test/v1", "abc", transport=httpx.MockTransport(server)))
    assert again == 0 and len(calls) == 1
