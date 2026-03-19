# ---- Build stage ----
FROM python:3.11-slim AS builder

# Optional dependency build args
ARG INSTALL_POSTGRES=false
ARG INSTALL_CACHE=false

RUN pip install --no-cache-dir poetry==2.3.2

WORKDIR /app
COPY pyproject.toml poetry.lock ./

# Export requirements and install without Poetry runtime overhead
RUN poetry export -f requirements.txt --without dev --without-hashes -o requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Conditionally install optional extras
RUN if [ "$INSTALL_POSTGRES" = "true" ]; then \
      pip install --no-cache-dir --prefix=/install asyncpg; \
    fi
RUN if [ "$INSTALL_CACHE" = "true" ]; then \
      pip install --no-cache-dir --prefix=/install redis; \
    fi

# ---- Runtime stage ----
FROM python:3.11-slim

# Install Node.js for Claude CLI (required for SDK auth via CLI)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy Python deps from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY src/ src/
COPY pyproject.toml ./

# Copy Grafana dashboard definitions for reference
COPY docs/grafana/ docs/grafana/

# Install the project itself (editable not needed in container)
RUN pip install --no-cache-dir --no-deps .

# Create data directory for SQLite
RUN mkdir -p /app/data

# Create non-root user
RUN useradd -m -s /bin/bash botuser && chown -R botuser:botuser /app
USER botuser

# Default env vars
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO

EXPOSE 8080

# Health check (works when API server is enabled via ENABLE_API_SERVER=true)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["claude-telegram-bot"]
