"""Delete ALL your Mini-Instinct data (asks you to type WIPE first).

    docker compose run --rm worker-agent python -m scripts.wipe
    docker compose down -v        # then: removes the local volumes (secrets, browser profile, Temporal state)

Order: revoke Google's access at Google -> delete local secrets -> drop the Supabase schema "app".
"""

import asyncio
import sys

from app import db
from app.config import get_settings


async def wipe(confirm: str) -> list[str]:
    if confirm != "WIPE":
        return ["Cancelled. Nothing was deleted."]
    done = []
    await db.connect(get_settings().database_url)
    try:
        from app import google
        await google.revoke()
        done.append("Google access revoked and local tokens deleted")
    except Exception as e:  # not connected, or already revoked
        done.append(f"Google: nothing to revoke ({type(e).__name__})")
    await db.execute("DROP SCHEMA IF EXISTS app CASCADE")
    done.append("Supabase schema 'app' dropped (messages, memory, audit, ...)")
    await db.close()
    done.append("Now run: docker compose down -v   (deletes secrets, browser profile and Temporal state)")
    return done


if __name__ == "__main__":
    answer = input("This deletes ALL your Mini-Instinct data. Type WIPE to continue: ").strip()
    for line in asyncio.run(wipe(answer), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None):
        print(line)
