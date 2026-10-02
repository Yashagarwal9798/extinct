import re
from pathlib import Path

from app import activities


async def test_three_tool_calls_three_audit_rows(appdb):
    turn = await appdb.fetchone("INSERT INTO agent_turns (tool_menu) VALUES (%s) RETURNING id",
                                (["remember_fact", "search_history"],))
    tid = str(turn["id"])
    calls = [("c1", "remember_fact", '{"kind": "other", "content": "a"}'),
             ("c2", "remember_fact", '{"kind": "other", "content": "b"}'),
             ("c3", "search_history", '{"query": "a"}')]
    for cid, name, args in calls:
        await activities.run_tool({"turn_id": tid, "call": {"id": cid, "name": name, "arguments": args}})
    rows = await appdb.fetchall("SELECT tool, decision, detail FROM audit_log ORDER BY id")
    assert [(r["tool"], r["decision"]) for r in rows] == [
        ("remember_fact", "executed"), ("remember_fact", "executed"), ("search_history", "executed")]
    assert rows[0]["detail"]["limit_key"] == "remember_fact"


async def test_retried_tool_call_is_not_audited_twice(appdb):
    turn = await appdb.fetchone("INSERT INTO agent_turns (tool_menu) VALUES (%s) RETURNING id", (["remember_fact"],))
    call = {"id": "c1", "name": "remember_fact", "arguments": '{"kind": "other", "content": "x"}'}
    for _ in range(2):
        await activities.run_tool({"turn_id": str(turn["id"]), "call": call})
    assert (await appdb.fetchone("SELECT count(*) AS n FROM audit_log"))["n"] == 1


async def test_denied_call_is_audited(appdb):
    turn = await appdb.fetchone("INSERT INTO agent_turns (tool_menu) VALUES (%s) RETURNING id", (["search_history"],))
    await activities.run_tool({"turn_id": str(turn["id"]), "call": {"id": "c1", "name": "send_email", "arguments": "{}"}})
    row = await appdb.fetchone("SELECT decision, detail FROM audit_log")
    assert row["decision"] == "denied" and "not available" in row["detail"]["reason"]


def test_no_code_updates_or_deletes_audit_rows():
    """Append-only by convention (the server is the table owner, so grants can't enforce it)."""
    for path in Path("app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"(UPDATE|DELETE FROM)\s+audit_log", src, re.I), path
