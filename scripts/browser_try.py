"""Try one browser goal with the REAL model, inside the browser container (watch it at http://localhost:6080).

    docker compose run --rm browser python -m scripts.browser_try "top 5 posts on Hacker News" --url https://news.ycombinator.com
    docker compose run --rm browser python -m scripts.browser_try "star my repo X" --mode act --url https://github.com/...

Stop the `browser` service first (docker compose stop browser): only one process can use the Chrome profile.
Prints the result, the actions taken and how many AI requests it used (T-31: compare free models this way).
"""

import argparse
import asyncio

from app import db, llm
from app.browser import MANAGER, run_browser_task
from app.config import get_settings


async def main(goal: str, mode: str, url: str | None):
    await db.connect(get_settings().database_url)
    before = await llm.requests_today()
    actions = []

    async def on_action(name, args, result, page_url):
        actions.append(f"{name} {args} -> {result}")
        print(f"  {name} {args} -> {result}")

    r = await run_browser_task(goal, mode, url, on_action=on_action)
    used = await llm.requests_today() - before
    print(f"\nmodel: {get_settings().model_browser}\nstatus: {r['status']}\n"
          f"{r.get('summary') or r.get('reason')}\nactions: {len(actions)} · AI requests: {used}")
    await MANAGER.close()
    await db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("goal")
    p.add_argument("--mode", choices=["read", "act"], default="read")
    p.add_argument("--url")
    a = p.parse_args()
    asyncio.run(main(a.goal, a.mode, a.url))
