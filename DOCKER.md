# Docker Installation Guide

Tento soubor obsahuje všechny způsoby, jak spustit **MultiCode AI Bot** v Dockeru.

## 🐳 Rychlý Start (Doporučeno)

### 1. Příprava

```bash
# Naklonuj repo
git clone https://github.com/milhy545/claude-code-telegram.git
cd claude-code-telegram

# Zkopíruj .env
cp .env.example .env
```

### 2. Konfiguruj .env

Minimálně potřebuješ:

```bash
# Edituj .env
nano .env

# Nastav:
TELEGRAM_BOT_TOKEN=tvůj_bot_token
TELEGRAM_BOT_USERNAME=tvůj_bot_username
ALLOWED_USERS=tvoje_telegram_id

# Vyber AI providera (některý z těchto):
DEFAULT_AI_PROVIDER=blackbox  # FREE, instant
# nebo
DEFAULT_AI_PROVIDER=gemini
GEMINI_API_KEY=tvůj_klíč  # FREE tier
```

### 3. Nastav projekty

```bash
# Vytvoř .env proměnnou pro cestu k projektům
echo "PROJECTS_DIR=/path/to/your/projects" >> .env
```

### 4. Spusť!

```bash
# Build a start
docker-compose up -d

# Zkontroluj logy
docker-compose logs -f

# Zastaví
docker-compose down
```

## 📦 Způsoby instalace

### A) Docker Compose (Doporučeno)

**Pro:** Nejjednodušší, persistent data, auto-restart

```bash
docker-compose up -d
```

Config v `docker-compose.yml`.

### B) Docker Run (Ruční)

```bash
# Build image
docker build -t multicode-ai-bot .

# Run
docker run -d \
  --name multicode-bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v /path/to/projects:/projects \
  multicode-ai-bot
```

### C) Docker Hub (Až bude publikováno)

```bash
# Pull z Docker Hub
docker pull yourusername/multicode-ai-bot:latest

# Run
docker run -d \
  --name multicode-bot \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v /path/to/projects:/projects \
  yourusername/multicode-ai-bot:latest
```

## 🔧 Konfigurace

### Environment Variables

Všechny proměnné z `.env` fungují. Nejdůležitější:

```bash
# Bot credentials
TELEGRAM_BOT_TOKEN=Required
TELEGRAM_BOT_USERNAME=Required
ALLOWED_USERS=Required

# AI Providers (vyber alespoň jeden)
DEFAULT_AI_PROVIDER=claude|gemini|openai|deepseek|groq|ollama|blackbox|windsurf

# API Keys (podle zvoleného providera)
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
GROQ_API_KEY=
CODEIUM_API_KEY=

# Ollama (pokud chceš lokální modely)
OLLAMA_HOST=http://ollama:11434  # v docker-compose
```

### Volumes

```yaml
volumes:
  - ./data:/app/data              # Database (DŮLEŽITÉ - persistentní!)
  - /path/to/projects:/projects   # Tvoje projekty
  - ./.env:/app/.env:ro           # Config (optional)
```

### Resource Limits

Defaultní limity v `docker-compose.yml`:

```yaml
limits:
  cpus: '2.0'
  memory: 2G
reservations:
  cpus: '0.5'
  memory: 512M
```

Uprav podle svého serveru!

## 🚀 Docker s Ollama (Lokální AI)

Pokud chceš 100% FREE lokální AI:

### 1. Odkomentuj Ollama v docker-compose.yml:

```yaml
services:
  # ... multicode-bot ...

  ollama:
    image: ollama/ollama:latest
    container_name: multicode-ollama
    restart: unless-stopped
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "11434:11434"

volumes:
  ollama-data:
```

### 2. Nastav .env:

```bash
DEFAULT_AI_PROVIDER=ollama
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=codellama
```

### 3. Spusť a stáhni model:

```bash
docker-compose up -d

# Stáhni CodeLlama model
docker exec -it multicode-ollama ollama pull codellama

# Nebo jiný model:
# docker exec -it multicode-ollama ollama pull llama2
# docker exec -it multicode-ollama ollama pull mistral
```

## 📊 Monitoring

### Logy

```bash
# Sleduj logy
docker-compose logs -f

# Pouze bot logy
docker-compose logs -f multicode-bot

# Posledních 100 řádků
docker-compose logs --tail=100 multicode-bot
```

### Status

```bash
# Zkontroluj běžící containery
docker-compose ps

# Resource usage
docker stats multicode-bot
```

### Health Check

```bash
# Manuální health check
docker exec multicode-bot python -c "import sqlite3; sqlite3.connect('/app/data/bot.db').close(); print('OK')"
```

## 🔄 Updates

### Aktualizace na novou verzi:

```bash
# Pull nejnovější kód
git pull

# Rebuild a restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Backup dat:

```bash
# Backup database
cp data/bot.db data/bot.db.backup

# Nebo kompletní backup
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

## 🐛 Troubleshooting

### Bot se nespustí

```bash
# Zkontroluj logy
docker-compose logs multicode-bot

# Zkontroluj .env
docker exec multicode-bot cat /app/.env

# Restart
docker-compose restart multicode-bot
```

### Permission errors

```bash
# Fix permissions na data directory
sudo chown -R 1000:1000 data/
```

### Database locked

```bash
# Zastaví všechny instance
docker-compose down

# Smaž lock file
rm -f data/bot.db-wal data/bot.db-shm

# Start znovu
docker-compose up -d
```

### Ollama nedostupný

```bash
# Zkontroluj, že běží
docker ps | grep ollama

# Test connection z botu
docker exec multicode-bot curl http://ollama:11434/api/tags
```

## 🔐 Produkční Deployment

### 1. Security

```bash
# Použij secrets místo .env (Docker Swarm/Kubernetes)
# Nebo minimálně:
chmod 600 .env
```

### 2. Reverse Proxy (Pokud chceš webhook)

```nginx
# nginx config
location /webhook {
    proxy_pass http://localhost:8080/webhook;
    proxy_set_header Host $host;
}
```

### 3. Auto-restart s systemd

```bash
# Vytvoř /etc/systemd/system/multicode-bot.service
[Unit]
Description=MultiCode AI Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/path/to/claude-code-telegram
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable multicode-bot
sudo systemctl start multicode-bot
```

## 📈 Performance Tuning

### Pro větší servery:

```yaml
# docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 4G
```

### Pro malé servery (VPS):

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1G
    reservations:
      cpus: '0.25'
      memory: 256M
```

## 📦 Multi-stage Build (Menší image)

Pokud chceš menší Docker image, viz `Dockerfile.alpine`.

---

**Otázky? Issues: https://github.com/milhy545/claude-code-telegram/issues**
