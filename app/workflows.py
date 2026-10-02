"""Temporal workflows. Workflow code only DECIDES and WAITS: no I/O, no clocks except workflow.now().
All real work happens in activities (app/activities.py), and they only talk to each other through here."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from app import activities

DEBOUNCE_QUIET = timedelta(seconds=2)
DEBOUNCE_MAX = timedelta(seconds=10)
SEEN_KEEP = 500
MAX_STEPS = 15
PROGRESS_AFTER = 30  # seconds before "Still working on it…" for browser tools

AGENT = dict(
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=5), backoff_coefficient=2, maximum_attempts=4),
)
BROWSER = dict(
    task_queue="browser",
    start_to_close_timeout=timedelta(minutes=10),
    heartbeat_timeout=timedelta(seconds=30),
    schedule_to_start_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


def _opts(queue: str) -> dict:
    return BROWSER if queue == "browser" else AGENT


@workflow.defn
class ConversationWorkflow:
    """One per user (we have one user): ID 'conversation'. Holds the inbox and processes it in order."""

    @workflow.init
    def __init__(self, carry: dict | None = None) -> None:
        # State is restored HERE (not in run) because signal-with-start delivers the signal before run() starts.
        carry = carry or {}
        self.inbox: list[dict] = carry.get("inbox", [])      # messages and events, in arrival order
        self.buttons: list[dict] = carry.get("buttons", [])  # button taps: handled by code, never by the model
        self.seen: list[int] = carry.get("seen", [])         # recent message ids, to drop duplicate signals
        self.max_turns: int = carry.get("max_turns", 100)
        self.turns = 0
        self.state = "idle"
        self.stop = False
        self.running: list[asyncio.Task] = []

    # ---------- signals & queries ----------

    def _first_time(self, msg_id: int | None) -> bool:
        if msg_id is None:
            return True
        if msg_id in self.seen:
            return False
        self.seen = (self.seen + [msg_id])[-SEEN_KEEP:]
        return True

    @workflow.signal
    def new_message(self, item: dict) -> None:
        if not self._first_time(item.get("msg_id")):
            return
        if item.get("stop") and self.state == "in_turn":
            self.stop = True  # exact "stop": cancel what's running instead of queueing it
            for task in self.running:
                task.cancel()
            return
        self.inbox.append(item)

    @workflow.signal
    def button(self, item: dict) -> None:
        if self._first_time(item.get("msg_id")):
            self.buttons.append(item)

    @workflow.signal
    def event(self, item: dict) -> None:
        """Non-message events: task_due, takeover_done, google_connected."""
        self.inbox.append(item)

    @workflow.query
    def status(self) -> dict:
        return {"state": self.state, "inbox": len(self.inbox), "buttons": len(self.buttons), "turns": self.turns}

    # ---------- main loop ----------

    @workflow.run
    async def run(self, carry: dict | None = None) -> None:
        while True:
            await workflow.wait_condition(lambda: bool(self.inbox or self.buttons))
            while self.buttons:
                await self._handle_button(self.buttons.pop(0))
            if self.inbox:
                if any(i.get("kind") == "message" for i in self.inbox):
                    await self._debounce()
                batch, self.inbox = self.inbox, []
                self.state = "in_turn"
                await self._turn(sorted(batch, key=lambda i: i.get("msg_id") or 0))
                self.turns += 1
                self.state = "idle"
            if not self.inbox and not self.buttons and (
                workflow.info().is_continue_as_new_suggested() or self.turns >= self.max_turns
            ):
                workflow.continue_as_new(
                    {"inbox": self.inbox, "buttons": self.buttons, "seen": self.seen, "max_turns": self.max_turns}
                )

    async def _debounce(self) -> None:
        """People type in bursts: wait until 2 s pass with no new message (10 s at most)."""
        self.state = "debouncing"
        deadline = workflow.now() + DEBOUNCE_MAX
        while True:
            remaining = (deadline - workflow.now()).total_seconds()
            if remaining <= 0:
                return
            n = len(self.inbox)
            try:
                await workflow.wait_condition(
                    lambda: len(self.inbox) > n, timeout=min(DEBOUNCE_QUIET.total_seconds(), remaining)
                )
            except asyncio.TimeoutError:
                return

    async def _turn(self, batch: list[dict]) -> None:
        """start_turn -> model_step -> tools (parallel) -> model_step ... -> send_reply."""
        turn_id = None
        try:
            turn_id = await workflow.execute_activity(activities.start_turn, batch, **AGENT)
            if not turn_id:
                return
            self.stop = False
            n = 1
            step = await workflow.execute_activity(activities.model_step, {"turn_id": turn_id, "step": n}, **AGENT)
            while step.get("tool_calls") and n < MAX_STEPS and not self.stop:
                self.running = [asyncio.ensure_future(self._run_tool(turn_id, c)) for c in step["tool_calls"]]
                await asyncio.gather(*self.running, return_exceptions=True)
                self.running = []
                if self.stop:
                    break
                extra = [i["msg_id"] for i in self.inbox if i.get("kind") == "message"]
                self.inbox = [i for i in self.inbox if i.get("kind") != "message"]
                n += 1
                step = await workflow.execute_activity(
                    activities.model_step, {"turn_id": turn_id, "step": n, "extra": extra}, **AGENT)
            if self.stop:
                text, status = "Stopped.", "stopped"
            elif step.get("tool_calls"):
                text, status = "That took too many steps, so I stopped. Could you split it into smaller asks?", "failed"
            else:
                text, status = step.get("reply", ""), "done"
        except ActivityError as e:
            workflow.logger.warning("turn failed: %s", e)
            if not turn_id:
                return
            text, status = "Sorry, something went wrong on my side. Please try again in a bit.", "failed"
        try:
            await workflow.execute_activity(
                activities.send_reply, {"turn_id": turn_id, "text": text, "status": status}, **AGENT)
        except ActivityError as e:
            workflow.logger.warning("send_reply failed: %s", e)

    async def _run_tool(self, turn_id: str, call: dict) -> dict:
        handle = workflow.start_activity(activities.run_tool, {"turn_id": turn_id, "call": call}, **_opts(call["queue"]))
        try:
            if call["queue"] == "browser":
                try:
                    await workflow.wait_condition(lambda: handle.done(), timeout=PROGRESS_AFTER)
                except asyncio.TimeoutError:
                    await workflow.execute_activity(activities.send_text, "Still working on it…", **AGENT)
            return await handle
        except asyncio.CancelledError:
            handle.cancel()  # "stop": ask the activity to stop too
            raise

    async def _handle_button(self, item: dict) -> None:
        """Approval and takeover buttons: handled by code. The model can never press a button."""
        try:
            res = await workflow.execute_activity(activities.claim_approval, {"data": item["data"]}, **AGENT)
            if event := res.get("event"):
                self.inbox.append(event)
            if res.get("run"):
                await workflow.execute_activity(activities.run_approved, res["approval_id"], **_opts(res["queue"]))
        except ActivityError as e:
            workflow.logger.warning("button handling failed: %s", e)


# ---------------------------------------------------------------- scheduled tasks (T-32, T-33)
# Stored in Temporal itself: a one-time task is a durable timer; a repeating task is a Temporal Schedule.


@workflow.defn
class ScheduledTaskWorkflow:
    """One-time task: sleep (durably) until fire_at, then fire. Cancelling it = cancelling the task."""

    @workflow.run
    async def run(self, task: dict) -> None:
        from datetime import datetime
        delay = (datetime.fromisoformat(task["fire_at"]) - workflow.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)  # a Temporal timer: survives restarts of everything
        await workflow.execute_activity(activities.fire_task, task, **AGENT)


@workflow.defn
class TaskFireWorkflow:
    """Started by a Temporal Schedule each time a repeating task is due."""

    @workflow.run
    async def run(self, task: dict) -> None:
        await workflow.execute_activity(activities.fire_task, task, **AGENT)
