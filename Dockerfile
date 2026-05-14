# Dockerfile
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libaio1 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml version.txt ./
RUN uv venv /opt/venv
RUN . /opt/venv/bin/activate && uv pip install .

# ---- runtime ----
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y \
    libaio1 \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Oracle Instant Client
RUN curl -o instantclient.zip https://download.oracle.com/otn_software/linux/instantclient/instantclient-basiclite-linux.x64-21.13.0.0.0dbru.zip && \
    unzip instantclient.zip && \
    mv instantclient_* /opt/oracle && \
    rm instantclient.zip

ENV LD_LIBRARY_PATH=/opt/oracle

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . .

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "dart.asgi:application"]
