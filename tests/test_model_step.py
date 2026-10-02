import json

import pytest

from app import activities, llm, telegram


@pytest.fixture
def no_telegram(monkeypatch):
    sent = []

    async def fake_send(text, reply_markup=None, turn_id=None):
        sent.append(text)
        return [len(sent)]

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(telegram, "send", fake_send)
    monkeypatch.setattr(telegram, "send_chat_action", nothing)
    return sent


@pytest.fixture
def fake_model(monkeypatch):
    script, seen = [], []

    async def chat(kind, model, messages, tools=None, max_tokens=2000):
        seen.append({"messages": json.loads(json.dumps(messages)), "tools": tools})
        nxt = script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    monkeypatch.setattr(llm, "chat", chat)
    return script, seen


def tool_reply(*calls):
    return {"message": {"role": "assistant", "content": "", "reasoning_details": [{"signature": "sig"}],
                        "tool_calls": [{"id": cid, "type": "function", "function": {"name": n, "arguments": a}}
                                       for cid, n, a in calls]}, "finish_reason": "tool_calls"}


def text_reply(t):
    return {"message": {"role": "assistant", "content": t}, "finish_reason": "stop"}


async def new_turn(appdb, body="hi"):
    m = await appdb.fetchone("INSERT INTO messages (direction, body) VALUES ('in', %s) RETURNING id", (body,))
    return await activities.start_turn([{"kind": "message", "msg_id": m["id"]}]), m["id"]


async def test_start_turn_freezes_menu_and_context(appdb, no_telegram):
    turn_id, mid = await new_turn(appdb, "what's up")
    turn = await appdb.fetchone("SELECT * FROM agent_turns WHERE id = %s", (turn_id,))
    assert turn["trigger"] == "message" and turn["prompt_version"] == "v1"
    assert "react_to_message" in turn["tool_menu"] and "search_email" not in turn["tool_menu"]
    assert turn["messages"][0]["role"] == "user" and "what's up" in turn["messages"][0]["content"]
    assert (await appdb.fetchone("SELECT turn_id FROM messages WHERE id = %s", (mid,)))["turn_id"] == turn["id"]


async def test_start_turn_skips_consumed_messages(appdb, no_telegram):
    m = await appdb.fetchone("INSERT INTO messages (direction, body, consumed_by) VALUES ('in', '123456', 'browser:x') RETURNING id")
    assert await activities.start_turn([{"kind": "message", "msg_id": m["id"]}]) is None


async def test_tool_loop_messages_and_reasoning_round_trip(appdb, no_telegram, fake_model):
    script, seen = fake_model
    script += [tool_reply(("c1", "react_to_message", '{"emoji":"👀"}')), text_reply("done!")]
    turn_id, _ = await new_turn(appdb)
    r1 = await activities.model_step({"turn_id": turn_id, "step": 1})
    assert r1 == {"tool_calls": [{"id": "c1", "name": "react_to_message", "arguments": '{"emoji":"👀"}', "queue": "agent"}]}
    assert seen[0]["messages"][0]["role"] == "system"
    await appdb.execute("INSERT INTO tool_results (turn_id, tool_call_id, tool, content) VALUES (%s, 'c1', 'react_to_message', %s)",
                        (turn_id, json.dumps("reacted")))
    r2 = await activities.model_step({"turn_id": turn_id, "step": 2})
    assert r2 == {"reply": "done!"}
    sent_msgs = seen[1]["messages"]
    assert sent_msgs[2]["reasoning_details"] == [{"signature": "sig"}]  # assistant message sent back unchanged
    assert sent_msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": "reacted"}


async def test_missing_tool_result_is_reported_not_dropped(appdb, no_telegram, fake_model):
    script, seen = fake_model
    script += [tool_reply(("c1", "react_to_message", "{}")), text_reply("ok")]
    turn_id, _ = await new_turn(appdb)
    await activities.model_step({"turn_id": turn_id, "step": 1})
    await activities.model_step({"turn_id": turn_id, "step": 2})
    assert "not executed" in seen[1]["messages"][-1]["content"]


async def test_mid_turn_messages_are_appended(appdb, no_telegram, fake_model):
    script, seen = fake_model
    script += [tool_reply(("c1", "react_to_message", "{}")), text_reply("ok")]
    turn_id, _ = await new_turn(appdb)
    await activities.model_step({"turn_id": turn_id, "step": 1})
    m = await appdb.fetchone("INSERT INTO messages (direction, body) VALUES ('in', 'also check X') RETURNING id")
    await activities.model_step({"turn_id": turn_id, "step": 2, "extra": [m["id"]]})
    last = seen[1]["messages"][-1]
    assert last["role"] == "user" and "also check X" in last["content"]


async def test_retried_step_does_not_call_model_again(appdb, no_telegram, fake_model):
    script, seen = fake_model
    script.append(text_reply("hello"))
    turn_id, _ = await new_turn(appdb)
    assert await activities.model_step({"turn_id": turn_id, "step": 1}) == {"reply": "hello"}
    assert await activities.model_step({"turn_id": turn_id, "step": 1}) == {"reply": "hello"}  # retry
    assert len(seen) == 1


async def test_budget_exhausted_says_so_once(appdb, no_telegram, fake_model):
    script, _ = fake_model
    script += [llm.BudgetExhausted("cap"), llm.BudgetExhausted("cap")]
    turn_id, _ = await new_turn(appdb)
    r = await activities.model_step({"turn_id": turn_id, "step": 1})
    assert r["reply"] == activities.QUOTA_MESSAGE
    await appdb.execute("INSERT INTO messages (direction, body) VALUES ('out', %s)", (activities.QUOTA_MESSAGE,))
    turn2, _ = await new_turn(appdb)
    assert (await activities.model_step({"turn_id": turn2, "step": 1}))["reply"] == ""


async def test_permanent_error_is_not_retried(appdb, no_telegram, fake_model):
    from temporalio.exceptions import ApplicationError
    fake_model[0].append(llm.Permanent("400 bad"))
    turn_id, _ = await new_turn(appdb)
    with pytest.raises(ApplicationError) as e:
        await activities.model_step({"turn_id": turn_id, "step": 1})
    assert e.value.non_retryable
