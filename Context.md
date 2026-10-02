# Context: the story of this project so far

A running record of our conversation: what we discussed, what we decided, and why. Read it top to bottom to study the project. It's updated after every task.

**Related files**
- [understand_what_instinct.md](understand_what_instinct.md): what Instinct is
- [PRD.md](PRD.md): what we're building (the product spec)
- [tasks.md](tasks.md): the step-by-step build plan
- [progress/](progress/): one "what we have done" file per finished task
- Your original *Reverse-Engineered Architecture* notes and Excalidraw diagram: the starting point for the architecture

---

## Part 1: What is Instinct? (2026-10-02)

You asked me to understand Instinct before anything else. I researched it and wrote `understand_what_instinct.md`.

**Instinct** is a personal AI agent from Spear Street Technology (founder Noah Shinn, ex-Sierra). You text it on iMessage/WhatsApp or call it, and it **does errands for you**: booking, ordering, filling forms, checking you into flights, following up on things you forgot. It runs on its own cloud computer with a browser, uses your connected accounts, and **messages you first**. It went viral in August 2026 (~$2.5B valuation), is invite-only, and is free during beta.

What makes it special:
1. **No new interface.** The chat thread *is* the product.
2. **It acts**, through APIs where they exist and a cloud browser where they don't.
3. **Persistent**: one long thread, memory, tasks that run for days.
4. **Proactive**: it messages you first.
5. **Secrets never go through chat**: passwords go to a secure web page (the "vault"), and Google access goes through OAuth.

Its public mistakes became our design rules:
- It followed instructions hidden in an email (prompt injection) → we treat email/web text as **untrusted data** and require a **button tap** for risky actions.
- It acted without asking (changed a seat, sent emails) → **approval tiers**.
- It kept an inbox copy after disconnect → we **don't copy your mailbox**.
- It made up financial data → the agent may only state facts a tool returned.

---

## Part 2: Your architecture notes

You shared your reverse-engineered notes and diagram. The key ideas we kept:

- **Webhook/ingest is fast and dumb**: save the message, hand it off, answer immediately.
- **Temporal** (durable execution) is the backbone. Analogy from your notes: Temporal is a **notebook**, the **workflow code is the manager** (decides and waits, never does real work), **activities are the employees** (do the real work, can be retried), and **task queues are the desks**.
- **One workflow per user** keeps messages in order. **Signals** deliver new messages into it. **Timers** do reminders. **Debounce** (wait 2 s) merges bursty messages.
- **Agent turn** = Context → Tool filter → Model call → Tool router. The model only *decides*; code *acts*. Each tool runs as its own activity, so one failure doesn't redo everything.
- **Guardrails G1–G6**: ingress checks, untrusted tagging before the model, re-check at execution + approvals, browser sandbox, outbound scan, data protection.
- **Browser**: the AI drives, a browser manager owns the browser, and the profile (cookies) persists.

---

## Part 3: First plan (v1), then a big change

I first wrote a PRD and tasks for a **WhatsApp**, multi-user, server-hosted version (v1). Then I checked an outside fact: **since 15 Jan 2026, Meta's WhatsApp Business API bans general-purpose AI assistants**. That made WhatsApp risky.

Also from research: the newest Claude models tie their internal reasoning to the exact conversation. So the design is **"fresh request per user message, append-only within a turn"** (never edit history mid-turn).

---

## Part 4: Your decisions → v2

