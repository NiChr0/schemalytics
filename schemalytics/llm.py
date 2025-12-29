"""Ollama LLM client."""
import json
import httpx
from typing import Any
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen-data:latest"
FALLBACK_MODEL = "qwen2.5-coder:7b"
LLM_TIMEOUT = 900.0  # 15 minutes for local models


def check_ollama_available() -> bool:
    """Check if Ollama is running and available."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except:
        return False


def query(prompt: str, model: str = DEFAULT_MODEL, json_mode: bool = False) -> str:
    """Send prompt to Ollama, return response text."""
    start_time = datetime.now()
    print(f"  ⏰ Started: {start_time.strftime('%I:%M:%S %p')}")
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    
    try:
        resp = httpx.post(OLLAMA_URL, json=payload, timeout=LLM_TIMEOUT)
        resp.raise_for_status()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"  ✓ Completed in {elapsed:.1f}s")
        
        return resp.json()["response"]
    except httpx.TimeoutException:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"  ⚠️  LLM timeout after {elapsed:.1f}s (model: {model})")
        if model != FALLBACK_MODEL:
            print(f"  ⚠️  Trying fallback model: {FALLBACK_MODEL}")
            return query(prompt, model=FALLBACK_MODEL, json_mode=json_mode)
        raise
    except httpx.HTTPError as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"  ⚠️  LLM error after {elapsed:.1f}s: {e}")
        if model != FALLBACK_MODEL:
            print(f"  ⚠️  Trying fallback model: {FALLBACK_MODEL}")
            return query(prompt, model=FALLBACK_MODEL, json_mode=json_mode)
        raise


def query_json(prompt: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Query LLM and parse JSON response."""
    response = query(prompt, model=model, json_mode=True)
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  Failed to parse LLM JSON response: {e}")
        print(f"  Raw response: {response[:200]}...")
        raise