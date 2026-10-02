"""Scenario evaluation with the REAL model (Telegram dry-run: nothing is sent to you).

    docker compose run --rm worker-agent python -m scripts.eval_scenarios --list
    docker compose run --rm worker-agent python -m scripts.eval_scenarios --only chat,memory_save
    docker compose run --rm worker-agent python -m scripts.eval_scenarios          # all that fit today's budget

Free tier: ~45 requests/day, so run in chunks across days. Browser scenarios run in the browser container:
    docker compose stop browser && docker compose run --rm browser python -m scripts.eval_scenarios --only browser_read
Target (PRD §14): >= 85 % pass overall.
"""

import argparse
import asyncio
import os
import sys

os.environ["TELEGRAM_DRY_RUN"] = "true"

from app import db, llm  # noqa: E402
from app.config import get_settings  # noqa: E402
from scripts.harness import ask  # noqa: E402

# name, messages (each one turn), expected tools (any order, subset), reply must contain (any of), est. requests, needs
SCENARIOS = [
    ("chat", ["hey, what can you do?"], [], [], 1, None),
    ("memory_save", ["remember that I'm vegetarian"], ["remember_fact"], [], 2, None),
    ("memory_use", ["remember that my sister is Priya", "who is my sister?"], ["remember_fact"], ["priya"], 3, None),
    ("memory_search", ["the plumber's name is Ramesh, number 98xxx", "what was the plumber's name?"], [], ["ramesh"], 3, None),
    ("time_reminder", ["remind me in 2 hours to drink water"], ["schedule_task"], [], 2, None),
    ("recurring", ["every monday at 9am remind me to plan the week"], ["schedule_task"], [], 2, None),
    ("list_tasks", ["what's scheduled for me?"], ["list_tasks"], [], 2, None),
    ("do_task", ["tomorrow at 8am check the top post on hacker news and tell me"], ["schedule_task"], [], 2, None),
    ("one_question", ["remind me at 7"], [], ["?"], 1, None),  # ambiguous (am/pm) -> one clarifying question
    ("gmail_read", ["any unread emails today?"], ["search_email"], [], 2, "gmail"),
    ("gmail_send", ["email test@example.com saying hi from my assistant"], ["send_email"], ["tap", "button", "approve", "send"], 2, "gmail"),
    ("browser_read", ["what's the top post on hacker news right now?"], ["browser_task"], [], 8, "browser"),
    ("browser_act_needs_ok", ["post 'hello' on my twitter"], ["browser_task"], ["tap", "button", "approve", "confirm"], 2, None),
    ("not_connected", ["check my instagram messages"], ["browser_task"], [], 5, "browser"),
    ("stop_word_alone", ["stop"], [], [], 1, None),
]


def available(needs) -> bool:
    if needs == "browser":
        return os.environ.get("BROWSER_PROFILE_DIR") is not None or os.path.exists("/profile")
    return True


async def run(name, msgs, want_tools, want_text, needs) -> tuple[bool, str]:
    if needs == "gmail" and not await db.fetchone("SELECT 1 FROM connections WHERE provider = 'google' AND status = 'connected'"):
        return False, "skipped: Gmail not connected"
    if not available(needs):
        return False, "skipped: run inside the browser container"
    tools, reply = [], ""
    for m in msgs:
        r = await ask(m)
        tools += r["tools"]
        reply = r["reply"]
    missing = [t for t in want_tools if t not in tools]
    text_ok = not want_text or any(w in reply.lower() for w in want_text)
    ok = not missing and text_ok and (bool(reply) or name == "stop_word_alone")
    return ok, f"tools={tools} reply={reply[:120]!r}" + (f" MISSING {missing}" if missing else "")


async def main(only: list[str] | None, list_only: bool):
    chosen = [s for s in SCENARIOS if not only or s[0] in only]
    if list_only:
        for s in SCENARIOS:
            print(f"{s[0]:<22} ~{s[4]} requests{'  (needs ' + s[5] + ')' if s[5] else ''}")
        return
    await db.connect(get_settings().database_url)
    left = get_settings().llm_daily_requests - await llm.requests_today()
    est = sum(s[4] for s in chosen)
    print(f"{len(chosen)} scenarios, ~{est} requests estimated, {left} left today")
    if est > left:
        sys.exit("Not enough budget today: use --only to run a subset.")
    passed = 0
    for name, msgs, tools, text, _, needs in chosen:
        try:
            ok, detail = await run(name, msgs, tools, text, needs)
        except llm.BudgetExhausted:
            print("Daily budget used up; stopping.")
            break
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"\n{passed}/{len(chosen)} passed ({passed * 100 // max(1, len(chosen))} %)")
    print("Note: scheduled tasks created by the eval are real. Cancel them with list_tasks/cancel_task or the Temporal UI.")
    await db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated scenario names")
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    asyncio.run(main(a.only.split(",") if a.only else None, a.list),
                loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
