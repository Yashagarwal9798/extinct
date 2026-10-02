# PRD: Mini-Instinct, a self-hosted personal agent on Telegram

| | |
|---|---|
| Status | Draft **v2** (replaces v1) |
| Date | 2026-10-02 |
| Owner | Yash (sole user) |
| Inputs | [understand_what_instinct.md](understand_what_instinct.md), *Instinct: Reverse-Engineered Architecture — Complete Study Notes* (**Notes §N**), architecture diagram |
| Companion | [tasks.md](tasks.md) |

---

## 1. Summary

Mini-Instinct is **your own** personal agent. You **text it on Telegram**, and it does things for you in **its own browser**: a real Chromium running in a Docker container on your machine. You can **watch it and take over at any time** through a live view. It also uses **Gmail** through Google's API, runs **reminders and scheduled tasks**, remembers you, and asks before it does anything risky. The MVP is designed to run at **$0** on free models.

Everything runs **self-hosted on your machine** with Docker Compose. Bulk app data goes to **Supabase**. **Credentials never leave your machine.**

**Core loop:** message in → understand intent → act (browser or Gmail) → reply. If the agent gets stuck, it hands the browser to you and continues after you tap **Done**.

---

## 2. Decisions (what changed from v1)

| Topic | v1 | **v2 decision** | Why |
|---|---|---|---|
| Users | Invite-only, multi-user | **Just you.** Your Telegram user ID is in config. | No signup, invites, or linking. Upgrade path: add `user_id` columns later. |
| Channel | WhatsApp Cloud API | **Telegram Bot API, long polling** | No Meta AI-assistant ban, no 24-h window or templates, no public URL needed |
| Hosting | Server/VM | **Self-hosted on your PC with Docker Compose** | No AWS. The browser runs at home, where a residential IP triggers fewer CAPTCHAs. |
| Model | Anthropic API | **Free models on OpenRouter (`:free`) by default**, through any OpenAI-compatible endpoint (`LLM_BASE_URL`) | $0 for the MVP. The same code works with another free tier (e.g. Gemini API), local Ollama, or a paid model later, by changing config only. |
| Reminders and scheduled tasks | M3 (after MVP) | **In the MVP, stored in Temporal** (timers + Schedules). No tasks table. | Temporal already keeps timers and schedules in its own database |
| Browser | Headless, Discord only, vault passwords | **One persistent, visible Chromium in a container. Any site. Live view (noVNC). You log in yourself.** | It's the main feature. Live view removes most of the need to store passwords. |
| Integrations in MVP | Gmail, Calendar, Discord | **Gmail (API) + browser (any site)** | Your MVP scope |
| App data | Postgres (2 DBs) | **Supabase** (`app` schema, not exposed via its REST API) | You want Supabase for the bulk data |
| Credentials | Separate secrets DB | **Local SQLite file on a Docker volume, every value encrypted. Master key in your local `.env`.** | Secrets never reach Supabase or any cloud |
| Web app | FastAPI pages (signup, OAuth, vault, settings) | **None in MVP.** Google is connected once with a local script. Settings live in `.env`. | Single user, so pages aren't needed |
| Durable execution | Temporal | **Temporal (kept)**, dev server in a container with a SQLite file. Task queues `agent` + `browser`. | Crash safety, retries, reminders, approvals |
| Email alerts | Pub/Sub push (needs public URL) | **After the MVP** (Gmail polling). Meanwhile a scheduled task ("every morning summarize my unread email") covers it. | No public URL when self-hosting; saves free requests |

---

## 3. Goals and non-goals

### Goals: MVP (M1 + M2 + M3)
1. Chat with the agent on Telegram. Only you can use it.
2. **Virtual browser:** the agent can do tasks on **any website** in a persistent Chromium (read, navigate, fill in forms, and, with your approval, submit, post, or send).
3. **Live view:** you can watch and control that browser from your PC (and from your phone via Tailscale). Logged-in sessions persist across restarts.
4. **Takeover:** on a login, CAPTCHA, or 2FA wall, the agent asks you to take over, then continues after you tap **Done**.
5. **Gmail:** search, read, summarize, draft, and send/reply (send only after a button tap).
6. Memory: facts about you + recent conversation + searching past messages.
7. Crash safety: no lost messages and no duplicated actions when anything restarts.
8. Guardrails: approvals for risky actions, an audit log, limits, and injected text in email or web pages treated as data, not instructions.
9. **Reminders and scheduled tasks**, one-time and recurring, stored in Temporal.
10. **Runs at $0** on free models, within free-tier limits.

### After the MVP
Important-email alerts and nightly summaries. Until then, a scheduled task such as "every morning at 8, summarize my unread email" covers most of it.

### Non-goals (for now)
Other users · WhatsApp/iMessage · voice calls · payments/purchases · device data capture · Calendar/Docs/Sheets · storing website passwords for automatic re-login (backlog) · CAPTCHA-solving services · cloud deployment.

---

## 4. User

**You.** You live in Telegram and Gmail, want errands done on the web, and are happy to log into sites once in the live view. Everything runs on your Windows PC (Docker Desktop + WSL2).

