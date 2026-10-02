# T-01: Project skeleton — what we have done

**Status:** done ✅ (2026-10-02)

## In one sentence
We created the empty "shell" of the project: the dependency list, the settings loader, the example settings file, and the test setup. No features yet.

## What was built

| File | What it is | In simple terms |
|---|---|---|
| `pyproject.toml` | The project's ID card | Lists every library we'll use (Telegram calls, database, Temporal, Google, browser…) and how to run the tests. |
| `uv.lock` | Exact library versions | Makes sure every machine (your PC, the Docker containers) installs the *same* versions. |
| `app/config.py` | Settings loader | Reads settings (bot token, database URL, keys…) from environment variables, checks them, and tells you clearly what's missing or wrong. |
| `.env.example` | Template for your settings | Copy it to `.env` and fill it in. Every variable has a comment saying which task needs it. |
| `.gitignore` | "Never save these to git" list | Keeps `.env` (your secrets) and junk folders out of git. |
| `README.md` | How to set up and run | The commands you'll use. |
| `tests/test_config.py` | 12 automatic checks | Proves the settings loader works (see below). |

We also ran `git init` (the folder is now a git repository; nothing committed yet) and installed **uv**, the tool that installs libraries and runs things.

## How the settings loader works
- **6 settings are required**: Telegram bot token, your Telegram user ID, the Supabase database URL, the master key, the AI API key, and the main AI model name. If any are missing, it lists **all** of them at once.
- **Everything else has a sensible default**. For example, the timezone defaults to `Asia/Kolkata`, the free-model daily budget to 45 requests, and quiet hours to 23:00–07:00.
- **It validates values**, not just presence. For example: the master key must be exactly 32 bytes, the timezone must be real, and the daily budget must be above 0. All problems are reported together.
- It loads **once, on first use** (`get_settings()`), not when Python imports the file. That way tests can run without a real `.env`. This is a small change from the original plan, and tasks.md has been updated.

## Tests (12, all passing)
- An empty environment lists all 6 missing settings.
- Blank values (just spaces) count as missing.
- Minimal settings get the right defaults.
- Custom values are read correctly (a trailing `/` on the AI URL is removed).
- Seven kinds of bad values are each reported by name: non-number user ID, short master key, non-base64 master key, fake timezone, bad time, a 0 budget, and non-object JSON.
- Several bad values are reported together.

## How to check it yourself
```sh
python -m uv run pytest                                  # → 12 passed
python -m uv run --env-file .env python -m app.config    # → "Config OK" or a list of problems
```

## Credentials needed?
**Not yet.** The `.env` gets filled step by step:
- Telegram bot token and your user ID → **T-05**
- Supabase database URL → **T-03**
- AI key + model names → **T-12**
- Master key → you can generate it now (command in README); it's first used in **T-04**

## Next
**T-02:** Docker base. Temporal server in a container, the app image, and storage volumes. Needs **Docker Desktop running** (it's installed: version 29.1.3).
