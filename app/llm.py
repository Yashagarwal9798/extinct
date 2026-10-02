"""Model calls through any OpenAI-compatible chat-completions endpoint (default: OpenRouter free models).

Every call: daily budget check first (free tier: 50 requests/day), then one llm_calls row.
No retries here: Temporal retries activities. Errors:
    Retryable        per-minute 429, 5xx, timeouts, empty answers  -> Temporal retries
    BudgetExhausted  daily cap (ours or the provider's)            -> friendly message, no retry
    Permanent        400/401/403/404 ...                            -> no retry

Probe findings (scripts/llm_probe.py), 2026-10-02:
    stealth/space-bunny-alpha: tool calls OK (ids present), answers after tool results, parallel calls OK,
    image input OK, no reasoning_details, cost $0 per call. Stealth models may log prompts and can vanish.
"""

import json
import uuid

import httpx

from app import db
from app.config import get_settings


class LLMError(Exception):
    pass


class Retryable(LLMError):
    pass


class Permanent(LLMError):
    pass


class BudgetExhausted(LLMError):
    pass


_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    return _client


async def requests_today() -> int:
    row = await db.fetchone(
        "SELECT count(*) AS n FROM llm_calls WHERE at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'")
    return row["n"]


async def _record(kind: str, model: str, status: str, usage: dict | None = None) -> None:
    usage = usage or {}
    await db.execute(
        "INSERT INTO llm_calls (kind, model, status, prompt_tokens, completion_tokens, cost) VALUES (%s, %s, %s, %s, %s, %s)",
        (kind, model, status, usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("cost")),
    )


def _is_daily_cap(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("per-day", "per day", "daily", "free-models-per-day"))


def _normalize_tool_calls(calls: list | None) -> list[dict]:
    """Some free models omit ids or send arguments as objects; make every call well-formed."""
    out = []
    for c in calls or []:
        fn = c.get("function") or {}
        args = fn.get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args or {})
        out.append({"id": c.get("id") or f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                    "function": {"name": fn.get("name", ""), "arguments": args or "{}"}})
    return out


async def chat(kind: str, model: str, messages: list[dict], tools: list[dict] | None = None,
               max_tokens: int = 2000) -> dict:
    """One model request. Returns {"message": {...assistant message...}, "finish_reason": str}."""
    s = get_settings()
    if await requests_today() >= s.llm_daily_requests:
        raise BudgetExhausted(f"daily request budget ({s.llm_daily_requests}) used up")

    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, **s.llm_extra_json}
    if tools:
        payload["tools"] = tools
    try:
        resp = await _http().post(f"{s.llm_base_url}/chat/completions", json=payload,
                                  headers={"Authorization": f"Bearer {s.llm_api_key}"})
    except httpx.HTTPError as e:
        raise Retryable(f"network error: {e!r}") from e

    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    status = resp.status_code if resp.status_code != 200 or not err else int(err.get("code") or 500)
    if status != 200:
        await _record(kind, model, "error")
        text = json.dumps(err or body)[:500] if (err or body) else resp.text[:500]
        if status == 429:
            raise (BudgetExhausted if _is_daily_cap(text) else Retryable)(f"429: {text}")
        if status >= 500 or status == 408:
            raise Retryable(f"{status}: {text}")
        raise Permanent(f"{status}: {text}")

    choices = body.get("choices") or []
    if not choices or not choices[0].get("message"):
        await _record(kind, model, "error")
        raise Retryable("empty response (no choices)")
    await _record(kind, model, "ok", body.get("usage"))
    raw = choices[0]["message"]
    msg = {"role": "assistant", "content": raw.get("content") or ""}
    if calls := _normalize_tool_calls(raw.get("tool_calls")):
        msg["tool_calls"] = calls
    if raw.get("reasoning_details"):
        msg["reasoning_details"] = raw["reasoning_details"]  # must go back unchanged (Claude via OpenRouter)
    return {"message": msg, "finish_reason": choices[0].get("finish_reason") or "stop"}
