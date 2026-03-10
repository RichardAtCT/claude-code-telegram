# RPG Gamification System — Design Spec

**Date:** 2026-03-10
**Project:** claude-code-telegram
**Branch:** feat/rpg-gamification
**Mode:** Solo player, full automation, Mini App dashboard

## Overview

Add an RPG gamification layer to the Telegram bot that tracks developer activity, awards XP, levels up stats, and unlocks achievements. Visualized through a Telegram Mini App with an RPG-style dashboard.

## Architecture

```
Claude Code (hooks in dotfiles)
  │
  ├─ PostToolUse: git commit → event
  ├─ QA-plugin: results → event
  │
  ▼
Telegram Bot (existing)
  │
  ├─ GamificationService (new)
  │   ├─ XP Engine
  │   ├─ Stat Calculator (STR/INT/DEX/CON/WIS)
  │   ├─ Achievement Checker
  │   └─ Streak Tracker
  │
  ├─ Event Bus (existing) + new subscriptions
  ├─ SQLite (existing) + new tables
  ├─ Bot commands: /stats, /achievements
  │
  └─ Mini App (new — React + Tailwind)
      ├─ RPG Dashboard
      ├─ Achievement Gallery
      └─ Activity Timeline
```

## Data Model

### Table: `rpg_profile`

One row per user.

| Column | Type | Description |
|--------|------|-------------|
| user_id | INTEGER PK FK → users | Telegram user ID |
| level | INTEGER DEFAULT 1 | Current level |
| total_xp | INTEGER DEFAULT 0 | Cumulative XP |
| str_points | INTEGER DEFAULT 0 | Backend, shell, infra |
| int_points | INTEGER DEFAULT 0 | Architecture, refactoring |
| dex_points | INTEGER DEFAULT 0 | Frontend, Swift, UI |
| con_points | INTEGER DEFAULT 0 | Tests, QA, security |
| wis_points | INTEGER DEFAULT 0 | Docs, skills, planning |
| current_streak | INTEGER DEFAULT 0 | Active streak days |
| longest_streak | INTEGER DEFAULT 0 | All-time best streak |
| last_activity_date | TEXT | ISO date for streak calc |
| title | TEXT DEFAULT 'Junior Developer' | Current title |

### Table: `xp_log`

Every XP award is logged.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AI | |
| user_id | INTEGER FK | |
| xp_amount | INTEGER | XP awarded |
| stat_type | TEXT NULL | 'str'\|'int'\|'dex'\|'con'\|'wis'\|null |
| source | TEXT | 'commit'\|'test_run'\|'qa_pass'\|'tool_usage'\|'streak_bonus' |
| details | TEXT | JSON context |
| created_at | TIMESTAMP | |

### Table: `achievement_definitions`

Catalog of all achievements (managed via DB).

| Column | Type | Description |
|--------|------|-------------|
| achievement_id | TEXT PK | e.g. 'first_blood' |
| name | TEXT | Display name |
| description | TEXT | How to unlock |
| icon | TEXT | Emoji or URL |
| category | TEXT | 'coding'\|'testing'\|'streak'\|'quality' |
| condition_type | TEXT | 'counter'\|'streak'\|'threshold'\|'unique' |
| condition_key | TEXT | 'commit_count'\|'streak_days'\|'qa_clean' |
| condition_value | INTEGER | Threshold to unlock |
| xp_reward | INTEGER | XP granted on unlock |
| rarity | TEXT | 'common'\|'rare'\|'epic'\|'legendary' |
| is_active | BOOLEAN DEFAULT TRUE | Soft-disable |

### Table: `achievements`

User's unlocked achievements.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AI | |
| user_id | INTEGER FK | |
| achievement_id | TEXT FK → achievement_definitions | |
| unlocked_at | TIMESTAMP | |
| data | TEXT | JSON context of unlock |

## XP Engine

### Sources and Stat Mapping

