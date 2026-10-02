# T-28: Browser sub-agent — what we have done

**Status:** done ✅ (tested with a scripted fake AI on real pages) · real-model check pending your key

## In one sentence
A small AI loop **drives the browser step by step** toward one goal, then reports back to the main agent.

## The loop (`run_browser_task`)
Each step:
1. **Look** at the page (T-27): URL, title, numbered elements, visible text (+ a screenshot only after `look`).
2. **Ask the AI** (a fresh, small request each step): goal, mode, step N/25, the last 15 actions, and the page.
3. **Do up to 3 actions** in a row (e.g. type → Enter → wait). It stops early if the page changes or an action fails, then looks again.
4. Finish with one of:
   - `done(summary, screenshot?)`: the answer, ≤ 1,500 characters; a screenshot is sent to you if useful
   - `need_user(reason)`: login/CAPTCHA/2FA, so you take over (T-30); **the tab stays open**
   - `fail(reason)`: impossible or stuck

## Saving your free quota
- Up to **3 actions per AI request** instead of 1.
- **25-step cap.**
- Each request is fresh and small (no growing history to resend).
- Text first; screenshots only on request.

## Robustness
- If the AI answers with words instead of actions, it's nudged once, then the task fails cleanly.
- Typed text is shown as "…" in the action log (no sensitive text repeated back).
- Uses `tool_choice: auto`. Some models (including the newest Claude ones) reject "forced" tool choice.

## Tests (6, real browser + scripted AI)
| Test | Proves |
|---|---|
| Read the answer from the page | The AI is given the real page text: "Item 3 costs $30" |
| **3 actions in one request** | The form is filled and submitted with only 3 AI requests total |
| need_user | Returns needs_user and **keeps the tab** for the takeover; the next task reuses it |
| Step limit | Fails after 25 steps; the tab is closed |
| Words instead of actions | One nudge, then a clean fail |
| Audit hook | Every action is reported |
| Vision off | `look` isn't offered when the model can't see images |

## Next
**T-29:** the `browser_task` tool for the main agent.
