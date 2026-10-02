# T-11: Context builder — what we have done

**Status:** done ✅

## In one sentence
We wrote the code that prepares **what the AI sees each turn**: one message that always has the same sections in the same order.

## What the AI receives (example)
```
<now>Fri 02 Oct 2026, 19:31 (Asia/Kolkata, UTC+05:30)</now>
<connections>
Gmail: connected (read)
Browser: available. The user logs into sites in the live view (...)
</connections>
<facts>
[f3] (preference) vegetarian
</facts>
<recent_messages>
[Thu 18:02] User: hey
[Thu 18:02] You: hi!
</recent_messages>
<events>
- Gmail was just connected.
</events>
<new_messages>
[19:31] User: any mail?
</new_messages>
```
- **now:** your local time and timezone, so "tomorrow at 8" works.
- **connections:** what's connected, so the AI offers a fix instead of failing.
- **facts:** what it remembers about you (newest first). Each has an ID like `[f3]` so it can forget one.
- **recent_messages:** the last 20 messages for context. Button data and messages a browser task used as input (e.g. a 2FA code) are left out.
- **events:** things that happened without a message: a scheduled task is due, you finished a browser takeover, Gmail got connected.
- **new_messages:** what you just sent (the whole burst).

## Size limits (free models have small memories)
Facts are capped at about 1k tokens and the whole message at about 6k tokens. Over the limit, the **oldest** recent messages are dropped first. Very long messages are shortened.

## Safety
- `untrusted(source, text)` wraps email/web text in `<untrusted>` tags. If the text itself contains `</untrusted>` (a trick to "escape" the box), it's neutralised.
- **G2:** this module never touches the secrets store. A test reads its import statements to make sure.

## Built as two parts
`gather()` reads the database; `render()` only formats. This keeps the formatting exactly testable.

## Tests (6, all passing)
Exact snapshot of a full context · empty sections and the Gmail "needs reconnecting" state · size caps drop the oldest first · `</untrusted>` can't close the box early · no secrets import · **real database test**: new vs recent messages, button and consumed rows excluded, facts, and the takeover / scheduled-task events rendered.

## Next
**T-12:** calling the AI model (OpenRouter free models), plus starting and running a turn.
