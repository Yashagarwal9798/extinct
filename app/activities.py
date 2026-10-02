"""Temporal activities: the steps that touch the outside world (DB, Telegram, the model, Gmail, the browser).
Temporal may retry any of them, so each is written to be safe to run twice."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app import db, llm, telegram
from app.agent import guard
from app.agent.context import build_turn_input
from app.agent.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolCtx, ToolError, definitions, load_connections, menu_for
from app.config import get_settings
from app.logs import turn_id_var

log = logging.getLogger("activities")

APPROVAL_TTL = timedelta(minutes=30)
TAKEOVER_TTL = timedelta(hours=2)
QUOTA_MESSAGE = "I've used today's free AI quota, so I'm pausing until midnight (UTC). Reminders still work."
TOOL_RESULT_MAX_CHARS = 16_000


def _non_retryable(e: Exception) -> ApplicationError:
    return ApplicationError(str(e), type=type(e).__name__, non_retryable=True)


async def _bodies(batch: list[dict]) -> list[str]:
    ids = [i["msg_id"] for i in batch if i.get("kind") == "message"]
    rows = await db.fetchall("SELECT body FROM messages WHERE id = ANY(%s) ORDER BY id", (ids,))
    return [r["body"] for r in rows]


@activity.defn
async def echo_reply(batch: list[dict]) -> None:
    """T-07 placeholder turn (kept for the dispatch end-to-end test)."""
    bodies = await _bodies(batch)
    if bodies:
        await telegram.send("You said: " + " / ".join(bodies))


# ---------------------------------------------------------------- turn start / model step

def _trigger(batch: list[dict]) -> str:
    kinds = {i.get("kind") for i in batch}
    return "message" if "message" in kinds else (sorted(kinds)[0] if kinds else "message")


@activity.defn
async def start_turn(batch: list[dict]) -> str | None:
    """Create the turn: frozen tool menu + the context message. None if there's nothing to answer."""
    ids = [i["msg_id"] for i in batch if i.get("kind") == "message"]
    events = [i for i in batch if i.get("kind") != "message"]
    if ids and not events:
        row = await db.fetchone(
            "SELECT count(*) AS n FROM messages WHERE id = ANY(%s) AND consumed_by IS NULL", (ids,))
        if row["n"] == 0:
            return None  # every message was used as input by a browser task (e.g. a 2FA code)
    if not ids and not events:
        return None
    await telegram.send_chat_action("typing")
    menu = menu_for(await load_connections())
    content = await build_turn_input(batch)
    row = await db.fetchone(
        "INSERT INTO agent_turns (trigger, prompt_version, model, messages, tool_menu)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (_trigger(batch), PROMPT_VERSION, get_settings().model_main,
         json.dumps([{"role": "user", "content": content}]), menu),
    )
    if ids:
        await db.execute("UPDATE messages SET turn_id = %s WHERE id = ANY(%s)", (row["id"], ids))
    return str(row["id"])


def _result_of(assistant: dict) -> dict:
    if calls := assistant.get("tool_calls"):
        return {"tool_calls": [{"id": c["id"], "name": c["function"]["name"], "arguments": c["function"]["arguments"],
                                "queue": TOOLS[c["function"]["name"]].queue if c["function"]["name"] in TOOLS else "agent"}
                               for c in calls]}
    return {"reply": assistant.get("content") or ""}


def _as_text(content) -> str:
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


@activity.defn
async def model_step(args: dict) -> dict:
    """One model request. args: {turn_id, step, extra: [msg ids that arrived mid-turn]}.
    Idempotent: if this step was already saved (a retry after a crash), return it without calling the model."""
    turn_id_var.set(args["turn_id"])
    turn = await db.fetchone("SELECT messages, tool_menu, steps FROM agent_turns WHERE id = %s", (args["turn_id"],))
    msgs: list[dict] = turn["messages"]
    if turn["steps"] >= args["step"]:
        return _result_of(msgs[-1])

    last = msgs[-1]
    if last["role"] == "assistant" and last.get("tool_calls"):
        rows = await db.fetchall("SELECT tool_call_id, content FROM tool_results WHERE turn_id = %s", (args["turn_id"],))
        done = {r["tool_call_id"]: r["content"] for r in rows}
        for c in last["tool_calls"]:
            content = done.get(c["id"], {"error": "not executed (stopped or cancelled)"})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": _as_text(content)})
    if extra := args.get("extra"):
        bodies = await db.fetchall(
            "SELECT body, sent_at FROM messages WHERE id = ANY(%s) AND consumed_by IS NULL ORDER BY id", (extra,))
        if bodies:
            lines = "\n".join(f"User: {b['body']}" for b in bodies)
            msgs.append({"role": "user", "content": f"<new_messages>\n{lines}\n</new_messages>"})

    try:
        r = await llm.chat("main", get_settings().model_main,
                           [{"role": "system", "content": SYSTEM_PROMPT}] + msgs, definitions(turn["tool_menu"]))
    except llm.BudgetExhausted:
        already = await db.fetchone(
            "SELECT 1 FROM messages WHERE direction = 'out' AND body = %s AND sent_at > now() - interval '20 hours'",
            (QUOTA_MESSAGE,))
        return {"reply": "" if already else QUOTA_MESSAGE}  # say it once, then stay quiet
    except llm.Permanent as e:
        raise _non_retryable(e) from e

    if r["finish_reason"] == "length" and not r["message"].get("tool_calls"):
        r["message"]["content"] = (r["message"]["content"] or "") + "…"
    msgs.append(r["message"])
    await db.execute("UPDATE agent_turns SET messages = %s, steps = %s WHERE id = %s",
                     (json.dumps(msgs), args["step"], args["turn_id"]))
    return _result_of(r["message"])


