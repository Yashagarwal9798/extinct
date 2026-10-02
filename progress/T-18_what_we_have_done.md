# T-18: Audit log, limits, budget — what we have done

**Status:** done ✅

## In one sentence
Every tool decision is written to a **diary** (`audit_log`), and there are **limits** everywhere, so a confused or tricked AI can't run wild or burn your free quota.

## The audit diary
Recorded decisions: `executed`, `failed`, `denied` (with the reason), `needs_approval`, `rejected` (you tapped Cancel), and `blocked` (the outbound leak check). Each row has the tool, risk tier, turn and details. Question it answers: *"why did the agent do that?"*

**Append-only, honestly stated:** on Supabase our server connects as the **owner** of the tables, and database permissions can't stop an owner from editing its own table. So "append-only" is enforced **by the code**: nothing anywhere updates or deletes audit rows, and a test scans the whole codebase to keep it that way. (The plan's `002_audit.sql` permission change was dropped for this reason; see tasks.md.)

## All the limits in one place
| Limit | Where | Value |
|---|---|---|
| Incoming messages | bot (T-06) | 60 / hour |
| Emails sent | guard | 10 / 24 h |
| Browser "act" tasks | guard | 20 / 24 h |
| Browser "read" tasks | guard | 60 / 24 h |
| AI think-steps per turn | workflow (T-13) | 15 |
| AI requests per day | `llm.chat` (T-12) | `LLM_DAILY_REQUESTS` (45) |
| Approval validity | approvals | 30 min |

## Retry safety (no duplicate actions)
- A tool call that's retried after finishing returns immediately: one result row, one audit row.
- An approved action can only be claimed once (T-17).
- A retried think-step doesn't call the AI again (T-12).

## Tests (4)
3 tool calls → exactly 3 "executed" rows · a retried call isn't audited twice · a denied call is audited with its reason · no code updates or deletes audit rows.

## Next
**T-19:** Google Cloud setup (manual steps for you) → **T-20:** connecting Gmail.
