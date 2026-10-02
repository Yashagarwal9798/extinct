# T-22: Sending email — what we have done

**Status:** done ✅ (tested with a fake Gmail) · live check pending connection

## In one sentence
"Reply to John saying I'll be late" → you see **exactly** what will be sent with **[Send] [Cancel]**, and nothing goes out until you tap Send.

## How it works
- `send_email(to[1-5], subject, body, reply_to_message_id?)` is tier **WO** (writes to other people), so it **always** needs your tap (T-17).
- The approval text is built **by code** from the exact inputs:
  ```
  Send email to john@acme.com
  Subject: Re: Standup
  ---
  Hi John, running about 15 minutes late.
  ```
- **Replies stay in the same thread:** we copy the original's `Message-ID` into `In-Reply-To`/`References`, use its thread ID, and add `Re:` to the subject.
- **Limit:** 10 emails per 24 h.
- The tool is hidden if you didn't grant the "send" permission.

## Tests
Reply goes into the right thread with correct headers · send needs approval and the summary shows the full email · hidden without the send scope · the 11th email in a day is refused · plus T-23's test: a fooled AI can't send.

## Next
**T-23:** prompt-injection tests.
