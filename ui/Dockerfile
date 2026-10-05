FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Only the `ui` dependency group: the UI image carries no backend code and no database driver.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --only-group ui --no-install-project


FROM python:3.12-slim-bookworm AS runtime

RUN useradd --system --create-home --uid 1000 kontor
WORKDIR /app

COPY --from=builder --chown=kontor:kontor /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY --chown=kontor:kontor ui ./ui

USER kontor
EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
