"""Check a model before using it (uses ~4 requests of your daily free budget).

    python -m uv run --env-file .env python -m scripts.llm_probe "some/model:free" [--image]

Checks: (a) tool call format, (b) sending the result back works, (c) two tools at once,
(d) finish reasons, (e) image input (with --image). Pick the best 1-2 models; write results at the top of app/llm.py.
"""

import asyncio
import json
import sys

from app import db, llm
from app.config import get_settings

TOOLS = [
    {"type": "function", "function": {"name": "get_weather", "description": "Weather for a city",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"],
                    "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_time", "description": "Local time in a city",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"],
                    "additionalProperties": False}}},
]
# 1x1 red pixel PNG
PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="


async def main(model: str, image: bool):
    await db.connect(get_settings().database_url)
    print(f"model: {model}\n")
    msgs = [{"role": "user", "content": "What's the weather in Pune? Use the tool."}]
    r = await llm.chat("probe", model, msgs, TOOLS)
    m = r["message"]
    print("(a) tool call:", json.dumps(m.get("tool_calls"), indent=1)[:600], "| finish:", r["finish_reason"])
    if not m.get("tool_calls"):
        print("    !! no tool call: this model is not usable for the agent")
        return
    msgs += [m, {"role": "tool", "tool_call_id": m["tool_calls"][0]["id"], "content": '{"temp_c": 31, "sky": "sunny"}'}]
    r = await llm.chat("probe", model, msgs, TOOLS)
    print("(b) answer after tool result:", repr(r["message"]["content"][:200]), "| finish:", r["finish_reason"])
    r = await llm.chat("probe", model, [{"role": "user", "content": "Weather AND local time in Delhi. Call both tools now."}], TOOLS)
    print("(c) parallel calls:", [c["function"]["name"] for c in r["message"].get("tool_calls", [])])
    print("    reasoning_details present:", "reasoning_details" in r["message"])
    if image:
        r = await llm.chat("probe", model, [{"role": "user", "content": [
            {"type": "text", "text": "What color is this image? One word."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PIXEL}"}}]}])
        print("(e) image:", repr(r["message"]["content"][:100]))
    print(f"\nrequests used today: {await llm.requests_today()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], "--image" in sys.argv),
                loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