| You said | What we decided |
|---|---|
| "I'll use an OpenRouter key" | The model is called through OpenRouter's OpenAI-compatible API |
| "Can we use Telegram?" | **Telegram**, with **long polling**: our bot asks Telegram for new messages, so no public URL is needed. No Meta ban, no 24-hour window. |
| "How are credentials kept safe?" | **Envelope encryption**: each secret gets its own random key, which is locked by a master key that exists only in your `.env`. The database only ever holds scrambled bytes. The AI never sees secrets. |
| "I want a proper virtual browser for every site" | **A real Chrome in a Docker container on your PC**, with a **live view** (noVNC) so you can watch and take over. **Any site.** |
| "MVP only Gmail" | Gmail through Google's API (search, read, send with approval) |
| "Self-host, no AWS" | Everything runs in **Docker Compose on your Windows PC**. Phone access to the live view goes through **Tailscale** (a private network). |
| "Are you using Temporal and task queues?" | Yes: Temporal with queues **`agent`** and **`browser`**. No separate message queue (save first, then signal, with a sweeper as backup). |
| "Supabase? Where do credentials go?" | **Supabase for bulk data**, **credentials local** (encrypted SQLite file). The browser profile also stays local. |
| "Just for me" | **Single user**: your Telegram ID is in config. No signup pages. |
| "The browser is the main feature" | The browser joins the MVP, with **takeover**: on a login/CAPTCHA/2FA wall, the bot sends you the live-view link plus a **Done** button. You log in yourself, and it continues. |

---

## Part 5: Making it free, adding scheduling

