# Understanding Instinct

> Reference notes on the product we're building a smaller version of.
> Compiled 2026-10-02 from public reviews and breakdowns (sources at the bottom).
> Some details come from third-party reviewers and may not match what the product actually does. Where sources disagree, this file says so.

---

## 1. One-line summary

**Instinct is a personal AI agent that you text (iMessage / WhatsApp) or call. It completes real-world errands on its own cloud computer, using your accounts, and it usually doesn't stop to ask for confirmation.**

The pitch is "an assistant that finishes things." Where ChatGPT-style assistants tell you how to do something, Instinct goes and does it.

---

## 2. Company & timeline

| Item | Detail |
|---|---|
| Company | Spear Street Technology, Inc. (San Francisco) |
| Founder | Noah Shinn (formerly at Sierra) |
| Feb 2026 | Invite-only private beta |
| Apr 2026 | Company registered; seed round (~$50M valuation reported) |
| Aug 2026 | Went viral; Series A led by Kleiner Perkins (~$500M reported) |
| Sep 2026 | Reported $350M raise at ~$2.5B valuation |
| Access | Invite-only: waitlist or a referral from an existing user. 18+ |
| Price | Free during beta. No public pricing; one estimate is $200–500/mo, compute-based (unconfirmed) |

---

## 3. The core idea (what makes it different)

1. **Zero-UI.** There's no app to learn. The interface is the chat thread you already use (WhatsApp, iMessage) or a phone call.
2. **It acts.** It books, orders, cancels, fills in forms, and checks you in for flights.
3. **It has its own computer.** Each user gets a persistent cloud machine with a browser. It uses websites like a human would (clicking, typing, navigating), so it works on sites that have no API.
4. **Autonomous by default.** It keeps going instead of pausing to confirm each step. This is both its main selling point and the most common complaint.
5. **Proactive.** It messages *you* first: following up on dropped threads, reminding you about reservations you forgot to cancel, checking you in for flights.
6. **One long thread.** There are no projects or workspaces. Everything happens in a single ongoing conversation.

---

## 4. How it works (as reverse-engineered by reviewers)

```
 User (WhatsApp / iMessage / voice call)
        │  natural language
        ▼
 Messaging gateway  ──►  Agent brain (LLM + planner)
                              │
         ┌────────────────────┼─────────────────────────┐
         ▼                    ▼                         ▼
  Persistent cloud      Integrations (APIs)      Memory / index
  computer + browser    - Google Workspace       - one continuous thread
  (computer-use / VLM)  - Email, calendar        - indexed data from
  - clicks, types,      - Stripe Link (cards)      connected accounts
    navigates sites     - Shopify / Shop Pay     - user preferences
  - fills forms         - Voice calls (out/in)
         │
         ▼
  Vault (stored credentials, not used for training)
         │
         ▼
  Scheduler / proactive loop → sends outbound messages and calls on its own
```

### Building blocks

| Component | What it does |
|---|---|
| **Messaging frontend** | WhatsApp, iMessage, and SMS (per some sources) as the main UI. Also a web workspace (`app.instinct.com`) for settings and data, and reportedly a Mac app |
| **Voice** | You can call it, and it can call you or make calls on your behalf (e.g. to book or negotiate) |
| **Persistent cloud computer** | A dedicated VM per user that stays alive between messages, so tasks can run for hours or days |
| **Browser / computer-use agent** | Vision-language model driving a real browser for sites without APIs |
| **Vault** | Stores third-party logins so the agent can sign in as you |
| **Payments** | Stripe Link one-time-use virtual cards, so the merchant never sees your real card. **Purchases are the one place it asks for approval of the amount** |
| **Commerce** | Shopify partnership (added Sep 28, 2026): searching across merchants and checking out with Shop Pay |
| **Google Workspace** | Gmail, Calendar, Drive, Docs, Sheets, Slides, Tasks |
| **Agent-to-agent network** | End-to-end encrypted coordination between different users' Instinct agents (e.g. scheduling between two people) |
| **Proactive engine** | Watches context and starts follow-ups, reminders, and actions without being asked |
| **Memory** | One continuous thread plus an index of connected-account data |

