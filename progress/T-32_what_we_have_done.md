# T-32: One-time scheduled tasks — what we have done

**Status:** done ✅ (tested on the real Temporal server + a time-skipping test server)

## In one sentence
"Remind me at 10pm to call mom" or "at 6pm check Hacker News for me" now fire reliably, **stored in Temporal itself**, with no tasks table.

## The tool: `schedule_task(kind, text, fire_at | cron)`
| kind | What happens at the time | AI requests |
|---|---|---|
| `remind` | **Code** sends "⏰ call mom" | **0** |
| `do` | The agent runs the instruction in a normal turn ("check HN and send me the top 5") | Like a normal message |

One-time (`fire_at`, e.g. `2026-10-02T22:00:00+05:30`):
- Must include a timezone offset, and be between 30 s and 1 year away.
- Starts a `ScheduledTaskWorkflow` with ID `task-xxxxxxxx`. It **sleeps on a Temporal timer**, which lives in Temporal's database (the `temporal-data` volume), so **restarts of anything don't lose it**. If the PC was off, it fires late but is never lost.
- The text, kind and time are stored in the workflow's **memo**, so they can be listed later without our own table.
- A `do` task arriving while you're away still needs your tap for anything risky.

## Tests
| Test | Proves |
|---|---|
| Create → it's a real Temporal workflow with the memo | ✅ |
| **Fires after 3 s; a cancelled one never fires** | ✅ |
| **3 days later** (time-skipping test server) | ✅ fires exactly once |
| `remind` sends "⏰ text" **without calling the AI** | ✅ |
| `do` signals the conversation with a `task_due` event | ✅ |
| 6 bad inputs (none or both times, not ISO, no offset, in the past, bad cron) | ✅ clear errors to the AI |

## Next
**T-33:** repeating tasks.
