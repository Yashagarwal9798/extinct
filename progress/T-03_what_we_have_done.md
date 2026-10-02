# T-03: Supabase database — what we have done

**Status:** code done ✅ · tested against a local Postgres ✅ · **live Supabase check pending your credentials**

## In one sentence
We wrote the database tables the agent needs, a script that creates them, and a small module the rest of the code uses to talk to the database.

## What was built

| File | In simple terms |
|---|---|
| `migrations/001_init.sql` | The **blueprint**: creates the `app` schema and 8 tables. |
| `scripts/migrate.py` | Applies blueprints you haven't applied yet, and remembers which ones it has run. Safe to run any number of times. |
| `app/db.py` | One small **pool** of database connections plus 3 helpers: `fetchone`, `fetchall`, `execute`. |
| `tests/conftest.py` | Test setup: fake settings plus a **throwaway local Postgres** that stands in for Supabase. |
| `tests/test_db_schema.py` | 7 database tests. |
| `docker-compose.yml` | Added `testdb` (only starts with `--profile test`). It lives in memory and is wiped on restart. |

### The 8 tables (all in schema `app`)
| Table | Holds |
|---|---|
| `messages` | Every Telegram message in and out. `tg_update_id` is unique, so a message is never stored twice. `dispatched` = "handed to Temporal yet?" |
| `agent_turns` | Each time the agent "thinks": the conversation sent to the AI, the tool menu, and the status |
| `tool_results` | The result of every tool call. Its key (turn + call ID) makes retries safe. |
| `memory_facts` | Things it remembers about you. Duplicates are blocked (case-insensitive). |
| `approvals` | Pending button actions (Send/Cancel, Done) |
| `audit_log` | A diary of every decision the guardrails made |
| `connections` | Is Gmail connected? Which permissions? |
| `llm_calls` | Every AI request, used for the 45/day free budget |

Two tables have built-in **search** columns (`messages`, `memory_facts`), so "what did I say about the handyman?" works later.

### Security
- **Row Level Security is on for every table, with no rules.** Supabase's public web API roles see **nothing**, even if the schema were exposed by mistake. Our server connects as the owner, so it can still read and write.
- You must also make sure `app` is **not** in Supabase's *exposed schemas* list (step below).

## Problems we hit and fixed
1. **Windows + async database driver:** Windows' default event loop doesn't work with async psycopg. The scripts and tests pick the compatible loop. Docker (Linux) is unaffected.
2. **`localhost` was slow:** it tried IPv6 first, adding 3 seconds per connection. The tests use `127.0.0.1`.
3. **Review fix:** I first set the schema with a connection "startup option", but Supabase's pooler may ignore that. Now every new connection runs `SET search_path = app`, which works everywhere.
4. **Review fix:** the Docker image didn't contain `scripts/` and `migrations/`. Added, and checked that `migrate` runs from inside the image.

## Tests (7, all passing; 20 in the whole suite)
- Running migrations twice changes nothing the second time.
- All 8 tables exist, and **every one has Row Level Security on**.
- A duplicate Telegram update is rejected, and "insert if new" returns nothing for duplicates.
- Full-text search finds "handyman".
- Connections use the `app` schema.
- **A non-owner role (standing in for Supabase's public API) sees 0 rows.**

## How to check it yourself
```sh
docker compose --profile test up -d testdb     # throwaway test database
python -m uv run pytest                        # 20 passed
```

## Credentials needed (to finish the live check)
1. supabase.com → **New project** → choose a region near you (e.g. Mumbai) → save the **database password**.
2. **Connect → Session pooler** → copy the URI (with your password in it) → put it in `.env` as `DATABASE_URL=...`
3. **Settings → Data API → Exposed schemas:** make sure `app` is **not** listed (the defaults `public, graphql_public` are fine).
4. Run: `docker compose run --rm worker-agent python -m scripts.migrate` → it should print `Applied: 001_init.sql`.

Note: free Supabase projects **pause after about 7 days without activity**. While the bot runs it stays active.

## Next
**T-04:** the local encrypted secrets store (Google tokens are kept there, never in Supabase).
