# Image for the bot and the agent worker.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ app/
COPY scripts/ scripts/
COPY migrations/ migrations/
