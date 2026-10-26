# GRIDPRINT engine worker image (agent orchestrator + MCP server + engine, SPEC Part 5).
# Multi-arch: build with `docker buildx build --platform linux/arm64` (production, Graviton)
# or `--platform linux/amd64` (x86 benchmark baseline only, SPEC Part 12 config A).
# Build context: repository root.
#   docker buildx build --platform linux/arm64 -f infra/docker/engine.Dockerfile -t gridprint-engine .
FROM ghcr.io/astral-sh/uv:0.11.8 AS uv

FROM python:3.11-slim

# ffmpeg for PyAV/ffprobe; pango/harfbuzz libraries for the WeasyPrint report renderer (DECISIONS D-008).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group agent --group pdf --no-install-project

COPY config ./config
COPY engine ./engine
COPY agent ./agent
COPY mcp_server ./mcp_server
COPY api ./api
COPY scripts/fetch_models.py ./scripts/fetch_models.py
# DNN models (S5, S12) are downloaded from opencv_zoo at build time; licenses and SHA-256 are recorded
RUN /opt/venv/bin/python scripts/fetch_models.py

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app:/app/engine

# Non-root user. FFmpeg decoding runs as this user (SPEC Part 13).
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin gridprint \
 && chown -R gridprint /app
USER 10001

# Worker entrypoint (interface set by the lead). The ECS task definition sets the same command.
CMD ["python", "-m", "api.worker", "--sqs"]
