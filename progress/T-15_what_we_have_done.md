# T-15: Remembering facts — what we have done

**Status:** done ✅

## In one sentence
The AI can **save** things you tell it about yourself ("I'm vegetarian", "Priya is my sister") and **forget** them, and it sees them in every future conversation.

## The tools (`app/agent/tools.py`)
- `remember_fact(kind, content)`: kind is preference / person / place / other, max 300 characters. **No duplicates:** "I am vegetarian" and "i am  VEGETARIAN" count as the same fact; saving it again just refreshes it. Each fact remembers which message it came from.
- `forget_fact("f12")`: deletes by the ID shown in the `<facts>` section.
- Facts appear in every turn's context, newest first (T-11).
- The prompt tells the AI to save **durable** facts only, not small talk.

## Tests (2, plus the end-to-end test)
Duplicate detection ignores case and spaces · forget works, and an unknown ID gives the AI a clear error · **end-to-end:** "I love chai" → the AI calls `remember_fact` → the fact is in the database.

## Next
**T-16:** searching old conversations.
