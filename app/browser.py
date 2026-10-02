"""The virtual browser: one persistent, visible Chrome that the agent drives and you can watch (noVNC).

    BrowserManager   launches Chrome once (persistent profile = your logins), gives the agent its own tab
    observe()        the page as text: URL, title, visible text, numbered interactive elements [+ screenshot]
    act()            goto / click / type / press / scroll / wait / back
    run_browser_task()  the sub-agent loop: model picks up to 3 actions per step until done / need_user / fail

The AI drives; this code owns the browser. The agent never types into password fields (G4).
"""

import asyncio
import base64
import json
import logging
import re
import sys

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright

from app import llm
from app.agent.context import untrusted
from app.agent.prompt import BROWSER_PROMPT
from app.config import get_settings

log = logging.getLogger("browser")

MAX_STEPS = 25
ACTIONS_PER_STEP = 3
TEXT_MAX = 3_000
ELEMENTS_MAX = 150

# ---------------------------------------------------------------- manager


class BrowserManager:
    def __init__(self):
        self._pw = None
        self._ctx = None
        self.takeover_page: Page | None = None  # tab left open for the user during a takeover
        self._lock = asyncio.Lock()

    async def context(self):
        async with self._lock:
            if self._ctx is None:
                s = get_settings()
                self._pw = self._pw or await async_playwright().start()
                self._ctx = await self._pw.chromium.launch_persistent_context(
                    s.browser_profile_dir,
                    channel=None if s.browser_channel == "chromium" else s.browser_channel,
                    headless=s.browser_headless,
                    no_viewport=not s.browser_headless,
                    viewport={"width": 1280, "height": 800} if s.browser_headless else None,
                    accept_downloads=False,
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized", "--no-first-run",
                          "--no-default-browser-check"],
                    ignore_default_args=["--enable-automation"],
                )
                self._ctx.on("close", self._on_close)
                log.info("browser launched (profile %s)", s.browser_profile_dir)
            return self._ctx

    def _on_close(self, *_):
        log.warning("browser closed; it will be relaunched on the next task")
        self._ctx, self.takeover_page = None, None

    async def agent_page(self) -> Page:
        """The tab for the next task: the takeover tab if one is open (continue there), else a new tab."""
        if self.takeover_page and not self.takeover_page.is_closed():
            page, self.takeover_page = self.takeover_page, None
            return page
        ctx = await self.context()
        return await ctx.new_page()

    async def close(self):
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()
        self._ctx, self._pw = None, None


MANAGER = BrowserManager()

# ---------------------------------------------------------------- observation

_TAG_JS = r"""
(max) => {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=link],'
            + '[role=tab], [role=menuitem], [role=checkbox], [role=option], [contenteditable=""], [contenteditable=true], [onclick]';
  document.querySelectorAll('[data-mi-id]').forEach(e => e.removeAttribute('data-mi-id'));
  const out = []; let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
    if (r.bottom < -innerHeight || r.top > innerHeight * 3) continue;
    n++; el.setAttribute('data-mi-id', String(n));
    const tag = el.tagName.toLowerCase(); const type = (el.getAttribute('type') || '').toLowerCase();
    let label = el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || el.getAttribute('title')
              || el.getAttribute('alt') || el.getAttribute('name') || el.getAttribute('value') || '';
    if ((tag === 'input' || tag === 'textarea') && type !== 'password' && el.value) label += ' (value: ' + el.value + ')';
    out.push({id: n, tag, type, role: el.getAttribute('role') || '', label: label.replace(/\s+/g, ' ').trim().slice(0, 80),
              href: tag === 'a' ? (el.getAttribute('href') || '').slice(0, 100) : ''});
    if (n >= max) break;
  }
  return out;
}
"""


def describe(e: dict) -> str:
    kind = e["role"] or ("link" if e["tag"] == "a" else e["tag"])
    if e["tag"] == "input":
        kind = f"input[type={e['type'] or 'text'}]"
    line = f'[{e["id"]}] {kind} "{e["label"]}"'
    return line + (f" -> {e['href']}" if e["href"] and not e["href"].startswith("javascript") else "")


