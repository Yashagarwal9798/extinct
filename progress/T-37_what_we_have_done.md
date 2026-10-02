# T-37: Scenario evaluation — ready to run

**Status:** tool done ✅ (tested with a fake AI) · **running it needs your OpenRouter key**

## In one sentence
A list of **15 realistic requests** you can run against the real free model to measure how often the agent does the right thing (target **≥ 85 %**).

## The scenarios (`scripts/eval_scenarios.py`)
chat · save a fact · use a fact · find an old message · reminder in 2 h · weekly reminder · list tasks · a scheduled `do` task · **ambiguous "remind me at 7" → one question** · Gmail unread · **Gmail send → asks for your tap** · browser read (HN) · **browser act → asks for your tap** · a not-yet-logged-in site · a lone "stop".

Each checks: **which tools were called**, the **reply** (e.g. it mentions the tap button), and that it answered at all.

## Running it on the free tier
```sh
docker compose run --rm worker-agent python -m scripts.eval_scenarios --list          # names + estimated requests
docker compose run --rm worker-agent python -m scripts.eval_scenarios --only chat,memory_save,memory_use
```
- It **estimates the requests first** and refuses to start if today's budget (45) isn't enough, so run it in chunks over a few days.
- Telegram is in **dry-run**: nothing is sent to you.
- Browser scenarios run inside the browser container (instructions at the top of the script).
- Scheduled tasks it creates are real: cancel them afterwards ("what's scheduled?" → cancel) or in the Temporal UI.

## Tests
The runner with a fake AI: "chat" passes, and "memory_save" correctly fails when no tool was called → "1/2 passed".

## Next
**T-38:** always-on + chaos checks.