| Trigger | XP | Stat | Detection |
|---------|-----|------|-----------|
| Commit (normal) | +10 | by files | tool_usage: Bash + git commit |
| Commit (>3 files) | +25 | by files | Parse file count from context |
| feat: commit | +30 | by files | Commit message prefix |
| fix: commit | +20 | by files | Commit message prefix |
| Test run (bats/pytest) | +10 | CON | tool_usage: Bash + pytest/bats |
| QA pass (no CRITICAL) | +15 | CON | QA orchestrator result |
| Read/Grep/Glob usage | +2 | INT | tool_usage tracking |
| Edit/Write usage | +3 | by files | tool_usage tracking |
| Daily streak bonus | +5 x days | WIS | Scheduler cron midnight |

### File Extension → Stat Mapping

| Extensions | Stat |
|------------|------|
| .py, .sh, .sql, .toml, Dockerfile | STR |
| .tsx, .jsx, .css, .html, .svelte | DEX |
| .swift, .xib, .storyboard | DEX |
| .test.*, .spec.*, .bats, test_*.py | CON |
| .md, CLAUDE.md, SKILL.md | WIS |
| refactor: commits | INT |

### Level Formula

```
XP for level N = floor(100 * N^1.5)

Lv.1  →      0 XP
Lv.2  →    100 XP
Lv.5  →  1,118 XP
Lv.10 →  3,162 XP
Lv.20 →  8,944 XP
Lv.50 → 35,355 XP
```

### Titles

| Level | Title |
|-------|-------|
| 1-4 | Junior Developer |
| 5-9 | Developer |
| 10-14 | Senior Developer |
| 15-19 | Staff Engineer |
| 20-29 | Principal Engineer |
| 30-39 | Distinguished Engineer |
| 40-49 | Fellow |
| 50+ | Legendary Architect |

## Achievement System

### Starter Achievements (seed data)

**Common:**
- `first_blood` — First Blood — 1 commit — 10 XP
- `toolbox` — Toolbox — 5 different tools used — 10 XP
- `early_bird` — Early Bird — Activity before 7:00 — 10 XP
- `night_owl` — Night Owl — Activity after 23:00 — 10 XP

**Rare:**
- `test_ninja` — Test Ninja — 50 test runs — 50 XP
- `streak_week` — Week Warrior — 7 day streak — 30 XP
- `polyglot` — Polyglot — Commits in 3+ languages — 40 XP
- `bug_hunter` — Bug Hunter — 10 fix: commits — 40 XP
- `architect` — Architect — 10 refactor: commits — 40 XP

**Epic:**
- `clean_sweep` — Clean Sweep — QA full with no findings — 100 XP
- `streak_month` — Monthly Devotion — 30 day streak — 100 XP
- `centurion` — Centurion — 100 commits — 100 XP
- `stat_master` — Stat Master — Any stat >= 100 — 100 XP

**Legendary:**
- `streak_100` — Unstoppable — 100 day streak — 300 XP
- `max_level` — Legendary Architect — Reach Lv.50 — 500 XP
- `pentagram` — Pentagram — All 5 stats >= 50 — 300 XP
- `thousand` — Thousand Commits — 1000 commits — 500 XP

### Achievement Checker Logic

```python
async def check_achievements(self, user_id: int):
    unlocked = await self.repo.get_user_achievements(user_id)
    unlocked_ids = {a.achievement_id for a in unlocked}
    definitions = await self.repo.get_active_definitions()
    profile = await self.repo.get_profile(user_id)

    for defn in definitions:
        if defn.achievement_id in unlocked_ids:
            continue
        value = self._resolve_counter(profile, defn.condition_key)
        if defn.condition_type == 'counter' and value >= defn.condition_value:
            await self._unlock(user_id, defn)
        elif defn.condition_type == 'streak' and profile.current_streak >= defn.condition_value:
            await self._unlock(user_id, defn)
        elif defn.condition_type == 'threshold' and value >= defn.condition_value:
            await self._unlock(user_id, defn)
```

## Mini App

### Stack

- React 19 + TypeScript
- Tailwind CSS v4
- Vite
- @twa-dev/sdk (Telegram Web App SDK)