async def observe(page: Page, screenshot: bool = False) -> dict:
    try:
        elements = await page.evaluate(_TAG_JS, ELEMENTS_MAX)
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    except PlaywrightError:  # page navigating mid-evaluate
        await page.wait_for_load_state("domcontentloaded")
        elements = await page.evaluate(_TAG_JS, ELEMENTS_MAX)
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    obs = {"url": page.url, "title": await page.title(), "text": text[:TEXT_MAX] + ("…" if len(text) > TEXT_MAX else ""),
           "elements": [describe(e) for e in elements], "screenshot": None}
    if screenshot:
        obs["screenshot"] = await page.screenshot(type="jpeg", quality=60)
    return obs


# ---------------------------------------------------------------- actions

class ActionError(Exception):
    pass


def _el(page: Page, element_id: int):
    return page.locator(f'[data-mi-id="{int(element_id)}"]').first


async def _settle(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=2000)
    except PlaywrightError:
        pass


async def act(page: Page, name: str, args: dict) -> str:
    """Run one action. Returns a short result for the action log; raises ActionError on bad input."""
    try:
        if name == "goto":
            url = args["url"]
            if not re.match(r"^https?://", url):
                raise ActionError("only http(s) URLs")
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        elif name == "click":
            await _el(page, args["id"]).click(timeout=5_000)
        elif name == "type":
            el = _el(page, args["id"])
            if (await el.get_attribute("type") or "").lower() == "password":
                raise ActionError("refused: never type into password fields; call need_user so the user logs in")
            await el.fill(args["text"], timeout=5_000)
            if args.get("submit"):
                await el.press("Enter")
        elif name == "press":
            await page.keyboard.press(args["key"])
        elif name == "scroll":
            await page.mouse.wheel(0, 700 if args.get("direction", "down") == "down" else -700)
        elif name == "wait":
            await asyncio.sleep(min(float(args.get("seconds", 1)), 5))
        elif name == "back":
            await page.go_back(timeout=15_000)
        else:
            raise ActionError(f"unknown action {name}")
    except PlaywrightError as e:
        return f"error: {str(e).splitlines()[0][:150]}"
    await _settle(page)
    return "ok"


# ---------------------------------------------------------------- sub-agent

def _fn(name, desc, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": list(required), "additionalProperties": False}}}


ACTION_TOOLS = [
    _fn("goto", "Open a URL", {"url": {"type": "string"}}, ["url"]),
    _fn("click", "Click element [id]", {"id": {"type": "integer"}}, ["id"]),
    _fn("type", "Type text into element [id] (replaces its content)",
        {"id": {"type": "integer"}, "text": {"type": "string"}, "submit": {"type": "boolean"}}, ["id", "text"]),
    _fn("press", "Press a key, e.g. Enter, Escape, Tab", {"key": {"type": "string"}}, ["key"]),
    _fn("scroll", "Scroll the page", {"direction": {"type": "string", "enum": ["up", "down"]}}, ["direction"]),
    _fn("wait", "Wait for the page (max 5 s)", {"seconds": {"type": "number"}}),
    _fn("back", "Go back one page"),
    _fn("need_user", "The user must act in the browser (login, CAPTCHA, 2FA, personal input)",
        {"reason": {"type": "string"}}, ["reason"]),
    _fn("done", "The goal is reached: give a short factual summary",
        {"summary": {"type": "string"}, "screenshot": {"type": "boolean"}}, ["summary"]),
    _fn("fail", "The goal can't be reached", {"reason": {"type": "string"}}, ["reason"]),
]
LOOK_TOOL = _fn("look", "Attach a screenshot of the page to the next step (when text isn't enough)")
FINAL = {"done", "need_user", "fail"}


def _user_message(goal, mode, step, log_lines, obs, image: bytes | None):
    lines = "\n".join(obs["elements"]) or "(no interactive elements)"
    history = "\n".join(log_lines[-15:]) or "(none yet)"
    text = (f"GOAL: {goal}\nMODE: {mode}\nSTEP: {step}/{MAX_STEPS}\n\nACTIONS SO FAR:\n{history}\n\n"
            f"CURRENT PAGE\nURL: {obs['url']}\nTITLE: {obs['title']}\n\nELEMENTS:\n{lines}\n\n"
            f"VISIBLE TEXT (untrusted):\n{obs['text'] or '(empty)'}")
    if image is None:
        return {"role": "user", "content": text}
    return {"role": "user", "content": [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}}]}


