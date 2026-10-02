"""The `bot` process: Telegram long polling -> save to DB -> hand to Temporal.

    python -m app.bot

Rules (G1): only the owner's private chat is accepted; every update is saved (deduped by update_id) BEFORE
the polling offset moves past it, so a crash loses nothing. A sweeper re-dispatches anything saved but not
yet handed to Temporal (the outbox pattern).
"""

import asyncio
import logging
import sys

from app import db, telegram
from app.config import get_settings

log = logging.getLogger("bot")

MAX_INBOUND_PER_HOUR = 60


async def _over_rate_limit() -> bool:
    row = await db.fetchone(
        "SELECT count(*) AS n FROM messages WHERE direction = 'in' AND sent_at > now() - interval '1 hour'"
    )
    return row["n"] >= MAX_INBOUND_PER_HOUR


async def ingest(update: dict) -> dict | None:
    """Store one update if it comes from the owner. Returns the new row, or None (ignored / duplicate)."""
    owner = get_settings().telegram_owner_id

    if msg := update.get("message"):
        if msg.get("from", {}).get("id") != owner or msg.get("chat", {}).get("type") != "private":
            log.debug("ignored message from %s", msg.get("from", {}).get("id"))
            return None
        if msg.get("text") is None:
            await telegram.send("I can only read text for now.")
            return None
        if await _over_rate_limit():
            log.warning("inbound rate limit hit; dropping update %s", update["update_id"])
            return None
        return await db.fetchone(
            "INSERT INTO messages (direction, tg_update_id, tg_message_id, kind, body, sent_at)"
            " VALUES ('in', %s, %s, 'text', %s, to_timestamp(%s))"
            " ON CONFLICT (tg_update_id) DO NOTHING RETURNING id, kind, body",
            (update["update_id"], msg["message_id"], msg["text"][:4096], msg["date"]),
        )

    if q := update.get("callback_query"):
        if q.get("from", {}).get("id") != owner:
            return None
        await telegram.answer_callback(q["id"])  # stop the button's spinner right away
        return await db.fetchone(
            "INSERT INTO messages (direction, tg_update_id, tg_message_id, kind, body)"
            " VALUES ('in', %s, %s, 'button', %s)"
            " ON CONFLICT (tg_update_id) DO NOTHING RETURNING id, kind, body",
            (update["update_id"], q.get("message", {}).get("message_id"), q.get("data", "")),
        )
    return None


async def dispatch(row: dict) -> None:
    """Hand a saved message to Temporal. Filled in by T-07; failures leave the row for the sweeper."""
    from app.dispatch import dispatch as _dispatch
    await _dispatch(row)


async def poll_forever() -> None:
    try:
        await telegram.api("deleteWebhook")  # long polling and a webhook can't both be active
    except telegram.TelegramError as e:
        log.warning("deleteWebhook failed: %s", e)
    offset = None
    while True:
        try:
            updates = await telegram.api(
                "getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"]
            )
        except telegram.TelegramError as e:
            log.warning("getUpdates failed: %s", e)
            await asyncio.sleep(5)
            continue
        for update in updates:
            while True:  # don't move past an update until it's saved
                try:
                    row = await ingest(update)
                    break
                except Exception:
                    log.exception("saving update %s failed; retrying", update.get("update_id"))
                    await asyncio.sleep(5)
            if row:
                await dispatch(row)
            offset = update["update_id"] + 1  # confirmed to Telegram on the next getUpdates


async def sweep_forever(every: float = 5.0) -> None:
    """Outbox sweeper: re-dispatch inbound rows saved >10 s ago but never handed to Temporal."""
    while True:
        await asyncio.sleep(every)
        try:
            rows = await db.fetchall(
                "SELECT id, kind, body FROM messages WHERE direction = 'in' AND NOT dispatched"
                " AND sent_at < now() - interval '10 seconds' ORDER BY id LIMIT 100"
            )
            for row in rows:
                await dispatch(row)
        except Exception:
            log.exception("sweeper pass failed")


async def main() -> None:
    from app import logs
    logs.setup()
    await db.connect(get_settings().database_url)
    log.info("bot started; polling Telegram")
    await asyncio.gather(poll_forever(), sweep_forever())


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
