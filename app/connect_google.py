"""One-time Gmail connection. Run inside Docker (port 8765 forwarded to your PC):

    docker compose run --rm -p 127.0.0.1:8765:8765 worker-agent python -m app.connect_google

It prints a Google link: open it in your PC's browser, approve, and you're done. Tokens are stored
encrypted in the local secrets store; Supabase only learns "google: connected" and which scopes.
Run it again any time Gmail says it needs reconnecting.
"""

import asyncio
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app import db, google
from app.config import get_settings


def authorize():
    flow = InstalledAppFlow.from_client_config(google.client_config(), google.SCOPES)
    return flow.run_local_server(
        host="localhost", bind_addr="0.0.0.0", port=8765, open_browser=False,
        authorization_prompt_message="\nOpen this link in your browser and approve:\n\n{url}\n",
        success_message="Gmail connected. You can close this tab and go back to Telegram.",
        access_type="offline", prompt="consent",  # always get a refresh token
    )


async def main():
    creds = await asyncio.to_thread(authorize)
    profile = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
    await db.connect(get_settings().database_url)
    await google.save_connection(creds, profile["emailAddress"])
    print(f"Connected {profile['emailAddress']} with scopes: {sorted(creds.granted_scopes or creds.scopes)}")
    missing = set(google.SCOPES) - set(creds.granted_scopes or creds.scopes or [])
    if missing:
        print(f"Note: you didn't grant {sorted(missing)}; the matching tools stay hidden.")
    try:
        from app.dispatch import signal_event
        await signal_event({"kind": "google_connected"})
    except Exception as e:
        print(f"(Couldn't notify the agent: {e!r}. It will notice on the next message.)")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