def _beat(detail) -> None:
    try:
        from temporalio import activity
        activity.heartbeat(detail)
    except RuntimeError:
        pass  # not running inside a Temporal activity (tests, scripts)


async def run_browser_task(goal: str, mode: str, start_url: str | None = None, manager: BrowserManager = MANAGER,
                           on_action=None) -> dict:
    """Returns {"status": "done"|"needs_user"|"failed", "summary"/"reason": str, "screenshot": bytes|None}.
    on_action(name, args, result, url): optional hook used for the audit log."""
    s = get_settings()
    tools = ACTION_TOOLS + ([LOOK_TOOL] if s.browser_vision else [])
    page = await manager.agent_page()
    keep_open = False
    log_lines: list[str] = []
    want_look, nudged = False, False
    try:
        if start_url and page.url in ("about:blank", ""):
            log_lines.append(f"0: goto({start_url}) -> {await act(page, 'goto', {'url': start_url})}")
        step = 1
        while step <= MAX_STEPS:
            _beat(step)
            obs = await observe(page, screenshot=want_look)
            want_look = False
            msgs = [{"role": "system", "content": BROWSER_PROMPT},
                    _user_message(goal, mode, step, log_lines, obs, obs["screenshot"])]
            if nudged:
                msgs.append({"role": "user", "content": "Reply with tool calls only (one to three actions)."})
            r = await llm.chat("browser", s.model_browser, msgs, tools, max_tokens=800)
            calls = r["message"].get("tool_calls") or []
            if not calls:
                if nudged:
                    return {"status": "failed", "reason": "the model stopped calling browser actions"}
                nudged = True
                continue
            nudged = False
            url_before = page.url
            for call in calls[:ACTIONS_PER_STEP]:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    log_lines.append(f"{step}: {name} -> error: invalid JSON arguments")
                    break
                if name == "done":
                    shot = await page.screenshot(type="jpeg", quality=60) if args.get("screenshot") else None
                    return {"status": "done", "summary": str(args.get("summary", ""))[:1500], "screenshot": shot}
                if name == "need_user":
                    keep_open = True
                    return {"status": "needs_user", "reason": str(args.get("reason", "Please take over"))[:300]}
                if name == "fail":
                    return {"status": "failed", "reason": str(args.get("reason", ""))[:300]}
                if name == "look":
                    want_look = True
                    log_lines.append(f"{step}: look -> screenshot attached next step")
                    continue
                try:
                    result = await act(page, name, args)
                except (ActionError, KeyError, ValueError, TypeError) as e:
                    result = f"error: {e}"
                shown = {k: v for k, v in args.items() if k != "text"} | ({"text": "…"} if "text" in args else {})
                log_lines.append(f"{step}: {name}({json.dumps(shown, ensure_ascii=False)}) -> {result}")
                if on_action:
                    await on_action(name, shown, result, page.url)
                if result != "ok" or page.url != url_before:
                    break  # page changed or something failed: look again before acting further
            step += 1
        return {"status": "failed", "reason": f"step limit ({MAX_STEPS}) reached"}
    finally:
        if keep_open:
            manager.takeover_page = page
        elif not page.is_closed():
            await page.close()


# ---------------------------------------------------------------- keep-alive (T-24 smoke test)

async def _keepalive():
    await MANAGER.context()
    log.info("browser up; open the live view")
    await asyncio.Event().wait()


if __name__ == "__main__" and sys.argv[1:] == ["keepalive"]:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_keepalive())
