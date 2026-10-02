"""Hand a saved inbound message to the conversation workflow (signal-with-start).

Signals carry IDs only; activities read message bodies from the DB. If Temporal is unreachable the row stays
`dispatched = false` and the bot's sweeper retries it. The workflow drops duplicates, so a re-dispatch is safe.
"""

import logging

from app import db
from app.clients import temporal

log = logging.getLogger("dispatch")

CONVERSATION_ID = "conversation"
AGENT_QUEUE = "agent"


def signal_for(row: dict) -> tuple[str, dict]:
    if row["kind"] == "button":
        return "button", {"msg_id": row["id"], "data": row["body"]}
    return "new_message", {"kind": "message", "msg_id": row["id"], "stop": row["body"].strip().lower() == "stop"}


async def signal_conversation(signal: str, item: dict) -> None:
    from app.workflows import ConversationWorkflow

    client = await temporal()
    await client.start_workflow(
        ConversationWorkflow.run,
        None,
        id=CONVERSATION_ID,
        task_queue=AGENT_QUEUE,
        start_signal=signal,
        start_signal_args=[item],
    )


async def signal_event(item: dict) -> None:
    """Deliver a non-message event (task_due, google_connected, ...) to the conversation, starting it if needed."""
    await signal_conversation("event", item)


async def dispatch(row: dict) -> None:
    signal, item = signal_for(row)
    try:
        await signal_conversation(signal, item)
    except Exception as e:
        log.warning("dispatch of message %s failed (sweeper will retry): %r", row["id"], e)
        return
    await db.execute("UPDATE messages SET dispatched = true WHERE id = %s", (row["id"],))