**You:** "I don't want to pay for the MVP." → **Free models** (OpenRouter `:free`).
- Limit: **50 requests/day** (20/min) without buying credits.
- So the design **saves requests**: plain chat = 1, Gmail question ≈ 2, button taps = 0 (code handles them), reminders = 0 (code sends them), a browser task ≈ 5–15.
- The browser reads pages **as text first**; screenshots only on demand; up to 3 actions per request; a 25-step cap.
- Daily budget: 45 requests, with a friendly message when it runs out.
- Trade-off: free models are weaker (especially at browsing), and free providers may log prompts.
- The code works with **any OpenAI-compatible endpoint**, so switching (to Gemini's free tier, local Ollama, or paid) is config only.

**You:** "Temporal has its own database, so add reminders and scheduled tasks to the MVP." → Correct.
- One tool, `schedule_task`. Kind **`remind`**: code sends "⏰ …" (0 requests). Kind **`do`**: the agent performs an instruction at that time.
- One-time tasks are **durable timers**; recurring ones are **Temporal Schedules**. **No tasks table**, because Temporal's database is the store.

---

## Part 6: Confirming the diagram

You asked whether everything else still matches your diagram. **Yes.** Workflow code and activities are separate, there are task queues, and G1–G6 are kept. Differences are only what we chose in chat. The full box-by-box mapping is in **PRD §8.10**.

Notable behavior difference: approvals are **non-blocking**. The turn ends, and your later button tap runs the action. The model can't fake a tap.

**Browser logins:** you log in once in the live view, and Chrome's **whole profile** (cookies + local storage) is saved on a Docker volume, so later tasks are already logged in. Browser management is described in **PRD §8.9**.

---

## Part 7: How we build (working agreement)

- **One task at a time**, then stop and wait for your "go".
- After each task: a **`progress/T-XX_what_we_have_done.md`** in simple words, **unit tests** where they matter, this **Context.md** updated, and a clear list of **credentials needed**, if any.

---

## Build log

| Task | Date | Result | Notes |
|---|---|---|---|
| T-01 Project skeleton | 2026-10-02 | ✅ 12 tests pass | Installed uv; settings load via `get_settings()` (not at import), so tests don't need a `.env`. [details](progress/T-01_what_we_have_done.md) |
| T-02 Docker base | 2026-10-02 | ✅ 13 tests pass | Stopped your "hippocrates" containers first (not deleted). Temporal 1.9.1 dev server in Docker with its state on a volume (mounted at `/home/temporal` because the image runs as non-root). Live smoke test + restart-persistence check pass. Docker has 3.7 GB RAM: raise it to about 6 GB before T-24. [details](progress/T-02_what_we_have_done.md) |


### Change of working style (your `/goal`)
You asked me to **code every task continuously** and fill in `.env` at the end. Per task I: understand what came before → build → review → write docs → move on. Checks that need real accounts are tested with stand-ins (a local Postgres instead of Supabase, mocked Telegram/AI, local test web pages) and marked **pending credentials**.

| Task | Date | Result | Notes |
|---|---|---|---|
| T-03 Supabase schema | 2026-10-02 | ✅ 20 tests (live check pending) | 8 tables in schema `app`, RLS on all, migration runner, `db.py` pool. Tested on a throwaway local Postgres. Review fixes: `SET search_path` per connection (poolers may drop startup options); scripts/migrations added to the image. [details](progress/T-03_what_we_have_done.md) |
| T-04 Secrets store | 2026-10-02 | ✅ 9 tests | Envelope encryption (AES-256-GCM) in local SQLite; each secret bound to its name. [details](progress/T-04_what_we_have_done.md) |
| T-05 Telegram client | 2026-10-02 | ✅ 18 tests | Send/buttons/photos/reactions/edit over plain HTTP; markdown → Telegram HTML with escaping; dry-run mode. [details](progress/T-05_what_we_have_done.md) |
| T-06 Bot (ingest) | 2026-10-02 | ✅ 7 tests | Long polling; owner-only; saved before the offset moves; dedupe by update_id. [details](progress/T-06_what_we_have_done.md) |
| T-07 Into Temporal | 2026-10-02 | ✅ | Signal-with-start + outbox sweeper; 2 s debounce. **Bug found by tests:** state must be restored in `@workflow.init`, not `run()` (the first signal arrives before run). [details](progress/T-07_what_we_have_done.md) |
| T-08 Workflow hardening | 2026-10-02 | ✅ | Status query, continue-as-new, upgrade policy in the README. [details](progress/T-08_what_we_have_done.md) |
| T-09 System prompt | 2026-10-02 | ✅ 4 tests | ~670 tokens, frozen; browser prompt too. [details](progress/T-09_what_we_have_done.md) |
| T-10 Tools + guard | 2026-10-02 | ✅ 16 tests | Registry with tiers; G3 checks at execution; G5 leak patterns (dropped the noisy "any base64" rule). [details](progress/T-10_what_we_have_done.md) |
| T-11 Context | 2026-10-02 | ✅ 6 tests | Fixed-order sections, ~6k-token cap, untrusted wrapper. [details](progress/T-11_what_we_have_done.md) |
| T-12 LLM + model_step | 2026-10-02 | ✅ 18 tests | OpenAI-compatible client, daily request budget, 3 error kinds, retry-safe steps, reasoning_details round-trip. [details](progress/T-12_what_we_have_done.md) |
| T-13 Agent loop | 2026-10-02 | ✅ | Parallel tools, mid-turn messages, "stop", browser progress, failures caught so the workflow never dies. [details](progress/T-13_what_we_have_done.md) |
| T-14 send_reply | 2026-10-02 | ✅ | G5 block + formatting. [details](progress/T-14_what_we_have_done.md) |
| T-15/16 Memory | 2026-10-02 | ✅ | remember/forget facts; keyword search over history and facts. [T-15](progress/T-15_what_we_have_done.md) · [T-16](progress/T-16_what_we_have_done.md) |
| T-17 Approvals | 2026-10-02 | ✅ 8 tests | Code-written summary + buttons; atomic claim; re-check at execution. [details](progress/T-17_what_we_have_done.md) |
| T-18 Audit + limits | 2026-10-02 | ✅ 4 tests | Append-only by code (the owner role can't be restricted by grants). [details](progress/T-18_what_we_have_done.md) |
| T-19–T-23 Gmail | 2026-10-02 | ✅ 14 tests | Connect script (Desktop OAuth client, tokens encrypted locally); search/read/send (approval, threading); **a fully fooled model still can't send mail**. [T-19](progress/T-19_what_we_have_done.md) · [T-20](progress/T-20_what_we_have_done.md) · [T-21](progress/T-21_what_we_have_done.md) · [T-22](progress/T-22_what_we_have_done.md) · [T-23](progress/T-23_what_we_have_done.md) |

**M1 (chat + Gmail): code complete. 140 tests pass.** Live checks wait for credentials.

| Task | Date | Result | Notes |
|---|---|---|---|
| T-24 Browser container | 2026-10-02 | ✅ smoke-tested | Real Chrome + Xvfb + noVNC; `navigator.webdriver` false; logins persist; VNC never published. [details](progress/T-24_what_we_have_done.md) |
| T-25 Tailscale | 2026-10-02 | 📋 your steps | Private phone access to the live view. [details](progress/T-25_what_we_have_done.md) |
| T-26 Browser worker | 2026-10-02 | ✅ | Manager owns Chrome; one task at a time; takeover tab reused. [details](progress/T-26_what_we_have_done.md) |
| T-27 Observe/act | 2026-10-02 | ✅ 5 tests | Numbered elements, hidden text invisible, password fields refused. [details](progress/T-27_what_we_have_done.md) |
| T-28 Sub-agent | 2026-10-02 | ✅ 7 tests | Up to 3 actions per request, 25-step cap, nudge then fail. [details](progress/T-28_what_we_have_done.md) |
| T-29/T-30 browser_task + takeover | 2026-10-02 | ✅ 7 tests | read vs act (approval); live-view link + Done; continues on the same tab. [T-29](progress/T-29_what_we_have_done.md) · [T-30](progress/T-30_what_we_have_done.md) |
| T-31 Real sites | 2026-10-02 | 📋 ready | `scripts.browser_try` to compare free models. [details](progress/T-31_what_we_have_done.md) |
| T-32–T-34 Scheduling | 2026-10-02 | ✅ 12 tests | Stored in Temporal (timers + Schedules, memo); remind = 0 AI requests; 3-day test via time skipping. [T-32](progress/T-32_what_we_have_done.md) · [T-33](progress/T-33_what_we_have_done.md) · [T-34](progress/T-34_what_we_have_done.md) |
| T-35 Logs + usage | 2026-10-02 | ✅ 3 tests | JSON logs with turn_id; bot token kept out of logs; usage report. [details](progress/T-35_what_we_have_done.md) |
| T-36 Backup + wipe | 2026-10-02 | ✅ tested | `scripts/backup.sh` (DB + secrets + Temporal), `scripts.wipe` (type WIPE). [details](progress/T-36_what_we_have_done.md) |
| T-37 Eval | 2026-10-02 | 📋 ready | 15 scenarios, budget-aware chunks. [details](progress/T-37_what_we_have_done.md) |
| T-38 Always-on | 2026-10-02 | ✅ / 📋 | Restart policies; whole stack booted in Docker (dummy keys): every service starts and the workflow survives failures. Chaos checklist ready. [details](progress/T-38_what_we_have_done.md) |

## Where we are now (2026-10-02)

**All 38 tasks are coded. 177 automated tests pass.** The full Docker stack boots.

What's left is **only things that need your accounts**. Follow the **Go live** checklist in [README.md](README.md):
1. `.env`: master key, Telegram token + your ID, Supabase URL, OpenRouter key + free models, VNC password, Google client.
2. `scripts.migrate` → `scripts.llm_probe` (pick models) → `docker compose up -d` → text the bot.
3. `app.connect_google` once → log into sites in the live view.
4. Optional checks: `injection_check`, `browser_try`, `eval_scenarios`.

### Things worth studying in the code
- `app/workflows.py`: the "manager". How a turn, parallel tools, "stop" and buttons work in Temporal.
- `app/activities.py`: the "employees". Notice how each one is safe to run twice.
- `app/agent/guard.py`: why safety lives in code, not in the AI (see `tests/test_injection_guard.py`).
- `app/browser.py`: how a web page becomes text an AI can act on.
