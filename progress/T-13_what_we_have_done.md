# T-13: The agent loop — what we have done

**Status:** done ✅ (tested on the real Temporal server)

## In one sentence
The workflow now runs the **full "think → use tools → think again → answer" loop**: tools run in parallel, messages you send mid-task are included, and "stop" really stops.

## The loop (in `app/workflows.py`, the "manager")
```
start_turn → model_step(1) ─┬─ reply? → send_reply
                            └─ tools? → run each tool as its OWN activity, in parallel
                                       → add any messages you sent meanwhile
                                       → model_step(2) → … (max 15 steps)
```
- **Each tool is its own activity:** if one fails, only that one is retried; nothing else is redone.
- **Parallel:** "check my mail and remind me at 9" runs both tools at the same time.
- **Mid-turn messages:** if you add "also check X" while it's working, it's added before the next think step.
- **"stop"** (exactly that word, any case): cancels the running tools right away and replies "Stopped."
- **Browser tools:** after 30 s you get "Still working on it…" once.
- **Step limit:** after 15 think steps it stops and asks you to split the request.
- **Buttons:** taps are handled **by code, never by the AI**. An approval runs the approved action; a takeover "Done" starts a new turn so the AI continues the browser task.

## An important safety net (found while reviewing)
In Temporal, if an activity fails for good and the workflow doesn't handle it, **the whole conversation workflow dies**. Every turn and every button tap is now wrapped: a failure becomes "Sorry, something went wrong on my side" and the workflow keeps going. A test proves it survives and answers the next message.

## Also added: the memory tools
`remember_fact`, `forget_fact` and `search_history` (T-15/T-16, documented there), because the end-to-end test uses them.

## Tests (all passing; about 75 s because they use real timers)
| Test | Proves |
|---|---|
| Burst + duplicate | One turn for `[1, 2, 3]` |
| **Parallel tools** | Two 1.5 s tools overlap in time |
| Step limit | 14 tool rounds then a "too many steps" reply |
| **Stop** | A 60 s tool is cancelled; "Stopped." arrives in under 8 s |
| Browser progress | "Still working on it…" after 30 s |
| **Failure** | The model breaks → polite message → the workflow still answers the next message |
| Buttons | Approval runs the action with no AI turn; takeover Done → a new turn |
| Continue-as-new | Still deduplicates after refreshing |
| **End-to-end** | Real activities + fake AI: "I love chai" → AI calls `remember_fact` → fact saved → reply "Noted ☕"; turn = done, 2 steps |

## Next
**T-14:** sending the reply safely (formatting + leak check).
