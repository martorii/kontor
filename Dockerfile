FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

RUN useradd --system --create-home --uid 1000 kontor
WORKDIR /app

COPY --from=builder --chown=kontor:kontor /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY --chown=kontor:kontor alembic.ini ./
COPY --chown=kontor:kontor migrations ./migrations

USER kontor
EXPOSE 8000
CMD ["uvicorn", "--factory", "kontor.api.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
