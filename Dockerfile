FROM python:3.12-slim

LABEL org.opencontainers.image.title="PULSE8.ai Cortex"
LABEL org.opencontainers.image.description="Agent-native knowledge OS built on Markdown"
LABEL org.opencontainers.image.vendor="PULSE8.ai"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY cortex/ cortex/
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev
RUN uv run python -m spacy download en_core_web_sm

RUN mkdir -p /vault/raw /vault/wiki /vault/agents /vault/sessions /vault/daily /vault/.cortex

ENV CORTEX_VAULT_PATH=/vault
ENV CORTEX_MCP_TRANSPORT=http
ENV CORTEX_MCP_SSE_PORT=8420

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8420/api/v1/health || exit 1

CMD ["uv", "run", "uvicorn", "cortex.main:app", "--host", "0.0.0.0", "--port", "8420"]
