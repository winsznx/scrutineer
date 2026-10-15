"""Replay F1 items on the official Apertus 1.5 8B weights and compare with the hosted run.

This checks that the Public AI endpoint serves the official checkpoint: 100 F1 items,
seeded sample, greedy decoding, same chat template and `max_tokens` as the hosted run.
Needs `pip install -e ".[replay]"`, swiss-ai's transformers build for Apertus 1.5 and an
`HF_TOKEN` that has accepted the model licence.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from scrutineer.grade.parse import parse_label
from scrutineer.run.runner import DEFAULT_MAX_TOKENS, read_records

MODEL_ID = "swiss-ai/Apertus-v1.5-8B"
SAMPLE_SEED = 0
SAMPLE_SIZE = 100


def sample_items(items: list[dict[str, Any]], hosted: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """F1 items in de/fr/it/en that the hosted run answered, sampled with a fixed seed."""
    pool = sorted(
        (i for i in items if i["family"] == "F1" and i["lang"] in {"de", "fr", "it", "en"}
         and hosted.get(i["item_id"], {}).get("status") == "ok"),
        key=lambda i: i["item_id"],
    )
    return random.Random(SAMPLE_SEED).sample(pool, min(SAMPLE_SIZE, len(pool)))


def generate(items: list[dict[str, Any]], out_path: Path, device: str | None = None) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    done = read_records(out_path)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)
    target = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model.to(target).eval()
    revision = getattr(model.config, "_commit_hash", None)
    with out_path.open("a", encoding="utf-8") as handle:
        for item in items:
            if item["item_id"] in done:
                continue
            messages = [{"role": "user", "content": item["prompt"]}]
            inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(target)
            with torch.no_grad():
                output = model.generate(inputs, max_new_tokens=DEFAULT_MAX_TOKENS, do_sample=False)
            text = tokenizer.decode(output[0, inputs.shape[1]:], skip_special_tokens=True)
            handle.write(json.dumps({"item_id": item["item_id"], "status": "ok", "response": text,
                                     "model": MODEL_ID, "revision": revision, "dtype": "bfloat16",
                                     "device": target}, ensure_ascii=False) + "\n")
            handle.flush()


def agreement(items: list[dict[str, Any]], local: dict[str, dict[str, Any]],
              hosted: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pairs = [(i, local[i["item_id"]]["response"], hosted[i["item_id"]]["response"])
             for i in items if i["item_id"] in local]
    labels = [(parse_label(a, i["lang"], "F1"), parse_label(b, i["lang"], "F1")) for i, a, b in pairs]
    n = len(pairs)
    return {
        "model": MODEL_ID,
        "hosted_run": "R2",
        "n": n,
        "label_agreement": round(sum(a == b for a, b in labels) / n, 6) if n else None,
        "exact_agreement": round(sum(a.strip() == b.strip() for _, a, b in pairs) / n, 6) if n else None,
        "disagreements": [i["item_id"] for (i, _, _), (a, b) in zip(pairs, labels, strict=True) if a != b],
    }
