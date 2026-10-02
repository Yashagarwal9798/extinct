"""Saved message -> dispatch -> ConversationWorkflow -> REAL activities (fake model, dry-run Telegram) -> reply row."""

import asyncio
import uuid

import pytest
from temporalio.worker import Worker

from app import clients, dispatch, llm
from app.config import get_settings
from app.worker import AGENT_ACTIVITIES
from app.workflows import ConversationWorkflow


@pytest.fixture
async def temporal_client():
    try:
        return await clients.temporal()
    except Exception:
        pytest.skip("Temporal not running")


async def test_message_to_reply_through_real_activities(appdb, temporal_client, monkeypatch):
    script = [
        {"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
                     "function": {"name": "remember_fact", "arguments": '{"kind": "preference", "content": "likes chai"}'}}]},
         "finish_reason": "tool_calls"},
        {"message": {"role": "assistant", "content": "Noted ☕"}, "finish_reason": "stop"},
    ]

    async def fake_chat(kind, model, messages, tools=None, max_tokens=2000):
        return script.pop(0)

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setenv("TELEGRAM_DRY_RUN", "true")
    get_settings.cache_clear()
    wf_id, queue = f"conv-{uuid.uuid4()}", f"q-{uuid.uuid4()}"
    monkeypatch.setattr(dispatch, "CONVERSATION_ID", wf_id)
    monkeypatch.setattr(dispatch, "AGENT_QUEUE", queue)
    try:
        row = await appdb.fetchone("INSERT INTO messages (direction, kind, body) VALUES ('in', 'text', 'I love chai') RETURNING id, kind, body")
        async with Worker(temporal_client, task_queue=queue, workflows=[ConversationWorkflow], activities=AGENT_ACTIVITIES):
            await dispatch.dispatch(row)
            for _ in range(150):
                out = await appdb.fetchone("SELECT body FROM messages WHERE direction = 'out'")
                if out:
                    break
                await asyncio.sleep(0.1)
            assert out and out["body"] == "Noted ☕"
            await temporal_client.get_workflow_handle(wf_id).terminate()
        turn = await appdb.fetchone("SELECT status, steps FROM agent_turns")
        assert turn == {"status": "done", "steps": 2}
        assert (await appdb.fetchone("SELECT tool, is_error FROM tool_results")) == {"tool": "remember_fact", "is_error": False}
        assert (await appdb.fetchone("SELECT content FROM memory_facts"))["content"] == "likes chai"
    finally:
        get_settings.cache_clear()


async def test_dispatch_failure_leaves_row_for_sweeper(appdb, monkeypatch):
    async def boom(*a, **k):
        raise ConnectionError("temporal down")

    monkeypatch.setattr(dispatch, "signal_conversation", boom)
    row = await appdb.fetchone("INSERT INTO messages (direction, kind, body) VALUES ('in', 'text', 'x') RETURNING id, kind, body")
    await dispatch.dispatch(row)  # must not raise
    assert not (await appdb.fetchone("SELECT dispatched FROM messages"))["dispatched"]
