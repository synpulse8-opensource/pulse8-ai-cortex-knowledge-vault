FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @tobilu/qmd \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY cortex/ cortex/
COPY scripts/ scripts/

RUN mkdir -p /vault/raw /vault/wiki /vault/agents /vault/sessions /vault/daily /vault/.cortex

ENV CORTEX_VAULT_PATH=/vault
ENV CORTEX_MCP_TRANSPORT=sse
ENV CORTEX_MCP_SSE_PORT=8420

EXPOSE 8420

CMD ["uv", "run", "uvicorn", "cortex.main:app", "--host", "0.0.0.0", "--port", "8420"]
