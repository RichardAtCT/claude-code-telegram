# Publishing MultiCode AI Bot to PyPI

Tento návod ti ukáže, jak publikovat **MultiCode AI Bot** jako PyPI balíček, aby ho mohli ostatní jednoduše instalovat pomocí `pip install multicode-ai-bot`.

## 🎯 Co potřebuješ

1. **PyPI účet**
   - Registruj se na https://pypi.org/account/register/
   - Ověř email

2. **TestPyPI účet** (pro testování)
   - Registruj se na https://test.pypi.org/account/register/
   - TestPyPI je sandbox pro testování před publikací

3. **API Token** (doporučeno místo hesla)
   - Jdi na https://pypi.org/manage/account/
   - Klikni "Add API token"
   - Zkopíruj token (začíná `pypi-...`)

## 📦 Krok 1: Příprava balíčku

### Aktualizuj autor info v `pyproject.toml`:

```toml
authors = [
    "Tvoje Jméno <tvuj.email@example.com>",
    "Richard Atkinson <richardatk01@gmail.com> (original author)"
]
```

### Zkontroluj verzi:

```toml
version = "1.0.0"  # První stabilní release!
```

### Ujisti se, že máš všechny soubory:

```bash
# Zkontroluj, že máš tyto soubory:
ls -la
# README.md ✓
# LICENSE ✓
# pyproject.toml ✓
# MULTI_AI_STATUS.md ✓
# src/ ✓
```

## 🏗️ Krok 2: Build balíčku

```bash
# Nainstaluj build nástroje
pip install --upgrade build twine

# Vyčisti staré buildy
rm -rf dist/ build/ *.egg-info

# Zbuilduj balíček
python -m build

# Měl by vytvořit:
# dist/multicode_ai_bot-1.0.0-py3-none-any.whl
# dist/multicode_ai_bot-1.0.0.tar.gz
```

## 🧪 Krok 3: Testování na TestPyPI

**DŮLEŽITÉ:** Vždy nejdřív testuj na TestPyPI!

```bash
# Upload na TestPyPI
python -m twine upload --repository testpypi dist/*

# Zadej credentials:
# Username: __token__
# Password: tvůj-test-pypi-token

# Test instalace z TestPyPI
pip install --index-url https://test.pypi.org/simple/ multicode-ai-bot

# Zkus spustit:
multicode-bot --help
```

## 🚀 Krok 4: Publikace na PyPI (production)

Když testování na TestPyPI fungovalo:

```bash
# Upload na skutečný PyPI
python -m twine upload dist/*

# Zadej credentials:
# Username: __token__
# Password: tvůj-pypi-token
```

🎉 **Hotovo!** Tvůj balíček je nyní na PyPI!

## 📥 Instalace uživateli

Teď může kdokoliv nainstalovat tvůj bot:

```bash
# Instalace z PyPI
pip install multicode-ai-bot

# Nebo s poetry
poetry add multicode-ai-bot

# Spuštění
multicode-bot
```

## 🔄 Aktualizace balíčku (nové verze)

Když děláš změny:

### 1. Aktualizuj verzi v `pyproject.toml`:

```toml
# Semantic versioning:
# 1.0.0 -> 1.0.1 (bugfix)
# 1.0.0 -> 1.1.0 (nová feature)
# 1.0.0 -> 2.0.0 (breaking change)

version = "1.1.0"  # Například
```

### 2. Vytvoř changelog:

Přidej do `CHANGELOG.md`:

```markdown
## [1.1.0] - 2025-11-15

### Added
- Nový AI provider XYZ
- Podpora pro ABC

### Fixed
- Opravena chyba v DEF
```

### 3. Commit a tag:

```bash
git add .
git commit -m "Release v1.1.0"
git tag v1.1.0
git push origin main --tags
```

### 4. Build a upload:

```bash
rm -rf dist/
python -m build
python -m twine upload dist/*
```

## 🔐 Bezpečnost API tokenů

### Nikdy necommituj tokeny do gitu!

**Správně:**

```bash
# Použij environment variable
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-...

# Pak upload bez zadávání hesla
python -m twine upload dist/*
```

**Nebo použij `.pypirc`:**

```bash
# ~/.pypirc (POZOR: nezahrnuj do gitu!)
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmcC...

[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBpLm9...
```

Pak:

```bash
chmod 600 ~/.pypirc  # Ochrana souboru
python -m twine upload dist/*  # Použije .pypirc automaticky
```

## 📊 Monitorování balíčku

### PyPI Dashboard:

- https://pypi.org/project/multicode-ai-bot/
- Vidíš download statistiky
- Můžeš mazat staré verze (ale to se nedoporučuje)

### Badges do README:

```markdown
[![PyPI version](https://badge.fury.io/py/multicode-ai-bot.svg)](https://badge.fury.io/py/multicode-ai-bot)
[![Downloads](https://pepy.tech/badge/multicode-ai-bot)](https://pepy.tech/project/multicode-ai-bot)
```

## 🐛 Řešení problémů

### Chyba: "File already exists"

```bash
# Nemůžeš nahrát stejnou verzi dvakrát
# Musíš zvýšit verzi v pyproject.toml
```

### Chyba: "Invalid distribution"

```bash
# Zkontroluj, že máš správnou strukturu:
twine check dist/*
```

### Chyba: "403 Forbidden"

```bash
# Špatný token nebo nemáš oprávnění
# Zkontroluj token na https://pypi.org/manage/account/token/
```

## 📝 Checklist před publikací

- [ ] Aktualizovaný README.md s multi-AI info
- [ ] Správná verze v pyproject.toml
- [ ] Autor info aktualizováno
- [ ] Všechny testy projdou (`make test`)
- [ ] Changelog aktualizován
- [ ] Otestováno na TestPyPI
- [ ] Git tag vytvořen
- [ ] Všechno commitnuto a pushnuto

## 🎓 Best Practices

1. **Vždy testuj na TestPyPI první**
2. **Používej semantic versioning** (1.0.0 → 1.0.1 → 1.1.0 → 2.0.0)
3. **Nikdy nemazej verze z PyPI** (lidi by to mohli používat)
4. **Udržuj CHANGELOG.md**
5. **Používej git tags** pro verze
6. **Testuj instalaci** před publikací

## 🔗 Užitečné odkazy

- PyPI: https://pypi.org/
- TestPyPI: https://test.pypi.org/
- Python Packaging Guide: https://packaging.python.org/
- Semantic Versioning: https://semver.org/
- Twine docs: https://twine.readthedocs.io/

## 💡 Tipy

### Automatizace s GitHub Actions:

Můžeš nastavit automatickou publikaci při vytvoření release:

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install build twine
      - run: python -m build
      - run: python -m twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
```

Pak přidáš `PYPI_API_TOKEN` do GitHub Secrets!

---

**Gratuluju!** 🎉 Teď máš vlastní PyPI balíček který můžou používat lidi po celém světě!
