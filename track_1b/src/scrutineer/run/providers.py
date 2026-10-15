"""OpenAI-compatible endpoints the runner can talk to, and their list prices."""

from __future__ import annotations

import os
from dataclasses import dataclass

USER_AGENT = "scrutineer/1.0 (+https://github.com/winsznx/scrutineer)"

# USD per 1M tokens (input, output), from Public AI's model catalogue on 2026-10-15
# (platform.publicai.co docs/src/modelCatalogData.ts; /v1/developer/pricing for the
# non-thinking ids). Thinking variants are listed at the same price as their base model.
PUBLICAI_PRICES: dict[str, tuple[float, float]] = {
    "swiss-ai/apertus-v1.5-8b": (0.10, 0.20),
    "swiss-ai/apertus-v1.5-8b-thinking": (0.10, 0.20),
    "swiss-ai/apertus-v1.5-70b": (0.82, 2.92),
    "swiss-ai/apertus-v1.5-70b-thinking": (0.82, 2.92),
}


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str | None
    model_suffix: str = ""
    billing_url: str | None = None

    def wire_model(self, model: str) -> str:
        return f"{model}{self.model_suffix}"

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def _publicai_key() -> str | None:
    return os.environ.get("LLM_API_KEY") or os.environ.get("PUBLIC_AI_API_KEY")


def resolve_provider(name: str) -> Provider:
    """`publicai` and `hf` are built in. `env` uses LLM_BASE_URL and LLM_API_KEY as given."""
    if name == "publicai":
        base = os.environ.get("LLM_BASE_URL", "https://api.publicai.co/v1")
        return Provider(
            name="publicai",
            base_url=base,
            api_key=_publicai_key(),
            billing_url=f"{base.rstrip('/')}/developer/billing",
        )
    if name == "hf":
        return Provider(
            name="hf",
            base_url="https://router.huggingface.co/v1",
            api_key=os.environ.get("HF_TOKEN"),
            model_suffix=":publicai",
        )
    if name == "env":
        env_base = os.environ.get("LLM_BASE_URL")
        if not env_base:
            raise SystemExit("--provider env needs LLM_BASE_URL")
        return Provider(name="env", base_url=env_base, api_key=os.environ.get("LLM_API_KEY"))
    raise SystemExit(f"unknown provider {name!r}; use publicai, hf or env")


def price_for(model: str) -> tuple[float, float] | None:
    return PUBLICAI_PRICES.get(model)
