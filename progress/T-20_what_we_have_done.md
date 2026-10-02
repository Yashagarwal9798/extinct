# T-20: Connecting Gmail + token handling — what we have done

**Status:** code done ✅ · tested with fakes ✅ · **live connect pending your Google credentials (T-19)**

## In one sentence
One command connects your Gmail. The access keys Google gives us are **stored encrypted on your PC**, refreshed automatically, and the agent tells you clearly if you need to reconnect.

## What was built
| File | In simple terms |
|---|---|
| `app/connect_google.py` | The one-time connect script. It prints a Google link; you approve; done. |
| `app/google.py` | Token loading/refreshing/revoking + the Gmail calls (T-21/T-22) |
| `app/dispatch.py` | New `signal_event()`: tells the conversation "Gmail was just connected" |

### How connecting works (OAuth)
1. You run: `docker compose run --rm -p 127.0.0.1:8765:8765 worker-agent python -m app.connect_google`
2. It prints a Google link → you open it on your PC → sign in → approve.
3. Google redirects to `http://localhost:8765`, which the script catches. **Your Google password never touches our code**; you type it on Google's own page.
4. Google hands us two keys: an **access token** (lasts about 1 hour) and a **refresh token** (gets new access tokens). Both are **encrypted** into the local secrets store (T-04).
5. Supabase only learns `google: connected`, which permissions you granted, and your address. **Never the tokens.**
6. If you untick a permission (e.g. "send"), the matching tool simply stays hidden.

### Every time a Gmail tool runs
- An expired access token is **refreshed automatically**, and the new one saved (encrypted).
- If Google says the access was **revoked or expired** → Gmail is marked `needs_reauth`, Gmail tools disappear from the menu, and the AI tells you to run the connect script again.
- `revoke()` tells Google to cancel our access and deletes the local tokens (used by the wipe script later).

## Tests (5 here, 13 in `test_gmail.py` overall)
Not connected → clear error · valid token used without refreshing · **refreshed token is saved** · revoked → `needs_reauth` and tools hidden · **saving a connection puts no token in Supabase**.

## Credentials needed
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (T-19), plus `MASTER_KEY` and `DATABASE_URL`. Then run the command above once.

## Next
**T-21/T-22:** the Gmail tools.
