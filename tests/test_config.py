import base64
from datetime import time

import pytest

from app.config import ConfigError, load

KEY = base64.b64encode(b"k" * 32).decode()

MINIMAL = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "TELEGRAM_OWNER_ID": "42",
    "DATABASE_URL": "postgresql://u:p@host:5432/postgres",
    "MASTER_KEY": KEY,
    "LLM_API_KEY": "sk-or-v1-test",
    "MODEL_MAIN": "some/model:free",
}


def test_empty_env_lists_every_missing_var():
    with pytest.raises(ConfigError) as e:
        load({})
    for name in MINIMAL:
        assert name in str(e.value)


def test_blank_values_count_as_missing():
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        load({**MINIMAL, "LLM_API_KEY": "   "})


def test_minimal_env_gets_defaults():
    s = load(MINIMAL)
    assert s.telegram_owner_id == 42
    assert s.master_key == b"k" * 32
    assert s.model_browser == "some/model:free"  # falls back to MODEL_MAIN
    assert s.llm_base_url == "https://openrouter.ai/api/v1"
    assert s.llm_daily_requests == 45
    assert s.llm_extra_json == {}
    assert str(s.owner_timezone) == "Asia/Kolkata"
    assert s.quiet_start == time(23, 0) and s.quiet_end == time(7, 0)
    assert s.recurring_do_min_minutes == 60


def test_overrides_are_parsed():
    s = load({
        **MINIMAL,
        "MODEL_BROWSER": "other/model",
        "LLM_BASE_URL": "http://localhost:11434/v1/",
        "LLM_DAILY_REQUESTS": "10",
        "LLM_EXTRA_JSON": '{"reasoning": {"effort": "low"}}',
        "OWNER_TIMEZONE": "Europe/London",
    })
    assert s.model_browser == "other/model"
    assert s.llm_base_url == "http://localhost:11434/v1"  # trailing slash removed
    assert s.llm_daily_requests == 10
    assert s.llm_extra_json == {"reasoning": {"effort": "low"}}
    assert str(s.owner_timezone) == "Europe/London"


@pytest.mark.parametrize("name,value", [
    ("TELEGRAM_OWNER_ID", "not-a-number"),
    ("MASTER_KEY", base64.b64encode(b"short").decode()),
    ("MASTER_KEY", "not base64!!"),
    ("OWNER_TIMEZONE", "Mars/Olympus"),
    ("QUIET_START", "25:99"),
    ("LLM_DAILY_REQUESTS", "0"),
    ("LLM_EXTRA_JSON", "[1, 2]"),
])
def test_bad_values_are_reported_by_name(name, value):
    with pytest.raises(ConfigError, match=name):
        load({**MINIMAL, name: value})


def test_all_bad_values_reported_together():
    with pytest.raises(ConfigError) as e:
        load({**MINIMAL, "TELEGRAM_OWNER_ID": "x", "OWNER_TIMEZONE": "Nope/Nope"})
    assert "TELEGRAM_OWNER_ID" in str(e.value) and "OWNER_TIMEZONE" in str(e.value)
