# MultiCode AI Bot - Docker Image
# Supports all 8 AI providers in a containerized environment

FROM python:3.11-slim

# Metadata
LABEL maintainer="your.email@example.com"
LABEL description="Multi-AI Telegram Bot with 8 AI providers (Claude, Gemini, OpenAI, DeepSeek, Groq, Ollama, Blackbox, Windsurf)"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Configure Poetry to not create virtual env (we're already in container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy application code
COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data && chmod 777 /app/data

# Create directory for approved projects
RUN mkdir -p /projects && chmod 777 /projects

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APPROVED_DIRECTORY=/projects
ENV DATABASE_URL=sqlite:///app/data/bot.db

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sqlite3; conn = sqlite3.connect('/app/data/bot.db'); conn.close()" || exit 1

# Run as non-root user for security
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app /projects
USER botuser

# Expose any ports if needed (Telegram bot doesn't need exposed ports by default)
# EXPOSE 8080

# Start the bot
CMD ["python", "-m", "src.main"]
