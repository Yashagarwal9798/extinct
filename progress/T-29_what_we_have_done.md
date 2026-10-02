# T-29: `browser_task` tool — what we have done

**Status:** done ✅

## In one sentence
The main agent can now say "use the browser to do X", **reading freely** but **acting only after your tap**.

## The tool
`browser_task(goal, mode, start_url?)`
| mode | Meaning | Risk tier | Approval |
|---|---|---|---|
| `read` | Look, search, read, check | R | No |
| `act` | Submit, post, send, buy, delete, change | **WO** | **Yes**: "Do this in your browser: {goal} (start: …)" + [Do it] [Cancel] |

- Runs on the **`browser` queue**, so the browser container does the work (10-minute limit, heartbeat every step).
- **Limits:** 60 read tasks and 20 act tasks per 24 h.
- `start_url` must be http(s).
- **Results** reach the main AI wrapped as `<untrusted source="browser">`. Web text is never trusted.
- **Screenshot:** if the sub-agent asked for one, it's sent to your Telegram.
- **"Still working on it…"** after 30 s (from T-13).
- **Approved act tasks** run on the browser worker too. The result is sent to you and the approval message edited to "✓ Done". If the act task hits a login, the message changes to "⏸ Waiting for you to take over".
- Every browser action is written to the audit log as `browser_action` (URL + action, no typed text).

## Tests (7)
Done → untrusted result + screenshot + audit · failure → a clear error to the AI · **needs_user → live-view link + Done button** and the tap becomes an event · read needs no approval, act does (with the exact text) · bad start_url refused · **approved act task runs on the browser queue** and you get the result · approved act task that needs a takeover → "Waiting for you".

## Next
**T-30:** the takeover flow.
