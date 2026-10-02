# T-07: Messages flow into Temporal — what we have done

**Status:** done ✅ (tested end-to-end with the real Temporal server; Telegram faked)

## In one sentence
Every saved message is now handed to a **Temporal workflow** that waits a moment for you to finish typing, then handles all your messages together. For now it just echoes them back; the AI comes in T-13.

## The pieces
| File | In simple terms |
|---|---|
| `app/dispatch.py` | **Hand-off.** Sends the message ID to the workflow with "signal-with-start" (= "start the workflow if needed, and deliver this"). Then marks the message `dispatched`. If Temporal is down, it leaves the row for the sweeper. |
| `app/workflows.py` | **The manager (workflow code).** `ConversationWorkflow`: an inbox, a 2-second "are you still typing?" wait, then one turn for the whole batch. |
| `app/activities.py` | **The employees (activities).** For now just `echo_reply`. |
| `app/worker.py` | The process that runs the workflow and activities (`python -m app.worker agent`). |
| `app/clients.py` | One shared connection to Temporal. |
| `docker-compose.yml` | `bot` and `worker-agent` now run their real commands. They're **stopped until `.env` is filled**, otherwise they would restart in a loop. |

## How a message travels
```
you type → bot saves it (T-06) → dispatch: signal-with-start "conversation" with {msg_id}
        → workflow inbox → wait 2 s with no new message (max 10 s) → turn with ALL waiting messages
        → activity reads the texts from the DB → reply
```
Signals carry **only IDs**, never your text. Temporal's history stays small, and your words stay in our database.

## Problems found by the tests (and fixed)
1. **A real bug:** with signal-with-start, Temporal delivers the first message *before* the workflow's main code starts. Restoring saved state in the main code was wiping out that message. **Fix:** restore state in the workflow's constructor (`@workflow.init`), which runs before any signal. Without the test, a message could have been lost right after the workflow "refreshes" itself (continue-as-new).
2. A default value in `dispatch` was fixed at import time, so the test accidentally started the real `conversation` workflow. Fixed, and the stray workflow was cleaned up.

## Tests (6 new, all passing)
| Test | Proves |
|---|---|
| 3 quick messages, one sent twice | → **one** turn with `[1, 2, 3]`: burst merged, duplicate dropped |
| Two messages with a gap | → two separate turns |
| Continue-as-new | The workflow "refreshes" after N turns and **still remembers** which messages it saw |
| `signal_for` | Text → `new_message` (an exact "stop" is flagged); button → `button` |
| **End-to-end** | Saved message → dispatch → real workflow → real echo activity → reply row "You said: ping" |
| Temporal down | dispatch doesn't crash, and the row stays undispatched for the sweeper |

## Credentials needed?
Not for the logic. To run it live: the Telegram token, your owner ID, and `DATABASE_URL`, then `docker compose up -d`.

## Next
**T-08:** the workflow's status check and upgrade policy (mostly done in T-07).
