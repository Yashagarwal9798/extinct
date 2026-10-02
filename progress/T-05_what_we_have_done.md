# T-05: Telegram client — what we have done

**Status:** code done ✅ · tested against a fake Telegram ✅ · **live check pending your bot token**

## In one sentence
We wrote the part of the program that **talks to Telegram**: sending messages, buttons, photos, the "typing…" indicator and emoji reactions, plus tidying up the AI's text so it looks right in Telegram.

## What was built
| File | In simple terms |
|---|---|
| `app/telegram.py` | All Telegram calls, using plain HTTP (no bot framework) |
| `scripts/tg_demo.py` | A live demo you can run once you have a bot token |
| `tests/test_telegram.py` | 18 tests against a **fake Telegram server** |
| `app/config.py` | New setting `TELEGRAM_DRY_RUN` (record messages, but don't really send) for the evaluation in T-37 |

### What it can do
- `send(text, buttons)`: sends text. Long text is split into at most **3 messages**, and buttons go on the last one. **Every sent message is saved** in the database.
- `send_photo` (screenshots), `send_chat_action` ("typing…"), `set_reaction` (👀), `answer_callback` (stops the button's loading spinner), `edit_message_text` (e.g. turns a Send/Cancel message into "✓ Sent" and removes the buttons).
- **Error types:** "try again later" (rate limit, server error, network) vs "won't work" (bad request). Temporal uses this to decide whether to retry.

### Formatting (AI markdown → Telegram)
The AI writes `**bold**`, `*italic*`, `` `code` ``, `[links](url)`, `# headings`, `- bullets`, and tables. Telegram understands a small set of HTML tags, so we convert. **Everything else is escaped**, so a message containing `<script>` shows as text and can't break anything. If Telegram still rejects the HTML, we send it as plain text instead of failing.

## Tests (18, all passing)
- 10 formatting cases, including escaping, links with `&`, `snake_case` names left alone, `2 * 3 * 4` left alone, tables, and code blocks kept untouched.
- Splitting: short text = 1 message, long text capped at 3 messages with "(cut off)", and huge paragraphs split safely.
- Button data over Telegram's 64-byte limit is rejected.
- A fake Telegram returns 429 / 502 / 400 → mapped to the right error type.
- Sending saves rows in the database, and buttons go only on the last bubble.
- Bad HTML → automatically re-sent as plain text.
- Dry-run sends nothing but still records.

## Credentials needed (you do this; about 3 minutes)
1. In Telegram, open **@BotFather** → `/newbot` → choose a name and a username ending in `bot` → copy the **token** into `.env` as `TELEGRAM_BOT_TOKEN`.
2. In BotFather: `/setjoingroups` → choose your bot → **Disable** (so nobody can add it to groups).
3. Send your new bot any message. Then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and find `"from":{"id": 123456789…` → put that number in `.env` as `TELEGRAM_OWNER_ID`.
4. Live check: `python -m uv run --env-file .env python -m scripts.tg_demo` → you'll get a formatted message, a 👀 reaction, and a button message that gets edited.

## Next
**T-06:** the bot process that **receives** your messages (long polling).
