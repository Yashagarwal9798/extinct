"""T-35 logging + usage report, T-36 wipe safety."""

import json
import logging

from app.logs import JsonFormatter, turn_id_var


def test_json_log_line_includes_turn_id():
    token = turn_id_var.set("turn-123")
    try:
        record = logging.LogRecord("x", logging.WARNING, __file__, 1, "budget hit %s", ("now",), None)
        line = json.loads(JsonFormatter().format(record))
    finally:
        turn_id_var.reset(token)
    assert line["msg"] == "budget hit now" and line["level"] == "WARNING" and line["turn_id"] == "turn-123"


def test_httpx_request_logs_are_silenced():
    from app import logs
    logs.setup()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING  # URLs contain the bot token


async def test_usage_report_runs(appdb, capsys):
    from scripts import usage
    await appdb.execute("INSERT INTO llm_calls (kind, model, prompt_tokens, completion_tokens) VALUES"
                        " ('main', 'm:free', 100, 10), ('browser', 'b:free', 200, 20), ('main', 'm:free', 50, 5)")
    await usage.main(1)
    out = capsys.readouterr().out
    assert "total requests: 3" in out and "left today: 42" in out and "m:free" in out


async def test_wipe_needs_exact_confirmation(appdb):
    from scripts.wipe import wipe
    assert await wipe("wipe") == ["Cancelled. Nothing was deleted."]
    assert await appdb.fetchone("SELECT 1 AS ok FROM pg_namespace WHERE nspname = 'app'")


async def test_eval_runner_with_fake_model(appdb, monkeypatch, capsys):
    from app import llm, telegram
    from scripts import eval_scenarios

    async def chat(kind, model, messages, tools=None, max_tokens=2000):
        return {"message": {"role": "assistant", "content": "I can chat, remember things, use Gmail and a browser."},
                "finish_reason": "stop"}

    async def nothing(*a, **k):
        return [1]

    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(telegram, "send", nothing)
    monkeypatch.setattr(telegram, "send_chat_action", nothing)
    await eval_scenarios.main(["chat", "memory_save"], False)
    out = capsys.readouterr().out
    assert "[PASS] chat" in out and "[FAIL] memory_save" in out and "1/2 passed" in out
