"""Postgres (Supabase) access: one small connection pool + three helpers.

    await db.connect(url)          # once at startup
    row  = await db.fetchone("SELECT ... WHERE id = %s", (id,))   -> dict | None
    rows = await db.fetchall(...)                                  -> list[dict]
    n    = await db.execute(...)                                   -> rows affected
"""

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


async def connect(url: str, max_size: int = 3) -> None:
    """Open the pool. Small on purpose: Supabase's free pooler has few connections."""
    global _pool
    if _pool is not None:
        return
    _pool = AsyncConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
        # SET per connection instead of the "options" startup parameter, which poolers may drop.
        configure=_use_app_schema,
    )
    await _pool.open(wait=True, timeout=30)


async def _use_app_schema(conn) -> None:
    await conn.execute("SET search_path = app")


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("db.connect() was not called")
    return _pool


async def fetchone(sql: str, params: tuple | dict = ()) -> dict | None:
    async with pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchone() if cur.description else None


async def fetchall(sql: str, params: tuple | dict = ()) -> list[dict]:
    async with pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchall() if cur.description else []


async def execute(sql: str, params: tuple | dict = ()) -> int:
    async with pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return cur.rowcount
