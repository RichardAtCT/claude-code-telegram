# TODO-9: Deployment & Documentation

## Objective
Prepare the project for production deployment and open-source release with comprehensive documentation, Docker configuration, CI/CD pipelines, and community guidelines.

## Deployment Architecture

### Infrastructure Options
```
Deployment Options:
├── Docker Standalone
├── Docker Compose
├── Kubernetes
├── Cloud Services
│   ├── AWS (EC2, ECS, Lambda)
│   ├── Google Cloud (Compute, Cloud Run)
│   └── Azure (VMs, Container Instances)
└── VPS (DigitalOcean, Linode, etc.)
```

## Docker Configuration

### Production Dockerfile
```dockerfile
# docker/Dockerfile
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN curl -fsSL https://storage.googleapis.com/public-download-service-anthropic/claude-code/install.sh | bash

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements
COPY requirements/base.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Claude Code from builder
COPY --from=builder /usr/local/bin/claude /usr/local/bin/claude

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv

# Create non-root user
RUN useradd -m -u 1000 botuser && \
    mkdir -p /app /data && \
    chown -R botuser:botuser /app /data

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CLAUDE_CODE_PATH=/usr/local/bin/claude

# Copy application
WORKDIR /app
COPY --chown=botuser:botuser . .

# Switch to non-root user
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python scripts/check_health.py

# Run bot
CMD ["python", "-m", "src.main"]
```

### Docker Compose Configuration
```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  bot:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: claude-code-bot
    restart: unless-stopped
    env_file:
      - ../.env
    volumes:
      - bot-data:/data
      - ${APPROVED_DIRECTORY}:/projects:ro
    networks:
      - bot-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M

  # Optional: Monitoring
  prometheus:
    image: prom/prometheus:latest
    container_name: bot-prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    networks:
      - bot-network
    ports:
      - "9090:9090"

  # Optional: Grafana
  grafana:
    image: grafana/grafana:latest
    container_name: bot-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    networks:
      - bot-network
    ports:
      - "3000:3000"

volumes:
  bot-data:
  prometheus-data:
  grafana-data:

networks:
  bot-network:
    driver: bridge
```

## Kubernetes Deployment

### Kubernetes Manifests
```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: claude-code-bot
  labels:
    app: claude-code-bot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: claude-code-bot
  template:
    metadata:
      labels:
        app: claude-code-bot
    spec:
      serviceAccountName: claude-code-bot
      containers:
      - name: bot
        image: your-registry/claude-code-bot:latest
        imagePullPolicy: Always
        env:
        - name: DATABASE_URL
          value: "sqlite:///data/bot.db"
        envFrom:
        - secretRef:
            name: claude-code-bot-secrets
        volumeMounts:
        - name: data
          mountPath: /data
        - name: projects
          mountPath: /projects
          readOnly: true
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: bot-data-pvc
      - name: projects
        hostPath:
          path: /opt/projects
          type: Directory

---
apiVersion: v1
kind: Service
metadata:
  name: claude-code-bot
spec:
  selector:
    app: claude-code-bot
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: bot-data-pvc
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

## Documentation

### README.md
```markdown
# Claude Code Telegram Bot

