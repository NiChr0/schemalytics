"""Ollama LLM client."""
import json
import httpx
from typing import Any

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen-data:latest"
FALLBACK_MODEL = "qwen2.5-coder:7b"


def query(prompt: str, model: str = DEFAULT_MODEL, json_mode: bool = False) -> str:
    """Send prompt to Ollama, return response text."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    
    try:
        resp = httpx.post(OLLAMA_URL, json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()["response"]
    except httpx.HTTPError:
        if model != FALLBACK_MODEL:
            return query(prompt, model=FALLBACK_MODEL, json_mode=json_mode)
        raise


def query_json(prompt: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Query LLM and parse JSON response."""
    response = query(prompt, model=model, json_mode=True)
    return json.loads(response)
