import re

from app.agent.prompt import BROWSER_PROMPT, SYSTEM_PROMPT


def test_system_prompt_size_fits_free_models():
    assert 400 <= len(SYSTEM_PROMPT) // 4 <= 900  # rough token estimate


def test_prompts_are_frozen_text():
    # No template slots or dates: per-turn data (time, status) belongs in the user message.
    for p in (SYSTEM_PROMPT, BROWSER_PROMPT):
        assert not re.search(r"\{[a-z_]+\}", p)
        assert "{now" not in p


def test_system_prompt_covers_the_rules():
    for must in ["<untrusted", "approval_requested", "<now>", "<connections>", "<events>", "remember_fact",
                 "search_history", "browser_task", "schedule_task", "passwords", "ONE short clarifying"]:
        assert must in SYSTEM_PROMPT, must


def test_browser_prompt_covers_the_rules():
    for must in ["need_user", "done", "fail", "read", "act", "untrusted", "Never type passwords", "look"]:
        assert must in BROWSER_PROMPT, must
