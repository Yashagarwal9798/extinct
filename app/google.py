"""Google OAuth tokens (stored encrypted in the local secrets store) + Gmail API calls.

Tokens never go to Supabase or into the model's context. Google's client library is blocking, so every call
runs in a thread. Email content returned to the model is wrapped as untrusted (it's written by other people).
"""

import asyncio
import base64
import json
import logging
from email.message import EmailMessage
from html.parser import HTMLParser

import httpx
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app import db
from app.agent.context import untrusted
from app.agent.tools import ToolError
from app.config import get_settings
from app.secrets import secret_store

log = logging.getLogger("google")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
BODY_MAX_CHARS = 16_000


def client_config() -> dict:
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise SystemExit("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first (see progress/T-19).")
    return {"installed": {"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                          "token_uri": "https://oauth2.googleapis.com/token",
                          "redirect_uris": ["http://localhost"]}}


async def save_connection(c: Credentials, email: str) -> None:
    secret_store().put("oauth", "google", c.to_json().encode(), {"email": email})
    scopes = sorted(c.granted_scopes or c.scopes or [])
    await db.execute(
        "INSERT INTO connections (provider, status, scopes, meta, updated_at) VALUES ('google', 'connected', %s, %s, now())"
        " ON CONFLICT (provider) DO UPDATE SET status = 'connected', scopes = EXCLUDED.scopes, meta = EXCLUDED.meta,"
        " updated_at = now()", (scopes, json.dumps({"email": email})))


async def _mark(status: str) -> None:
    await db.execute("UPDATE connections SET status = %s, updated_at = now() WHERE provider = 'google'", (status,))


async def creds() -> Credentials:
    """Valid credentials, refreshed if needed. Raises ToolError the model can explain to the user."""
    raw = secret_store().get("oauth", "google")
    if raw is None:
        raise ToolError("Gmail is not connected. The user must run connect_google on their PC.")
    c = Credentials.from_authorized_user_info(json.loads(raw))
    if not c.valid:
        try:
            await asyncio.to_thread(c.refresh, Request())
        except RefreshError as e:
            await _mark("needs_reauth")
            log.warning("google refresh failed: %s", e)
            raise ToolError("Gmail access expired or was revoked. The user must run connect_google again.") from e
        secret_store().put("oauth", "google", c.to_json().encode())
    return c


async def service():
    c = await creds()
    return build("gmail", "v1", credentials=c, cache_discovery=False)


async def run(request):
    """Execute a googleapiclient request in a thread, mapping API errors to ToolError."""
    try:
        return await asyncio.to_thread(request.execute)
    except HttpError as e:
        if e.resp.status in (401, 403):
            await _mark("needs_reauth")
        if e.resp.status >= 500 or e.resp.status == 429:
            raise  # transient: let Temporal retry the activity
        raise ToolError(f"Gmail error {e.resp.status}: {e.reason}") from e


async def revoke() -> None:
    raw = secret_store().get("oauth", "google")
    if raw:
        token = json.loads(raw).get("refresh_token") or json.loads(raw).get("token")
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post("https://oauth2.googleapis.com/revoke", params={"token": token})
    secret_store().delete("oauth", "google")
    await _mark("revoked")


# ---------------------------------------------------------------- reading mail

def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextOnly()
    p.feed(html)
    lines = [" ".join(line.split()) for line in "".join(p.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def extract_body(payload: dict) -> str:
    """Prefer text/plain anywhere in the MIME tree; fall back to stripped text/html."""
    plain, html = [], []

    def walk(part):
        mime, data = part.get("mimeType", ""), part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            html.append(_decode(data))
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    return html_to_text("\n".join(html)) if html else ""


async def search_email(query: str, max_results: int = 5) -> list[dict]:
    svc = await service()
    listing = await run(svc.users().messages().list(userId="me", q=query, maxResults=max_results))
    out = []
    for m in listing.get("messages", []):
        msg = await run(svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                                   metadataHeaders=["From", "Subject", "Date"]))
        h = _headers(msg)
        out.append({"id": msg["id"], "thread_id": msg.get("threadId"), "from": h.get("from", ""),
                    "subject": h.get("subject", ""), "date": h.get("date", ""), "snippet": msg.get("snippet", ""),
                    "unread": "UNREAD" in msg.get("labelIds", [])})
    return out


async def read_email(message_id: str) -> dict:
    svc = await service()
    msg = await run(svc.users().messages().get(userId="me", id=message_id, format="full"))
    h = _headers(msg)
    body = extract_body(msg.get("payload", {}))
    if len(body) > BODY_MAX_CHARS:
        body = body[:BODY_MAX_CHARS] + "\n…(truncated)"
    return {"id": msg["id"], "thread_id": msg.get("threadId"), "from": h.get("from", ""), "to": h.get("to", ""),
            "subject": h.get("subject", ""), "date": h.get("date", ""), "body": body}


# ---------------------------------------------------------------- sending mail

def build_message(to: list[str], subject: str, body: str, sender: str = "",
                  in_reply_to: str = "", references: str = "") -> EmailMessage:
    m = EmailMessage()
    m["To"] = ", ".join(to)
    if sender:
        m["From"] = sender
    m["Subject"] = subject
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = f"{references} {in_reply_to}".strip()
    m.set_content(body)
    return m


async def send_email(to: list[str], subject: str, body: str, reply_to_message_id: str | None = None) -> dict:
    svc = await service()
    thread_id, in_reply_to, refs = None, "", ""
    if reply_to_message_id:
        orig = await run(svc.users().messages().get(userId="me", id=reply_to_message_id, format="metadata",
                                                     metadataHeaders=["Message-ID", "References", "Subject"]))
        h = _headers(orig)
        thread_id, in_reply_to, refs = orig.get("threadId"), h.get("message-id", ""), h.get("references", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {h.get('subject', subject)}"
    raw = base64.urlsafe_b64encode(build_message(to, subject, body, "", in_reply_to, refs).as_bytes()).decode()
    payload = {"raw": raw, **({"threadId": thread_id} if thread_id else {})}
    sent = await run(svc.users().messages().send(userId="me", body=payload))
    return {"sent": True, "id": sent.get("id"), "thread_id": sent.get("threadId")}


def wrap(source: str, data) -> str:
    return untrusted(source, json.dumps(data, ensure_ascii=False, indent=1))
