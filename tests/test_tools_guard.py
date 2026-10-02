import json

import pytest

from app.agent import guard, tools
from app.agent.guard import Allowed, Denied, NeedsApproval
from app.agent.tools import TOOLS, Tool, definitions, menu_for

GMAIL_RO = "https://www.googleapis.com/auth/gmail.readonly"


async def _noop(ctx, args):
    return "ok"


@pytest.fixture
def fake_tools():
    added = {
        "zz_read": Tool("zz_read", "read", {"q": {"type": "string"}}, ("q",), _noop, tier="R"),
        "zz_mail": Tool("zz_mail", "mail", {"to": {"type": "string"}}, ("to",), _noop, tier="WO",
                        needs="gmail.readonly", render=lambda a: f"Send to {a['to']}"),
        "zz_maybe": Tool("zz_maybe", "maybe", {"mode": {"type": "string", "enum": ["read", "act"]}}, ("mode",), _noop,
                         tier=lambda a: "WO" if a["mode"] == "act" else "R",
                         limit_key=lambda a: f"zz_maybe:{a['mode']}"),
    }
    TOOLS.update(added)
    yield added
    for k in added:
        TOOLS.pop(k)


def test_menu_depends_on_connections(fake_tools):
    assert "zz_mail" not in menu_for({})
    connected = {"google": {"status": "connected", "scopes": [GMAIL_RO]}}
    assert "zz_mail" in menu_for(connected)
    assert "zz_mail" not in menu_for({"google": {"status": "needs_reauth", "scopes": [GMAIL_RO]}})
    m = menu_for(connected)
    assert m == sorted(m) and "react_to_message" in m


def test_definitions_are_strict_openai_functions(fake_tools):
    [d] = definitions(["zz_read"])
    assert d["type"] == "function" and d["function"]["name"] == "zz_read"
    assert d["function"]["parameters"] == {"type": "object", "properties": {"q": {"type": "string"}},
                                           "required": ["q"], "additionalProperties": False}


async def test_check_rejects_bad_calls(appdb, fake_tools):
    menu = ["zz_read"]
    assert isinstance(await guard.check("zz_mail", "{}", menu), Denied)            # not on this turn's menu
    assert isinstance(await guard.check("nope", "{}", menu + ["nope"]), Denied)     # unknown tool
    assert isinstance(await guard.check("zz_read", "{not json", menu), Denied)
    assert isinstance(await guard.check("zz_read", "[1]", menu), Denied)
    d = await guard.check("zz_read", '{"q": 5}', menu)
    assert isinstance(d, Denied) and "invalid arguments" in d.reason
    assert isinstance(await guard.check("zz_read", '{"q": "x", "extra": 1}', menu), Denied)
    ok = await guard.check("zz_read", '{"q": "x"}', menu)
    assert ok == Allowed({"q": "x"}, "R")


async def test_connection_is_rechecked_at_execution(appdb, fake_tools):
    # The menu was built while Google was connected; it got disconnected mid-turn.
    d = await guard.check("zz_mail", '{"to": "a@b.c"}', ["zz_mail"])
    assert isinstance(d, Denied) and "not connected" in d.reason


async def test_risky_tier_needs_approval_unless_approved(appdb, fake_tools):
    await appdb.execute("INSERT INTO connections (provider, status, scopes) VALUES ('google', 'connected', %s)", ([GMAIL_RO],))
    d = await guard.check("zz_mail", '{"to": "a@b.c"}', ["zz_mail"])
    assert d == NeedsApproval({"to": "a@b.c"}, "WO", "Send to a@b.c")
    assert isinstance(await guard.check("zz_mail", '{"to": "a@b.c"}', ["zz_mail"], approved=True), Allowed)


async def test_dynamic_tier(appdb, fake_tools):
    assert isinstance(await guard.check("zz_maybe", '{"mode": "read"}', ["zz_maybe"]), Allowed)
    assert isinstance(await guard.check("zz_maybe", '{"mode": "act"}', ["zz_maybe"]), NeedsApproval)


async def test_daily_limit(appdb, fake_tools, monkeypatch):
    monkeypatch.setitem(guard.DAILY_LIMITS, "zz_maybe:read", 2)
    for _ in range(2):
        await guard.audit("zz_maybe", "executed", detail={"limit_key": "zz_maybe:read"})
    d = await guard.check("zz_maybe", '{"mode": "read"}', ["zz_maybe"])
    assert isinstance(d, Denied) and "daily limit" in d.reason
    assert isinstance(await guard.check("zz_maybe", '{"mode": "act"}', ["zz_maybe"]), NeedsApproval)  # other bucket


async def test_audit_writes_row(appdb):
    await guard.audit("x", "denied", tier="R", detail={"reason": "test"})
    row = await appdb.fetchone("SELECT tool, decision, detail FROM audit_log")
    assert row["decision"] == "denied" and row["detail"] == {"reason": "test"}


@pytest.mark.parametrize("text,leaky", [
    ("here's your summary", False),
    ("token ya29.a0AfH6SMBxyz1234567890", True),
    ("refresh 1//0gAbCdEfGhIjKlMn", True),
    ("key sk-or-v1-0123456789abcdef0123456789abcdef", True),
    ("bot 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1", True),
    ("-----BEGIN RSA PRIVATE KEY-----", True),
])
def test_leak_patterns(text, leaky):
    assert (guard.leaks(text) is not None) == leaky


def test_leak_saved_secret():
    assert guard.leaks("your password is hunter22", [b"hunter22"])
    assert guard.leaks("ok", [b"hunter22"]) is None
    assert guard.leaks("a b c", [b"a"]) is None  # very short values are ignored (false positives)


async def test_react_tool(appdb, monkeypatch):
    from app import telegram
    seen = []

    async def fake_reaction(mid, emoji):
        seen.append((mid, emoji))

    monkeypatch.setattr(telegram, "set_reaction", fake_reaction)
    await appdb.execute("INSERT INTO messages (direction, tg_message_id, body) VALUES ('in', 77, 'hi')")
    out = await TOOLS["react_to_message"].handler(tools.ToolCtx("t", "c"), {"emoji": "👀"})
    assert out == "reacted" and seen == [(77, "👀")]
