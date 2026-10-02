"""Live check of the Telegram client (needs TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID, DATABASE_URL in env).

    python -m uv run --env-file .env python -m scripts.tg_demo
"""

import asyncio
import sys

from app import db, telegram
from app.config import get_settings


async def main():
    await db.connect(get_settings().database_url)
    await telegram.send_chat_action()
    [mid] = await telegram.send("**Hello** from Mini-Instinct 👋\n\n- formatting\n- `code`\n- [a link](https://example.com)")
    await telegram.set_reaction(mid, "👀")
    [bid] = await telegram.send("Buttons test:", reply_markup=telegram.buttons(("Yes", "demo:y"), ("No", "demo:n")))
    await asyncio.sleep(2)
    await telegram.edit_message_text(bid, "✓ Buttons removed by editing the message")
    print("Sent. Check your Telegram chat with the bot.")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
