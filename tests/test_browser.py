"""Browser primitives + sub-agent loop, on local test pages with headless Chromium (no DB, fake model).
Needs: python -m playwright install chromium"""

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

from app import browser, llm
from app.config import get_settings

pytestmark = pytest.mark.proactor  # Playwright needs the Proactor loop on Windows

SITE = Path(__file__).parent / "fixtures" / "site"


@pytest.fixture(scope="module")
def site():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
async def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_CHANNEL", "chromium")
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path / "profile"))
    get_settings.cache_clear()
    m = browser.BrowserManager()
    try:
        await m.context()
    except Exception as e:
        pytest.skip(f"Chromium not installed ({e!r})")
    yield m
    await m.close()
    get_settings.cache_clear()


# ---------- observation & actions (T-27) ----------

async def test_observe_lists_visible_elements_only(manager, site):
    page = await manager.agent_page()
    await page.goto(f"{site}/index.html")
    obs = await browser.observe(page)
    assert obs["title"] == "Test Shop" and "Item 3 — $30" in obs["text"]
    assert any('link "Contact form" -> form.html' in e for e in obs["elements"])
    assert not any("Hidden button" in e for e in obs["elements"])
    assert obs["screenshot"] is None
    assert (await browser.observe(page, screenshot=True))["screenshot"][:2] == b"\xff\xd8"  # JPEG


async def test_hidden_injection_text_is_not_shown(manager, site):
    page = await manager.agent_page()
    await page.goto(f"{site}/inject.html")
    obs = await browser.observe(page)
    assert "evil.example" not in obs["text"]          # display:none text is invisible to the model
    assert "Delete account" in "\n".join(obs["elements"])  # the visible trap is there (the prompt must resist it)


async def test_type_and_submit(manager, site):
    page = await manager.agent_page()
    await page.goto(f"{site}/form.html")
    obs = await browser.observe(page)
    name_id = int(next(e for e in obs["elements"] if "Your name" in e).split("]")[0][1:])
    assert await browser.act(page, "type", {"id": name_id, "text": "Yash", "submit": True}) == "ok"
    assert await page.title() == "Sent"
    assert "Thanks, Yash" in (await browser.observe(page))["text"]


async def test_password_fields_are_refused(manager, site):
    page = await manager.agent_page()
    await page.goto(f"{site}/login.html")
    obs = await browser.observe(page)
    pw_id = int(next(e for e in obs["elements"] if "type=password" in e).split("]")[0][1:])
    with pytest.raises(browser.ActionError, match="password"):
        await browser.act(page, "type", {"id": pw_id, "text": "hunter2"})


async def test_bad_inputs(manager, site):
    page = await manager.agent_page()
    with pytest.raises(browser.ActionError):
        await browser.act(page, "goto", {"url": "file:///etc/passwd"})
    await page.goto(f"{site}/index.html")
    await browser.observe(page)
    assert (await browser.act(page, "click", {"id": 999})).startswith("error")


# ---------- manager (T-26) ----------

async def test_profile_persists_across_restarts(tmp_path, monkeypatch, site):
    monkeypatch.setenv("BROWSER_CHANNEL", "chromium")
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path / "p"))
    get_settings.cache_clear()
    try:
        m1 = browser.BrowserManager()
        page = await m1.agent_page()
        await page.goto(f"{site}/index.html")
        await page.evaluate("localStorage.setItem('session', 'logged-in')")
        await m1.close()
        m2 = browser.BrowserManager()   # "container restart"
        page = await m2.agent_page()
        await page.goto(f"{site}/index.html")
        assert await page.evaluate("localStorage.getItem('session')") == "logged-in"
        await m2.close()
    finally:
        get_settings.cache_clear()


# ---------- sub-agent loop (T-28) ----------

def call(name, **args):
    return {"id": f"c-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def model(monkeypatch, decide):
    """decide(user_text, step_count) -> list of tool calls (or [] for a text-only reply)."""
    seen = []

    async def chat(kind, model_name, messages, tools=None, max_tokens=2000):
        content = messages[1]["content"]
        text = content if isinstance(content, str) else content[0]["text"]
        seen.append({"text": text, "tools": [t["function"]["name"] for t in tools], "n": len(messages)})
        calls = decide(text, len(seen))
        return {"message": {"role": "assistant", "content": "" if calls else "hmm", **({"tool_calls": calls} if calls else {})},
                "finish_reason": "tool_calls" if calls else "stop"}

    monkeypatch.setattr(llm, "chat", chat)
    return seen


def element_id(text, label):
    return int(next(line for line in text.splitlines() if label in line).split("]")[0][1:])


async def test_reads_answer_from_page(manager, site, monkeypatch):
    def decide(text, n):
        price = next(line for line in text.splitlines() if "Item 3" in line).split("$")[1]
        return [call("done", summary=f"Item 3 costs ${price}")]

    seen = model(monkeypatch, decide)
    r = await browser.run_browser_task("price of item 3", "read", f"{site}/index.html", manager)
    assert r == {"status": "done", "summary": "Item 3 costs $30", "screenshot": None}
    assert "look" not in seen[0]["tools"]  # BROWSER_VISION=false: no screenshots offered


async def test_three_actions_in_one_step(manager, site, monkeypatch):
    def decide(text, n):
        if "TITLE: Contact" in text:
            return [call("type", id=element_id(text, "Your name"), text="Yash"), call("press", key="Enter")]
        if "TITLE: Sent" in text:
            return [call("done", summary="sent")]
        return [call("click", id=element_id(text, "Contact form"))]

    seen = model(monkeypatch, decide)
    r = await browser.run_browser_task("send the contact form as Yash", "act", f"{site}/index.html", manager)
    assert r["status"] == "done" and len(seen) == 3  # click | type+Enter in ONE request | done
    assert 'type({"id": 1, "text": "…"})' in seen[2]["text"]  # typed text is hidden from the log


async def test_need_user_keeps_tab_for_takeover(manager, site, monkeypatch):
    model(monkeypatch, lambda text, n: [call("need_user", reason="Login required")])
    r = await browser.run_browser_task("read my messages", "read", f"{site}/login.html", manager)
    assert r == {"status": "needs_user", "reason": "Login required"}
    kept = manager.takeover_page
    assert kept and not kept.is_closed()
    assert await manager.agent_page() is kept   # the continuation starts on the same tab


async def test_step_limit_and_tab_closed(manager, site, monkeypatch):
    model(monkeypatch, lambda text, n: [call("scroll", direction="down")])
    r = await browser.run_browser_task("loop forever", "read", f"{site}/index.html", manager)
    assert r["status"] == "failed" and "step limit" in r["reason"]
    ctx = await manager.context()
    assert all(p.is_closed() for p in ctx.pages if p.url.endswith("index.html"))


async def test_text_only_replies_fail_after_one_nudge(manager, site, monkeypatch):
    seen = model(monkeypatch, lambda text, n: [])
    r = await browser.run_browser_task("x", "read", f"{site}/index.html", manager)
    assert r["status"] == "failed" and len(seen) == 2


async def test_audit_hook_sees_every_action(manager, site, monkeypatch):
    actions = []

    async def on_action(name, args, result, url):
        actions.append((name, result))

    model(monkeypatch, lambda text, n: [call("scroll", direction="down")] if n == 1 else [call("done", summary="ok")])
    await browser.run_browser_task("scroll once", "read", f"{site}/index.html", manager, on_action=on_action)
    assert actions == [("scroll", "ok")]