### Directory Structure

```
mini-app/
  package.json
  vite.config.ts
  src/
    App.tsx
    api/
      client.ts
    pages/
      Dashboard.tsx
      Achievements.tsx
      Timeline.tsx
    components/
      StatBar.tsx
      XpProgressBar.tsx
      AvatarCard.tsx
      AchievementCard.tsx
      StreakBadge.tsx
    hooks/
      useTelegram.ts
      useProfile.ts
    styles/
      rarity.ts
```

### API Endpoints (FastAPI)

```
GET  /api/rpg/profile          — rpg_profile + level + title
GET  /api/rpg/achievements     — unlocked + all definitions
GET  /api/rpg/timeline?limit=  — xp_log recent entries
GET  /api/rpg/stats/chart      — radar chart data (5 stats)
```

Auth via Telegram initData validation.

### Dashboard Layout

```
┌─────────────────────────────┐
│     [Avatar/Icon]           │
│   wooslash · Lv.14          │
│   Staff Engineer            │
│  ████████████░░░ 2340/3000  │
├─────────────────────────────┤
│  STR ████████░░  18         │
│  INT ██████░░░░  15         │
│  DEX █████░░░░░  12         │
│  CON ███████░░░  16         │
│  WIS ████░░░░░░   9         │
├─────────────────────────────┤
│  Streak: 7 days             │
│  Today: +45 XP              │
├─────────────────────────────┤
│  Recent Achievements        │
│  [Test Ninja]  [Polyglot]   │
│  [All Achievements →]       │
└─────────────────────────────┘
```

### Achievement Gallery

- Grid of cards, unlocked = colored, locked = greyed silhouette
- Filter by category and rarity
- Rarity styles:
  - Common — gray border
  - Rare — blue border + subtle glow
  - Epic — purple border + glow
  - Legendary — gold border + shimmer animation

### Telegram Integration

- Theme adapts via `Telegram.WebApp.themeParams`
- Haptic feedback on level up / achievement unlock
- Bot inline button "Open Dashboard" → Mini App URL

## Bot Integration

### New Module

```
src/gamification/
  service.py       — GamificationService
  models.py        — RpgProfile, XpLog, Achievement, AchievementDefinition
  repository.py    — GamificationRepository
  constants.py     — file mappings, XP table, titles
  streak.py        — StreakTracker
```

### Event Bus Subscriptions

```python
event_bus.subscribe("message_saved", gamification.on_message)
event_bus.subscribe("tool_usage_saved", gamification.on_tool_usage)
event_bus.subscribe("session_ended", gamification.on_session_end)
```

Requires adding `event_bus.publish()` after `ToolUsageRepository.save_tool_usage()` — currently writes to DB without publishing.

### New Event Types

```python
XpGainedEvent(user_id, xp_amount, stat_type, source, new_total_xp)
LevelUpEvent(user_id, new_level, title, previous_level)
AchievementUnlockedEvent(user_id, achievement_id, name, rarity, xp_reward)
```

### Notifications

- LevelUpEvent → "Level Up! Lv.14 → Lv.15 Staff Engineer"
- AchievementUnlockedEvent → "Achievement Unlocked! [Test Ninja] (Rare) +50 XP"

### Bot Commands

| Command | Action |
|---------|--------|
| /stats | Text RPG card + inline button "Open Dashboard" |
| /achievements | Top-5 recent + counter + "All Achievements" button |

### Streak Scheduler

```python
scheduler.add_job("streak_check", "0 0 * * *", handler=gamification.check_daily_streaks)
```

### DB Migration

`005_gamification.sql` — creates 4 tables + seeds achievement_definitions.

### Feature Flag

```env
ENABLE_GAMIFICATION=true
```

If false, GamificationService is not initialized, commands not registered, Mini App not served.

## Serving

- Dev: Vite dev server (localhost:5173), proxied via FastAPI
- Prod: `vite build` → static files served by FastAPI at `/mini-app/`
- Bot registers Web App URL pointing to the FastAPI endpoint
