"""Temporal worker process.

    python -m app.worker agent     # conversation workflow + agent activities
    python -m app.worker browser   # browser activities (inside the browser container)
"""

import asyncio
import logging
import sys

from temporalio.worker import Worker

from app import activities, db, workflows
from app.clients import temporal
from app.config import get_settings

AGENT_WORKFLOWS = [workflows.ConversationWorkflow, workflows.ScheduledTaskWorkflow, workflows.TaskFireWorkflow]
AGENT_ACTIVITIES = [
    activities.start_turn, activities.model_step, activities.run_tool, activities.send_reply,
    activities.send_text, activities.claim_approval, activities.run_approved, activities.fire_task,
]


async def main(queue: str) -> None:
    from app import logs
    logs.setup()
    await db.connect(get_settings().database_url)
    client = await temporal()
    if queue == "agent":
        worker = Worker(client, task_queue="agent", workflows=AGENT_WORKFLOWS, activities=AGENT_ACTIVITIES)
    elif queue == "browser":
        # One browser, one task at a time. run_tool / run_approved here execute browser_task in this container.
        worker = Worker(client, task_queue="browser", activities=[activities.run_tool, activities.run_approved],
                        max_concurrent_activities=1)
        from app import browser
        await browser.MANAGER.context()  # open Chrome now so the live view works before the first task
    else:
        raise SystemExit(f"unknown queue {queue!r}")
    logging.getLogger("worker").info("worker started on queue %r", queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "agent"),
                loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