---

## 5. User stories

| ID | Story | Milestone |
|---|---|---|
| U1 | I text the bot "hey" and get a short, natural reply. Strangers who find the bot get nothing. | M1 |
| U2 | I send "can u" / "check my" / "unread mail" quickly and get **one** coherent answer. | M1 |
| U3 | "remember I'm vegetarian" is used weeks later. | M1 |
| U4 | "what did I say about the handyman?" finds the old conversation. | M1 |
| U5 | "summarize my unread email" / "any mail from Amazon this week?" | M1 |
| U6 | "reply to John saying I'll be 15 min late" → I see the exact draft with **Send / Cancel** buttons, and nothing is sent until I tap Send. | M1 |
| U7 | "stop" cancels whatever is running. | M1 |
| U8 | "open hacker news and tell me the top 5 posts" → it browses and summarizes, optionally with a screenshot. | M2 |
| U9 | I open the live view on my PC or phone and see the agent's browser. I can click and type in it myself. | M2 |
| U10 | "check my Discord DMs" → Discord isn't logged in → the agent sends me the live-view link and a **Done** button → I log in myself → tap Done → it reads my DMs. | M2 |
| U11 | The next day "any new Discord DMs?" works without logging in again. | M2 |
| U12 | "post this on X: …" → **Approve / Cancel** buttons with the exact goal → after approval it posts and sends me a screenshot. | M2 |
| U13 | A web page with hidden "ignore your instructions…" text can't make the agent do anything I didn't ask. | M2 |
| U14 | "remind me to call mom at 10pm", "every Monday 9am plan the week". | M3 |
| U15 | An important email (flight delayed) → the agent texts me first. Never newsletters, never during quiet hours. | Later |
| U16 | "every morning at 8, check Hacker News and send me the top 5" runs on its own. "what's scheduled?" lists it, and "cancel that" stops it. | M3 |

---

## 6. User experience

### 6.1 One-time setup (about 30 min, documented in tasks.md)
1. Create the bot with @BotFather and put the token plus your Telegram user ID in `.env`.
2. Create a Supabase project and put its connection string in `.env`.
3. Generate a master key and put it in `.env`.
4. Add your OpenRouter key to `.env` (no credits needed for `:free` models).
5. `docker compose up -d`.
6. Run `docker compose run … connect_google` once and approve in your PC's browser. The tokens are stored encrypted on your machine.
7. Optional: install Tailscale on the PC and your phone so the live view works from your phone.

### 6.2 Conversation behavior
- **Instant feedback:** a typing indicator at turn start. The model may react with an emoji to messages that will take a while.
- **Telegram style:** short, plain, Telegram HTML formatting (bold, italic, code, links), at most 3 messages per reply.
- **One clarifying question at most.** Otherwise act.
- **Approvals:** inline keyboard buttons under a code-generated description of exactly what will happen.
- **Honesty:** never states email or website facts that no tool returned. Failures are explained in one line.

