# T-26: Browser worker (browser manager) — what we have done

**Status:** done ✅

## In one sentence
The browser container runs a **Temporal worker** on the `browser` queue that **owns Chrome**: it opens it at startup, gives each task its own tab, and keeps your logins.

## The browser manager (`BrowserManager` in `app/browser.py`)
This is the "Browser Manager" diamond from your diagram. **The AI drives; this code owns the browser.**
| Job | How |
|---|---|
| Start Chrome | Once, when the worker starts, so the live view works right away. Persistent profile = your logins. |
| Chrome crashed or you closed it | Noticed automatically; reopened on the next task |
| One task at a time | The `browser` worker runs **max 1** activity; other browser tasks wait in Temporal's queue |
| The agent's own tab | Each task opens a new tab and closes it at the end. Your tabs are never touched. |
| Takeover | If the task needs you (login/CAPTCHA), its tab **stays open**, and the next task continues **on that same tab** |
| Alive / stop | Heartbeat every step; "stop" cancels and closes the tab |

## The worker (`python -m app.worker browser`)
- Listens on the `browser` queue and runs `run_tool` (browser tasks) and `run_approved` (approved "act" tasks).
- **No Chrome remote-control port exists:** the worker launches Chrome itself inside the same container, so there's nothing to expose.

## Tests
- **Logins persist:** data saved in Chrome is still there after a full "container restart" (two separate managers on the same profile folder).
- Smoke test in the real container (T-24).
- Takeover tab reuse (T-28 tests).

## Next
**T-27:** how the agent sees and acts on pages.
