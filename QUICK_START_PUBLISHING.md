# 🚀 Rychlý start: Publikace na PyPI

Tento soubor ti ukáže, **jak publikovat MultiCode AI Bot na PyPI za 5 minut**.

## ✅ Co máš hotové

- ✅ 8 AI providerů implementováno
- ✅ Kompletní dokumentace (README.md, MULTI_AI_STATUS.md)
- ✅ PyPI metadata (pyproject.toml)
- ✅ Testy (85%+ coverage)
- ✅ Nový název: **MultiCode AI Bot**

## 🎯 Co teď?

### 1️⃣ Slouč do main (pokud ještě není)

```bash
# Přepni na main
git checkout main

# Stáhni nejnovější změny
git pull origin main

# Slouč feature branch
git merge claude/testing-mhzoyuh0tvdr14n6-014cSp82j6QTi5bqawybwh2C

# Pushni do main
git push origin main
```

### 2️⃣ Vytvoř účty

1. **PyPI account**: https://pypi.org/account/register/
2. **TestPyPI account**: https://test.pypi.org/account/register/

### 3️⃣ Vytvoř API tokeny

**PyPI:**
1. Jdi na https://pypi.org/manage/account/token/
2. Klikni "Add API token"
3. Name: `multicode-ai-bot`
4. Scope: "Entire account" (později můžeš změnit)
5. Zkopíruj token (začíná `pypi-...`)

**TestPyPI (stejný postup):**
1. https://test.pypi.org/manage/account/token/

### 4️⃣ Nastav své jméno v pyproject.toml

```bash
nano pyproject.toml
```

Změň:
```toml
authors = [
    "Tvoje Jméno <tvuj.email@example.com>",  # <--- ZMĚŇ TOHLE
    "Richard Atkinson <richardatk01@gmail.com> (original author)"
]
```

### 5️⃣ Build balíček

```bash
# Nainstaluj build nástroje
pip install --upgrade build twine

# Vyčisti staré buildy
rm -rf dist/ build/ *.egg-info

# Build!
python -m build
```

Měl bys vidět:
```
Successfully built multicode_ai_bot-1.0.0.tar.gz and multicode_ai_bot-1.0.0-py3-none-any.whl
```

### 6️⃣ Test na TestPyPI

```bash
# Upload na TestPyPI (TEST sandbox)
python -m twine upload --repository testpypi dist/*

# Zadej:
# Username: __token__
# Password: [tvůj TestPyPI token]
```

Zkontroluj: https://test.pypi.org/project/multicode-ai-bot/

### 7️⃣ Testuj instalaci

```bash
# Vytvoř testovací virtualenv
python -m venv test_env
source test_env/bin/activate

# Instaluj z TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple multicode-ai-bot

# Zkus spustit
multicode-bot --help
```

Funguje? Skvělé! Deaktivuj virtualenv:
```bash
deactivate
rm -rf test_env
```

### 8️⃣ Publikuj na PyPI! 🚀

```bash
# Upload na SKUTEČNÝ PyPI
python -m twine upload dist/*

# Zadej:
# Username: __token__
# Password: [tvůj PyPI token]
```

### 9️⃣ Ověř publikaci

1. Zkontroluj na PyPI: https://pypi.org/project/multicode-ai-bot/
2. Zkus instalaci:
   ```bash
   pip install multicode-ai-bot
   multicode-bot --version
   ```

## 🎉 HOTOVO!

Tvůj balíček je nyní veřejný na PyPI! Kdokoliv může:

```bash
pip install multicode-ai-bot
```

## 📝 Přidej badges do README

Přidej na začátek README.md:

```markdown
[![PyPI version](https://badge.fury.io/py/multicode-ai-bot.svg)](https://badge.fury.io/py/multicode-ai-bot)
[![Downloads](https://pepy.tech/badge/multicode-ai-bot)](https://pepy.tech/project/multicode-ai-bot)
```

## 🔄 Budoucí aktualizace

Když přidáš nové funkce:

```bash
# 1. Změň verzi v pyproject.toml
version = "1.1.0"

# 2. Commit změny
git add .
git commit -m "Release v1.1.0: Added XYZ feature"
git tag v1.1.0
git push origin main --tags

# 3. Build a publikuj
rm -rf dist/
python -m build
python -m twine upload dist/*
```

## 🆘 Pomoc

Pokud něco nejde, podívej se na **PUBLISHING.md** pro detailní troubleshooting!

## 💡 Tip: Automatizace

Později můžeš nastavit GitHub Actions pro automatickou publikaci.
Viz PUBLISHING.md sekce "Automatizace s GitHub Actions".

---

**Gratuluju k publikaci tvého prvního PyPI balíčku! 🎊**
