import json

import pytest

from app import activities, telegram
from app.agent.tools import TOOLS, Tool


@pytest.fixture
def tg(monkeypatch):
    log = {"sent": [], "edits": []}

    async def fake_send(text, reply_markup=None, turn_id=None):
        log["sent"].append((text, reply_markup))
        return [900 + len(log["sent"])]

    async def fake_edit(mid, text):
        log["edits"].append((mid, text))

    monkeypatch.setattr(telegram, "send", fake_send)
    monkeypatch.setattr(telegram, "edit_message_text", fake_edit)
    return log


@pytest.fixture
def risky_tool():
    runs = []

    async def handler(ctx, args):
        runs.append(args)
        return {"sent_to": args["to"], "user_text": f"Mail to {args['to']} is on its way"}

    TOOLS["zz_send"] = Tool("zz_send", "send", {"to": {"type": "string"}}, ("to",), handler, tier="WO",
                            render=lambda a: f"Send email to {a['to']}")
    yield runs
    TOOLS.pop("zz_send")


async def make_turn(appdb, menu=("zz_send",)):
    row = await appdb.fetchone("INSERT INTO agent_turns (tool_menu) VALUES (%s) RETURNING id", (list(menu),))
    return str(row["id"])


async def ask(appdb, tg, risky_tool):
    turn_id = await make_turn(appdb)
    await activities.run_tool({"turn_id": turn_id, "call": {"id": "c1", "name": "zz_send", "arguments": '{"to": "john@x.com"}'}})
    appr = await appdb.fetchone("SELECT * FROM approvals")
    return turn_id, appr


async def test_risky_tool_asks_instead_of_running(appdb, tg, risky_tool):
    turn_id, appr = await ask(appdb, tg, risky_tool)
    assert risky_tool == []  # NOT executed
    text, markup = tg["sent"][0]
    assert text == "Send email to john@x.com"  # written by code, not by the model
    datas = [b["callback_data"] for b in markup["inline_keyboard"][0]]
    assert datas == [f"appr:{appr['id']}:y", f"appr:{appr['id']}:n"]
    assert appr["status"] == "pending" and appr["tg_message_id"] == 901
    result = await appdb.fetchone("SELECT content FROM tool_results")
    assert result["content"]["status"] == "approval_requested"


async def test_tap_yes_runs_once(appdb, tg, risky_tool):
    _, appr = await ask(appdb, tg, risky_tool)
    claim = await activities.claim_approval({"data": f"appr:{appr['id']}:y"})
    assert claim == {"run": True, "approval_id": str(appr["id"]), "queue": "agent"}
    await activities.run_approved(claim["approval_id"])
    await activities.run_approved(claim["approval_id"])  # a retry must not run it again
    assert risky_tool == [{"to": "john@x.com"}]
    row = await appdb.fetchone("SELECT status, result FROM approvals")
    assert row["status"] == "executed" and row["result"]["sent_to"] == "john@x.com"
    assert tg["edits"][-1] == (901, "Send email to john@x.com\n\n✓ Done")
    assert tg["sent"][-1][0] == "Mail to john@x.com is on its way"   # the tool's user_text
    decisions = [r["decision"] for r in await appdb.fetchall("SELECT decision FROM audit_log ORDER BY id")]
    assert decisions == ["needs_approval", "executed"]


async def test_double_tap_runs_once(appdb, tg, risky_tool):
    _, appr = await ask(appdb, tg, risky_tool)
    first = await activities.claim_approval({"data": f"appr:{appr['id']}:y"})
    second = await activities.claim_approval({"data": f"appr:{appr['id']}:y"})
    assert first["run"] and second == {}
    assert "expired or was already handled" in tg["sent"][-1][0]


async def test_expired_approval(appdb, tg, risky_tool):
    _, appr = await ask(appdb, tg, risky_tool)
    await appdb.execute("UPDATE approvals SET expires_at = now() - interval '1 minute'")
    assert await activities.claim_approval({"data": f"appr:{appr['id']}:y"}) == {}
    assert risky_tool == []


async def test_cancel(appdb, tg, risky_tool):
    _, appr = await ask(appdb, tg, risky_tool)
    assert await activities.claim_approval({"data": f"appr:{appr['id']}:n"}) == {}
    assert (await appdb.fetchone("SELECT status FROM approvals"))["status"] == "rejected"
    assert tg["edits"][-1][1].endswith("✗ Cancelled") and risky_tool == []


async def test_guard_rechecks_at_execution(appdb, tg, risky_tool, monkeypatch):
    _, appr = await ask(appdb, tg, risky_tool)
    await activities.claim_approval({"data": f"appr:{appr['id']}:y"})
    # Tool became unavailable between the tap and the run (e.g. disconnected): must not run.
    monkeypatch.setattr(activities, "menu_for", lambda conns: [])
    await activities.run_approved(str(appr["id"]))
    assert risky_tool == [] and (await appdb.fetchone("SELECT status FROM approvals"))["status"] == "failed"


async def test_takeover_done_becomes_event(appdb, tg):
    aid = await activities.request_approval(None, "takeover", {"goal": "read DMs"}, "Log in please", kind="take")
    assert tg["sent"][0][1]["inline_keyboard"][0][0]["callback_data"] == f"take:{aid}"
    assert await activities.claim_approval({"data": f"take:{aid}"}) == {"event": {"kind": "takeover_done", "approval_id": aid}}
    assert await activities.claim_approval({"data": f"take:{aid}"}) == {}  # second tap ignored


async def test_garbage_button_data_is_ignored(appdb, tg):
    assert await activities.claim_approval({"data": "appr:nonsense"}) == {}
    assert await activities.claim_approval({"data": "hello"}) == {}
    assert await activities.claim_approval({"data": "appr:not-a-uuid:y"}) == {}
    assert await activities.claim_approval({"data": "take:x"}) == {}
