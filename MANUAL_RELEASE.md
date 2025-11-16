# Manuální Release Guide - v1.0.0

Tento soubor obsahuje přesné kroky, jak dokončit release **MultiCode AI Bot v1.0.0**.

## ✅ Co je hotové

- ✅ Git tag v1.0.0 vytvořen lokálně
- ✅ PyPI package zbuildován (`dist/`)
- ✅ CHANGELOG.md vytvořen
- ✅ RELEASE_NOTES.md připraven
- ✅ Všechna dokumentace aktualizovaná

## 📦 Co máš v `dist/`:

```
dist/
├── multicode_ai_bot-1.0.0-py3-none-any.whl  (160KB)
└── multicode_ai_bot-1.0.0.tar.gz            (126KB)
```

## 🚀 Krok 1: Push Git Tag

```bash
# Najdi tag (už je vytvořený):
git tag -l

# Push tag na GitHub:
git push origin v1.0.0

# Pokud to nefunguje (403 error), udělej to na GitHubu ručně:
# 1. Jdi na: https://github.com/milhy545/claude-code-telegram/releases/new
# 2. Tag: v1.0.0
# 3. Target: vyberte svůj branch (claude/testing-...)
# 4. Release title: "v1.0.0 - MultiCode AI Bot with 8 AI Providers"
# 5. Description: zkopíruj z RELEASE_NOTES.md
```

## 📦 Krok 2: Publikuj na PyPI

### 2a. Test na TestPyPI (doporučeno první):

```bash
# Upload na TestPyPI
python -m twine upload --repository testpypi dist/*

# Zadej credentials:
# Username: __token__
# Password: [tvůj TestPyPI token z https://test.pypi.org/manage/account/token/]

# Test instalace:
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ multicode-ai-bot
```

### 2b. Publikuj na PyPI (production):

```bash
# Upload na PyPI
python -m twine upload dist/*

# Zadej credentials:
# Username: __token__
# Password: [tvůj PyPI token z https://pypi.org/manage/account/token/]
```

**Vytvoř PyPI tokeny:**
1. PyPI: https://pypi.org/manage/account/token/
2. TestPyPI: https://test.pypi.org/manage/account/token/

## 🎉 Krok 3: GitHub Release

### 3a. Vytvoř Release na GitHubu:

1. Jdi na: https://github.com/milhy545/claude-code-telegram/releases/new
2. **Tag**: v1.0.0
3. **Release title**: `v1.0.0 - MultiCode AI Bot with 8 AI Providers 🎉`
4. **Description**: Zkopíruj obsah z `RELEASE_NOTES.md`

### 3b. Nahraj Assets:

Do release přidej tyto soubory:

**Z `dist/`:**
- ✅ `multicode_ai_bot-1.0.0-py3-none-any.whl`
- ✅ `multicode_ai_bot-1.0.0.tar.gz`

**Dokumentace (optional):**
- ✅ `CHANGELOG.md`
- ✅ `INSTALLATION.md`
- ✅ `DOCKER.md`

### 3c. Vytvoř Instalační Script Asset:

```bash
# Vytvoř tarball s install scriptem
tar -czf multicode-bot-install-1.0.0.tar.gz install.sh INSTALLATION.md

# Nahraj do release assets
```

## 🐳 Krok 4: Publikuj Docker Image

### 4a. Build a tag:

```bash
# Build
docker build -t multicode-ai-bot:1.0.0 .
docker build -t multicode-ai-bot:latest .

# Tag pro Docker Hub (nahraď 'yourusername')
docker tag multicode-ai-bot:1.0.0 yourusername/multicode-ai-bot:1.0.0
docker tag multicode-ai-bot:latest yourusername/multicode-ai-bot:latest
```

### 4b. Push na Docker Hub:

```bash
# Login
docker login

# Push
docker push yourusername/multicode-ai-bot:1.0.0
docker push yourusername/multicode-ai-bot:latest
```

**Update v dokumentaci:**
Pak aktualizuj `DOCKER.md` a `INSTALLATION.md` s:
```bash
docker pull yourusername/multicode-ai-bot:latest
```

## 📱 Krok 5: Publikuj na Flathub (optional)

### 5a. Fork Flathub repo:

```bash
# Fork: https://github.com/flathub/flathub
# Clone tvůj fork
git clone https://github.com/yourusername/flathub.git
cd flathub
```

### 5b. Přidej manifest:

