"""Shared test setup.

- Fake settings, so code that calls get_settings() works without a real .env.
- `appdb` fixture: a real Postgres (docker compose --profile test up -d testdb) with migrations applied
  and every table emptied before each test. Skips if the test DB isn't running.
"""

import asyncio
import base64
import os
import sys

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54329/postgres")

os.environ.update({
    "TELEGRAM_BOT_TOKEN": "123456789:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz1",
    "TELEGRAM_OWNER_ID": "42",
    "DATABASE_URL": TEST_DATABASE_URL,
    "MASTER_KEY": base64.b64encode(b"m" * 32).decode(),
    "LLM_API_KEY": "sk-or-v1-test",
    "MODEL_MAIN": "test/main:free",
    "MODEL_BROWSER": "test/browser:free",
    "TEMPORAL_ADDRESS": "localhost:7233",
    "OWNER_TIMEZONE": "Asia/Kolkata",
    "SECRETS_DB_PATH": os.path.join(__import__("tempfile").mkdtemp(prefix="mi-secrets-"), "secrets.db"),
    "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-secret",
})

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

TABLES = ["messages", "agent_turns", "tool_results", "memory_facts", "approvals", "audit_log", "connections", "llm_calls"]


def pytest_configure(config):
    config.addinivalue_line("markers", "proactor: run on the Proactor loop on Windows (Playwright needs subprocesses)")


def pytest_asyncio_loop_factories(config, item):
    # psycopg async needs the selector loop on Windows; Playwright needs Proactor. Linux: default loop.
    if sys.platform != "win32":
        return None
    if item.get_closest_marker("proactor"):
        return {"proactor": asyncio.ProactorEventLoop}
    return {"selector": asyncio.SelectorEventLoop}


_migrated = False


@pytest.fixture
async def appdb():
    global _migrated
    import psycopg

    try:
        conn = await psycopg.AsyncConnection.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=3)
    except Exception:
        pytest.skip("test DB not running (docker compose --profile test up -d testdb)")
    async with conn:
        if not _migrated:
            await conn.execute("DROP SCHEMA IF EXISTS app CASCADE")
            from scripts.migrate import migrate
            await migrate(TEST_DATABASE_URL)
            _migrated = True
        await conn.execute("TRUNCATE " + ", ".join(f"app.{t}" for t in TABLES) + " RESTART IDENTITY")
    await db.connect(TEST_DATABASE_URL)
    yield db
    await db.close()
