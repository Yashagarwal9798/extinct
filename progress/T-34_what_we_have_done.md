# T-34: Listing and cancelling tasks — what we have done

**Status:** done ✅

## In one sentence
"What's scheduled?" and "cancel the mom one" work, reading **straight from Temporal**.

## Tools
- `list_tasks()`:
  - running `ScheduledTaskWorkflow`s (one-time), read from their memo
  - Temporal Schedules starting with `task-` (repeating)
  - pending approval buttons (from Supabase)

  For example:
  ```
  [task-1a2b3c4d] remind · Fri 02 Oct 22:00 · 'call mom'
  [task-9f8e7d6c] do · repeating '0 8 * * *' · 'summarize unread email'
  waiting for your tap: Send email to john@acme.com
  ```
- `cancel_task("task-1a2b3c4d")`: cancels the one-time workflow, or deletes the schedule. An unknown ID → "already gone".
- A cancelled one-time task wakes up, sees the cancellation, and ends **without firing** (tested).

## Note
Temporal's list is updated a split second after changes, so a task created this very instant may take a moment to appear.

## Tests
Create → appears in the list → cancel → status CANCELED, and the fake fire activity was never called · unknown ID → "already gone".

## 🏁 Milestone M3 = MVP code complete
Chat · memory · approvals · Gmail · virtual browser with takeover · reminders and scheduled tasks.
