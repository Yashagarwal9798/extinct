# The virtual browser: Temporal worker ("browser" queue) + headful Chrome on a virtual screen + noVNC live view.
# Playwright version must match uv.lock (1.63.0).
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb fluxbox x11vnc novnc websockify fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    DISPLAY=:99 BROWSER_PROFILE_DIR=/profile BROWSER_CHANNEL=chrome BROWSER_HEADLESS=false

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev \
 && playwright install --with-deps chrome   # real Google Chrome (amd64): fewer "unsupported browser" walls

COPY app/ app/
COPY scripts/ scripts/
COPY docker/browser-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "app.worker", "browser"]
