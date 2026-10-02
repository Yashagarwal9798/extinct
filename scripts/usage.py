"""How much of the free AI quota you used, by kind and model.

    docker compose run --rm worker-agent python -m scripts.usage            # today (UTC day, like OpenRouter)
    docker compose run --rm worker-agent python -m scripts.usage --days 7
"""

import argparse
import asyncio
import sys

from app import db
from app.config import get_settings


async def main(days: int):
    s = get_settings()
    await db.connect(s.database_url)
    since = "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'" + (f" - interval '{days - 1} days'" if days > 1 else "")
    rows = await db.fetchall(
        f"SELECT kind, model, count(*) AS requests, count(*) FILTER (WHERE status <> 'ok') AS errors,"
        f" coalesce(sum(prompt_tokens), 0) AS tokens_in, coalesce(sum(completion_tokens), 0) AS tokens_out,"
        f" coalesce(sum(cost), 0) AS cost FROM llm_calls WHERE at >= {since} GROUP BY kind, model ORDER BY requests DESC")
    turns = await db.fetchone(f"SELECT count(*) AS n, count(*) FILTER (WHERE status = 'failed') AS failed"
                              f" FROM agent_turns WHERE started_at >= {since}")
    total = sum(r["requests"] for r in rows)
    print(f"Last {days} day(s) (UTC)\n")
    print(f"{'kind':<9}{'model':<45}{'requests':>9}{'errors':>8}{'tokens in':>11}{'out':>8}{'cost $':>9}")
    for r in rows:
        print(f"{r['kind']:<9}{r['model'][:44]:<45}{r['requests']:>9}{r['errors']:>8}{r['tokens_in']:>11}"
              f"{r['tokens_out']:>8}{float(r['cost']):>9.4f}")
    print(f"\ntotal requests: {total}" + (f" · daily budget {s.llm_daily_requests} · left today: "
                                          f"{max(0, s.llm_daily_requests - total)}" if days == 1 else ""))
    print(f"agent turns: {turns['n']} ({turns['failed']} failed)")
    await db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=1)
    asyncio.run(main(p.parse_args().days), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
