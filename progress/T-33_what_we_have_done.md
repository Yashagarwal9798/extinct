# T-33: Repeating tasks — what we have done

**Status:** done ✅

## In one sentence
"Every Monday at 9am remind me to plan the week" or "every day at 8am summarize my unread email" become **Temporal Schedules** that run in your timezone.

## How it works
- `schedule_task(..., cron="0 9 * * MON")` (5 fields: minute hour day month weekday) creates a Temporal **Schedule** with ID `task-xxxxxxxx`, in `OWNER_TIMEZONE`. Each time it's due, it starts a small `TaskFireWorkflow` → the same `fire_task` as one-time tasks.
- **Minimum interval** (checked using Temporal's own list of upcoming run times): `remind` every 1 min at most; `do` every 60 min at most (`RECURRING_DO_MIN_MINUTES`), because each `do` run uses AI requests from your 45/day.
- **Overlap:** skip if the previous run is still going.
- **Catch-up:** if the PC was off, a missed run still fires if it's less than 1 hour late; older misses are skipped, so you don't get a burst of 10 old reminders.
- You see the first run time in the reply: "Scheduled [task-…] repeating '0 9 * * MON' (Asia/Kolkata), first at Mon 05 Oct 09:00".

## Tests
Repeating schedule created in your timezone with the right first run · `do` every 5 minutes refused · cancel deletes the schedule.

## Next
**T-34:** listing and cancelling.
