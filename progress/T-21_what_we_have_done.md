# T-21: Reading Gmail — what we have done

**Status:** done ✅ (tested with a fake Gmail) · live check pending connection

## In one sentence
The AI can **search** your inbox and **read** emails, and it always treats email text as **untrusted data**.

## Tools
| Tool | What it does |
|---|---|
| `search_email(query, max ≤ 10)` | Uses Gmail's own search syntax: `is:unread newer_than:2d`, `from:amazon`, `subject:invoice`… Returns sender, subject, date, snippet, unread flag. |
| `read_email(message_id)` | The full text of one email. Plain text preferred; HTML-only emails are converted to clean text (scripts and styles removed). Max 16,000 characters. |

- **No copy of your mailbox:** every question asks Gmail live. (Instinct kept a copy and got in trouble when users disconnected.)
- **Untrusted wrapping:** results go to the AI inside `<untrusted source="gmail">…</untrusted>`. An email trying to "close the box" with its own `</untrusted>` is neutralised.
- **Status block:** the AI sees `Gmail: connected (read, send)` / `needs reconnecting` / `not connected` (built in T-11).
- Google errors: 5xx/429 → retried by Temporal; 401/403 → marked `needs_reauth`; others → a clear message to the AI.

## Tests
Plain text preferred over HTML · HTML stripped (scripts gone, line breaks kept) · search wraps results as untrusted, the fake `</untrusted>` in a subject is neutralised, and Gmail is called with the right query · read works · Gmail tools hidden when the permission is missing.

## Next
**T-22:** sending email (with approval).
