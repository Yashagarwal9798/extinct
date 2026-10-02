"""Settings from environment variables.

Check your .env with:  python -m uv run --env-file .env python -m app.config
Code reads settings with get_settings(); it is loaded once and cached.
"""

import base64
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from functools import cache
from zoneinfo import ZoneInfo

REQUIRED = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_OWNER_ID",
    "DATABASE_URL",
    "MASTER_KEY",
    "LLM_API_KEY",
    "MODEL_MAIN",
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_owner_id: int
    database_url: str
    master_key: bytes
    llm_api_key: str
    model_main: str
    model_browser: str
    llm_base_url: str
    llm_daily_requests: int
    llm_extra_json: dict
    owner_timezone: ZoneInfo
    quiet_start: time
    quiet_end: time
    secrets_db_path: str
    temporal_address: str
    google_client_id: str
    google_client_secret: str
    vnc_password: str
    live_view_url: str
    recurring_do_min_minutes: int
    telegram_dry_run: bool
    browser_profile_dir: str
    browser_channel: str
    browser_headless: bool
    browser_vision: bool


def _bool(raw: str) -> bool:
    if raw.lower() in ("1", "true", "yes"):
        return True
    if raw.lower() in ("", "0", "false", "no"):
        return False
    raise ValueError("must be true/false")


def _master_key(raw: str) -> bytes:
    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise ValueError(f"must decode to 32 bytes, got {len(key)}")
    return key


def _positive_int(raw: str) -> int:
    n = int(raw)
    if n <= 0:
        raise ValueError("must be > 0")
    return n


def _json_object(raw: str) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("must be a JSON object")
    return value


def load(env: Mapping[str, str] = os.environ) -> Settings:
    """Build Settings from env. Raises ConfigError listing every problem at once."""
    missing = [k for k in REQUIRED if not env.get(k, "").strip()]
    if missing:
        raise ConfigError("Missing required env vars: " + ", ".join(missing))

    errors: list[str] = []

    def get(name: str, parse=str, default: str = ""):
        raw = env.get(name, "").strip() or default
        try:
            return parse(raw)
        except Exception as e:
            errors.append(f"{name}: {e}")

    model_main = get("MODEL_MAIN")
    settings = dict(
        telegram_bot_token=get("TELEGRAM_BOT_TOKEN"),
        telegram_owner_id=get("TELEGRAM_OWNER_ID", int),
        database_url=get("DATABASE_URL"),
        master_key=get("MASTER_KEY", _master_key),
        llm_api_key=get("LLM_API_KEY"),
        model_main=model_main,
        model_browser=get("MODEL_BROWSER", default=model_main),
        llm_base_url=get("LLM_BASE_URL", default="https://openrouter.ai/api/v1").rstrip("/"),
        llm_daily_requests=get("LLM_DAILY_REQUESTS", _positive_int, "45"),
        llm_extra_json=get("LLM_EXTRA_JSON", _json_object, "{}"),
        owner_timezone=get("OWNER_TIMEZONE", ZoneInfo, "Asia/Kolkata"),
        quiet_start=get("QUIET_START", time.fromisoformat, "23:00"),
        quiet_end=get("QUIET_END", time.fromisoformat, "07:00"),
        secrets_db_path=get("SECRETS_DB_PATH", default="/secrets/secrets.db"),
        temporal_address=get("TEMPORAL_ADDRESS", default="temporal:7233"),
        google_client_id=get("GOOGLE_CLIENT_ID"),
        google_client_secret=get("GOOGLE_CLIENT_SECRET"),
        vnc_password=get("VNC_PASSWORD"),
        live_view_url=get("LIVE_VIEW_URL", default="http://localhost:6080/vnc.html"),
        recurring_do_min_minutes=get("RECURRING_DO_MIN_MINUTES", _positive_int, "60"),
        telegram_dry_run=get("TELEGRAM_DRY_RUN", _bool, "false"),
        browser_profile_dir=get("BROWSER_PROFILE_DIR", default="/profile"),
        browser_channel=get("BROWSER_CHANNEL", default="chrome"),
        browser_headless=get("BROWSER_HEADLESS", _bool, "false"),
        browser_vision=get("BROWSER_VISION", _bool, "false"),
    )
    if errors:
        raise ConfigError("Invalid env vars: " + "; ".join(errors))
    return Settings(**settings)


@cache
def get_settings() -> Settings:
    return load()


if __name__ == "__main__":
    try:
        s = load()
    except ConfigError as e:
        print(f"Config problem: {e}")
        sys.exit(1)
    print("Config OK")
    print(f"  owner id      : {s.telegram_owner_id}")
    print(f"  timezone      : {s.owner_timezone}")
    print(f"  llm           : {s.llm_base_url}  main={s.model_main}  browser={s.model_browser}")
    print(f"  daily requests: {s.llm_daily_requests}")
    print(f"  temporal      : {s.temporal_address}")
    print(f"  google oauth  : {'set' if s.google_client_id else 'not set (needed from T-19)'}")
