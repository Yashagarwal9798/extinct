# Mini-Instinct

A self-hosted personal agent you text on **Telegram**. It uses **its own Chrome** (which you can watch and take over), your **Gmail**, and runs **reminders and scheduled tasks**. Everything runs on your PC with Docker, on **free AI models**.

- What and why: [PRD.md](PRD.md) · Build plan: [tasks.md](tasks.md) · Per-task notes: [progress/](progress/) · Story and decisions: [Context.md](Context.md)

## Go live (first time, about 45 minutes)

Do these in order. Each step says which file in `progress/` has the details.

1. **Prerequisites:** Docker Desktop (WSL2), with "Start when you sign in" on and Memory ≥ 6 GB (Settings → Resources). Python 3.12+ and uv: `python -m pip install --user uv`.
2. `cp .env.example .env`, then fill it in as you go:
   | `.env` value | Where it comes from | Details |
   |---|---|---|
   | `MASTER_KEY` | `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"` (save a copy in your password manager!) | T-04 |
   | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID` | @BotFather + `getUpdates` | T-05 |
   | `DATABASE_URL` | Supabase → Connect → **Session pooler** | T-03 |
   | `LLM_API_KEY`, `MODEL_MAIN`, `MODEL_BROWSER` | openrouter.ai (free models with "tools") | T-12 |
   | `VNC_PASSWORD` (≤ 8 characters) | You choose | T-24 |
   | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Cloud, Desktop OAuth client | T-19 |
   | `LIVE_VIEW_URL` (optional) | Tailscale | T-25 |
3. Check it: `python -m uv run --env-file .env python -m app.config` → "Config OK".
4. Build and create the tables:
   ```sh
   docker compose build
   docker compose up -d temporal
   docker compose run --rm worker-agent python -m scripts.migrate     # → Applied: 001_init.sql
   ```
5. Pick your free models (about 4 requests each):
   ```sh
   docker compose run --rm worker-agent python -m scripts.llm_probe "<model id>" [--image]
   ```
6. Start everything: `docker compose up -d` → text your bot "hi".
7. Connect Gmail (once):
   ```sh
   docker compose run --rm -p 127.0.0.1:8765:8765 worker-agent python -m app.connect_google
   ```
8. Open the live browser at http://localhost:6080/vnc.html and log into the sites you want the agent to use.
9. Optional checks: `scripts.injection_check` (T-23), `scripts.browser_try` (T-31), `scripts.eval_scenarios` (T-37).

## Everyday commands

```sh
docker compose ps                         # what's running
docker compose logs -f worker-agent       # JSON logs; grep a turn_id to follow one turn
docker compose run --rm worker-agent python -m scripts.usage     # free AI quota used today
docker compose down                       # stop (your data is kept)
sh scripts/backup.sh                      # backup into ./backup/<date>/ (T-36)
```
- Temporal UI (workflows, timers, scheduled tasks): http://localhost:8233
- Live browser: http://localhost:6080/vnc.html
- Every port is bound to `127.0.0.1`, so nothing is reachable from your network.

## What runs where

| Service | Does |
|---|---|
| `temporal` | Durable state: conversations, timers, scheduled tasks (SQLite on the `temporal-data` volume) |
| `bot` | Telegram long polling → saves messages → hands them to Temporal |
| `worker-agent` | The agent: context, model calls, tools (memory, Gmail, scheduling), approvals |
| `browser` | Chrome on a virtual screen + noVNC live view + the `browser` worker |

Data: bulk app data in **Supabase** (schema `app`, not exposed via its API) · tokens **encrypted locally** (`secrets` volume) · your logins in the local **browser profile** (`browser-profile` volume).

## Development

```sh
python -m uv sync
docker compose up -d temporal                 # some tests use the real Temporal dev server
docker compose --profile test up -d testdb    # throwaway Postgres standing in for Supabase
python -m uv run python -m playwright install chromium   # browser tests
python -m uv run pytest                       # 177 tests (~2 min)
```
Tests that need Temporal, the test DB or Chromium skip themselves if those aren't available.

### Changing workflow code (upgrade policy)

A running workflow replays its history with the **current** code. If you change `app/workflows.py` in a way that changes the order of steps, terminate the running conversation so it restarts cleanly. The next message recreates it, and saved messages are never lost:

```sh
docker compose exec temporal temporal --address 127.0.0.1:7233 workflow terminate --workflow-id conversation --reason upgrade
```

Scheduled tasks (`task-*` workflows and schedules) are separate and keep running. Once the project is stable, use `workflow.patched()` for changes instead.

Check what the conversation workflow is doing:

```sh
docker compose exec temporal temporal --address 127.0.0.1:7233 workflow query --workflow-id conversation --type status
```

### WSL2 memory (Chrome needs it)
Create `%UserProfile%\.wslconfig`:
```
[wsl2]
memory=6GB
```
then run `wsl --shutdown` and restart Docker Desktop.
