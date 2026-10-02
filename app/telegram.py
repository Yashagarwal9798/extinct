"""Telegram Bot API over plain httpx (no bot framework), plus markdown -> Telegram-HTML formatting.

Every message goes to the owner's private chat (chat id == owner's user id).
Every sent message is recorded in app.messages (direction 'out').
"""

import html
import itertools
import json
import re

import httpx

from app import db
from app.config import get_settings


class TelegramError(Exception):
    pass


class Retryable(TelegramError):
    """Rate limit, server error or network problem: try again later."""


class Permanent(TelegramError):
    """Bad request: retrying won't help."""


_client: httpx.AsyncClient | None = None
_fake_ids = itertools.count(1_000_000)  # message ids in dry-run mode


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(70.0, connect=10.0))
    return _client


async def api(method: str, files: dict | None = None, **params):
    """Call a Bot API method and return its `result`."""
    url = f"https://api.telegram.org/bot{get_settings().telegram_bot_token}/{method}"
    try:
        if files:  # multipart: nested values must be JSON strings
            data = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in params.items()}
            resp = await _http().post(url, data=data, files=files)
        else:
            resp = await _http().post(url, json=params)
    except httpx.HTTPError as e:
        raise Retryable(f"{method}: network error: {e!r}") from e
    try:
        body = resp.json()
    except ValueError:
        raise Retryable(f"{method}: HTTP {resp.status_code}, non-JSON body") from None
    if body.get("ok"):
        return body["result"]
    code, desc = body.get("error_code", resp.status_code), body.get("description", "")
    if code == 429 or code >= 500:
        raise Retryable(f"{method}: {code} {desc}")
    raise Permanent(f"{method}: {code} {desc}")


# ---------- formatting ----------

def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def to_telegram_html(md: str) -> str:
    """Convert the simple markdown models write into Telegram's HTML subset. Everything else is escaped."""
    saved: list[str] = []

    def keep(fragment: str) -> str:
        saved.append(fragment)
        return f"\x00{len(saved) - 1}\x00"

    md = re.sub(r"```[^\n`]*\n?(.*?)```", lambda m: keep(f"<pre>{_esc(m.group(1).rstrip())}</pre>"), md, flags=re.S)
    md = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{_esc(m.group(1))}</code>"), md)
    md = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
        lambda m: keep(f'<a href="{html.escape(m.group(2), quote=True)}">{_esc(m.group(1))}</a>'),
        md,
    )
    lines = []
    for line in _esc(md).split("\n"):
        s = line.strip()
        if re.fullmatch(r"\|?(\s*:?-{3,}:?\s*\|?)+", s):  # table separator row
            continue
        if len(s) > 1 and s.startswith("|") and s.endswith("|"):  # table row -> "a · b"
            line = " · ".join(c.strip() for c in s.strip("|").split("|"))
        if m := re.match(r"#{1,6}\s+(.*)", s):  # heading -> bold
            line = f"**{m.group(1)}**"
        line = re.sub(r"^(\s*)[-*]\s+", r"\1• ", line)  # bullets
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], text)


def split_bubbles(text: str, max_bubbles: int = 3, max_len: int = 3800) -> list[str]:
    """Split on blank lines into at most `max_bubbles` messages of at most `max_len` chars (before HTML)."""
    pieces = []
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        while len(para) > max_len:
            cut = para.rfind("\n", 0, max_len)
            if cut < max_len // 2:
                cut = para.rfind(" ", 0, max_len)
            if cut <= 0:
                cut = max_len
            pieces.append(para[:cut])
            para = para[cut:].lstrip()
        if para:
            pieces.append(para)
    chunks: list[str] = []
    for p in pieces:
        if chunks and len(chunks[-1]) + 2 + len(p) <= max_len:
            chunks[-1] += "\n\n" + p
        else:
            chunks.append(p)
    if len(chunks) > max_bubbles:
        chunks = chunks[:max_bubbles]
        chunks[-1] = chunks[-1][: max_len - 20] + "\n…(cut off)"
    return chunks


def buttons(*row: tuple[str, str]) -> dict:
    """One row of inline buttons: buttons(("Send", "appr:..:y"), ("Cancel", "appr:..:n"))."""
    for _, data in row:
        if len(data.encode()) > 64:
            raise ValueError(f"callback data too long: {data!r}")
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]]}


# ---------- sending ----------

def _owner() -> int:
    return get_settings().telegram_owner_id


async def record_out(body: str, tg_message_id: int | None, kind: str = "text", turn_id: str | None = None) -> None:
    await db.execute(
        "INSERT INTO messages (direction, tg_message_id, kind, body, dispatched, turn_id) VALUES ('out', %s, %s, %s, true, %s)",
        (tg_message_id, kind, body, turn_id),
    )


async def _send_one(text: str, reply_markup: dict | None) -> int:
    if get_settings().telegram_dry_run:
        return next(_fake_ids)
    params = {"chat_id": _owner(), "text": to_telegram_html(text), "parse_mode": "HTML",
              "link_preview_options": {"is_disabled": True}}
    if reply_markup:
        params["reply_markup"] = reply_markup
    try:
        msg = await api("sendMessage", **params)
    except Permanent as e:
        if "parse entities" not in str(e):
            raise
        params.pop("parse_mode")  # our HTML was rejected: send it plain rather than not at all
        params["text"] = text
        msg = await api("sendMessage", **params)
    return msg["message_id"]


async def send(text: str, reply_markup: dict | None = None, turn_id: str | None = None) -> list[int]:
    """Send text (split into bubbles). Buttons, if any, go on the last bubble. Returns message ids."""
    chunks = split_bubbles(text)
    ids = []
    for i, chunk in enumerate(chunks):
        mid = await _send_one(chunk, reply_markup if i == len(chunks) - 1 else None)
        await record_out(chunk, mid, "text", turn_id)
        ids.append(mid)
    return ids


async def send_photo(image: bytes, caption: str = "", turn_id: str | None = None) -> int:
    if get_settings().telegram_dry_run:
        mid = next(_fake_ids)
    else:
        msg = await api("sendPhoto", files={"photo": ("screenshot.jpg", image, "image/jpeg")},
                        chat_id=_owner(), caption=caption[:1000])
        mid = msg["message_id"]
    await record_out(caption or "[photo]", mid, "photo", turn_id)
    return mid


async def send_chat_action(action: str = "typing") -> None:
    if not get_settings().telegram_dry_run:
        try:
            await api("sendChatAction", chat_id=_owner(), action=action)
        except TelegramError:
            pass  # cosmetic; never fail a turn over it


async def set_reaction(message_id: int, emoji: str) -> None:
    if not get_settings().telegram_dry_run:
        await api("setMessageReaction", chat_id=_owner(), message_id=message_id,
                  reaction=[{"type": "emoji", "emoji": emoji}])


async def answer_callback(callback_id: str, text: str | None = None) -> None:
    if not get_settings().telegram_dry_run:
        try:
            await api("answerCallbackQuery", callback_query_id=callback_id, **({"text": text} if text else {}))
        except TelegramError:
            pass  # the spinner stops by itself after a while


async def edit_message_text(message_id: int, text: str) -> None:
    """Replace a message's text and remove its buttons."""
    if not get_settings().telegram_dry_run:
        try:
            await api("editMessageText", chat_id=_owner(), message_id=message_id,
                      text=to_telegram_html(text), parse_mode="HTML")
        except Permanent as e:
            if "message is not modified" not in str(e):
                raise
