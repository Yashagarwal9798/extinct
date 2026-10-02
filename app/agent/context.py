"""Builds the per-turn user message: everything the model needs to know right now, in a FIXED order.

G2: this module never reads secrets (a test enforces that it doesn't import app.secrets).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app import db
from app.config import get_settings

RECENT_LIMIT = 20
FACTS_MAX_CHARS = 4_000      # ~1k tokens
TOTAL_MAX_CHARS = 24_000     # ~6k tokens
MESSAGE_MAX_CHARS = 1_500


def untrusted(source: str, text: str) -> str:
    """Wrap third-party text (emails, web pages) so the model treats it as data, never instructions."""
    safe = text.replace("</untrusted", "<\\/untrusted")
    return f'<untrusted source="{source}">\n{safe}\n</untrusted>'


@dataclass
class TurnData:
    now: datetime
    connections: dict
    facts: list[dict] = field(default_factory=list)
    recent: list[dict] = field(default_factory=list)   # oldest -> newest
    events: list[str] = field(default_factory=list)
    new: list[dict] = field(default_factory=list)
    live_view_url: str = ""


def _when(dt: datetime, tz, with_day: bool = True) -> str:
    local = dt.astimezone(tz)
    return local.strftime("%a %H:%M") if with_day else local.strftime("%H:%M")


def _connections_block(c: dict, live_view_url: str) -> str:
    g = c.get("google")
    if g and g["status"] == "connected":
        caps = [n for n, s in (("read", "gmail.readonly"), ("send", "gmail.send")) if any(x.endswith(s) for x in g["scopes"])]
        gmail = f"connected ({', '.join(caps) or 'no gmail permissions'})"
    elif g and g["status"] == "needs_reauth":
        gmail = "needs reconnecting: the user must run connect_google on their PC"
    else:
        gmail = "not connected: the user can run connect_google on their PC"
    return (f"Gmail: {gmail}\n"
            f"Browser: available. The user logs into sites in the live view ({live_view_url}); "
            "browser_task asks them to take over when a login is needed.")


def render(d: TurnData) -> str:
    tz = get_settings().owner_timezone
    now = d.now.astimezone(tz)
    offset = now.strftime("%z")
    facts, used = [], 0
    for f in d.facts:  # newest first
        line = f"[f{f['id']}] ({f['kind']}) {f['content']}"
        if used + len(line) > FACTS_MAX_CHARS:
            break
        facts.append(line)
        used += len(line)

    def msg_line(m, with_day=True):
        who = "You" if m["direction"] == "out" else "User"
        body = m["body"][:MESSAGE_MAX_CHARS] + ("…" if len(m["body"]) > MESSAGE_MAX_CHARS else "")
        return f"[{_when(m['sent_at'], tz, with_day)}] {who}: {body}"

    new = "\n".join(msg_line(m, with_day=False) for m in d.new) or "(none)"
    events = "\n".join(f"- {e}" for e in d.events) or "(none)"
    head = (f"<now>{now:%a %d %b %Y, %H:%M} ({tz}, UTC{offset[:3]}:{offset[3:]})</now>\n"
            f"<connections>\n{_connections_block(d.connections, d.live_view_url)}\n</connections>\n"
            f"<facts>\n{chr(10).join(facts) or '(none)'}\n</facts>\n")
    tail = f"<events>\n{events}\n</events>\n<new_messages>\n{new}\n</new_messages>"

    recent = [msg_line(m) for m in d.recent]
    budget = TOTAL_MAX_CHARS - len(head) - len(tail) - 40
    while recent and sum(len(r) + 1 for r in recent) > budget:
        recent.pop(0)  # drop oldest first
    return head + f"<recent_messages>\n{chr(10).join(recent) or '(none)'}\n</recent_messages>\n" + tail


async def _event_text(item: dict) -> str:
    kind = item.get("kind")
    if kind == "task_due":
        return f"Scheduled task [{item['task_id']}] is due now. Do it and report the result: {item['text']}"
    if kind == "takeover_done":
        row = await db.fetchone("SELECT input FROM approvals WHERE id = %s", (item["approval_id"],))
        task = (row or {}).get("input", {})
        return ("The user finished taking over the browser. Continue this browser task now with browser_task: "
                f"goal={task.get('goal')!r}, mode={task.get('mode', 'read')!r}")
    if kind == "google_connected":
        return "Gmail was just connected."
    return f"{kind}: {item}"


async def gather(batch: list[dict]) -> TurnData:
    s = get_settings()
    ids = [i["msg_id"] for i in batch if i.get("kind") == "message"]
    rows = await db.fetchall("SELECT provider, status, scopes FROM connections")
    new = await db.fetchall(
        "SELECT direction, body, sent_at FROM messages WHERE id = ANY(%s) AND consumed_by IS NULL ORDER BY id", (ids,))
    recent = await db.fetchall(
        "SELECT * FROM (SELECT id, direction, body, sent_at FROM messages"
        " WHERE kind IN ('text', 'photo') AND consumed_by IS NULL AND NOT (id = ANY(%s))"
        " ORDER BY id DESC LIMIT %s) r ORDER BY id", (ids, RECENT_LIMIT))
    facts = await db.fetchall("SELECT id, kind, content FROM memory_facts ORDER BY updated_at DESC, id DESC LIMIT 200")
    events = [await _event_text(i) for i in batch if i.get("kind") != "message"]
    return TurnData(now=datetime.now(timezone.utc), connections={r["provider"]: r for r in rows}, facts=facts,
                    recent=recent, events=events, new=new, live_view_url=s.live_view_url)


async def build_turn_input(batch: list[dict]) -> str:
    return render(await gather(batch))
