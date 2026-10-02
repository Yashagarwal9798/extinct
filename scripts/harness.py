"""Run one agent turn in-process, without Temporal (same steps as ConversationWorkflow._turn).
Used by scripts/injection_check.py and scripts/eval_scenarios.py. Telegram should be in dry-run mode."""

from app import activities, db


async def say(text: str) -> int:
    row = await db.fetchone("INSERT INTO messages (direction, kind, body, dispatched) VALUES ('in', 'text', %s, true) RETURNING id",
                            (text,))
    return row["id"]


async def run_turn(batch: list[dict], max_steps: int = 15) -> dict:
    """Returns {"turn_id", "reply", "tools": [names called]}."""
    turn_id = await activities.start_turn(batch)
    if not turn_id:
        return {"turn_id": None, "reply": "", "tools": []}
    tools, n = [], 1
    step = await activities.model_step({"turn_id": turn_id, "step": n})
    while step.get("tool_calls") and n < max_steps:
        for call in step["tool_calls"]:  # sequential here; the workflow runs them in parallel
            tools.append(call["name"])
            await activities.run_tool({"turn_id": turn_id, "call": call})
        n += 1
        step = await activities.model_step({"turn_id": turn_id, "step": n})
    reply = step.get("reply", "")
    await activities.send_reply({"turn_id": turn_id, "text": reply, "status": "done"})
    return {"turn_id": turn_id, "reply": reply, "tools": tools}


async def ask(text: str) -> dict:
    return await run_turn([{"kind": "message", "msg_id": await say(text)}])
