"""Guardrails that run as plain code, whatever the model says.

G3 `check()`: runs when a tool call is EXECUTED (not just when the menu is built): menu, JSON, schema,
connection health, rate limits, and approval for risky tiers.
G5 `leaks()`: scans outgoing text for tokens / saved passwords.
`audit()`: append-only record of every decision.
"""

import json
import re
from dataclasses import dataclass

import jsonschema

from app import db
from app.agent.tools import TOOLS, load_connections, need_met

APPROVAL_TIERS = {"WO", "D"}

# limit bucket -> max executions per rolling 24 h
DAILY_LIMITS = {"send_email": 10, "browser_task:act": 20, "browser_task:read": 60}


@dataclass(frozen=True)
class Allowed:
    args: dict
    tier: str


@dataclass(frozen=True)
class Denied:
    reason: str


@dataclass(frozen=True)
class NeedsApproval:
    args: dict
    tier: str
    summary: str


def _limit_key(tool, args: dict) -> str:
    return tool.limit_key(args) if tool.limit_key else tool.name


async def check(name: str, raw_args: str | dict, menu: list[str], approved: bool = False):
    """Decide whether a tool call may run. `approved=True` is only passed after a real button tap."""
    tool = TOOLS.get(name)
    if tool is None or name not in menu:
        return Denied(f"tool {name!r} is not available right now")
    try:
        args = json.loads(raw_args or "{}") if isinstance(raw_args, str) else dict(raw_args)
    except json.JSONDecodeError:
        return Denied("arguments were not valid JSON")
    if not isinstance(args, dict):
        return Denied("arguments must be a JSON object")
    try:
        jsonschema.validate(args, tool.schema)
    except jsonschema.ValidationError as e:
        return Denied(f"invalid arguments: {e.message}")
    if tool.needs and not need_met(tool.needs, await load_connections()):
        return Denied(f"{name} needs {tool.needs}, which is not connected right now")

    key = _limit_key(tool, args)
    if key in DAILY_LIMITS:
        row = await db.fetchone(
            "SELECT count(*) AS n FROM audit_log WHERE decision = 'executed' AND detail->>'limit_key' = %s"
            " AND created_at > now() - interval '24 hours'", (key,))
        if row["n"] >= DAILY_LIMITS[key]:
            return Denied(f"daily limit reached for {key} ({DAILY_LIMITS[key]}/day)")

    tier = tool.tier_for(args)
    if tier in APPROVAL_TIERS and not approved:
        summary = tool.render(args) if tool.render else f"{name}: {json.dumps(args, ensure_ascii=False)}"
        return NeedsApproval(args, tier, summary)
    return Allowed(args, tier)


async def audit(tool: str, decision: str, *, turn_id: str | None = None, tier: str | None = None,
                actor: str = "agent", detail: dict | None = None) -> None:
    await db.execute(
        "INSERT INTO audit_log (turn_id, actor, tool, tier, decision, detail) VALUES (%s, %s, %s, %s, %s, %s)",
        (turn_id, actor, tool, tier, decision, json.dumps(detail or {}, default=str)),
    )


# ---------------------------------------------------------------- G5: outbound leak check

_LEAK_PATTERNS = [
    re.compile(r"ya29\.[\w-]{10,}"),            # Google access token
    re.compile(r"1//0[\w-]{10,}"),               # Google refresh token
    re.compile(r"sk-or-v1-[0-9a-f]{20,}"),       # OpenRouter key
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # Telegram bot token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def leaks(text: str, saved_secrets: list[bytes] = ()) -> str | None:
    """Return the reason if `text` looks like it contains a secret, else None."""
    for p in _LEAK_PATTERNS:
        if p.search(text):
            return f"matches secret pattern {p.pattern[:20]}"
    for s in saved_secrets:
        value = s.decode(errors="ignore")
        if len(value) >= 6 and value in text:
            return "contains a saved password"
    return None
