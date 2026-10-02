import json

import httpx
import pytest

from app import telegram
from app.telegram import Permanent, Retryable, buttons, split_bubbles, to_telegram_html


# ---------- formatting ----------

@pytest.mark.parametrize("md,expected", [
    ("**bold** and *it* and _it2_", "<b>bold</b> and <i>it</i> and <i>it2</i>"),
    ("<script>alert(1)</script> & co", "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co"),
    ("use `a<b>` here", "use <code>a&lt;b&gt;</code> here"),
    ("[docs](https://x.com/a?b=1&c=2)", '<a href="https://x.com/a?b=1&amp;c=2">docs</a>'),
    ("# Title", "<b>Title</b>"),
    ("- one\n- two", "• one\n• two"),
    ("snake_case_name stays", "snake_case_name stays"),
    ("2 * 3 * 4", "2 * 3 * 4"),
    ("| a | b |\n|---|---|\n| 1 | 2 |", "a · b\n1 · 2"),
])
def test_to_telegram_html(md, expected):
    assert to_telegram_html(md) == expected


def test_code_block_is_escaped_and_untouched():
    out = to_telegram_html("```python\nx = **not bold** < 3\n```")
    assert out == "<pre>x = **not bold** &lt; 3</pre>"


# ---------- splitting ----------

def test_short_text_is_one_bubble():
    assert split_bubbles("hi\n\nthere") == ["hi\n\nthere"]


def test_long_text_splits_on_paragraphs_and_caps_bubbles():
    paras = ["x" * 1000 for _ in range(20)]
    chunks = split_bubbles("\n\n".join(paras), max_bubbles=3, max_len=2100)
    assert len(chunks) == 3
    assert all(len(c) <= 2100 for c in chunks)
    assert chunks[-1].endswith("(cut off)")


def test_giant_paragraph_is_hard_split():
    chunks = split_bubbles("word " * 2000, max_bubbles=10, max_len=1000)
    assert all(len(c) <= 1000 for c in chunks) and len(chunks) > 5


def test_buttons_reject_long_callback_data():
    assert buttons(("Send", "appr:1:y"))["inline_keyboard"][0][0]["callback_data"] == "appr:1:y"
    with pytest.raises(ValueError):
        buttons(("x", "y" * 65))


# ---------- API calls against a fake Telegram ----------

@pytest.fixture
def fake_tg(monkeypatch):
    calls = []
    responses = []  # queue of (status, body) to return; default ok

    def handler(request: httpx.Request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.headers.get("content-type", "").startswith("application/json") else {}
        calls.append((method, body))
        status, payload = responses.pop(0) if responses else (200, {"ok": True, "result": {"message_id": len(calls)}})
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(telegram, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return calls, responses


async def test_error_mapping(fake_tg):
    calls, responses = fake_tg
    responses += [(429, {"ok": False, "error_code": 429, "description": "Too Many Requests"}),
                  (502, {"ok": False, "error_code": 502, "description": "Bad Gateway"}),
                  (400, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})]
    with pytest.raises(Retryable):
        await telegram.api("sendMessage")
    with pytest.raises(Retryable):
        await telegram.api("sendMessage")
    with pytest.raises(Permanent):
        await telegram.api("sendMessage")


async def test_send_records_rows_and_puts_buttons_on_last_bubble(fake_tg, appdb):
    calls, _ = fake_tg
    text = ("a" * 3000) + "\n\n" + ("b" * 3000)
    ids = await telegram.send(text, reply_markup=buttons(("OK", "x")))
    assert len(ids) == 2
    assert "reply_markup" not in calls[0][1] and "reply_markup" in calls[1][1]
    assert calls[0][1]["chat_id"] == 42 and calls[0][1]["parse_mode"] == "HTML"
    rows = await appdb.fetchall("SELECT direction, tg_message_id FROM messages ORDER BY id")
    assert [r["tg_message_id"] for r in rows] == ids and all(r["direction"] == "out" for r in rows)


async def test_bad_html_falls_back_to_plain_text(fake_tg, appdb):
    calls, responses = fake_tg
    responses.append((400, {"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities"}))
    await telegram.send("**a *b** c*")
    assert len(calls) == 2
    assert "parse_mode" not in calls[1][1] and calls[1][1]["text"] == "**a *b** c*"


async def test_dry_run_sends_nothing(fake_tg, appdb, monkeypatch):
    from app.config import get_settings
    calls, _ = fake_tg
    monkeypatch.setenv("TELEGRAM_DRY_RUN", "true")
    get_settings.cache_clear()
    try:
        await telegram.send("hello")
        await telegram.send_chat_action()
    finally:
        monkeypatch.delenv("TELEGRAM_DRY_RUN")
        get_settings.cache_clear()
    assert calls == []
    assert (await appdb.fetchone("SELECT body FROM messages"))["body"] == "hello"
