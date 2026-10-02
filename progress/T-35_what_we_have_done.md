# T-35: Logs and usage report — what we have done

**Status:** done ✅

## In one sentence
You can see **what happened** (one log line per event, tagged with the turn) and **how much of your free AI quota** you've used.

## Logs (`app/logs.py`)
- Every log line is **JSON**: time, level, message, and inside Temporal activities also `workflow_id`, `activity`, `attempt` and **`turn_id`**. Follow one conversation turn from start to finish:
  ```sh
  docker compose logs worker-agent | grep <turn_id>
  ```
- **Security fix found in review:** the HTTP library logs every request URL at INFO level, and Telegram URLs contain your **bot token**. Those logs are switched off (warnings only). A test keeps it that way.
- Warnings worth grepping for: "blocked" (G5), "budget", "failed", "needs_reauth".

## Usage report (`scripts/usage.py`)
```sh
docker compose run --rm worker-agent python -m scripts.usage            # today
docker compose run --rm worker-agent python -m scripts.usage --days 7
```
It shows requests, errors, tokens and cost per kind (main / browser / probe) and model, **how many requests are left today**, and how many turns failed. The day resets at UTC midnight, like OpenRouter.

Plus the **Temporal UI** at http://localhost:8233 shows every workflow, step and retry.

## Tests (3)
A JSON line includes the turn ID · HTTP request logging is silenced · the usage report counts correctly (3 used, 42 left).

## Next
**T-36:** backups and wipe.
