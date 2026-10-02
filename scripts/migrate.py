"""Apply migrations/*.sql in name order, each once, each in its own transaction.

    python -m scripts.migrate            # uses DATABASE_URL
"""

import asyncio
import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


async def migrate(url: str) -> list[str]:
    applied_now = []
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS app")
        await conn.execute("CREATE TABLE IF NOT EXISTS app.schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        cur = await conn.execute("SELECT name FROM app.schema_migrations")
        done = {r[0] for r in await cur.fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO app.schema_migrations (name) VALUES (%s)", (path.name,))
            applied_now.append(path.name)
    return applied_now


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set")
    # psycopg async needs the selector loop on Windows (Linux is unaffected).
    applied = asyncio.run(migrate(url), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    print("Applied: " + ", ".join(applied) if applied else "Nothing to apply, already up to date.")
