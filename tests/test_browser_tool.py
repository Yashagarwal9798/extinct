"""browser_task tool + takeover flow, with the browser itself faked (real-browser tests: test_browser.py)."""

import json

import pytest

from app import activities, browser, telegram
from app.agent import guard
from app.agent.tools import TOOLS, ToolCtx, ToolError


@pytest.fixture
def tg(monkeypatch):
    out = {"sent": [], "photos": [], "edits": []}

    async def send(text, reply_markup=None, turn_id=None):
        out["sent"].append((text, reply_markup))
        return [500 + len(out["sent"])]

    async def photo(image, caption="", turn_id=None):
        out["photos"].append(caption)
        return 1

    async def edit(mid, text):
        out["edits"].append(text)

    monkeypatch.setattr(telegram, "send", send)
    monkeypatch.setattr(telegram, "send_photo", photo)
    monkeypatch.setattr(telegram, "edit_message_text", edit)
    return out


def fake_browser(monkeypatch, result, actions=()):
    async def run(goal, mode, start_url=None, manager=None, on_action=None):
        for a in actions:
            await on_action(*a)
        return result

    monkeypatch.setattr(browser, "run_browser_task", run)


async def handler(args, turn_id=None):
    return await TOOLS["browser_task"].handler(ToolCtx(turn_id or "", "c1"), args)


async def test_done_returns_untrusted_summary_and_screenshot(appdb, tg, monkeypatch):
    fake_browser(monkeypatch, {"status": "done", "summary": "Top post: X", "screenshot": b"\xff\xd8jpeg"},
                 actions=[("click", {"id": 3}, "ok", "https://news.ycombinator.com/")])
    r = await handler({"goal": "top HN post", "mode": "read"})
    assert r["status"] == "done" and r["result"].startswith('<untrusted source="browser">') and r["user_text"] == "Top post: X"
    assert tg["photos"] == ["top HN post"]
    a = await appdb.fetchone("SELECT tool, decision, detail FROM audit_log")
    assert a["tool"] == "browser_action" and a["detail"]["action"] == "click"


async def test_failure_is_a_tool_error(appdb, tg, monkeypatch):
    fake_browser(monkeypatch, {"status": "failed", "reason": "captcha"})
    with pytest.raises(ToolError, match="captcha"):
        await handler({"goal": "x", "mode": "read"})


async def test_needs_user_sends_live_view_link_and_done_button(appdb, tg, monkeypatch):
    fake_browser(monkeypatch, {"status": "needs_user", "reason": "Discord login required"})
    r = await handler({"goal": "read my Discord DMs", "mode": "read", "start_url": "https://discord.com/app"})
    assert r["status"] == "needs_user" and "wait" in r["note"]
    text, markup = tg["sent"][0]
    assert "Discord login required" in text and "http://localhost:6080/vnc.html" in text
    data = markup["inline_keyboard"][0][0]["callback_data"]
    assert data.startswith("take:")
    row = await appdb.fetchone("SELECT tool, input, status FROM approvals")
    assert row["tool"] == "takeover" and row["input"]["goal"] == "read my Discord DMs" and row["status"] == "pending"
    # Tapping Done turns into an event the next turn sees
    claim = await activities.claim_approval({"data": data})
    assert claim["event"]["kind"] == "takeover_done"


async def test_act_mode_needs_approval_read_mode_does_not(appdb):
    menu = ["browser_task"]
    assert isinstance(await guard.check("browser_task", json.dumps({"goal": "read HN", "mode": "read"}), menu), guard.Allowed)
    d = await guard.check("browser_task", json.dumps({"goal": "post 'hi' on X", "mode": "act", "start_url": "https://x.com"}), menu)
    assert isinstance(d, guard.NeedsApproval)
    assert d.summary == "Do this in your browser:\npost 'hi' on X\n(start: https://x.com)"


async def test_bad_start_url_rejected(appdb):
    d = await guard.check("browser_task", json.dumps({"goal": "x", "mode": "read", "start_url": "file:///etc"}), ["browser_task"])
    assert isinstance(d, guard.Denied)


async def test_approved_act_task_sends_result(appdb, tg, monkeypatch):
    fake_browser(monkeypatch, {"status": "done", "summary": "Posted ✓", "screenshot": None})
    turn = await appdb.fetchone("INSERT INTO agent_turns (tool_menu) VALUES (%s) RETURNING id", (["browser_task"],))
    await activities.run_tool({"turn_id": str(turn["id"]), "call": {"id": "c1", "name": "browser_task",
                                                                      "arguments": '{"goal": "post hi", "mode": "act"}'}})
    appr = await appdb.fetchone("SELECT id FROM approvals")
    claim = await activities.claim_approval({"data": f"appr:{appr['id']}:y"})
    assert claim["queue"] == "browser"  # the approved task runs on the browser worker
    await activities.run_approved(claim["approval_id"])
    assert tg["edits"][-1].endswith("✓ Done") and tg["sent"][-1][0] == "Posted ✓"


async def test_approved_act_task_that_needs_takeover(appdb, tg, monkeypatch):
    fake_browser(monkeypatch, {"status": "needs_user", "reason": "Login required"})
    turn = await appdb.fetchone("INSERT INTO agent_turns (tool_menu) VALUES (%s) RETURNING id", (["browser_task"],))
    await activities.run_tool({"turn_id": str(turn["id"]), "call": {"id": "c1", "name": "browser_task",
                                                                      "arguments": '{"goal": "post hi", "mode": "act"}'}})
    appr = await appdb.fetchone("SELECT id FROM approvals WHERE tool = 'browser_task'")
    await activities.claim_approval({"data": f"appr:{appr['id']}:y"})
    await activities.run_approved(str(appr["id"]))
    assert "Waiting for you to take over" in tg["edits"][-1]
    assert (await appdb.fetchone("SELECT count(*) AS n FROM approvals WHERE tool = 'takeover'"))["n"] == 1