```bash
# Vytvoř branch
git checkout -b com.github.milhy545.MultiCodeBot

# Zkopíruj manifest
cp /path/to/claude-code-telegram/flatpak/com.github.milhy545.MultiCodeBot.yml .
cp /path/to/claude-code-telegram/flatpak/*.desktop .
cp /path/to/claude-code-telegram/flatpak/*.xml .
cp /path/to/claude-code-telegram/flatpak/*.svg .

# Commit
git add .
git commit -m "Add MultiCode AI Bot"
git push origin com.github.milhy545.MultiCodeBot
```

### 5c. Vytvoř PR na Flathub:

1. Jdi na: https://github.com/flathub/flathub/compare
2. Compare across forks
3. Vytvoř PR s tvým branchem

## 📦 Krok 6: Publikuj na Snap Store (optional)

### 6a. Build Snap:

```bash
cd snap
snapcraft

# Output: multicode-bot_1.0.0_amd64.snap
```

### 6b. Upload:

```bash
# Login
snapcraft login

# Upload
snapcraft upload multicode-bot_1.0.0_amd64.snap --release stable

# Set jako stable
snapcraft release multicode-bot 1.0.0 stable
```

**Registrace:**
1. Registruj jméno: https://snapcraft.io/register
2. Přihlas se: `snapcraft login`

## 💿 Krok 7: Vytvoř AppImage (optional)

### 7a. Build:

```bash
cd appimage
./build-appimage.sh

# Output: build/MultiCode-AI-Bot-1.0.0-x86_64.AppImage
```

### 7b. Nahraj do GitHub Release:

1. Jdi na tvůj release na GitHubu
2. Edit release
3. Nahraj `MultiCode-AI-Bot-1.0.0-x86_64.AppImage`

## ✅ Checklist

Zkontroluj, že máš hotové:

- [ ] Git tag v1.0.0 pushnutý na GitHub
- [ ] GitHub Release vytvořený s RELEASE_NOTES
- [ ] PyPI package publikovaný
- [ ] Docker image na Docker Hub
- [ ] README.md má odkazy na install script
- [ ] CHANGELOG.md commitnutý
- [ ] Assets nahrané do GitHub Release:
  - [ ] .whl soubor
  - [ ] .tar.gz soubor
  - [ ] AppImage (optional)
- [ ] Flathub PR vytvořený (optional)
- [ ] Snap Store upload (optional)

## 📢 Krok 8: Oznámení

Po dokončení release:

### Update README.md badges:

```markdown
[![PyPI version](https://badge.fury.io/py/multicode-ai-bot.svg)](https://badge.fury.io/py/multicode-ai-bot)
[![Docker Pulls](https://img.shields.io/docker/pulls/yourusername/multicode-ai-bot.svg)](https://hub.docker.com/r/yourusername/multicode-ai-bot)
[![Downloads](https://pepy.tech/badge/multicode-ai-bot)](https://pepy.tech/project/multicode-ai-bot)
```

### Oznámení:

1. **GitHub Discussions**: Ohlásit release
2. **Reddit**: r/Python, r/selfhosted
3. **Twitter/X**: Tweet o release
4. **Dev.to**: Článek o multi-AI architektuře

### Template pro oznámení:

```
🎉 MultiCode AI Bot v1.0.0 Released!

Telegram bot s podporou 8 AI providerů pro kódování:
- Claude, Gemini, OpenAI, DeepSeek, Groq, Ollama, Blackbox, Windsurf
- 6 FREE opcí
- Multi-platform instalace (Docker, PyPI, Flatpak, Snap, AppImage)
- 85%+ test coverage

Install:
curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh | bash

GitHub: https://github.com/milhy545/claude-code-telegram
PyPI: https://pypi.org/project/multicode-ai-bot/
```

## 🆘 Troubleshooting

### "403 Forbidden" při git push tag

**Řešení**: Vytvoř tag manuálně na GitHubu:
1. Releases → New Release
2. Create new tag: v1.0.0
3. Target: tvůj branch

### "Package already exists" na PyPI

**Řešení**: Nemůžeš nahrát stejnou verzi dvakrát. Zvyš verzi v `pyproject.toml`:
```toml
version = "1.0.1"
```

### Docker build fails

**Řešení**: Zkontroluj, že máš všechny soubory:
```bash
docker build --no-cache -t multicode-ai-bot:1.0.0 .
```

## 📝 Po Release

1. **Merge do main**:
   ```bash
   git checkout main
   git merge claude/testing-mhzoyuh0tvdr14n6-014cSp82j6QTi5bqawybwh2C
   git push origin main
   ```

2. **Update dokumentace**:
   - Přidej PyPI install link do README
   - Přidej Docker Hub link

3. **Začni pracovat na v1.1.0**:
   - Vytvoř nový branch
   - Aktualizuj version v pyproject.toml

---

**Gratuluju k release! 🎊**

Máš nějaké otázky? Open an issue!
