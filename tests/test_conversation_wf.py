"""ConversationWorkflow against the real Temporal dev server (docker compose up -d temporal),
with fake activities that record calls and return scripted results."""

import asyncio
import time
import uuid

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from app.dispatch import signal_for
from app.workflows import ConversationWorkflow


@pytest.fixture
async def client():
    try:
        return await Client.connect("localhost:7233")
    except Exception:
        pytest.skip("Temporal not running (docker compose up -d temporal)")


class FakeAgent:
    """Fake activities with the real names. `steps` = scripted model_step results; default: reply 'ok'."""

    def __init__(self, steps=None, tool_seconds=0.0, fail_model=False):
        self.batches, self.replies, self.tool_runs, self.texts, self.buttons, self.approved = [], [], [], [], [], []
        self.steps = list(steps or [])
        rec = self

        @activity.defn(name="start_turn")
        async def start_turn(batch: list[dict]) -> str:
            rec.batches.append([i.get("msg_id") or i.get("kind") for i in batch])
            return f"turn-{len(rec.batches)}"

        @activity.defn(name="model_step")
        async def model_step(args: dict) -> dict:
            if fail_model:
                raise ApplicationError("model broke", non_retryable=True)
            return rec.steps.pop(0) if rec.steps else {"reply": "ok"}

        @activity.defn(name="run_tool")
        async def run_tool(args: dict) -> dict:
            start = time.monotonic()
            while time.monotonic() - start < tool_seconds:
                activity.heartbeat()
                await asyncio.sleep(0.2)
            rec.tool_runs.append((args["call"]["id"], start, time.monotonic()))
            return {"ok": True}

        @activity.defn(name="send_reply")
        async def send_reply(args: dict) -> None:
            rec.replies.append((args["text"], args["status"]))

        @activity.defn(name="send_text")
        async def send_text(text: str) -> None:
            rec.texts.append(text)

        @activity.defn(name="claim_approval")
        async def claim_approval(args: dict) -> dict:
            rec.buttons.append(args["data"])
            if args["data"].startswith("take:"):
                return {"event": {"kind": "takeover_done", "approval_id": args["data"][5:]}}
            return {"run": True, "approval_id": "a1", "queue": "agent"}

        @activity.defn(name="run_approved")
        async def run_approved(approval_id: str) -> None:
            rec.approved.append(approval_id)

        self.activities = [start_turn, model_step, run_tool, send_reply, send_text, claim_approval, run_approved]


async def start(client, queue, wf_id, signal, item, carry=None):
    await client.start_workflow(ConversationWorkflow.run, carry, id=wf_id, task_queue=queue,
                                start_signal=signal, start_signal_args=[item])


async def wait_for(pred, timeout=20):
    for _ in range(int(timeout * 10)):
        if pred():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not met in time")


def msg(i, stop=False):
    return {"kind": "message", "msg_id": i, "stop": stop}


def calls(*ids, queue="agent"):
    return {"tool_calls": [{"id": i, "name": "t", "arguments": "{}", "queue": queue} for i in ids]}


async def run_case(client, agent, body, browser=False):
    queue, wf_id = f"q-{uuid.uuid4()}", f"conv-{uuid.uuid4()}"
    workers = [Worker(client, task_queue=queue, workflows=[ConversationWorkflow], activities=agent.activities)]
    if browser:  # browser tools run on the "browser" queue: a second worker serves it
        workers.append(Worker(client, task_queue="browser", activities=agent.activities))
    async with workers[0]:
        if browser:
            async with workers[1]:
                await body(queue, wf_id)
        else:
            await body(queue, wf_id)
    await client.get_workflow_handle(wf_id).terminate()


async def test_burst_becomes_one_turn_and_duplicates_are_dropped(client):
    agent = FakeAgent()

    async def body(queue, wf_id):
        for i in (1, 2, 2, 3):
            await start(client, queue, wf_id, "new_message", msg(i))
            await asyncio.sleep(0.3)
        await wait_for(lambda: agent.replies)
        await asyncio.sleep(3)
        assert agent.batches == [[1, 2, 3]] and agent.replies == [("ok", "done")]
        status = await client.get_workflow_handle(wf_id).query(ConversationWorkflow.status)
        assert status["turns"] == 1 and status["state"] == "idle"

    await run_case(client, agent, body)


