# T-30: Takeover ("please log in, then tap Done") — what we have done

**Status:** done ✅

## In one sentence
When a site needs **you** (login, CAPTCHA, 2FA), the agent sends you the **live-view link and a Done button**. You handle it in the browser, tap Done, and the agent **continues where it stopped**.

## The flow
```
"check my Discord DMs"
 → browser sub-agent sees a login page → need_user("Discord login required")
 → the tab STAYS OPEN on that page
 → code sends you: "Discord login required. Open your browser here: <live view link>. Tap Done when finished." [Done ✅]
 → the AI tells you briefly and waits (the chat stays usable)
you log in via the live view (PC, or phone via Tailscale) → tap Done
 → the tap becomes a "takeover_done" event → new turn
 → the AI sees "The user finished taking over. Continue: goal='read my Discord DMs'"
 → it calls browser_task again → it continues ON THE SAME TAB, now logged in
 → next time, no login needed: the cookies are in the profile
```
- The Done button lives in the `approvals` table (tool = `takeover`, valid 2 hours) and is claimed once.
- Typing "done" also works, since the AI understands it. The button is just quicker. A takeover isn't a security gate, so no tap is required.
- **Your password never touches our code.** You type it on the real site in the real Chrome.

## Tests
Built from the T-17 (button claim → event), T-13 (event starts a turn), T-11 (event text includes the goal), T-28 (tab kept and reused) and T-29 (link + Done button sent) tests. Each step of the chain is covered.

## Next
**T-31:** real-site validation (needs your model key).
