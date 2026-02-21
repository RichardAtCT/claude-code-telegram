FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir poetry==2.1.1

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml poetry.lock ./

# Export to requirements.txt so the runtime image doesn't need Poetry
RUN poetry export -f requirements.txt --without dev -o requirements.txt

FROM python:3.11-slim

# Install git (needed for Claude Code operations) and clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies from exported requirements
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ src/
COPY pyproject.toml ./

# Install the project itself (for entry point and metadata)
RUN pip install --no-cache-dir --no-deps .

# Create a non-root user
RUN useradd --create-home botuser
USER botuser

# Default working directory for Claude Code operations
RUN mkdir -p /home/botuser/workspace
WORKDIR /home/botuser/workspace

ENTRYPOINT ["claude-telegram-bot"]