# ---------------------------------------------------------------- tools

async def _store_result(turn_id: str, call: dict, content, is_error: bool = False) -> None:
    text = _as_text(content)
    if len(text) > TOOL_RESULT_MAX_CHARS:
        content = text[:TOOL_RESULT_MAX_CHARS] + "…(truncated)"
    await db.execute(
        "INSERT INTO tool_results (turn_id, tool_call_id, tool, content, is_error) VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT DO NOTHING",
        (turn_id, call["id"], call["name"], json.dumps(content), is_error))


async def request_approval(turn_id: str | None, tool: str, args: dict, summary: str,
                           ttl: timedelta = APPROVAL_TTL, kind: str = "appr") -> str:
    """Store a pending button action and send the buttons. kind 'appr' = Send/Cancel, 'take' = Done."""
    row = await db.fetchone(
        "INSERT INTO approvals (turn_id, tool, input, summary, expires_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (turn_id, tool, json.dumps(args), summary, datetime.now(timezone.utc) + ttl))
    aid = str(row["id"])
    if kind == "take":
        markup = telegram.buttons(("Done ✅", f"take:{aid}"))
    else:
        yes = "Send" if tool == "send_email" else "Do it"
        markup = telegram.buttons((yes, f"appr:{aid}:y"), ("Cancel", f"appr:{aid}:n"))
    [*_, mid] = await telegram.send(summary, reply_markup=markup, turn_id=turn_id)
    await db.execute("UPDATE approvals SET tg_message_id = %s WHERE id = %s", (mid, aid))
    return aid


async def execute_tool(turn_id: str | None, call_id: str, name: str, args: dict, tier: str):
    """Run a tool handler and audit it. Returns (content, is_error)."""
    tool = TOOLS[name]
    limit_key = tool.limit_key(args) if tool.limit_key else name
    try:
        result = await tool.handler(ToolCtx(turn_id or "", call_id), args)
    except ToolError as e:
        await guard.audit(name, "failed", turn_id=turn_id, tier=tier, detail={"error": str(e)})
        return {"error": str(e)}, True
    await guard.audit(name, "executed", turn_id=turn_id, tier=tier, detail={"limit_key": limit_key})
    return result, False


@activity.defn
async def run_tool(args: dict) -> dict:
    """Guard (G3) + execute one tool call. args: {turn_id, call: {id, name, arguments}}."""
    turn_id, call = args["turn_id"], args["call"]
    turn_id_var.set(turn_id)
    if await db.fetchone("SELECT 1 FROM tool_results WHERE turn_id = %s AND tool_call_id = %s", (turn_id, call["id"])):
        return {"ok": True}  # already done (retry)
    turn = await db.fetchone("SELECT tool_menu FROM agent_turns WHERE id = %s", (turn_id,))
    decision = await guard.check(call["name"], call["arguments"], turn["tool_menu"])

    if isinstance(decision, guard.Denied):
        await guard.audit(call["name"], "denied", turn_id=turn_id, detail={"reason": decision.reason})
        await _store_result(turn_id, call, {"error": decision.reason}, True)
        return {"ok": False}
    if isinstance(decision, guard.NeedsApproval):
        await guard.audit(call["name"], "needs_approval", turn_id=turn_id, tier=decision.tier)
        await request_approval(turn_id, call["name"], decision.args, decision.summary)
        await _store_result(turn_id, call, {"status": "approval_requested",
                                            "note": "Not executed yet. The user must tap the button."})
        return {"ok": True}

    content, is_error = await execute_tool(turn_id, call["id"], call["name"], decision.args, decision.tier)
    await _store_result(turn_id, call, content, is_error)
    return {"ok": not is_error}


# ---------------------------------------------------------------- replies

@activity.defn
async def send_reply(args: dict) -> None:
    """G5 check, then send. args: {turn_id, text, status}."""
    text = (args.get("text") or "").strip()
    turn_id = args.get("turn_id")
    if text:
        from app.secrets import secret_store
        try:
            saved = secret_store().values_of_kind("site")
        except Exception:
            saved = []
        if reason := guard.leaks(text, saved):
            await guard.audit("send_reply", "blocked", turn_id=turn_id, detail={"reason": reason})
            text = "I blocked a reply because it contained something that looked sensitive."
        await telegram.send(text, turn_id=turn_id)
    if turn_id:
        await db.execute("UPDATE agent_turns SET status = %s, ended_at = now() WHERE id = %s",
                         (args.get("status", "done"), turn_id))


@activity.defn
async def send_text(text: str) -> None:
    """Small fixed messages from workflow code, e.g. 'Still working on it…'."""
    await telegram.send(text)


# ---------------------------------------------------------------- buttons (approvals & takeovers)

@activity.defn
async def claim_approval(args: dict) -> dict:
    """Handle a button tap. args: {data}. Returns {"run": True, "queue": q, "approval_id": id} when an approved
    action must now run, {"event": {...}} for a finished takeover, or {} when nothing more is needed."""
    data: str = args["data"]
    parts = data.split(":")
    try:
        uuid.UUID(parts[1])
    except (IndexError, ValueError):
        return {}  # not a button we created
    if data.startswith("take:"):
        aid = data[5:]
        row = await db.fetchone(
            "UPDATE approvals SET status = 'done', decided_at = now() WHERE id = %s AND status = 'pending' RETURNING tg_message_id",
            (aid,))
        if not row:
            return {}
        await _edit(row["tg_message_id"], "✓ Got it, continuing…")
        return {"event": {"kind": "takeover_done", "approval_id": aid}}

    if not data.startswith("appr:") or data.count(":") != 2:
        return {}
    _, aid, choice = data.split(":")
    if choice == "n":
        row = await db.fetchone(
            "UPDATE approvals SET status = 'rejected', decided_at = now() WHERE id = %s AND status = 'pending'"
            " RETURNING tool, summary, tg_message_id", (aid,))
        if row:
            await guard.audit(row["tool"], "rejected", actor="user", detail={"approval_id": aid})
            await _edit(row["tg_message_id"], f"{row['summary']}\n\n✗ Cancelled")
        return {}
    row = await db.fetchone(
        "UPDATE approvals SET status = 'executing', decided_at = now()"
        " WHERE id = %s AND status = 'pending' AND expires_at > now() RETURNING tool", (aid,))
    if not row:
        await telegram.send("That request expired or was already handled. Ask me again if you still want it.")
        return {}
    tool = TOOLS.get(row["tool"])
    return {"run": True, "approval_id": aid, "queue": tool.queue if tool else "agent"}


async def _edit(message_id: int | None, text: str) -> None:
    if message_id:
        try:
            await telegram.edit_message_text(message_id, text)
        except telegram.TelegramError as e:
            log.warning("edit of message %s failed: %s", message_id, e)


@activity.defn
async def run_approved(approval_id: str) -> None:
    """Execute an action the user approved with a real button tap (re-checking the guard first)."""
    row = await db.fetchone("SELECT * FROM approvals WHERE id = %s", (approval_id,))
    if not row or row["status"] != "executing":
        return  # already finished (retry) or never claimed
    decision = await guard.check(row["tool"], row["input"], menu_for(await load_connections()), approved=True)
    if not isinstance(decision, guard.Allowed):
        reason = getattr(decision, "reason", "not allowed")
        await db.execute("UPDATE approvals SET status = 'failed', result = %s WHERE id = %s",
                         (json.dumps({"error": reason}), approval_id))
        await _edit(row["tg_message_id"], f"{row['summary']}\n\n✗ Couldn't do it: {reason}")
        return
    content, is_error = await execute_tool(str(row["turn_id"]) if row["turn_id"] else None, f"approval:{approval_id}",
                                           row["tool"], decision.args, decision.tier)
    await db.execute("UPDATE approvals SET status = %s, result = %s WHERE id = %s",
                     ("failed" if is_error else "executed", json.dumps(content, default=str), approval_id))
    if is_error:
        await _edit(row["tg_message_id"], f"{row['summary']}\n\n✗ Failed: {content.get('error')}")
        return
    if isinstance(content, dict) and content.get("status") == "needs_user":
        await _edit(row["tg_message_id"], f"{row['summary']}\n\n⏸ Waiting for you to take over in the browser")
        return
    done = "✓ Sent" if row["tool"] == "send_email" else "✓ Done"
    await _edit(row["tg_message_id"], f"{row['summary']}\n\n{done}")
    if isinstance(content, dict) and content.get("user_text"):
        await telegram.send(content["user_text"])


# ---------------------------------------------------------------- scheduled tasks (T-32)

@activity.defn
async def fire_task(task: dict) -> None:
    """remind: code sends the text (no model request). do: the agent runs the instruction in a normal turn."""
    if task["kind"] == "remind":
        await telegram.send(f"⏰ {task['text']}")
    else:
        from app.dispatch import signal_event
        await signal_event({"kind": "task_due", "task_id": task["id"], "text": task["text"]})
