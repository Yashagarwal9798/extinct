# T-27: Seeing and acting on pages — what we have done

**Status:** done ✅ (tested on local test pages with a real headless browser)

## In one sentence
We turned a web page into **text the AI can read** (with numbered buttons and fields) and wrote the **actions** it can take: click, type, scroll, and so on.

## How the AI "sees" a page (`observe`)
```
URL: https://news.ycombinator.com/
TITLE: Hacker News
ELEMENTS:
[1] link "new" -> newest
[2] input[type=text] "Search"
[3] button "Log in"
VISIBLE TEXT (untrusted):
1. Show HN: ... 420 points ...
```
- A small script **numbers every visible clickable or typeable thing** (links, buttons, fields, menus…), up to 150. **Hidden elements are skipped.**
- Visible page text, up to 3,000 characters. **Text hidden with CSS is invisible to the AI**, which defeats one common injection trick (tested).
- **Text first, screenshot only on request** (`look`, and only if your browser model accepts images). Text is much cheaper and works with text-only free models.

## Actions (`act`)
`goto(url)` (http/https only) · `click(id)` · `type(id, text, submit?)` · `press(key)` · `scroll(up/down)` · `wait(≤5 s)` · `back()`. After each one we wait briefly for the page to settle.

## Safety (G4)
- **The agent never types into password fields.** It's refused with "call need_user so the user logs in". You log in yourself in the live view.
- `goto` refuses `file://` and other non-web addresses.
- Every action is written to the audit log (T-29), with the typed text hidden.

## Tests (5, real browser, local test pages)
Visible elements listed and hidden ones skipped; screenshot only when asked · **hidden injection text not shown to the AI** · type + Enter submits a form · **password field refused** · bad URL refused, missing element reports an error.

## Next
**T-28:** the browser sub-agent loop.
