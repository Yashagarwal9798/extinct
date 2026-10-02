# T-08: Workflow hardening — what we have done

**Status:** done ✅

## In one sentence
The conversation workflow can run for **months**, you can **ask it what it's doing**, and there's a clear rule for **updating its code** safely.

## What's in place
1. **Status query:** `status()` answers `{"state": "idle" | "debouncing" | "in_turn", "inbox": n, "buttons": n, "turns": n}` without disturbing anything. Command in the README.
2. **Continue-as-new:** Temporal records every step in a history, and a history that grows forever gets slow. After 100 turns (or when Temporal suggests it) and only when idle, the workflow **restarts itself fresh**, carrying over its inbox, pending buttons and the "already seen" list. This was built and tested in T-07, including the bug fix that keeps no message lost during the switch.
3. **Upgrade policy (README):** Temporal replays a workflow's history with the current code, so changing the order of steps can confuse a running workflow. While developing, terminate the `conversation` workflow after such a change. The next message recreates it, and nothing is lost because messages live in our database. Later we'll use `workflow.patched()`.

## Tests
Covered by T-07's tests: the status query after a turn, and continue-as-new keeping the dedupe memory.

## Next
**T-09:** the AI's system prompt.
