# T-14: Sending the reply safely — what we have done

**Status:** done ✅

## In one sentence
Before the AI's answer reaches you, code checks it for **leaked secrets** (G5), then formats it nicely for Telegram and records it.

## What `send_reply` does (`app/activities.py`)
1. **Leak check (G5):** looks for Google/OpenRouter/Telegram tokens, private keys, and any **website password you saved** (from the local secrets store). On a hit, the reply is replaced by "I blocked a reply because it contained something that looked sensitive", and the block is written to the audit log.
2. **Formatting + splitting** (from T-05): markdown → Telegram HTML; at most 3 messages; every message recorded.
3. **Closes the turn:** status `done` / `stopped` / `failed`, plus the end time.
4. An empty reply sends nothing (used when the free quota message was already sent today).

Quiet hours aren't applied: reminders you set yourself should arrive when you asked. Quiet hours return later with email alerts (backlog).

## Tests (3, all passing)
A normal reply is sent and the turn closed · a reply containing a Google token is **blocked** and audited · an empty reply sends nothing.

## Next
**T-15/T-16:** memory tools.
