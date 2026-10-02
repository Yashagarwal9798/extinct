"""T-14 send_reply (G5) and T-15/T-16 memory tools."""

import pytest

from app import activities, telegram
from app.agent.tools import TOOLS, ToolCtx, ToolError

CTX = ToolCtx("t", "c")


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    async def fake_send(text, reply_markup=None, turn_id=None):
        sent.append(text)
        return [1]

    monkeypatch.setattr(telegram, "send", fake_send)
    return sent


async def _turn(appdb):
    return str((await appdb.fetchone("INSERT INTO agent_turns DEFAULT VALUES RETURNING id"))["id"])


async def test_send_reply_sends_and_closes_turn(appdb, outbox):
    tid = await _turn(appdb)
    await activities.send_reply({"turn_id": tid, "text": "hello", "status": "done"})
    assert outbox == ["hello"]
    row = await appdb.fetchone("SELECT status, ended_at FROM agent_turns")
    assert row["status"] == "done" and row["ended_at"]


async def test_send_reply_blocks_leaked_token(appdb, outbox):
    tid = await _turn(appdb)
    await activities.send_reply({"turn_id": tid, "text": "your token is ya29.a0AfH6SMBxyz1234567890", "status": "done"})
    assert "blocked" in outbox[0] and "ya29" not in outbox[0]
    assert (await appdb.fetchone("SELECT decision FROM audit_log"))["decision"] == "blocked"


async def test_empty_reply_sends_nothing(appdb, outbox):
    tid = await _turn(appdb)
    await activities.send_reply({"turn_id": tid, "text": "  ", "status": "done"})
    assert outbox == []


async def test_remember_dedupes_case_insensitively(appdb):
    a = await TOOLS["remember_fact"].handler(CTX, {"kind": "preference", "content": "I am vegetarian"})
    b = await TOOLS["remember_fact"].handler(CTX, {"kind": "preference", "content": "i am  VEGETARIAN "})
    assert a == b
    assert (await appdb.fetchone("SELECT count(*) AS n FROM memory_facts"))["n"] == 1


async def test_forget(appdb):
    saved = await TOOLS["remember_fact"].handler(CTX, {"kind": "person", "content": "Priya is my sister"})
    assert await TOOLS["forget_fact"].handler(CTX, {"fact_id": saved["saved"]}) == "forgotten"
    with pytest.raises(ToolError):
        await TOOLS["forget_fact"].handler(CTX, {"fact_id": "f999"})


async def test_search_history_finds_old_messages_and_facts(appdb):
    await appdb.execute("INSERT INTO messages (direction, body, sent_at) VALUES"
                        " ('in', 'the handyman Ramesh 98xxxx fixed the sink', now() - interval '30 days'),"
                        " ('in', 'what is for dinner', now())")
    await appdb.execute("INSERT INTO memory_facts (kind, content) VALUES ('person', 'Ramesh is the handyman')")
    r = await TOOLS["search_history"].handler(CTX, {"query": "handyman"})
    assert len(r["results"]) == 2 and r["results"][0].startswith("[") and "Fact: Ramesh" in r["results"][0]
    assert any("98xxxx" in x for x in r["results"])
    r = await TOOLS["search_history"].handler(CTX, {"query": "who was the handyman"})  # natural question still hits
    assert any("Ramesh" in x for x in r["results"])
    assert (await TOOLS["search_history"].handler(CTX, {"query": "zzzz"}))["results"] == []
