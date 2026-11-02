"""Small SoCLaaS client wrapper for AGORA.

Uses NUS School of Computing's documented OpenAI-compatible chat endpoint.
Model support varies; intentionally avoid API-specific structured-output features.
"""
from __future__ import annotations
import json
import os
from typing import Any

BASE_URL = "https://soclaas-api.comp.nus.edu.sg/v1"


def get_client():
    key = os.getenv("SOCLAAS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Missing SOCLAAS_API_KEY. Sign in to the NUS SoCLaaS portal "
            "on the NUS network, create a key, and export it in this terminal."
        )
    # Lazy import ensures no API dependency for offline tests.
    from openai import OpenAI
    return OpenAI(api_key=key, base_url=BASE_URL, timeout=240.0, max_retries=2)


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a model response as a single JSON object; never execute model text."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("SoCLaaS model returned no text")
    text = raw.strip()
    # Accept a single markdown fence from models that wrap JSON unexpectedly.
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or lines[0].strip().lower() not in ("```", "```json") or lines[-1].strip() != "```":
            raise ValueError("LLM response is not a standalone JSON object")
        text = "\n".join(lines[1:-1]).strip()
    if len(text) > 20000:
        raise ValueError("LLM response too long")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM did not return valid JSON; no repair action will execute") from exc
    if not isinstance(value, dict):
        raise ValueError("LLM JSON must be an object")
    return value


def chat_json(*, model: str, messages: list[dict[str, str]], client=None) -> dict[str, Any]:
    """Submit to /v1/chat/completions and parse strict JSON.

    Caller must apply its own Pydantic / action-whitelist validation afterwards.
    No `response_format`, temperature, tool calls, or model-specific features:
    these are not guaranteed across SoCLaaS models.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Choose a SoCLaaS chat model with --model or SOCLAAS_MODEL")
    if client is None:
        client = get_client()
    result = client.chat.completions.create(model=model, messages=messages)
    if not result.choices:
        raise RuntimeError("SoCLaaS returned no choices")
    first = result.choices[0]
    if getattr(first, "finish_reason", None) == "length":
        raise RuntimeError("SoCLaaS model output was truncated; no action executed")
    return parse_json_object(first.message.content)
