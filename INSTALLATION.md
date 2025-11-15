# Installation Guide - MultiCode AI Bot

Všechny způsoby, jak nainstalovat **MultiCode AI Bot** na jakýkoliv systém!

## 🚀 Rychlá Instalace (curl | bash)

**Nejrychlejší způsob** - instalace jedním příkazem (jako Claude CLI):

```bash
curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh | bash
```

### S vlastní cestou:

```bash
curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh | bash -s -- --dir /custom/path
```

Po instalaci:
```bash
cd ~/.multicode-bot
nano .env  # Konfiguruj
./multicode-bot  # Spusť!
```

---

## 🐳 Docker (Doporučeno pro servery)

**Nejlepší pro:** Produkční servery, VPS, NAS

### Quick Start:

```bash
git clone https://github.com/milhy545/claude-code-telegram.git
cd claude-code-telegram

cp .env.example .env
nano .env  # Konfiguruj

docker-compose up -d
```

### S Ollama (lokální AI):

```yaml
# Odkomentuj v docker-compose.yml:
ollama:
  image: ollama/ollama:latest
  ...

# Pak:
docker-compose up -d
docker exec -it multicode-ollama ollama pull codellama
```

📖 **Detailní návod:** [DOCKER.md](DOCKER.md)

---

## 📦 PyPI (Python Package)

**Nejlepší pro:** Python vývojáře, virtualenv použití

```bash
# S pip
pip install multicode-ai-bot

# S poetry
poetry add multicode-ai-bot

# Spusť
multicode-bot
```

Po instalaci vytvoř `.env` a nakonfiguruj.

📖 **Publishing guide:** [PUBLISHING.md](PUBLISHING.md)

---

## 📱 Flatpak (Linux Desktop)

**Nejlepší pro:** Linux desktop uživatele, sandboxing

### Instalace z Flathub (až bude publikováno):

```bash
flatpak install flathub com.github.milhy545.MultiCodeBot
flatpak run com.github.milhy545.MultiCodeBot
```

### Build lokálně:

```bash
# Instaluj flatpak-builder
sudo apt install flatpak-builder

# Build
cd flatpak
flatpak-builder --user --install --force-clean build com.github.milhy545.MultiCodeBot.yml

# Run
flatpak run com.github.milhy545.MultiCodeBot
```

### Permissions:

```bash
# Přidej přístup k dalším složkám
flatpak override --user --filesystem=/path/to/projects com.github.milhy545.MultiCodeBot
```

---

## 📦 Snap (Ubuntu/Ubuntu-based)

**Nejlepší pro:** Ubuntu, Ubuntu-based distribuce

### Instalace ze Snap Store (až bude publikováno):

```bash
sudo snap install multicode-bot
multicode-bot
```

### Build lokálně:

```bash
cd snap
snapcraft

# Instaluj
sudo snap install multicode-bot_1.0.0_amd64.snap --dangerous

# Run
multicode-bot
```

### Permissions:

```bash
# Home access (už enabled v snapcraft.yaml)
snap connect multicode-bot:home
```

---

## 💿 AppImage (Univerzální Linux)

**Nejlepší pro:** Chceš jeden soubor bez instalace

### Download (až bude release):

```bash
wget https://github.com/milhy545/claude-code-telegram/releases/download/v1.0.0/MultiCode-AI-Bot-1.0.0-x86_64.AppImage
chmod +x MultiCode-AI-Bot-1.0.0-x86_64.AppImage
./MultiCode-AI-Bot-1.0.0-x86_64.AppImage
```

### Build lokálně:

```bash
cd appimage
./build-appimage.sh

# Run
./build/MultiCode-AI-Bot-1.0.0-x86_64.AppImage
```

### Integrace do systému (optional):

```bash
# Install AppImageLauncher
sudo apt install appimagelauncher

# Přesuň AppImage do ~/Applications
# AppImageLauncher automaticky vytvoří desktop entry
```

---

## 🛠️ Manuální Instalace (Ze source)

**Nejlepší pro:** Vývojáře, vlastní úpravy

### Požadavky:

- Python 3.10+
- Poetry (nebo pip)
- Git

