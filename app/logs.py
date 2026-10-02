"""JSON logs. Every line from inside an activity carries workflow_id, activity and (when known) turn_id,
so `docker compose logs worker-agent | grep <turn_id>` shows one turn end to end."""

import json
import logging
from contextvars import ContextVar

turn_id_var: ContextVar[str | None] = ContextVar("turn_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage()}
        try:
            from temporalio import activity
            info = activity.info()
            out |= {"workflow_id": info.workflow_id, "activity": info.activity_type, "attempt": info.attempt}
        except RuntimeError:
            pass  # not inside an activity
        if tid := turn_id_var.get():
            out["turn_id"] = tid
        if record.exc_info:
            out["error"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every request URL (they contain the bot token)
