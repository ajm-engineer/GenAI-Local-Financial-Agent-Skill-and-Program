from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

import requests

log = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OLLAMA = "http://localhost:11434"


class LLMError(RuntimeError):
    pass


def settings_for(config: dict, section: str | None = None) -> dict:
    base = dict(config.get("digest", {}))
    if section:
        base.update({k: v for k, v in (config.get(section) or {}).items()
                     if k in ("provider", "model", "local_model", "local_url",
                              "local_context", "local_temperature",
                              "web_search", "web_search_tool_type",
                              "web_search_max_uses")})
    return base


def complete(system: str, user: str, config: dict,
             want_json: bool = False, max_tokens: int = 2000,
             section: str | None = None) -> str:
    settings = settings_for(config, section)
    provider = settings.get("provider", "anthropic").lower()

    if provider == "ollama":
        return _ollama(system, user, settings, want_json, max_tokens)
    if provider == "anthropic":
        return _anthropic(system, user, settings, max_tokens)
    raise LLMError(f"unknown provider '{provider}' (use 'ollama' or 'anthropic')")


def _ollama(system: str, user: str, settings: dict,
            want_json: bool, max_tokens: int) -> str:
    url = settings.get("local_url", DEFAULT_OLLAMA).rstrip("/")
    model = settings.get("local_model", "qwen3.5:9b")
    ctx = int(settings.get("local_context", 32768))

    body = {
        "model": model,
        "prompt": user,
        "system": system,
        "stream": False,
        "options": {
            "temperature": float(settings.get("local_temperature", 0.2)),
            "num_ctx": ctx,
            "num_predict": max_tokens,
        },
    }
    if want_json:
        body["format"] = "json"

    try:
        resp = requests.post(f"{url}/api/generate", json=body, timeout=600)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError as exc:
        raise LLMError(
            f"cannot reach Ollama at {url}. Is `ollama serve` running? "
            f"({exc})") from exc
    except Exception as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc


def _anthropic(system: str, user: str, settings: dict, max_tokens: int) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY not set")

    body = {"model": settings.get("model", "claude-sonnet-5-5"),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}]}

    if settings.get("web_search"):
        body["tools"] = [{
            "type": settings.get("web_search_tool_type", "web_search_20250305"),
            "name": "web_search",
            "max_uses": int(settings.get("web_search_max_uses", 5)),
        }]

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={"x-api-key": api_key,
                     "anthropic-version": ANTHROPIC_VERSION,
                     "content-type": "application/json"},
            json=body,
            timeout=300 if settings.get("web_search") else 120)
        resp.raise_for_status()
        return "".join(b.get("text", "") for b in resp.json().get("content", [])
                       if b.get("type") == "text").strip()
    except Exception as exc:
        raise LLMError(f"Anthropic request failed: {exc}") from exc


def parse_json_array(text: str) -> list:
    text = text.strip()
    for fence in ("```json", "```JSON", "```"):
        text = text.replace(fence, "")
    text = text.strip()

    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            obj = json.loads(text[s:e + 1])
            if isinstance(obj, dict):
                for key in ("hypotheses", "claims", "results", "items"):
                    if isinstance(obj.get(key), list):
                        return obj[key]
                return [obj]
        raise LLMError("no JSON array found in model output")

    return json.loads(text[start:end + 1])


def parse_json_object(text: str) -> dict:
    text = text.strip()
    for fence in ("```json", "```JSON", "```"):
        text = text.replace(fence, "")
    s_, e_ = text.find("{"), text.rfind("}")
    if s_ == -1 or e_ <= s_:
        raise LLMError("no JSON object found in model output")
    obj = json.loads(text[s_:e_ + 1])
    if not isinstance(obj, dict):
        raise LLMError("model output was JSON but not an object")
    return obj


def template_base_rate(category: str, ledger_db: Path,
                       minimum: int = 8) -> float | None:
    if not ledger_db.exists():
        return None
    try:
        c = sqlite3.connect(ledger_db)
        row = c.execute(
            "SELECT COUNT(*), SUM(outcome) FROM hypotheses "
            "WHERE status='resolved' AND category=?", (category,)).fetchone()
        c.close()
    except Exception:
        return None

    n, hits = row[0] or 0, row[1] or 0
    if n < minimum:
        return None
    return round(hits / n, 2)


def assign_confidence(category: str, model_confidence: float | None,
                      config: dict, ledger_db: Path) -> tuple[float, str]:
    provider = config.get("digest", {}).get("provider", "anthropic").lower()

    if provider != "ollama":
        if model_confidence is not None:
            return float(model_confidence), "model"
        return 0.5, "default"

    base = template_base_rate(category, ledger_db)
    if base is not None:
        return base, f"base rate for '{category}'"
    return 0.5, "default (insufficient history for a base rate)"