### Instalace:

```bash
# Clone
git clone https://github.com/milhy545/claude-code-telegram.git
cd claude-code-telegram

# Instaluj Poetry (pokud nemáš)
curl -sSL https://install.python-poetry.org | python3 -

# Instaluj dependencies
poetry install

# Config
cp .env.example .env
nano .env

# Run
poetry run python -m src.main
```

### Development Mode:

```bash
# Instaluj dev dependencies
poetry install

# Run tests
poetry run pytest

# Run with hot reload
make run-debug
```

---

## 🍺 Homebrew (macOS)

**Až bude tap vytvořen:**

```bash
brew tap milhy545/multicode-bot
brew install multicode-bot
multicode-bot
```

---

## 🎯 Která Metoda Je Pro Mě?

| Použití | Metoda | Proč |
|---------|--------|------|
| **Server produkce** | 🐳 Docker | Izolace, auto-restart, snadné updates |
| **Vývoj/testování** | 🛠️ Manuální | Plná kontrola, debugging |
| **Linux desktop** | 📱 Flatpak | Sandboxing, auto-updates |
| **Ubuntu desktop** | 📦 Snap | Native Ubuntu integrace |
| **Jeden soubor** | 💿 AppImage | Portable, no install |
| **Python projekt** | 📦 PyPI | Integrace s existujícím projektem |
| **Rychlá instalace** | 🚀 curl\|bash | Jeden příkaz, vše nastaví |

---

## ⚙️ Post-Installation

### 1. Získej Telegram Bot Token:

```bash
# Message @BotFather on Telegram:
/newbot
# Follow prompts, save token
```

### 2. Najdi své Telegram ID:

```bash
# Message @userinfobot on Telegram
# Save your user ID
```

### 3. Konfiguruj .env:

**Minimální konfigurace:**

```bash
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_BOT_USERNAME=my_bot
ALLOWED_USERS=123456789
APPROVED_DIRECTORY=/path/to/projects

# Vyber AI providera
DEFAULT_AI_PROVIDER=blackbox  # FREE, instant!
```

**Nebo s API keys:**

```bash
DEFAULT_AI_PROVIDER=gemini
GEMINI_API_KEY=your_key  # FREE tier!
```

### 4. Spusť a testuj:

```bash
# V Telegramu napiš svému botovi:
/start
/help
```

---

## 🆘 Troubleshooting

### "Command not found"

```bash
# Přidej do PATH
export PATH="$HOME/.multicode-bot:$PATH"

# Nebo přidej do ~/.bashrc:
echo 'export PATH="$HOME/.multicode-bot:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### "Permission denied"

```bash
# Docker
sudo usermod -aG docker $USER
newgrp docker

# AppImage
chmod +x MultiCode-AI-Bot*.AppImage

# Install script
chmod +x install.sh
```

### "Python version too old"

```bash
# Ubuntu/Debian
sudo apt install python3.11

# macOS
brew install python@3.11

# Check version
python3 --version  # Should be 3.10+
```

### "Poetry not found"

```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

---

## 📝 Next Steps

Po instalaci:

1. **Konfigurace** - Nastav `.env` podle [.env.example](.env.example)
2. **AI Providers** - Přečti [MULTI_AI_STATUS.md](MULTI_AI_STATUS.md) pro všechny 8 providerů
3. **Docker** - Pro produkci viz [DOCKER.md](DOCKER.md)
4. **Publishing** - Publikuj na PyPI pomocí [PUBLISHING.md](PUBLISHING.md)

---

## 🌟 Features po instalaci

- 🤖 **8 AI Providerů** - Claude, Gemini, OpenAI, DeepSeek, Groq, Ollama, Blackbox, Windsurf
- 💰 **6 FREE Opcí** - Většina providerů má free tier
- 🏠 **Lokální AI** - Ollama pro 100% privacy
- ⚡ **Ultra-rychlé** - Groq LPU pro real-time
- 💸 **Ultra-levné** - DeepSeek za $0.14/1M tokens

---

**Enjoy coding with 8 AI assistants! 🚀**

Problémy? [Open an issue](https://github.com/milhy545/claude-code-telegram/issues)
