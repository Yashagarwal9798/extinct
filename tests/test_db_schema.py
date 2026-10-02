import psycopg
import pytest

from conftest import TABLES, TEST_DATABASE_URL
from scripts.migrate import migrate


async def test_migrate_is_idempotent(appdb):
    assert await migrate(TEST_DATABASE_URL) == []  # already applied by the fixture


async def test_all_tables_exist_with_rls(appdb):
    rows = await appdb.fetchall(
        "SELECT relname, relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'app' AND c.relkind = 'r' AND relname <> 'schema_migrations'"
    )
    found = {r["relname"]: r["relrowsecurity"] for r in rows}
    assert set(found) == set(TABLES)
    assert all(found.values()), "every table must have row level security enabled"


async def test_duplicate_update_id_rejected(appdb):
    await appdb.execute("INSERT INTO messages (direction, tg_update_id, body) VALUES ('in', 7, 'hi')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        await appdb.execute("INSERT INTO messages (direction, tg_update_id, body) VALUES ('in', 7, 'again')")


async def test_on_conflict_do_nothing_dedupes(appdb):
    sql = "INSERT INTO messages (direction, tg_update_id, body) VALUES ('in', 8, 'x') ON CONFLICT DO NOTHING RETURNING id"
    assert await appdb.fetchone(sql) is not None
    assert await appdb.fetchone(sql) is None


async def test_full_text_search_column(appdb):
    await appdb.execute("INSERT INTO messages (direction, body) VALUES ('in', 'the handyman Ramesh fixed the sink')")
    row = await appdb.fetchone("SELECT body FROM messages WHERE tsv @@ websearch_to_tsquery('simple', 'handyman')")
    assert row and "Ramesh" in row["body"]


async def test_search_path_is_app(appdb):
    row = await appdb.fetchone("SHOW search_path")
    assert row["search_path"] == "app"


async def test_non_owner_role_cannot_read(appdb):
    # Stand-in for Supabase's anon role: RLS with no policies -> no rows visible.
    await appdb.execute("INSERT INTO messages (direction, body) VALUES ('in', 'secret')")
    async with await psycopg.AsyncConnection.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        await conn.execute("DROP ROLE IF EXISTS anon_test")
        await conn.execute("CREATE ROLE anon_test")
        await conn.execute("GRANT USAGE ON SCHEMA app TO anon_test; GRANT SELECT ON app.messages TO anon_test")
        await conn.execute("SET ROLE anon_test")
        cur = await conn.execute("SELECT count(*) FROM app.messages")
        assert (await cur.fetchone())[0] == 0
        await conn.execute("RESET ROLE")
        await conn.execute("DROP OWNED BY anon_test; DROP ROLE anon_test")
