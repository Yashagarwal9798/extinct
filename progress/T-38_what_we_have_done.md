# T-38: Always-on and chaos checks — what we have done

**Status:** set-up ✅ · Temporal restart already proven (T-02) · **full chaos run after `.env` is filled**

## In one sentence
The stack restarts itself after crashes and reboots, and nothing is lost or done twice when any piece dies mid-task.

## What's in place
- Every service has `restart: unless-stopped`: crashed containers come back by themselves, and after a reboot they start with Docker.
- **Why nothing is lost** (built in earlier tasks):
  - Messages are saved **before** Telegram is told we have them (T-06).
  - The outbox sweeper re-sends anything Temporal missed (T-07).
  - Workflows, timers and scheduled tasks live in Temporal's database (T-02, T-32).
- **Why nothing runs twice:** tool results are keyed by call (T-13), approvals are claimed once (T-17), and think-steps are numbered (T-12).

## Windows settings (you do this once)
1. Docker Desktop → Settings → General → **Start Docker Desktop when you sign in** ✅
2. Windows Settings → System → Power → **Screen and sleep → When plugged in, put my device to sleep after: Never**
3. Docker Desktop → Settings → Resources → **Memory ≥ 6 GB** (or `.wslconfig`, see README)
4. Note: after a reboot, Docker starts only **once you sign in** to Windows.

## Chaos checklist (run once everything is configured)
| Do this | Expect |
|---|---|
| Send a message, then immediately `docker compose kill worker-agent`, then `docker compose up -d` | The reply still arrives, once |
| `docker compose kill bot` while you send messages, then start it | All messages handled, none twice |
| Start a browser task, `docker compose kill browser`, then start it | The task retries once or reports failure; Chrome logins still there |
| `docker compose restart temporal` during a 2-minute reminder | The reminder still fires |
| Reboot the PC with a reminder 10 min out, then sign in | The reminder fires (late if the PC was off at fire time) |

Already proven by tests: a killed worker mid-debounce, Temporal down while a message arrives, Temporal restarted with a running workflow, a worker kill mid-tool, and retried steps not repeating.

## 🏁 All 38 tasks coded
See `Context.md` for the summary and the **go-live checklist**.
