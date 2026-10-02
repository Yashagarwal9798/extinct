# T-06: Long-polling bot (receiving messages) — what we have done

**Status:** code done ✅ · tested with a fake Telegram + test database ✅ · **live check pending your bot token**

## In one sentence
We wrote the **`bot` program** that keeps asking Telegram "any new messages?", saves **your** messages and button taps to the database exactly once, and ignores everyone else.

## How it works
1. **Long polling:** the bot calls `getUpdates` and Telegram holds the request open for up to 50 s until something arrives. No public web address is needed, which is why we chose this over webhooks.
2. **Only you (G1):** a message counts only if it's from `TELEGRAM_OWNER_ID` **and** in a private chat. Strangers get no reply at all, so the bot doesn't reveal it exists.
3. **Saved before confirmed:** Telegram keeps re-sending an update until we ask for the next ones. We move past an update **only after it's saved**. If the database is down, we wait and retry the same update, so **nothing is ever lost**.
4. **Never twice:** `tg_update_id` is unique in the database, so a re-sent update is skipped.
5. **Button taps** are saved too (kind `button`), and we immediately tell Telegram to stop the button's loading spinner.
6. **Photos/voice notes** get "I can only read text for now."
7. **Rate limit:** more than 60 messages in an hour → extra ones are dropped and logged.
8. **Sweeper:** every 5 s it looks for messages saved but not yet handed to Temporal and hands them over (finished in T-07).

## What was built
| File | In simple terms |
|---|---|
| `app/bot.py` | `ingest` (filter + save), `poll_forever` (the loop), `sweep_forever` (safety net), `main` |
| `tests/test_bot_ingest.py` | 7 tests |

## Tests (7, all passing)
Your text is stored · a duplicate update is ignored · strangers, groups and a stranger's button taps are ignored with no reply · button taps are stored and the spinner answered · non-text gets a polite reply · rate limit · **the loop doesn't move past an update until it's saved** (we simulated the database failing once).

## Credentials needed?
The Telegram token and your user ID (see T-05). Live check: `docker compose up -d bot` (after T-07 sets its real command), send your bot a message, and see it appear in the `messages` table.

## Next
**T-07:** hand each saved message to **Temporal** (signal-with-start) and build the conversation workflow.