async def test_parallel_tools_then_reply(client):
    agent = FakeAgent(steps=[calls("c1", "c2"), {"reply": "both done"}], tool_seconds=1.5)

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "new_message", msg(1))
        await wait_for(lambda: agent.replies)
        (_, s1, e1), (_, s2, e2) = agent.tool_runs
        assert s1 < e2 and s2 < e1, "tools should overlap in time"
        assert agent.replies == [("both done", "done")]

    await run_case(client, agent, body)


async def test_step_limit(client):
    agent = FakeAgent(steps=[calls(f"c{i}") for i in range(20)])

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "new_message", msg(1))
        await wait_for(lambda: agent.replies, timeout=60)
        assert len(agent.tool_runs) == 14 and agent.replies[0][1] == "failed"

    await run_case(client, agent, body)


async def test_stop_cancels_running_tool(client):
    agent = FakeAgent(steps=[calls("slow")], tool_seconds=60)

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "new_message", msg(1))
        await asyncio.sleep(4)  # debounce + tool started
        t = time.monotonic()
        await start(client, queue, wf_id, "new_message", msg(2, stop=True))
        await wait_for(lambda: agent.replies)
        assert agent.replies == [("Stopped.", "stopped")] and time.monotonic() - t < 8
        assert agent.tool_runs == []  # cancelled, never finished

    await run_case(client, agent, body)


async def test_browser_tool_sends_progress_message(client):
    # Slow test (~40 s): uses the real 30 s threshold (the workflow sandbox re-imports modules, so it can't be patched).
    agent = FakeAgent(steps=[calls("b1", queue="browser"), {"reply": "here"}], tool_seconds=35)

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "new_message", msg(1))
        await wait_for(lambda: agent.replies, timeout=60)
        assert agent.texts == ["Still working on it…"] and agent.replies == [("here", "done")]

    await run_case(client, agent, body, browser=True)


async def test_model_failure_becomes_polite_message_and_workflow_survives(client):
    agent = FakeAgent(fail_model=True)

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "new_message", msg(1))
        await wait_for(lambda: agent.replies)
        assert agent.replies[0][1] == "failed" and "went wrong" in agent.replies[0][0]
        await start(client, queue, wf_id, "new_message", msg(2))  # still alive
        await wait_for(lambda: len(agent.replies) == 2)

    await run_case(client, agent, body)


async def test_buttons_run_approved_action_and_takeover_starts_a_turn(client):
    agent = FakeAgent()

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "button", {"msg_id": 1, "data": "appr:a1:y"})
        await wait_for(lambda: agent.approved == ["a1"])
        assert agent.batches == []  # an approval needs no model turn
        await start(client, queue, wf_id, "button", {"msg_id": 2, "data": "take:xyz"})
        await wait_for(lambda: agent.replies)
        assert agent.batches == [["takeover_done"]]

    await run_case(client, agent, body)


async def test_continue_as_new_keeps_dedupe_memory(client):
    agent = FakeAgent()

    async def body(queue, wf_id):
        await start(client, queue, wf_id, "new_message", msg(1), carry={"max_turns": 1})
        await wait_for(lambda: len(agent.batches) == 1)
        first_run = (await client.get_workflow_handle(wf_id).describe()).run_id
        await asyncio.sleep(1)
        await start(client, queue, wf_id, "new_message", msg(1))  # duplicate of an old message
        await start(client, queue, wf_id, "new_message", msg(2))
        await wait_for(lambda: len(agent.batches) == 2)
        assert agent.batches == [[1], [2]]
        assert (await client.get_workflow_handle(wf_id).describe()).run_id != first_run

    await run_case(client, agent, body)


def test_signal_for():
    assert signal_for({"id": 5, "kind": "text", "body": " Stop "}) == ("new_message", {"kind": "message", "msg_id": 5, "stop": True})
    assert signal_for({"id": 6, "kind": "button", "body": "appr:x:y"}) == ("button", {"msg_id": 6, "data": "appr:x:y"})
