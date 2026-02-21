# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install poetry==2.1.1 poetry-plugin-export==1.9.0

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml poetry.lock ./

# Export to requirements.txt so the runtime image doesn't need Poetry
RUN poetry export -f requirements.txt --without dev -o requirements.txt

FROM python:3.11-slim

# Install git (needed for Claude Code operations) and gosu (for dropping
# root privileges in the entrypoint after fixing volume permissions)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git gosu && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies — cache mount keeps downloaded wheels across builds
COPY --from=builder /app/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy application source and files needed for pip install
COPY src/ src/
COPY pyproject.toml README.md ./

# Install the project itself (for entry point and metadata)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps .

# Copy entrypoint script and set up non-root user in one layer
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    useradd --create-home botuser && \
    mkdir -p /home/botuser/workspace

# NOTE: No USER directive here — the entrypoint starts as root to fix
# volume permissions (named volumes are root-owned), then drops to
# botuser via gosu before exec'ing the command.
WORKDIR /home/botuser/workspace

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["claude-telegram-bot"]
