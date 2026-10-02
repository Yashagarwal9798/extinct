# T-17: Approval buttons — what we have done

**Status:** done ✅

## In one sentence
Anything that affects other people, posts publicly, or can't be undone **waits for you to tap a button**, and only a real tap can make it happen.

## The flow
1. The AI calls a risky tool (tier **WO**/**D**, e.g. sending an email).
2. The guard says "needs approval". **Code** writes the summary from the exact inputs (e.g. "Send email to john@x.com / Subject… / body"), saves an `approvals` row (valid 30 min), and sends it with **[Send] [Cancel]** buttons.
3. The AI only hears "approval requested, not executed yet", so it tells you to tap. The chat stays usable meanwhile; nothing is blocked.
4. You tap → the bot saves the tap → the workflow hands it to **code** (`claim_approval`), never to the AI.
5. **Claim:** one database statement switches `pending → executing` only if it's still pending **and** not expired. A double tap can't run it twice.
6. **Run:** the guard checks **again** (is it still allowed and connected?), then the action runs, the audit log records it, and the button message is edited to "✓ Sent" / "✓ Done" (or "✗ Failed: reason").
7. **Cancel** → "✗ Cancelled". **Late tap** → "That request expired or was already handled, ask me again."

**Typing "yes" never approves anything.** Typed text goes to the AI, and the AI cannot press buttons. This is our main defence against an email or web page tricking the agent (Instinct's incident).

The **takeover "Done" button** (browser, T-30) uses the same table: its tap becomes an event that starts a new turn.

## Tests (8, all passing)
| Test | Proves |
|---|---|
| Risky tool asks instead of running | Nothing executed; code-written text; correct buttons; AI told "approval_requested" |
| **Tap yes → runs once** | Even if the run step is retried; message edited to "✓ Done"; audit = needs_approval → executed |
| **Double tap** | Second tap does nothing |
| Expired | Late tap doesn't run |
| Cancel | Marked rejected, nothing runs |
| **Re-check at execution** | Tool became unavailable after the tap → not run, marked failed |
| Takeover Done | Becomes a `takeover_done` event, once |
| Garbage button data | Ignored safely (review fix: IDs are validated first) |

## Next
**T-18:** audit log and limits.
