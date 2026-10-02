# T-12: Calling the AI (free models) — what we have done

**Status:** code done ✅ · tested with a fake AI server ✅ · **choosing real free models pending your OpenRouter key**

## In one sentence
We wrote the code that **asks the AI model** what to do. It keeps to the free daily limit, records every request, and starts and advances each "turn" of thinking.

## What was built
| File | In simple terms |
|---|---|
| `app/llm.py` | Sends one request to any OpenAI-compatible AI service (default: OpenRouter free models). |
| `scripts/llm_probe.py` | A checker you run on a model **before** choosing it (uses about 4 of your 50 daily requests). |
| `app/activities.py` | `start_turn` and `model_step` (plus the tool, reply and button steps used in T-13, T-14 and T-17). |

### `llm.chat()`: one AI request
1. **Budget first:** if today's requests (counted in `llm_calls`, resetting at UTC midnight like OpenRouter) have reached `LLM_DAILY_REQUESTS` (45), it doesn't call at all.
2. Sends the conversation plus the tool menu; extra settings from `LLM_EXTRA_JSON` are merged in.
3. **Logs every request** (model, tokens, cost) in `llm_calls`.
4. **Sorts errors into 3 kinds:**
   - *try again* (per-minute rate limit, server down, timeout, empty answer) → Temporal retries
   - *quota used up* (daily cap) → a friendly message, no retries
   - *won't work* (bad request, wrong key) → no retries
5. **Tidies tool calls:** some free models forget call IDs or send arguments in the wrong shape; these are fixed so the rest of the code can rely on them.
6. Keeps `reasoning_details` exactly as received. Claude models via OpenRouter need it sent back unchanged.

### `start_turn`: begin a turn
Shows "typing…", **freezes the tool menu** for this turn, builds the context message (T-11), and saves the turn. If all the messages were already used by a browser task (e.g. you replied with a 2FA code), no turn starts.

### `model_step`: one round of thinking
1. Adds the results of the tools the AI asked for last round. A tool that never ran (stopped) is reported as "not executed" rather than silently missing.
2. Adds any messages you sent **during** the turn.
3. Calls the AI and **appends** its answer exactly as returned. Earlier messages are never edited.
4. Returns either "run these tools" or "send this reply".
- **Retry-safe:** each step has a number. If Temporal retries a step that was already saved, it returns the saved answer **without asking the AI again**, so no request is wasted.
- **Quota message once:** when the free quota runs out, you get one message, then silence until it resets.

## Tests (18 new, all passing)
Tool-call tidying and logging · extra settings merged · **7 error cases** (per-minute vs daily 429, 503, 400, 401, error hidden in a 200, empty answer) · our own budget stops *before* calling · turn start freezes the menu and links messages · consumed messages don't start a turn · **the full tool round-trip keeps `reasoning_details` unchanged** · missing tool results reported · mid-turn messages appended · **a retried step doesn't call the AI twice** · quota message only once · permanent errors aren't retried.

## Credentials needed: choose your free models
1. openrouter.ai → sign up → **Keys** → create a key → `.env`: `LLM_API_KEY=...`
2. openrouter.ai/models → filter **Prices: Free** and **Supported parameters: tools**. Pick 2–3 candidates. Also check each model's provider **data policy** (some free providers log prompts).
3. Test each: `python -m uv run --env-file .env python -m scripts.llm_probe "<model id>"` (add `--image` for browser candidates).
4. Put the best in `.env`: `MODEL_MAIN=...` (and `MODEL_BROWSER=...` if different).

## Next
**T-13:** the full agent loop in the workflow (tools in parallel, mid-turn messages, "stop").