### 6.3 The browser experience
- **One browser, always on.** It's a real Chromium window inside the `browser` container, with the profile on a Docker volume. It's a separate browser from your Windows Chrome.
- **Live view:** `http://localhost:6080/vnc.html` on your PC, or `https://<pc>.<tailnet>.ts.net/` on your phone. It's password-protected.
- **The agent works in its own tab** and closes it when done (unless it's waiting for you).
- **Takeover:** "Discord needs you to log in. Open the live browser: <link>. Tap Done when finished. [Done]"
- **Screenshots:** the agent can attach a screenshot of the result when that helps ("here's the confirmation page").
- **Don't drive the browser while the agent is working**, except when it asks you to take over.

### 6.4 Examples

```
You:   what are the top 3 posts on hacker news right now
Agent: 1. … (420 pts)  2. … (310 pts)  3. … (250 pts)
```

```
You:   check my discord dms
Agent: You're not logged into Discord in my browser. Log in here, then tap Done:
       https://pc.tailnet.ts.net/vnc.html                       [Done]
You:   (logs in on phone via live view, taps Done)
Agent: 2 new DMs: Priya asked about Saturday; Rahul sent a meme.
```

```
You:   reply to john's email saying i'll be 15 min late
Agent: Send email to john@acme.com
       Subject: Re: Standup
       ---
       Hi John, running about 15 minutes late. See you soon.
       [Send] [Cancel]
You:   (taps Send)
Agent: ✓ Sent
```

---

## 7. Functional requirements

### 7.1 Telegram channel
- **FR-1** Long polling with `getUpdates` (timeout 50 s) in the `bot` process. No webhook and no public URL.
- **FR-2** Only updates whose `from.id == TELEGRAM_OWNER_ID` (and private chat) are processed. Everything else is ignored and logged at debug level.
- **FR-3** Every update is saved to `app.messages` (`UNIQUE tg_update_id`) **before** the polling offset moves past it. Telegram redelivers unconfirmed updates, so a crash loses nothing. The unique constraint drops duplicates.
- **FR-4** Supported inbound types: text and button taps (`callback_query`). Other types get "I can only read text for now".
- **FR-5** Outbound: `sendMessage` (HTML parse mode, ≤ 4,096 chars, ≤ 3 bubbles), `sendChatAction typing`, `setMessageReaction`, inline keyboards, `sendPhoto` (screenshots), `answerCallbackQuery`, `editMessageText` (to update a message after a tap).

### 7.2 Durable conversation (Notes §7–8)
- **FR-6** One Temporal workflow, `conversation`, started or signalled with **signal-with-start**.
- **FR-7** **Debounce:** a 2-second quiet period (10 s maximum) after messages arrive, then one turn for the whole batch, sorted by Telegram `date` + `message_id`.
- **FR-8** **Outbox + sweeper:** messages are saved with `dispatched=false`. The bot process re-signals undispatched rows older than 10 s. The workflow drops duplicate signals (it remembers the last 500 message IDs).
- **FR-9** Messages that arrive mid-turn join the running turn between tool rounds. An exact "stop" cancels the in-flight activities.
- **FR-10** **Continue-as-new** when Temporal suggests it or after 100 turns.
- **FR-11** A `status` query returns idle / debouncing / in_turn.

### 7.3 Agent runtime (Notes §10)
- **FR-12** `model_step` activity = context → tool menu → OpenRouter call → returns either tool calls or a reply. **It never runs tools.**
- **FR-13** Each tool call is its **own activity**. Independent calls run in parallel. Results are stored in `tool_results` (the `(turn_id, tool_call_id)` primary key makes retries idempotent).
- **FR-14** Limits per turn: 15 model steps and 5 minutes (browser tasks have their own limit). There's a daily **request** budget (`LLM_DAILY_REQUESTS`).
- **FR-15** Tool errors go back to the model as error results.
- **FR-16** A status block tells the model: Gmail connected or not, and that the browser is available.

### 7.4 Memory
- **FR-17** `remember_fact` / `forget_fact`. All facts are included in context (capped at about 2k tokens).
- **FR-18** Context includes the last 30 messages verbatim.
- **FR-19** `search_history` runs Postgres full-text search over messages and facts.

### 7.5 Approvals and guardrails (Notes §15)
- **FR-20** Tool tiers: **R** read · **WS** write to self · **WO** write to others / public · **D** destructive. **WO and D need a button tap.**
- **FR-21** The approval message text is **generated by code from the tool input**, not written by the model.
- **FR-22** Approvals are non-blocking (the chat stays usable). They expire after 30 min, checked at tap time. A tap claims the approval atomically, so it runs exactly once.
- **FR-23** **Typed text never approves anything.** Only the inline button does.
- **FR-24** Every guard decision and execution is written to `audit_log`.

### 7.6 Gmail
- **FR-25** Google is connected once with a local OAuth script (loopback redirect). Scopes: `gmail.readonly`, `gmail.send`, `openid`, `email`.
- **FR-26** Tokens are encrypted in the local secrets store and refreshed automatically. `invalid_grant` marks the connection `needs_reauth` and the agent tells you to rerun the script.
- **FR-27** Tools: `search_email(query)`, `read_email(id)`, `send_email(to, subject, body, reply_to_id?)` (**WO**). Email content is wrapped as untrusted.
- **FR-28** No mailbox copy. Gmail is queried live.

### 7.7 Virtual browser (the main feature)
- **FR-29** One `browser` container runs: a virtual display (Xvfb) + a window manager + **Chrome launched by Playwright as a persistent, visible (headful) context** + x11vnc + noVNC. **The same container runs the Temporal worker for the `browser` queue**, so no Chrome remote-debugging port is ever exposed.
- **FR-30** The profile (`/profile`) lives on a named Docker volume, so logins persist across restarts. **The browser stays open between tasks** so you can use it in the live view.
- **FR-31** noVNC is published **only on `127.0.0.1:6080`** and protected by a VNC password. It can be reached from your phone via **Tailscale** (`tailscale serve`). No ports are open to the internet.
- **FR-32** `browser_task(goal, mode, start_url?)` runs on the **`browser` queue**, one at a time (concurrency 1), with heartbeats, a 10-minute limit, and at most 25 steps (up to 3 actions per step). `mode="read"` → tier R. `mode="act"` (submit, post, send, buy, delete) → tier **WO, approved up front**, with the goal shown on the button message.
- **FR-33** **Browser sub-agent:** each step is a fresh model request with the goal, a log of earlier actions, and the current page **as text** (URL, title, text excerpt, numbered list of interactive elements). A screenshot is attached only after the agent calls `look`, and only if the browser model accepts images. This text-first approach saves tokens and works with text-only free models. It returns **up to 3** actions per step: `goto`, `click`, `type`, `press`, `scroll`, `wait`, `back`, `look`, `need_user`, `done`, `fail`.
- **FR-34** **Takeover:** on a login wall, CAPTCHA, 2FA, or anything uncertain → `need_user(reason)` → the task ends with `needs_user`. **Code** sends the live-view link and a **Done** button. A tap signals the workflow, which starts a new turn, and the agent continues the task. The tab stays open on that page.
- **FR-35** `done(summary, screenshot: bool)`: the summary goes back to the main agent wrapped as untrusted. With `screenshot`, the image is also sent to Telegram.
- **FR-36** It uses real Chrome (`channel="chrome"`) without automation flags to reduce bot detection. It **doesn't bypass** CAPTCHAs or anti-bot systems. It hands over to you instead.
- **FR-37** Downloads are disabled. Every action is written to the audit log (URL + action, no typed text if the field is a password field).

### 7.8 Reminders and scheduled tasks (MVP, M3)
- **FR-38** One tool: `schedule_task(kind, text, fire_at? | cron?)`.
  - `kind="remind"`: at fire time, **code** sends "⏰ {text}". No model call, so it's free.
  - `kind="do"`: at fire time, the agent runs `text` as an instruction in a normal turn with tools (for example "check HN and send me the top 5"). WO/D actions still wait for a button tap.
- **FR-39** One-time tasks → a standalone `ScheduledTaskWorkflow` (`task-{id}`, durable timer). Recurring tasks → a **Temporal Schedule** (`task-{id}`, cron in your timezone). **Temporal's own database is the store**: the kind, text, and time live in the workflow or schedule memo. There's no tasks table.
- **FR-40** `list_tasks` reads them back from Temporal (running `ScheduledTaskWorkflow`s + schedules). `cancel_task(id)` cancels the workflow or deletes the schedule.
- **FR-41** Minimum interval: 1 min for recurring `remind` tasks, 60 min for recurring `do` tasks (each run costs model requests against the daily free limit).
- **FR-42** If the PC was off at fire time, one-time tasks fire late, never lost. Recurring tasks catch up within a 1-hour window, and one missed run fires at most once.

---

## 8. Architecture

### 8.1 Overview

```
 ┌──────────────── Your Windows PC (Docker Desktop / WSL2) ─────────────────────────────┐
 │                                                                                       │
 │  bot (Python)            temporal (dev server + UI :8233)                             │
 │  getUpdates loop ──signal-with-start──► history · timers · signals · schedules       │
 │  save → Supabase              │   task queue "agent"       task queue "browser"      │
 │  sweeper                      ▼                              ▼                        │
 │                     worker-agent (Python)          browser (one container)            │
 │                     ConversationWorkflow           Temporal worker "browser" queue    │
 │                     model_step ──► OpenRouter      Playwright → Chrome (headful,      │
 │                     Gmail tools ──► Google API        persistent profile)             │
 │                     send ──► Telegram API          Xvfb + fluxbox + x11vnc + noVNC    │
 │                            │                         127.0.0.1:6080 ◄── you (PC)      │
 │                            │                                 ▲                        │
 │        volumes:  secrets (secrets.db, encrypted) · browser-profile · temporal-data     │
 └────────────────────────────┼─────────────────────────────────┼────────────────────────┘
                              ▼                                 │ Tailscale (private)
                  Supabase (cloud Postgres, schema "app")    your phone
                  messages · turns · tool_results · facts · approvals · audit · tasks
```

### 8.2 Containers

| Service | Image | Runs | Volumes / ports |
|---|---|---|---|
| `temporal` | Temporal CLI image | `temporal server start-dev --ip 0.0.0.0 --db-filename /data/temporal.db` | `temporal-data`; UI `127.0.0.1:8233` |
| `bot` | app image | `python -m app.bot`: Telegram poller + sweeper | none |
| `worker-agent` | app image | `python -m app.worker agent` | `secrets` |
| `browser` | browser image (Playwright Python base + Chrome + Xvfb + x11vnc + noVNC) | entrypoint starts the display + VNC, then `python -m app.worker browser` | `browser-profile`, `secrets` (later, for vault); `127.0.0.1:6080` |

Every service has `restart: unless-stopped`. Use **named volumes**, not Windows bind mounts: SQLite and Chrome profiles have locking and performance problems on Windows bind mounts.

### 8.3 Where data lives

| Data | Where | Protection |
|---|---|---|
| Messages, agent turns, tool results (including email excerpts and page text), facts, approvals, audit, tasks | **Supabase**, schema `app` | Not in Supabase's exposed API schemas; RLS on with no policies; accessed only via the Postgres connection string from your containers |
| Google OAuth tokens (later: site passwords) | **Local** `secrets.db` (SQLite) on the `secrets` volume | Envelope encryption: AES-256-GCM per value, data key wrapped by `MASTER_KEY` from your local `.env` |
| Browser profile (cookies, logged-in sessions) | **Local** `browser-profile` volume | Never leaves the PC. Turn on BitLocker. Treat it like your own browser. |
| Workflow state, timers, **scheduled tasks** | **Local** `temporal-data` volume (Temporal's SQLite) | Local only. Back it up (T-36). |
| Keys: Telegram, OpenRouter, Supabase password, master key | **Local** `.env` | Never committed (`.gitignore`) |

**Supabase never sees a credential.** A Supabase leak exposes conversation data, not account access.

### 8.4 Life of a message
1. The `bot` process gets an update → owner check → `INSERT … ON CONFLICT (tg_update_id) DO NOTHING` → signal-with-start `conversation` with `{msg_id}` → `dispatched=true` → advance the offset.
2. The workflow debounces for 2 s → `start_turn` (typing indicator, `agent_turns` row, freezes the tool menu) → `model_step`.
3. Tool calls run as parallel activities (`agent` or `browser` queue), each guarded, audited, and stored in `tool_results`.
4. `model_step` again with the results (+ any mid-turn messages) → … → reply → `send_reply` (format, G5 scan, split, send).

### 8.5 LLM calls (free models by default)

Any OpenAI-compatible `chat/completions` endpoint, called with raw `httpx`. The default is OpenRouter `:free` models.

```python
POST {LLM_BASE_URL}/chat/completions
{
  "model": MODEL_MAIN,                       # a ":free" model chosen in T-12
  "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *turn.messages],
  "tools": definitions(turn.tool_menu),      # OpenAI function format, sorted by name
  "max_tokens": 2000
}
```

**Free-tier limits** (OpenRouter docs, checked 2026-10-02): `:free` models allow **20 requests/min and 50 requests/day** without purchased credits, or 1,000/day after a one-time $10 credit purchase (optional, not planned). The design therefore **minimises requests**:

| Action | Model requests |
|---|---|
| Plain chat reply | 1 |
| Gmail question | 2 (tool + answer) |
| Approval button tap | 0 (handled by code) |
| Reminder firing (`remind`) | 0 (sent by code) |
| Scheduled `do` task | same as a normal turn |
| Browser task | about 5–15 (up to 3 actions per step, 25-step cap) |

Rules:
- **New user turn = fresh request:** frozen `system` + stable `tools` + **one user message** with the per-turn context. No reasoning from earlier turns is replayed.
- **Within a turn, append only:** the assistant message is stored **verbatim, including `tool_calls` and `reasoning_details`**, and sent back unmodified (OpenRouter requires this for Claude tool calls). Tool results are `role:"tool"` messages with `tool_call_id`. Mid-turn user messages are appended after them.
- **Keep `system` and `tools` stable:** time and status go in the user message, **never** in `system`. This keeps prompts small, and it pays off with prompt caching if you ever switch to a paid model.
- **Daily request budget:** `LLM_DAILY_REQUESTS` (default 45, just under the free cap) is checked before every call. Every call is logged in `llm_calls`. When the budget runs out, the agent says so once. Reminders keep working because they need no model.
- **Browser sub-agent:** each step is an independent request with a **text-first** observation, so no history needs pruning.
- **Retries:** httpx makes no retries. **Temporal** retries per-minute 429s, 5xx, and timeouts. The daily-cap 429 and 400s are not retried.
- **Tool arguments** arrive as a JSON string: parse and validate against the schema (`jsonschema`). Invalid → an error result back to the model.
- **Models** (env): `MODEL_MAIN` (chat + tools) and `MODEL_BROWSER` (tools; image input optional). Both are picked in T-12 by testing 2–3 free models that support tool calling. Model IDs live in `.env`, never in code, because free models come and go.
- **Switching providers is config only:** `LLM_BASE_URL` + `LLM_API_KEY` + model IDs (for example Gemini's free tier through its OpenAI-compatible endpoint, a local Ollama server, or a paid model later). Provider-specific extras such as `reasoning` or `cache_control` go in `LLM_EXTRA_JSON`.
- **Privacy:** free endpoints may log prompts or train on them (R9).

### 8.6 Temporal layout

| Workflow | ID | Started by | Purpose |
|---|---|---|---|
| `ConversationWorkflow` | `conversation` | bot / sweeper / events (signal-with-start) | Inbox, debounce, turns, button handling |
| `ScheduledTaskWorkflow` | `task-{id}` | `schedule_task` activity | Durable timer → send the reminder, or a `task_due` event |
| Temporal Schedule | `task-{id}` | `schedule_task` activity | Recurring task (cron, your timezone) → `TaskFireWorkflow` |

Signals: `new_message`, `button` (approval / takeover-done), `event` (task_due, takeover_done, google_connected).

| Activity | Queue | Timeouts | Retry |
|---|---|---|---|
| `start_turn`, `model_step`, Gmail and memory tools, `send_reply`, `execute_approved` | agent | 2 min | backoff, 5 attempts; 400/validation errors are not retried |
| `browser_task` | browser (concurrency 1) | start-to-close 10 min, heartbeat 30 s, schedule-to-start 10 min | 1 retry |

Workflow code stays deterministic. Only IDs and small dicts go through Temporal history.

### 8.7 Approval flow
1. A gated tool → G3 says `NEEDS_APPROVAL` → an `approvals` row (30 min) → code sends the description + `[Send] [Cancel]` (`callback_data = appr:{id}:y|n`).
2. The model is told "approval requested, not executed" and replies normally.
3. A tap → the bot answers the callback → signal `button` → `execute_approved`: an atomic claim (`UPDATE … WHERE status='pending' AND expires_at>now()`) → execute → edit the message to "✓ Sent" or "✗ Cancelled" → audit.

### 8.8 Takeover flow
1. The sub-agent calls `need_user("Discord login required")` → `browser_task` returns `{status:"needs_user"}` and keeps the tab open.
2. The `run_tool` code sends: "Discord needs you to log in. Open the live browser: {LIVE_VIEW_URL}. Tap Done when finished." with `[Done]` (`callback_data = take:{tool_call_id}`).
3. The model is told "user asked to take over; wait for Done", and replies briefly or not at all.
4. **Done** → signal `button` → an inbox event `takeover_done` → a new turn → the model calls `browser_task` again with the same goal ("continue"). The page is still where you left it.

### 8.9 Browser manager (the diamond in your diagram)

The browser manager is plain code (`app/browser.py`) inside the browser worker. **The AI drives; the manager owns the browser.**

| Job | How |
|---|---|
| Start and keep Chrome alive | Launched once when the worker starts (persistent context, headful, real Chrome). Relaunched automatically if it crashes or you close it. |
| **Keep logins (cookies)** | Chrome's **whole profile** (cookies, localStorage, IndexedDB) lives on the `browser-profile` volume. You log in once through the live view, and every later task and every restart reuses that session automatically. Nothing is exported or copied. |
| Session expired | The sub-agent sees the login page → `need_user` → takeover (§8.8) → you log in again → the new cookies are saved automatically. Automatic re-login with stored passwords is backlog B1. |
| One task at a time | `browser` task queue with concurrency 1. Other browser tasks wait in Temporal's queue. |
| Agent's own tab | Each task opens a marked tab and closes it at the end. On takeover the tab stays open. Your own tabs are never touched. |
| Liveness and stop | Heartbeat every ≤ 10 s. Cancel / "stop" → close the tab. |
| Safety (G4) | No remote-debugging port; downloads off; the agent never types into password fields; every action audited; live view only on 127.0.0.1 / Tailscale with a password |
| Live view | Xvfb (virtual screen) + x11vnc + noVNC in the same container |

**Protect the profile like your logged-in laptop.** In a container, Chrome encrypts its cookie store with a built-in default key, so anyone with the volume could reuse your sessions. It never leaves your PC, and BitLocker is recommended.

### 8.10 Mapping to your original diagram

**Same as the diagram:**
- Temporal Server (history, timers, signals, task queues) with its own database.
- **Workflow code and activities kept strictly separate.** Workflow code only waits, orders, and sets timers (no API calls). `Run_Agent_Turn` (= `model_step`: Context → Tool filter → Model call → Tool router) and the Tool Activities (**G3 re-check first**, then Gmail / browser task / send message) connect only through the workflow and the event history, never directly.
- Workflow steps: wait for signal → 2 s debounce → `model_step` → each tool call → risky ones need a yes → send → continue-as-new. State: inbox, turn count.
- Activity settings: timeout, retry policy, heartbeat for long jobs, idempotency, task queue.
- Sub-agent → browser manager → virtual browser → profile storage.
- Guardrails G1–G6 (adapted, §11). Outbound sender. Memory + conversation history. Audit log.

| Diagram box | Now | Why (chat decision) |
|---|---|---|
| WhatsApp Cloud API + webhook server | Telegram + long-poll `bot` process (G1 = owner allowlist) | Telegram; no public URL |
| Message queue | Outbox + sweeper (save first, re-signal) | Optional with Temporal |
| Web app, vault page, Google OAuth page | `connect_google` script; logins via live view | Just you |
| Task queues: agent, browser, phone, background | **agent + browser** | No phone; no email sync / nightly jobs in the MVP |
| Signals: new_message, vault_submitted, user_confirmed, cancel | `new_message`, `button` (approval / takeover Done), `event` (task_due, takeover_done, google_connected); cancel = "stop" | No vault page in the MVP |
| Step 5 "Risky? wait for yes" | **Non-blocking:** the turn ends, and the button tap later runs `execute_approved` | Chat stays usable; a tap can't be faked by the model |
| App DB (Postgres): users, user_settings, emails, search_chunks, summaries, tasks | Supabase: messages, agent_turns, tool_results, memory_facts, approvals, audit_log, connections, llm_calls. Settings in `.env`; tasks in Temporal; no mailbox copy; full-text search | Single user, Temporal stores schedules, $0 |
| Secrets DB: oauth_tokens, vault_credentials, vault_requests | Local encrypted SQLite (`secrets`); vault later | Credentials stay on your PC |
| Browser storage: browser_sessions + object storage | Whole Chrome profile on a local Docker volume | Simpler and more complete than copying cookies |
| Redis | Dropped (unique IDs for dedupe, count queries for limits) | One less system |
| Access: Gmail, Docs, Calendar | Gmail only | MVP scope |
| Vector search | Postgres full-text first (backlog B4) | $0, simpler |

---

## 9. Tool catalog

Tiers: **R** read · **WS** write to self · **WO** write to others or public (approval) · **D** destructive (approval).

| Tool | Tier | Needs | Queue | Milestone |
|---|---|---|---|---|
| `react_to_message(emoji)` | WS | — | agent | M1 |
| `remember_fact(kind, content)` | WS | — | agent | M1 |
| `forget_fact(fact_id)` | WS | — | agent | M1 |
| `search_history(query, limit)` | R | — | agent | M1 |
| `search_email(query, max)` | R | gmail.readonly | agent | M1 |
| `read_email(message_id)` | R | gmail.readonly | agent | M1 |
| `send_email(to, subject, body, reply_to_message_id?)` | **WO** | gmail.send | agent | M1 |
| `browser_task(goal, mode, start_url?)` | R (read) / **WO** (act) | browser up | browser | M2 |
| `schedule_task(kind, text, fire_at?, cron?)` | WS | — | agent | M3 |
| `list_tasks()` | R | — | agent | M3 |
| `cancel_task(task_id)` | WS | — | agent | M3 |

Browser sub-agent actions (inside `browser_task`, not shown to the main model): `goto, click, type, press, scroll, wait, back, look, need_user, done, fail`.

---

## 10. Data model

### Supabase: schema `app` (no `user_id` columns, single user)

| Table | Key columns |
|---|---|
| `messages` | `id bigserial, direction (in/out), tg_update_id UNIQUE NULL, tg_message_id, kind (text/button/photo/other), body, sent_at, dispatched bool, consumed_by NULL, turn_id NULL, tsv GENERATED` · idx `(sent_at desc)`, GIN `tsv` |
| `agent_turns` | `id uuid, kind (main/browser), parent_turn_id NULL, trigger, status, model, prompt_version, messages jsonb, tool_menu text[], usage jsonb, steps, started_at, ended_at` |
| `tool_results` | `turn_id, tool_call_id, tool, content jsonb, is_error, created_at` · PK `(turn_id, tool_call_id)` |
| `memory_facts` | `id, kind, content, source_message_id, created_at, updated_at, tsv GENERATED` |
| `approvals` | `id uuid, turn_id, tool, input jsonb, summary, status (pending/executing/executed/rejected/failed), expires_at, decided_at` |
| `audit_log` | `id, turn_id, actor, tool, tier, decision, detail jsonb, created_at` · append-only |
| `connections` | `provider PK (google/browser), status (connected/needs_reauth/down), scopes text[], meta jsonb (email, gmail_history_id), updated_at` |
| `llm_calls` | `id, at, kind (main/browser/scheduled), model, prompt_tokens, completion_tokens, cost NULL` · idx `(at)`. Used for the daily request budget and the usage report. |

Scheduled tasks are **not** stored here. They live in Temporal (§7.8).

Lock-down: `app` is **not** added to Supabase's exposed API schemas. `ALTER TABLE … ENABLE ROW LEVEL SECURITY` with no policies (defense in depth). Connect with the **session pooler** connection string (IPv4-compatible; Supabase's direct host is IPv6-only on the free plan).

### Local `secrets.db` (SQLite)

| Table | Columns |
|---|---|
| `secrets` | `kind, key, value_enc, data_key_enc, meta, updated_at` · PK `(kind, key)` · e.g. `('oauth','google')`; later `('site','discord')` for the vault (backlog B1) |

---

## 11. Security (Notes §15, adapted)

| Gate | v2 checks |
|---|---|
| **G1** Ingress | Owner-ID allowlist; private chats only; dedupe on `update_id`; ≤ 4,096 chars; ≤ 60 msgs/hour |
| **G2** Before model | Email, page text, and browser summaries wrapped in `<untrusted source=…>`; never put secrets in context; trim tool results |
| **G3** At execution | Tool must be in the turn's frozen menu; connection healthy; JSON-schema validation; WO/D → button approval; per-tool limits; audit; idempotency via `tool_results` PK + atomic approval claim |
| **G4** Browser | noVNC on 127.0.0.1 + password, reachable only via Tailscale; no remote-debugging port; the agent uses its own tab; downloads off; `act` mode only after approval; every action audited; hands over instead of bypassing anti-bot checks |
| **G5** Outbound | Scan replies for token patterns (`ya29.`, `1//0`, `sk-or-`, long base64) → block + audit; quiet hours for proactive messages; ≤ 3 proactive/day |
| **G6** Data | Secrets only in the local encrypted store; Supabase `app` schema not exposed; `.env` git-ignored; BitLocker recommended; `scripts/wipe.py` to delete everything |

---

## 12. Non-functional requirements

| Area | Target |
|---|---|
| First feedback | Typing indicator within 3 s of the last message in a burst |
| Simple reply | p50 < 8 s |
| Gmail task | p50 < 15 s |
| Browser task | Typical < 2 min, hard cap 10 min, "still working…" after 30 s |
| Reliability | 0 lost messages / 0 duplicate actions when killing any container mid-turn |
| Availability | Runs while the PC is on. After sleep or reboot, everything restarts and catches up (late, not lost). |
| Cost | **$0** on free models. A daily request budget (`LLM_DAILY_REQUESTS`) is checked before every model call, with a friendly message when it runs out. Every call is logged. |
| Footprint | Fits on a normal PC: about 2–3 GB RAM total (Chrome is the biggest) |

---

## 13. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12, `uv` |
| Telegram | Bot API over raw `httpx` (no bot framework) |
| LLM | Any OpenAI-compatible chat-completions endpoint over raw `httpx`; default OpenRouter `:free` models |
| Durable execution | Temporal (`temporalio`), dev server in Docker with a SQLite file |
| App DB | Supabase Postgres via `psycopg` 3 (raw SQL, numbered migrations) |
| Secrets | `sqlite3` (stdlib) + `cryptography` AES-GCM |
| Google | `google-auth`, `google-auth-oauthlib`, `google-api-python-client` |
| Browser | Playwright (Python) driving Google Chrome, headful on Xvfb; x11vnc + noVNC; fluxbox |
| Validation | `jsonschema` |
| Remote access | Tailscale (`tailscale serve`) |
| Tests | `pytest`, Temporal time-skipping test environment |

---

## 14. Success metrics

| Metric | Target |
|---|---|
| Scenario eval pass rate (about 15 scripted tasks: chat, Gmail, browser read, browser act, takeover, scheduling; run in daily chunks) | ≥ 85 % |
| Unapproved WO/D actions | **0** |
| Injection tests (email + web page) | 0 unwanted actions |
| Chaos tests (kill each container mid-turn) | 0 lost / 0 duplicated |
| A logged-in site stays usable without re-login | ≥ 7 days |
| Monthly running cost | **$0** |
| You use it daily for 2 weeks | Go/no-go for post-MVP work |

---

## 15. Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | The browser has **full access to every account you log into**, and a malicious page could try to steer it | `act` needs up-front approval; page text is untrusted; one task at a time; audit; you can watch live; log into only the sites you want it to use |
| **R2** | **Sites ban automation** (LinkedIn, Instagram, X are strict), which can get your account restricted | Human pace (no bulk actions), real Chrome, your home IP, hand over instead of bypassing; your call per site |
| R3 | PC off or asleep → bot offline, reminders late | Restart policies; disable sleep when plugged in; Temporal catches up |
| R4 | Supabase free plan **pauses after about 7 days of inactivity**; conversation data sits in the cloud | The bot's polling keeps it active while the PC is on. Restore from the dashboard if paused. Accept or use local Postgres (Q4). |
| **R5** | **Free-tier limit: 50 requests/day** (20/min). A browser task can use 5–15 requests. | Request budget; fewer calls per task (3 actions per step, code-sent reminders, no model for buttons); point `LLM_BASE_URL` at another free tier if needed. An optional one-time $10 OpenRouter credit raises the cap to 1,000/day. |
| R6 | Google OAuth: in "Testing" status, refresh tokens expire in 7 days | Set the consent screen to **In production** (unverified; you'll see a warning screen) to avoid the weekly expiry. Rerun the connect script if needed. |
| **R7** | **Free models are weaker at tool calling and browsing**, so complex browser tasks fail more often than with a top model | Text-first pages, small focused goals, takeover as the fallback; pick the best of 2–3 free models in T-12/T-31; per-job model switch (a paid model only for the browser, if ever needed) |
| R8 | Docker Desktop on Windows quirks (bind mounts, memory) | Named volumes; give WSL2 enough RAM (≥ 6 GB) |
| **R9** | **Free endpoints may log prompts or use them for training.** Your emails and page text pass through them. | Check each free model's provider policy on OpenRouter before choosing; avoid asking about very sensitive mail; switch to a no-training provider later if it matters |

---

## 16. Milestones

| Milestone | Contents | Tasks | Demo |
|---|---|---|---|
| **M1: Chat + Gmail** | Foundation, Telegram, Temporal, agent brain, memory, approvals, Gmail | T-01 → T-23 | U1–U7 |
| **M2: Virtual browser** | Browser container, live view, browser worker, sub-agent, takeover, any site | T-24 → T-31 | U8–U13 |
| **M3: Reminders + scheduled tasks** (MVP complete) | `schedule_task`, recurring schedules, list/cancel, all stored in Temporal | T-32 → T-34 | U14, U16 |
| **M4: Ops** | Usage report, backups/wipe, eval, always-on | T-35 → T-38 | Metrics in §14 |

---

## 17. Open questions

| # | Question | Default |
|---|---|---|
| Q1 | When to add email alerts and nightly summaries? | After the MVP. A scheduled `do` task covers it meanwhile. |
| Q2 | Is the host this Windows PC, always on? | Yes; disable sleep when plugged in |
| Q3 | Tailscale for phone access to the live view? | Yes (PC-only live view still works without it) |
| Q4 | Supabase vs local Postgres for app data? | Supabase (your choice). Local Postgres is a drop-in swap. |
| Q5 | Which free models? | Picked in T-12 by testing 2–3 free models with tool calling (and image input for the browser if available) |
| Q6 | Store site passwords for automatic re-login (vault)? | Later. You log in via the live view. |

---

## 18. Glossary
See Notes §4. Also:
- **Turn:** one agent run for a batch of messages or events.
- **Live view:** noVNC page showing the container's browser.
- **Takeover:** the agent pauses and asks you to act in the live view.
- **Tool menu:** the tools offered for one turn, fixed during that turn.
- **Envelope encryption:** each secret encrypted with its own key, which is encrypted with the master key.
