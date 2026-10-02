"""Scheduled tasks live in Temporal (real dev server; a time-skipping server for the 3-day test)."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from app import clients
from app.agent.tools import TOOLS, ToolCtx, ToolError
from app.workflows import ScheduledTaskWorkflow

CTX = ToolCtx("t", "c")
IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
async def client():
    try:
        return await clients.temporal()
    except Exception:
        pytest.skip("Temporal not running")


@pytest.fixture
async def cleanup(client):
    ids = []
    yield ids
    for i in ids:  # never leave test tasks that a real worker could fire later
        for fn in (lambda: client.get_workflow_handle(i).terminate(), lambda: client.get_schedule_handle(i).delete()):
            try:
                await fn()
            except Exception:
                pass


def task_id(result: str) -> str:
    return result.split("[")[1].split("]")[0]


async def run(name, **args):
    return await TOOLS[name].handler(CTX, args)


async def test_one_time_task_create_list_cancel(appdb, client, cleanup):
    when = (datetime.now(IST) + timedelta(hours=2)).replace(microsecond=0)
    out = await run("schedule_task", kind="remind", text="call mom", fire_at=when.isoformat())
    tid = task_id(out)
    cleanup.append(tid)
    assert out.startswith(f"Scheduled [{tid}] for ")
    desc = await client.get_workflow_handle(tid).describe()
    assert desc.workflow_type == "ScheduledTaskWorkflow" and (await desc.memo())["text"] == "call mom"
    for _ in range(50):  # visibility is eventually consistent
        listed = (await run("list_tasks"))["tasks"]
        if any(tid in line for line in listed):
            break
        await asyncio.sleep(0.2)
    assert any(tid in line and "call mom" in line for line in listed)
    fired = []

    @activity.defn(name="fire_task")
    async def fire_task(task: dict) -> None:
        fired.append(task)

    # Cancelling only *requests* it; a worker (always running in production) applies it.
    async with Worker(client, task_queue="agent", workflows=[ScheduledTaskWorkflow], activities=[fire_task]):
        assert await run("cancel_task", task_id=tid) == f"cancelled {tid}"
        for _ in range(50):
            if (await client.get_workflow_handle(tid).describe()).status.name != "RUNNING":
                break
            await asyncio.sleep(0.2)
    assert (await client.get_workflow_handle(tid).describe()).status.name == "CANCELED" and fired == []
    assert "already gone" in await run("cancel_task", task_id="task-00000000")


async def test_repeating_task_and_min_interval(appdb, client, cleanup):
    out = await run("schedule_task", kind="remind", text="plan the week", cron="0 9 * * MON")
    tid = task_id(out)
    cleanup.append(tid)
    assert "repeating '0 9 * * MON' (Asia/Kolkata), first at Mon" in out
    desc = await client.get_schedule_handle(tid).describe()
    assert desc.schedule.spec.time_zone_name == "Asia/Kolkata"
    with pytest.raises(ToolError, match="at most every"):
        await run("schedule_task", kind="do", text="check HN", cron="*/5 * * * *")  # 'do' minimum is 60 min
    assert await run("cancel_task", task_id=tid) == f"cancelled repeating {tid}"


@pytest.mark.parametrize("args,match", [
    ({"kind": "remind", "text": "x"}, "exactly one"),
    ({"kind": "remind", "text": "x", "fire_at": "2026-01-01T00:00:00+05:30", "cron": "* * * * *"}, "exactly one"),
    ({"kind": "remind", "text": "x", "fire_at": "tomorrow"}, "ISO 8601"),
    ({"kind": "remind", "text": "x", "fire_at": "2030-01-01T08:00:00"}, "offset"),
    ({"kind": "remind", "text": "x", "fire_at": "2020-01-01T08:00:00+05:30"}, "at least 30 seconds"),
    ({"kind": "remind", "text": "x", "cron": "every monday"}, "5 fields"),
])
async def test_bad_schedules(appdb, client, args, match):
    with pytest.raises(ToolError, match=match):
        await run("schedule_task", **args)


async def test_one_time_task_fires_and_cancelled_one_does_not(client):
    fired = []

    @activity.defn(name="fire_task")
    async def fire_task(task: dict) -> None:
        fired.append(task["id"])

    queue = f"q-{uuid.uuid4()}"
    soon = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
    async with Worker(client, task_queue=queue, workflows=[ScheduledTaskWorkflow], activities=[fire_task]):
        a = await client.start_workflow(ScheduledTaskWorkflow.run, {"id": "a", "kind": "remind", "text": "x", "fire_at": soon},
                                        id=f"t-{uuid.uuid4()}", task_queue=queue)
        b = await client.start_workflow(ScheduledTaskWorkflow.run, {"id": "b", "kind": "remind", "text": "y", "fire_at": soon},
                                        id=f"t-{uuid.uuid4()}", task_queue=queue)
        await b.cancel()
        await a.result()
        await asyncio.sleep(1)
    assert fired == ["a"]


async def test_three_days_later_with_time_skipping():
    from temporalio.testing import WorkflowEnvironment
    try:
        env = await WorkflowEnvironment.start_time_skipping()
    except Exception as e:
        pytest.skip(f"time-skipping test server unavailable: {e!r}")
    fired = []

    @activity.defn(name="fire_task")
    async def fire_task(task: dict) -> None:
        fired.append(task["text"])

    async with env:
        later = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        async with Worker(env.client, task_queue="q", workflows=[ScheduledTaskWorkflow], activities=[fire_task]):
            await env.client.execute_workflow(ScheduledTaskWorkflow.run,
                                              {"id": "x", "kind": "remind", "text": "3 days later", "fire_at": later},
                                              id="t3", task_queue="q")
    assert fired == ["3 days later"]


async def test_fire_task_remind_sends_text_without_model(appdb, monkeypatch):
    from app import activities, llm, telegram
    sent = []

    async def send(text, reply_markup=None, turn_id=None):
        sent.append(text)

    async def no_model(*a, **k):
        raise AssertionError("a reminder must not call the model")

    monkeypatch.setattr(telegram, "send", send)
    monkeypatch.setattr(llm, "chat", no_model)
    await activities.fire_task({"id": "task-1", "kind": "remind", "text": "stretch"})
    assert sent == ["⏰ stretch"]


async def test_fire_task_do_signals_the_conversation(monkeypatch):
    from app import activities, dispatch
    events = []

    async def signal_event(item):
        events.append(item)

    monkeypatch.setattr(dispatch, "signal_event", signal_event)
    await activities.fire_task({"id": "task-1", "kind": "do", "text": "check HN"})
    assert events == [{"kind": "task_due", "task_id": "task-1", "text": "check HN"}]
