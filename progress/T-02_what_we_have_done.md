# T-02: Docker base — what we have done

**Status:** done ✅ (2026-10-02)

## In one sentence
We set up Docker so one command (`docker compose up -d`) starts the **Temporal server** and two empty app containers that later tasks fill in.

## Before we started
You had two containers from another project ("hippocrates": Postgres + Redis) running. I **stopped** them (not deleted). Their data is safe, and `docker start hippocrates-postgres hippocrates-redis` brings them back.

## What was built

| File | In simple terms |
|---|---|
| `docker-compose.yml` | The "recipe" listing our services. Docker reads it and runs them all. |
| `docker/app.Dockerfile` | How to build the image for our Python code (Python 3.12 + our libraries). |
| `.dockerignore` | Keeps `.env` (secrets), `.venv` and docs out of the image. |
| `tests/test_temporal_smoke.py` | A live test that runs a real mini workflow on the Temporal server. |

### The services

| Service | What it does now | Later |
|---|---|---|
| `temporal` | **Temporal server + web UI**: the "notebook" that remembers every workflow step, timer and scheduled task | Same |
| `bot` | Just waits (`sleep infinity`) | T-06: the Telegram long-polling bot |
| `worker-agent` | Just waits | T-07: the Temporal worker that runs the agent |

### Storage (Docker volumes)
- `temporal-data`: Temporal's database file. **This holds your scheduled tasks later, so it matters.** It survives restarts and `docker compose down`.
- `secrets`: where the encrypted secrets file will live (T-04). It never leaves your PC.

### Safety
Every port is bound to `127.0.0.1` (your PC only). Nobody on your Wi-Fi or the internet can reach them.

## Problems we hit and fixed
1. **Permission problem:** the Temporal image runs as a normal user (not root, which is good). A brand-new Docker volume is owned by root, though, so Temporal couldn't write its database. **Fix:** mount the volume at the user's own home folder (`/home/temporal`), which it owns. No root needed.
2. **Compose syntax:** "use `.env` if it exists" must be written as a list. Fixed.

## Tests and checks (all passed)
| Check | Result |
|---|---|
| All 3 services start; Temporal reports **healthy** | ✅ |
| Web UI at http://localhost:8233 answers | ✅ (HTTP 200) |
| **Smoke test:** a real workflow + activity runs on the server through our Python library | ✅ |
| **Persistence:** started a workflow → restarted Temporal → the workflow was still there | ✅ |
| The app image has Python 3.12 and our code imports fine | ✅ |
| Full test suite | ✅ 13 passed |

## Things to know
- **Docker currently has 3.7 GB of RAM.** That's fine now. Before the browser task (T-24), raise it to about 6 GB (instructions in the README).
- `docker compose down` stops everything but **keeps your data** (volumes). Only `docker compose down -v` deletes it. Don't use `-v` unless you mean it.

## How to check it yourself
```sh
docker compose ps                 # 3 services, temporal "healthy"
python -m uv run pytest           # 13 passed
```
Open http://localhost:8233 to see the Temporal UI (empty for now).

## Credentials needed?
**Not for T-02.** For **T-03 (Supabase)**, I'll need you to:
1. Create a free project at supabase.com (pick the region closest to you, e.g. Mumbai) and save the database password.
2. In the project, open **Connect → Session pooler** and copy that connection string into `.env` as `DATABASE_URL`.

## Next
**T-03:** the Supabase database. Create the `app` schema and tables, lock them so Supabase's public API can't reach them, and add a small migration runner.
