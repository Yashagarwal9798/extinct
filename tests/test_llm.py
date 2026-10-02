import json

import httpx
import pytest

from app import llm


@pytest.fixture
def fake_api(monkeypatch):
    sent, replies = [], []

    def handler(request):
        sent.append(json.loads(request.content))
        status, body = replies.pop(0)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(llm, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return sent, replies


def ok(message, finish="stop", usage=None):
    return 200, {"choices": [{"message": message, "finish_reason": finish}],
                 "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2}}


async def test_tool_calls_are_normalized_and_call_is_logged(appdb, fake_api):
    sent, replies = fake_api
    replies.append(ok({"role": "assistant", "content": None, "tool_calls": [
        {"type": "function", "function": {"name": "f", "arguments": {"x": 1}}}],  # no id, object args
        "reasoning_details": [{"type": "reasoning.text", "text": "t", "signature": "s"}]}, "tool_calls"))
    r = await llm.chat("main", "m:free", [{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    call = r["message"]["tool_calls"][0]
    assert call["id"].startswith("call_") and json.loads(call["function"]["arguments"]) == {"x": 1}
    assert r["message"]["content"] == "" and r["message"]["reasoning_details"][0]["signature"] == "s"
    assert sent[0]["model"] == "m:free" and sent[0]["tools"] and sent[0]["max_tokens"] == 2000
    row = await appdb.fetchone("SELECT kind, model, status, prompt_tokens FROM llm_calls")
    assert row == {"kind": "main", "model": "m:free", "status": "ok", "prompt_tokens": 10}


async def test_extra_json_is_merged(appdb, fake_api, monkeypatch):
    from app.config import get_settings
    sent, replies = fake_api
    replies.append(ok({"content": "hi"}))
    monkeypatch.setenv("LLM_EXTRA_JSON", '{"reasoning": {"effort": "low"}}')
    get_settings.cache_clear()
    try:
        await llm.chat("main", "m", [])
    finally:
        monkeypatch.delenv("LLM_EXTRA_JSON")
        get_settings.cache_clear()
    assert sent[0]["reasoning"] == {"effort": "low"}


@pytest.mark.parametrize("status,body,exc", [
    (429, {"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-min"}}, llm.Retryable),
    (429, {"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day"}}, llm.BudgetExhausted),
    (503, {"error": {"code": 503, "message": "provider down"}}, llm.Retryable),
    (400, {"error": {"code": 400, "message": "bad request"}}, llm.Permanent),
    (401, {"error": {"code": 401, "message": "no auth"}}, llm.Permanent),
    (200, {"error": {"code": 502, "message": "upstream"}}, llm.Retryable),   # error inside a 200
    (200, {"choices": []}, llm.Retryable),
])
async def test_error_mapping(appdb, fake_api, status, body, exc):
    fake_api[1].append((status, body))
    with pytest.raises(exc):
        await llm.chat("main", "m", [])


async def test_our_daily_budget_stops_before_calling(appdb, fake_api, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("LLM_DAILY_REQUESTS", "2")
    get_settings.cache_clear()
    try:
        await appdb.execute("INSERT INTO llm_calls (kind, model) VALUES ('main','m'), ('main','m')")
        await appdb.execute("INSERT INTO llm_calls (kind, model, at) VALUES ('main','m', now() - interval '2 days')")
        with pytest.raises(llm.BudgetExhausted):
            await llm.chat("main", "m", [])
        assert fake_api[0] == []  # never reached the API
    finally:
        monkeypatch.delenv("LLM_DAILY_REQUESTS")
        get_settings.cache_clear()
