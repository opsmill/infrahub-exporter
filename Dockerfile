ARG PYTHON_VER=3.12
ARG POETRY_VER=2.1.3
FROM docker.io/python:${PYTHON_VER}-slim AS base

ENV PYTHONUNBUFFERED=1

ENV PATH="${PATH}:/root/.local/bin"

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends build-essential curl \
    pkg-config build-essential ca-certificates && \
    curl -sSL https://install.python-poetry.org | POETRY_VERSION=$POETRY_VER python3 - && \
    apt-get autoremove -y && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/* && \
    pip --no-cache-dir install --no-compile --upgrade pip wheel

RUN poetry config virtualenvs.create false
# Poetry 2.1 workaround
ENV POETRY_VIRTUALENVS_CREATE=false


WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN poetry install --no-interaction --no-ansi --no-root --no-directory && \
    rm -rf /root/.cache

COPY . ./

EXPOSE 8001

CMD ["poetry", "run", "python", "infrahub_exporter/main.py", "--config", "/app/config.yml"]

