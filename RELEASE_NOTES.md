# Release v1.0.0 - MultiCode AI Bot 🎉

## 🚀 First Stable Release!

**MultiCode AI Bot** je Telegram bot s podporou **8 různých AI asistentů** pro kódování!

### ✨ Co je nového

#### 🤖 8 AI Providerů v Jednom Botu!

**Premium Kvalita:**
- 🏆 **Claude** ($3-15/1M) - Nejvyšší kvalita, plná podpora nástrojů
- 🏆 **OpenAI GPT-4** ($10-60/1M) - Průmyslový standard, vision

**FREE Možnosti (6x!):**
- 🆓 **Gemini** - 1M token context, vision, zdarma!
- ⚡ **Groq** - Ultra-rychlá LPU inference, zdarma!
- 🏠 **Ollama** - 100% lokální, soukromí, zdarma!
- 🆓 **Blackbox** - Web API, code-focused, zdarma!
- 🆓 **Windsurf** - Codeium cascade, zdarma!

**Ultra-levná:**
- 💰 **DeepSeek** ($0.14-0.28/1M) - **10-20x levnější než GPT-4!**

#### 📦 Instalace Pro Všechny Platformy

| Metoda | Příkaz |
|--------|--------|
| 🚀 curl\|bash | `curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh \| bash` |
| 🐳 Docker | `docker-compose up -d` |
| 📦 PyPI | `pip install multicode-ai-bot` |
| 📱 Flatpak | `flatpak install multicode-bot` |
| 💿 AppImage | Stáhni a spusť |
| 📦 Snap | `snap install multicode-bot` |

#### 📚 Kompletní Dokumentace

- **README.md** - Hlavní dokumentace
- **MULTI_AI_STATUS.md** - Srovnání 8 providerů
- **INSTALLATION.md** - Všechny instalační metody
- **DOCKER.md** - Docker guide (česky!)
- **PUBLISHING.md** - Jak publikovat na PyPI

### 📊 Statistiky

- **Test Coverage**: 85%+ (896 testů)
- **Lines of Code**: ~15,000
- **Files**: 50+ nových souborů
- **Providers**: 8 (6 FREE!)
- **Installation Methods**: 6 různých způsobů

### 🎯 Quick Start

#### Nejrychlejší způsob:

```bash
curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh | bash
cd ~/.multicode-bot
nano .env  # Konfiguruj
./multicode-bot
```

#### Docker (doporučeno pro server):

```bash
git clone https://github.com/milhy545/claude-code-telegram.git
cd claude-code-telegram
cp .env.example .env
nano .env
docker-compose up -d
```

### 🔧 Minimální Konfigurace

```env
# .env
TELEGRAM_BOT_TOKEN=tvůj_token_zde
TELEGRAM_BOT_USERNAME=tvůj_bot_username
ALLOWED_USERS=tvoje_telegram_id
DEFAULT_AI_PROVIDER=blackbox  # nebo gemini pro FREE!
```

### 🎨 Features

- ✅ 8 AI providerů
- ✅ 6 FREE opcí
- ✅ Directory navigation
- ✅ File upload & archive extraction
- ✅ Git integrace
- ✅ Session export
- ✅ Quick actions
- ✅ Image analysis
- ✅ Cost tracking
- ✅ Multi-layer security

### 📖 Dokumentace

- [Installation Guide](INSTALLATION.md)
- [Docker Guide](DOCKER.md)
- [AI Providers Comparison](MULTI_AI_STATUS.md)
- [Publishing to PyPI](PUBLISHING.md)

### 🙏 Poděkování

- **Original Project**: [RichardAtCT/claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram)
- **Contributors**: @milhy545, @RichardAtCT

### 📝 Full Changelog

Viz [CHANGELOG.md](CHANGELOG.md)

---

**Enjoy coding with 8 AI assistants!** 🚀