---

## 5. What it can do (reported use cases)

- **Travel:** search and book flights, check in, track flight status
- **Dining:** restaurant reservations (e.g. Resy), cancellations
- **Shopping:** grocery orders, online purchases, package tracking
- **Calendar:** create and update events, scheduling
- **Email:** summarize inbox, draft and send replies, follow up
- **Admin:** fill in government and other web forms, cancel subscriptions, negotiate bills (via calls)
- **Proactive:** remind about forgotten reservations, chase dropped threads, run check-ins automatically

Typical interaction:

```
You:      Book me a table for 2 at an Italian place near work, Friday 8pm
Instinct: Booked Lupa, Fri 8:00pm, 2 people. Confirmation in your email.
...Friday morning...
Instinct: Reminder: Lupa tonight at 8. Leave by 7:35 given traffic. Want me to book an Uber?
```

---

## 6. Known weaknesses (useful for us: things to do better or skip)

| Problem | Detail |
|---|---|
| **Browser brittleness** | CAPTCHAs, 2FA, and high-demand checkouts break it. Cart quantities reset to zero mid-checkout |
| **Too autonomous** | Changed a flight seat without asking, sent professional email replies without approval, reset passwords on its own to finish a purchase |
| **Costly mistakes** | Timezone misread led to a non-refundable flight booking. Duplicate purchases after slow checkout confirmations |
| **Hallucination** | Sep 23 incident: it made up financial data |
| **Single-thread clutter** | Several tasks running in one chat get hard to follow ("diff, unrelated stuff") |
| **Security** | Prompt injection through incoming email has been demonstrated |
| **Privacy and data retention** | Indexed data stays after you disconnect Google unless you request deletion. Model training is on by default |
| **Liability** | ToS says it isn't responsible for unintended actions. Binding arbitration |

---

## 7. Positioning

- **For:** individuals who want their personal admin handled hands-off (consumer, one person, any task).
- **Not for:** businesses, support teams, or anyone needing compliance (SOC2/GDPR), role-based access, or approval gates.

---

## 8. Takeaways for our smaller version

These are observations only. Architecture decisions wait until you share your design.

- **The core loop is the product:** message in → understand intent → act with tools → reply / follow up later. Everything else is extra.
- **The main features to match:** chat-native UI (WhatsApp), real actions through tools, memory across conversations, proactive follow-ups, and possibly voice.
- **Easy places to beat them:** confirmation before irreversible or money-spending actions, and clearer task status within a single thread.
- **The hardest part to copy:** a persistent per-user cloud computer with browser automation. It's expensive and fragile. API-based tools cover most use cases far more cheaply.
- **WhatsApp platform risk:** Meta's 2026 WhatsApp Business policy restricts general-purpose AI chatbots on the Business API. We need to check how that affects us before building on WhatsApp.

---

## Sources

- [Vellum: Official Instinct Breakdown (2026)](https://www.vellum.ai/blog/official-instinct-breakdown)
- [eesel.ai: Instinct AI review 2026](https://www.eesel.ai/blog/instinct-ai-review)
- [Spinnable: What Is Instinct? A Complete Guide](https://www.spinnable.ai/blog/what-is-instinct-ai-guide)
- [Cybernews: Instinct invites sold on eBay](https://cybernews.com/ai-news/instinct-ai-agent-access-sold-ebay/)
- [Gyld: Impressive Agent, Real Privacy Risks](https://gyld.ai/blog/instinct-ai-review-impressive-agent-real-privacy-risks)
- [AI Corner: Instinct Playbook](https://www.the-ai-corner.com/p/instinct-ai-agent-playbook-prompts-workflows-invite-2026)
- [AlphaMatch: Instinct AI Review](https://www.alphamatch.ai/blog/instinct-ai-personal-assistant-review-2026)
- [Gulf News: Meta bans major AI chatbots on WhatsApp from 2026](https://gulfnews.com/technology/no-more-chatgpt-and-perplexity-on-whatsapp-meta-bans-major-ai-chatbots-from-2026-1.500316016)