[![Tests](https://github.com/yourusername/claude-code-telegram/workflows/Tests/badge.svg)](https://github.com/yourusername/claude-code-telegram/actions)
[![Coverage](https://codecov.io/gh/yourusername/claude-code-telegram/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/claude-code-telegram)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Run Claude Code remotely through Telegram with a terminal-like interface.

![Demo GIF](docs/images/demo.gif)

## Features

✨ **Terminal-like Commands** - Navigate projects with familiar commands (`cd`, `ls`, `pwd`)  
🤖 **Full Claude Code Integration** - All Claude Code features available remotely  
🔒 **Security First** - Directory isolation, user authentication, rate limiting  
📁 **Project Management** - Easy project switching and session persistence  
🚀 **Advanced Features** - File uploads, Git integration, quick actions  
📊 **Usage Tracking** - Monitor costs and usage per user  
🔧 **Extensible** - Plugin-ready architecture for custom features  

## Quick Start

### 1. Prerequisites

- Python 3.9+
- Claude Code CLI installed
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Linux/macOS (Windows WSL supported)

### 2. Installation

```bash
# Clone repository
git clone https://github.com/yourusername/claude-code-telegram.git
cd claude-code-telegram

# Install dependencies
pip install -r requirements/base.txt

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 3. Configuration

Edit `.env` with your settings:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_BOT_USERNAME=your_bot_username
APPROVED_DIRECTORY=/home/user/projects
ALLOWED_USERS=123456789,987654321  # Your Telegram user ID
```

### 4. Run

```bash
# Development
poetry run claude-telegram-bot

# Production with Docker
docker-compose up -d
```

## Usage

### Basic Commands

```
/start - Initialize bot
/ls - List files in current directory
/cd <dir> - Change directory (resumes session for that project)
/pwd - Show current directory
/projects - Show all projects
/new - Clear context and start fresh session
/continue - Explicitly continue last session
/end - End current session and clear context
/status - Show session info (includes resumable sessions)
```

### Example Workflow

1. **Start a session**
   ```
   /projects
   [Select your project]
   ```

2. **Navigate and explore**
   ```
   /ls
   /cd src
   /pwd
   ```

3. **Code with Claude**
   ```
   You: Create a FastAPI endpoint for user authentication
   Claude: I'll create a FastAPI endpoint for user authentication...
   ```

4. **Use quick actions**
   ```
   [🧪 Run tests] [📦 Install deps] [🔍 Lint code]
   ```

## Security

- **Directory Isolation**: All operations confined to approved directory
- **User Authentication**: Whitelist or token-based access
- **Rate Limiting**: Prevent abuse and control costs
- **Input Validation**: Protection against injection attacks
- **Audit Logging**: Track all operations

See [SECURITY.md](SECURITY.md) for details.

## Development

### Setup Development Environment

```bash
# Install dev dependencies
pip install -r requirements/dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run with hot reload
poetry run claude-telegram-bot --debug
```

### Project Structure

```
claude-code-telegram/
├── src/               # Source code
├── tests/             # Test suite
├── docs/              # Documentation
├── docker/            # Docker files
└── scripts/           # Utility scripts
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## Deployment

### Docker

```bash
docker build -t claude-code-bot .
docker run -d --name claude-bot --env-file .env claude-code-bot
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

### Cloud Platforms

- [AWS Deployment Guide](docs/deployment/aws.md)
- [Google Cloud Guide](docs/deployment/gcp.md)
- [Azure Guide](docs/deployment/azure.md)

## Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | Required |
| `APPROVED_DIRECTORY` | Base directory for projects | Required |
| `ALLOWED_USERS` | Comma-separated user IDs | None |
| `RATE_LIMIT_REQUESTS` | Requests per minute | 10 |
| `CLAUDE_MAX_COST_PER_USER` | Max cost per user (USD) | 10.0 |

See [docs/configuration.md](docs/configuration.md) for all options.

## Troubleshooting

### Common Issues

**Bot not responding**
- Check bot token is correct
- Verify bot is not already running
- Check logs: `docker logs claude-bot`

**Permission denied errors**
- Ensure approved directory exists and is readable
- Check file permissions

**Rate limit errors**
- Adjust `RATE_LIMIT_REQUESTS` in config
- Check user hasn't exceeded cost limit

See [docs/troubleshooting.md](docs/troubleshooting.md) for more.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

- Anthropic for Claude Code
- Telegram Bot API
- Contributors and testers

## Support

- 📧 Email: support@example.com
- 💬 Discord: [Join our server](https://discord.gg/example)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/claude-code-telegram/issues)

---

Made with ❤️ by the community
```

### CONTRIBUTING.md
```markdown
# Contributing to Claude Code Telegram Bot

Thank you for your interest in contributing! We welcome contributions from everyone.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/yourusername/claude-code-telegram/issues)
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - System information

### Suggesting Features

1. Check [existing proposals](https://github.com/yourusername/claude-code-telegram/discussions)
2. Open a discussion with:
   - Use case description
   - Proposed implementation
   - Alternative solutions

### Code Contributions

#### Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/claude-code-telegram.git
   cd claude-code-telegram
   ```

3. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements/dev.txt
   pre-commit install
   ```

#### Development Process

1. Create feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make changes following our coding standards

3. Run tests:
   ```bash
   pytest
   make lint
   ```

4. Commit with descriptive message:
   ```bash
   git commit -m "feat: add amazing feature"
   ```

5. Push and create PR:
   ```bash
   git push origin feature/your-feature-name
   ```

### Coding Standards

- Follow PEP 8
- Use type hints
- Write docstrings for all functions
- Keep line length under 88 characters
- Use black for formatting
- Write tests for new features

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Formatting changes
- `refactor:` Code refactoring
- `test:` Test changes
- `chore:` Maintenance tasks

### Testing

- Write unit tests for new code
- Ensure all tests pass
- Maintain >80% coverage
- Include integration tests for features

### Documentation

- Update README if needed
- Add docstrings to new functions
- Include examples in docs
- Update configuration docs

## Pull Request Process

1. Update documentation
2. Add tests for changes
3. Ensure CI passes
4. Request review from maintainers
5. Address review feedback
6. Squash commits if requested

## Release Process

1. Maintainers will version according to SemVer
2. Changelog updated automatically
3. Docker images built and pushed
4. GitHub release created

## Getting Help

- 💬 [Discord Server](https://discord.gg/example)
- 📧 maintainers@example.com
- 🤔 [Discussions](https://github.com/yourusername/claude-code-telegram/discussions)

Thank you for contributing! 🎉
```

### SECURITY.md
```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability, please follow responsible disclosure:

### 1. **Do NOT** create a public issue

### 2. Email security@example.com with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### 3. Wait for response
- We'll acknowledge within 48 hours
- We'll provide an estimate for fix
- We'll notify you when fixed

## Security Measures

### Authentication
- Telegram user ID whitelist
- Optional token-based authentication
- Session management with expiry

### Authorization
- Directory traversal prevention
- Command injection protection
- File type validation

### Rate Limiting
- Per-user request limits
- Cost-based limiting
- Concurrent session limits

### Data Protection
- Local SQLite database
- No sensitive data in logs
- Secure token storage

### Infrastructure
- Run as non-root user
- Resource limits enforced
- Regular dependency updates

## Best Practices for Users

1. **Protect your bot token**
   - Never commit to version control
   - Use environment variables
   - Rotate regularly

2. **Limit approved directory**
   - Use minimal necessary access
   - Avoid system directories
   - Regular permission audits

3. **Monitor usage**
   - Check audit logs
   - Monitor costs
   - Review user activity

4. **Keep updated**
   - Apply security updates
   - Monitor announcements
   - Update dependencies

## Security Checklist

- [ ] Bot token is secure
- [ ] Approved directory is limited
- [ ] User whitelist configured
- [ ] Rate limits enabled
- [ ] Logs don't contain secrets
- [ ] Running as non-root
- [ ] Dependencies updated
- [ ] Backups configured

## Contact

Security issues: security@example.com  
PGP Key: [Download](https://example.com/pgp-key.asc)
```

## Deployment Scripts

### Health Check Script
```python
# scripts/check_health.py
"""
Health check for monitoring
"""

import sys
import asyncio
from pathlib import Path

async def check_health():
    """Perform health checks"""
    checks = {
        'database': check_database(),
        'claude': check_claude(),
        'telegram': check_telegram(),
        'storage': check_storage()
    }
    
    results = {}
    for name, check in checks.items():
        try:
            results[name] = await check
        except Exception as e:
            results[name] = False
            print(f"Health check failed for {name}: {e}")
    
    # Overall health
    healthy = all(results.values())
    
    if healthy:
        print("All health checks passed")
        sys.exit(0)
    else:
        print(f"Health checks failed: {results}")
        sys.exit(1)

async def check_database():
    """Check database connectivity"""
    from src.storage.database import DatabaseManager
    
    db = DatabaseManager(os.getenv('DATABASE_URL'))
    async with db.get_connection() as conn:
        await conn.execute("SELECT 1")
    return True

async def check_claude():
    """Check Claude Code availability"""
    import subprocess
    
    result = subprocess.run(['claude', '--version'], capture_output=True)
    return result.returncode == 0

async def check_telegram():
    """Check Telegram bot token"""
    import aiohttp
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.telegram.org/bot{token}/getMe') as resp:
            return resp.status == 200

async def check_storage():
    """Check storage availability"""
    data_dir = Path('/data')
    return data_dir.exists() and data_dir.is_dir() and os.access(data_dir, os.W_OK)

if __name__ == '__main__':
    asyncio.run(check_health())
```

### Deployment Script
```bash
#!/bin/bash
# scripts/deploy.sh

set -e

echo "🚀 Deploying Claude Code Telegram Bot"

# Load environment
source .env

# Build Docker image
echo "📦 Building Docker image..."
docker build -t claude-code-bot:latest -f docker/Dockerfile .

# Stop existing container
echo "🛑 Stopping existing container..."
docker stop claude-code-bot || true
docker rm claude-code-bot || true

# Run new container
echo "▶️ Starting new container..."
docker run -d \
  --name claude-code-bot \
  --restart unless-stopped \
  --env-file .env \
  -v claude-bot-data:/data \
  -v "${APPROVED_DIRECTORY}:/projects:ro" \
  claude-code-bot:latest

# Wait for health check
echo "⏳ Waiting for health check..."
sleep 10

# Check health
if docker exec claude-code-bot python scripts/check_health.py; then
    echo "✅ Deployment successful!"
else
    echo "❌ Health check failed!"
    docker logs claude-code-bot
    exit 1
fi

# Cleanup old images
echo "🧹 Cleaning up old images..."
docker image prune -f

echo "🎉 Deployment complete!"
```

## Monitoring Setup

### Prometheus Configuration
```yaml
# docker/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'claude-code-bot'
    static_configs:
      - targets: ['bot:8080']
    metrics_path: '/metrics'
```

### Grafana Dashboard
```json
{
  "dashboard": {
    "title": "Claude Code Bot Metrics",
    "panels": [
      {
        "title": "Active Users",
        "targets": [
          {
            "expr": "bot_active_users"
          }
        ]
      },
      {
        "title": "Message Rate",
        "targets": [
          {
            "expr": "rate(bot_messages_total[5m])"
          }
        ]
      },
      {
        "title": "Claude Cost",
        "targets": [
          {
            "expr": "bot_claude_cost_total"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(bot_errors_total[5m])"
          }
        ]
      }
    ]
  }
}
```

## Release Process

### GitHub Actions Release
```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Docker image
      run: |
        docker build -t claude-code-bot:${{ github.ref_name }} .
        docker tag claude-code-bot:${{ github.ref_name }} claude-code-bot:latest
    
    - name: Login to Registry
      uses: docker/login-action@v2
      with:
        username: ${{ secrets.DOCKER_USERNAME }}
        password: ${{ secrets.DOCKER_PASSWORD }}
    
    - name: Push images
      run: |
        docker push claude-code-bot:${{ github.ref_name }}
        docker push claude-code-bot:latest
    
    - name: Create Release
      uses: softprops/action-gh-release@v1
      with:
        files: |
          README.md
          LICENSE
        generate_release_notes: true
```

## Success Criteria

- [ ] Docker image builds successfully
- [ ] Health checks pass
- [ ] Documentation is complete and clear
- [ ] All deployment scripts tested
- [ ] CI/CD pipeline functional
- [ ] Monitoring dashboards configured
- [ ] Security documentation complete
- [ ] Contributing guidelines clear
- [ ] Release process automated
- [ ] Example configurations provided
- [ ] Troubleshooting guide comprehensive
- [ ] Open source checklist complete