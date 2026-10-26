# GRIDPRINT API image (FastAPI on arm64 Fargate, SPEC 10.1). Build context: repository root.
#   docker buildx build --platform linux/arm64 -f infra/docker/api.Dockerfile -t gridprint-api .
FROM ghcr.io/astral-sh/uv:0.11.8 AS uv

FROM python:3.11-slim

# ffprobe is used for input validation (container whitelist, duration limit).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group agent --no-install-project

COPY config ./config
COPY engine ./engine
COPY agent ./agent
COPY mcp_server ./mcp_server
COPY node/ingest ./node/ingest
COPY api ./api

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app:/app/engine

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin gridprint \
 && chown -R gridprint /app
USER 10001

EXPOSE 8000
# Interface set by the lead. The ECS task definition sets the same command.
CMD ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
