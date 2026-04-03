"""LLM client abstraction supporting Ollama and Anthropic via instructor."""
from __future__ import annotations

import os
from typing import TypeVar, Type

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

OLLAMA_DEFAULT_MODEL = os.environ.get("SCHEMALYTICS_OLLAMA_MODEL", "gemma3:12b-it-qat")
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_RETRIES = 3

# Singleton Ollama client — created once, reused across all calls.
_ollama_client: object | None = None


def get_provider() -> str:
    """Return the active LLM provider from env var (default: ollama)."""
    return os.environ.get("SCHEMALYTICS_LLM_PROVIDER", "ollama").lower()


def _get_ollama_client() -> object:
    """Return (and lazily initialise) the shared Ollama instructor client."""
    global _ollama_client
    if _ollama_client is None:
        from openai import OpenAI
        import instructor

        # timeout=600: a 12B model at 15 tok/s needs ~200s for 3000 tokens.
        # 120s (old value) caused instructor to time-out and retry 3× per call.
        _ollama_client = instructor.from_openai(
            OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=600),
            mode=instructor.Mode.JSON,
        )
    return _ollama_client


def query_structured(
    system: str,
    user: str,
    response_model: Type[T],
    model: str | None = None,
    max_tokens: int = 4096,
) -> T:
    """Query the LLM and return a structured Pydantic model response via instructor.

    Provider is selected via the SCHEMALYTICS_LLM_PROVIDER env var:
      - "ollama"    (default) — local Ollama at localhost:11434
      - "anthropic" — Anthropic API, requires ANTHROPIC_API_KEY

    Pass a per-agent max_tokens to avoid over-generating. A 12B model at
    15 tok/s burns ~9 min at 8192 tokens; right-sizing this is the single
    largest performance lever for local inference.
    """
    provider = get_provider()

    if model is None:
        model = ANTHROPIC_DEFAULT_MODEL if provider == "anthropic" else OLLAMA_DEFAULT_MODEL

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    if provider == "anthropic":
        import anthropic
        import instructor

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY env var is required when SCHEMALYTICS_LLM_PROVIDER=anthropic"
            )

        client = instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            response_model=response_model,
            max_retries=MAX_RETRIES,
        )

    else:  # ollama
        client = _get_ollama_client()
        return client.chat.completions.create(
            model=model,
            messages=messages,
            response_model=response_model,
            max_retries=MAX_RETRIES,
            temperature=0,
            max_tokens=max_tokens,
            # num_ctx: ensure KV cache covers the full prompt (fixed across all
            # calls — changing num_ctx triggers a full model reload in Ollama).
            # num_predict: explicitly set generation limit so it overrides any
            # Modelfile default (which can silently ignore max_tokens otherwise).
            extra_body={"num_ctx": 12288, "num_predict": max_tokens},
        )
