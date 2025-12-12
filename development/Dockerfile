ARG PYTHON_VER=3.12
FROM ghcr.io/astral-sh/uv:python${PYTHON_VER}-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY . ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8001

ENV EXPORTER_CONFIG=/app/config.yml
CMD ["/app/.venv/bin/python", "-m", "infrahub_exporter.main", "--config", "/app/config.yml"]
