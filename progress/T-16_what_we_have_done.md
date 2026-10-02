# T-16: Searching old conversations — what we have done

**Status:** done ✅

## In one sentence
"Who was that handyman last month?" now works: the AI can **search** all past messages and remembered facts by keywords.

## How it works
- `search_history(query, limit ≤ 10)` uses Postgres **full-text search**: the search columns we created in T-03.
- Words are combined with **OR**, so a natural question like "who was the handyman" still finds "the handyman Ramesh…". Results are ranked by relevance, and **facts rank above messages**.
- Results come back dated: `[2026-09-02 14:10] User: the handyman Ramesh …`.
- We use the `simple` search setting (no English word-stemming), because messages can mix English and Hinglish.

## Why not "AI vector search" yet?
Keyword search is free, instant, and needs no extra service. If it misses real questions, we add vector search later (backlog B4; Supabase has pgvector built in).

## Tests (1 test, 4 checks)
Finds a 30-day-old message **and** the matching fact (fact first) · a natural-language question still finds it · no match → empty result with a hint to try other words.

## Next
**T-17:** approval buttons (Send / Cancel).
