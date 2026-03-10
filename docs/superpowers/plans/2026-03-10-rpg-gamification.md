# RPG Gamification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RPG gamification to claude-code-telegram — XP engine, 5 stats, achievements, streaks, and React Mini App dashboard.

**Architecture:** Event-driven gamification service subscribing to existing Event Bus. New SQLite tables for RPG data. React + Tailwind Mini App served by FastAPI. Feature-flagged via ENABLE_GAMIFICATION.

**Tech Stack:** Python 3.11+, aiosqlite, FastAPI, React 19, TypeScript, Tailwind CSS v4, Vite, @twa-dev/sdk

**Spec:** `docs/superpowers/specs/2026-03-10-rpg-gamification-design.md`

---

## File Structure

### New files

```
src/gamification/
  __init__.py                  # Module init
  models.py                    # RpgProfile, XpLogEntry, AchievementDefinition, Achievement
  repository.py                # GamificationRepository (CRUD)
  constants.py                 # File→stat mapping, XP amounts, level formula, titles
  streak.py                    # StreakTracker
  service.py                   # GamificationService (XP engine + achievement checker)

tests/gamification/
  __init__.py
  test_models.py
  test_repository.py
  test_constants.py
  test_streak.py
  test_service.py

mini-app/
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx
    App.tsx
    api/client.ts
    pages/Dashboard.tsx
    pages/Achievements.tsx
    pages/Timeline.tsx
    components/AvatarCard.tsx
    components/XpProgressBar.tsx
    components/StatBar.tsx
    components/AchievementCard.tsx
    components/StreakBadge.tsx
    hooks/useTelegram.ts
    hooks/useProfile.ts
    styles/rarity.ts
```

### Modified files

```
src/storage/database.py        # Add migration 5 (gamification tables)
src/events/types.py            # Add XpGainedEvent, LevelUpEvent, AchievementUnlockedEvent, ToolUsageSavedEvent
src/storage/facade.py          # Publish ToolUsageSavedEvent after saving tool usage
src/config/settings.py         # Add ENABLE_GAMIFICATION flag
src/config/features.py         # Add gamification_enabled property
src/main.py                    # Wire GamificationService, subscribe events, add streak cron
src/bot/handlers/command.py    # Add /stats and /achievements commands
src/bot/orchestrator.py        # Register new commands
src/api/server.py              # Add /api/rpg/* endpoints
```

---

## Chunk 1: Backend Core (Tasks 1-6)

### Task 1: DB Migration

**Files:**
- Modify: `src/storage/database.py` (add migration 5 after line 312)

- [ ] **Step 1: Add migration 5 to _get_migrations()**

In `src/storage/database.py`, add a new tuple `(5, ...)` to the list returned by `_get_migrations()`, before the closing `]` at line 313:

```python
            (
                5,
                """
                -- RPG gamification tables
                CREATE TABLE IF NOT EXISTS rpg_profile (
                    user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
                    level INTEGER NOT NULL DEFAULT 1,
                    total_xp INTEGER NOT NULL DEFAULT 0,
                    str_points INTEGER NOT NULL DEFAULT 0,
                    int_points INTEGER NOT NULL DEFAULT 0,
                    dex_points INTEGER NOT NULL DEFAULT 0,
                    con_points INTEGER NOT NULL DEFAULT 0,
                    wis_points INTEGER NOT NULL DEFAULT 0,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    longest_streak INTEGER NOT NULL DEFAULT 0,
                    last_activity_date TEXT,
                    title TEXT NOT NULL DEFAULT 'Junior Developer'
                );

                CREATE TABLE IF NOT EXISTS xp_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    xp_amount INTEGER NOT NULL,
                    stat_type TEXT,
                    source TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_xp_log_user
                    ON xp_log(user_id, created_at);

                CREATE TABLE IF NOT EXISTS achievement_definitions (
                    achievement_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    icon TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'coding',
                    condition_type TEXT NOT NULL DEFAULT 'counter',
                    condition_key TEXT NOT NULL,
                    condition_value INTEGER NOT NULL DEFAULT 1,
                    xp_reward INTEGER NOT NULL DEFAULT 10,
                    rarity TEXT NOT NULL DEFAULT 'common',
                    is_active BOOLEAN NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    achievement_id TEXT NOT NULL REFERENCES achievement_definitions(achievement_id),
                    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data TEXT,
                    UNIQUE(user_id, achievement_id)
                );
                CREATE INDEX IF NOT EXISTS idx_achievements_user
                    ON achievements(user_id);

                -- Seed starter achievements
                INSERT OR IGNORE INTO achievement_definitions
                    (achievement_id, name, description, icon, category, condition_type, condition_key, condition_value, xp_reward, rarity)
                VALUES
                    ('first_blood', 'First Blood', 'Make your first commit', '', 'coding', 'counter', 'commit_count', 1, 10, 'common'),
                    ('toolbox', 'Toolbox', 'Use 5 different tools', '', 'coding', 'counter', 'unique_tools', 5, 10, 'common'),
                    ('early_bird', 'Early Bird', 'Activity before 7:00', '', 'coding', 'unique', 'early_activity', 1, 10, 'common'),
                    ('night_owl', 'Night Owl', 'Activity after 23:00', '', 'coding', 'unique', 'late_activity', 1, 10, 'common'),
                    ('test_ninja', 'Test Ninja', '50 test runs', '', 'testing', 'counter', 'test_runs', 50, 50, 'rare'),
                    ('streak_week', 'Week Warrior', '7 day streak', '', 'streak', 'streak', 'streak_days', 7, 30, 'rare'),
                    ('polyglot', 'Polyglot', 'Commits in 3+ languages', '', 'coding', 'counter', 'languages_used', 3, 40, 'rare'),
                    ('bug_hunter', 'Bug Hunter', '10 fix: commits', '', 'coding', 'counter', 'fix_commits', 10, 40, 'rare'),
                    ('architect', 'Architect', '10 refactor: commits', '', 'coding', 'counter', 'refactor_commits', 10, 40, 'rare'),
                    ('clean_sweep', 'Clean Sweep', 'QA full with no findings', '', 'quality', 'counter', 'qa_clean_runs', 1, 100, 'epic'),
                    ('streak_month', 'Monthly Devotion', '30 day streak', '', 'streak', 'streak', 'streak_days', 30, 100, 'epic'),
                    ('centurion', 'Centurion', '100 commits', '', 'coding', 'counter', 'commit_count', 100, 100, 'epic'),
                    ('stat_master', 'Stat Master', 'Any stat reaches 100', '', 'coding', 'threshold', 'max_stat', 100, 100, 'epic'),
                    ('streak_100', 'Unstoppable', '100 day streak', '', 'streak', 'streak', 'streak_days', 100, 300, 'legendary'),
                    ('max_level', 'Legendary Architect', 'Reach level 50', '', 'coding', 'threshold', 'level', 50, 500, 'legendary'),
                    ('pentagram', 'Pentagram', 'All 5 stats reach 50', '', 'coding', 'threshold', 'min_stat', 50, 300, 'legendary'),
                    ('thousand', 'Thousand Commits', '1000 commits', '', 'coding', 'counter', 'commit_count', 1000, 500, 'legendary');
                """,
            ),
```

- [ ] **Step 2: Verify migration loads**

Run: `cd ~/Projects/claude-code-telegram && uv run python -c "from src.storage.database import DatabaseManager; print('Migration 5 loaded OK')"`

- [ ] **Step 3: Commit**

```bash
git add src/storage/database.py
git commit -m "feat(gamification): add migration 005 with RPG tables and seed achievements"
```

---

### Task 2: Gamification Models

**Files:**
- Create: `src/gamification/__init__.py`
- Create: `src/gamification/models.py`
- Create: `tests/gamification/__init__.py`
- Create: `tests/gamification/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/gamification/__init__.py
# (empty)

# tests/gamification/test_models.py
"""Tests for gamification models."""

import pytest
from datetime import datetime, UTC

from src.gamification.models import (
    RpgProfile,
    XpLogEntry,
    AchievementDefinition,
    Achievement,
)


class TestRpgProfile:
    def test_default_values(self):
        profile = RpgProfile(user_id=123)
        assert profile.level == 1
        assert profile.total_xp == 0
        assert profile.str_points == 0
        assert profile.title == "Junior Developer"
        assert profile.current_streak == 0

    def test_to_dict(self):
        profile = RpgProfile(user_id=123, level=5, total_xp=1200)
        d = profile.to_dict()
        assert d["user_id"] == 123
        assert d["level"] == 5
        assert isinstance(d, dict)

    def test_from_row(self):
        row = {
            "user_id": 123, "level": 10, "total_xp": 5000,
            "str_points": 20, "int_points": 15, "dex_points": 10,
            "con_points": 18, "wis_points": 8,
            "current_streak": 7, "longest_streak": 14,
            "last_activity_date": "2026-03-10", "title": "Senior Developer",
        }
        profile = RpgProfile.from_row(row)
        assert profile.user_id == 123
        assert profile.level == 10
        assert profile.str_points == 20


class TestXpLogEntry:
    def test_creation(self):
        entry = XpLogEntry(
            user_id=123, xp_amount=10, source="commit",
            stat_type="str",
        )
        assert entry.xp_amount == 10
        assert entry.stat_type == "str"

    def test_to_dict_serializes_details(self):
        entry = XpLogEntry(
            user_id=123, xp_amount=10, source="commit",
            details={"files": ["a.py"]},
        )
        d = entry.to_dict()
        assert isinstance(d["details"], str)  # JSON string


class TestAchievementDefinition:
    def test_from_row(self):
        row = {
            "achievement_id": "first_blood", "name": "First Blood",
            "description": "Make your first commit", "icon": "",
            "category": "coding", "condition_type": "counter",
            "condition_key": "commit_count", "condition_value": 1,
            "xp_reward": 10, "rarity": "common", "is_active": True,
        }
        defn = AchievementDefinition.from_row(row)
        assert defn.achievement_id == "first_blood"
        assert defn.xp_reward == 10


class TestAchievement:
    def test_from_row(self):
        row = {
            "id": 1, "user_id": 123,
            "achievement_id": "first_blood",
            "unlocked_at": "2026-03-10T12:00:00",
            "data": None,
        }
        ach = Achievement.from_row(row)
        assert ach.achievement_id == "first_blood"
        assert isinstance(ach.unlocked_at, datetime)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_models.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement models**

```python
# src/gamification/__init__.py
"""RPG gamification system."""

# src/gamification/models.py
"""Gamification data models."""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Optional


def _parse_datetime(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


@dataclass
class RpgProfile:
    user_id: int
    level: int = 1
    total_xp: int = 0
    str_points: int = 0
    int_points: int = 0
    dex_points: int = 0
    con_points: int = 0
    wis_points: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    last_activity_date: Optional[str] = None
    title: str = "Junior Developer"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "RpgProfile":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class XpLogEntry:
    user_id: int
    xp_amount: int
    source: str
    id: Optional[int] = None
    stat_type: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["details"] is not None:
            d["details"] = json.dumps(d["details"])
        if d["created_at"]:
            d["created_at"] = d["created_at"].isoformat()
        return d

    @classmethod
    def from_row(cls, row) -> "XpLogEntry":
        data = dict(row)
        data["created_at"] = _parse_datetime(data.get("created_at"))
        if data.get("details") and isinstance(data["details"], str):
            data["details"] = json.loads(data["details"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AchievementDefinition:
    achievement_id: str
    name: str
    description: str
    icon: str = ""
    category: str = "coding"
    condition_type: str = "counter"
    condition_key: str = ""
    condition_value: int = 1
    xp_reward: int = 10
    rarity: str = "common"
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "AchievementDefinition":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Achievement:
    user_id: int
    achievement_id: str
    id: Optional[int] = None
    unlocked_at: Optional[datetime] = field(default_factory=lambda: datetime.now(UTC))
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["unlocked_at"]:
            d["unlocked_at"] = d["unlocked_at"].isoformat()
        if d["data"] is not None:
            d["data"] = json.dumps(d["data"])
        return d

    @classmethod
    def from_row(cls, row) -> "Achievement":
        data = dict(row)
        data["unlocked_at"] = _parse_datetime(data.get("unlocked_at"))
        if data.get("data") and isinstance(data["data"], str):
            data["data"] = json.loads(data["data"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
```

- [ ] **Step 4: Run tests**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/gamification/ tests/gamification/
git commit -m "feat(gamification): add RPG data models with TDD"
```

---

### Task 3: Constants

**Files:**
- Create: `src/gamification/constants.py`
- Create: `tests/gamification/test_constants.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/gamification/test_constants.py
"""Tests for gamification constants."""

from src.gamification.constants import (
    get_stat_for_file,
    get_xp_for_action,
    calculate_level,
    xp_for_level,
    get_title,
)


class TestFileStatMapping:
    def test_python_file_is_str(self):
        assert get_stat_for_file("server.py") == "str"

    def test_shell_file_is_str(self):
        assert get_stat_for_file("install.sh") == "str"

    def test_tsx_file_is_dex(self):
        assert get_stat_for_file("App.tsx") == "dex"

    def test_swift_file_is_dex(self):
        assert get_stat_for_file("ContentView.swift") == "dex"

    def test_test_file_is_con(self):
        assert get_stat_for_file("test_server.py") == "con"

    def test_spec_file_is_con(self):
        assert get_stat_for_file("app.spec.ts") == "con"

    def test_bats_file_is_con(self):
        assert get_stat_for_file("install.bats") == "con"

    def test_markdown_is_wis(self):
        assert get_stat_for_file("README.md") == "wis"

    def test_unknown_file_returns_none(self):
        assert get_stat_for_file("data.csv") is None


class TestXpForAction:
    def test_commit_normal(self):
        assert get_xp_for_action("commit") == 10

    def test_commit_feat(self):
        assert get_xp_for_action("commit_feat") == 30

    def test_commit_fix(self):
        assert get_xp_for_action("commit_fix") == 20

    def test_test_run(self):
        assert get_xp_for_action("test_run") == 10

    def test_qa_pass(self):
        assert get_xp_for_action("qa_pass") == 15


class TestLevelFormula:
    def test_level_1_is_0_xp(self):
        assert xp_for_level(1) == 0

    def test_level_2_is_100_xp(self):
        assert xp_for_level(2) == 100

    def test_calculate_level_0_xp(self):
        assert calculate_level(0) == 1

    def test_calculate_level_99_xp(self):
        assert calculate_level(99) == 1

    def test_calculate_level_100_xp(self):
        assert calculate_level(100) == 2

    def test_calculate_level_5000_xp(self):
        assert calculate_level(5000) >= 10


class TestTitles:
    def test_level_1(self):
        assert get_title(1) == "Junior Developer"

    def test_level_10(self):
        assert get_title(10) == "Senior Developer"

    def test_level_50(self):
        assert get_title(50) == "Legendary Architect"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_constants.py -v`

- [ ] **Step 3: Implement constants**

```python
# src/gamification/constants.py
"""Gamification constants: XP tables, stat mappings, level formula, titles."""

import math
from pathlib import Path

# File extension → stat mapping
_EXT_TO_STAT: dict[str, str] = {
    ".py": "str", ".sh": "str", ".sql": "str", ".toml": "str",
    ".dockerfile": "str", ".yml": "str", ".yaml": "str",
    ".tsx": "dex", ".jsx": "dex", ".css": "dex", ".html": "dex",
    ".svelte": "dex", ".vue": "dex",
    ".swift": "dex", ".xib": "dex", ".storyboard": "dex",
    ".md": "wis",
    ".bats": "con",
}

# Filename patterns for tests → CON
_TEST_PATTERNS = ("test_", "spec.", ".test.", ".spec.", "_test.")

# XP amounts per action
_XP_TABLE: dict[str, int] = {
    "commit": 10,
    "commit_large": 25,
    "commit_feat": 30,
    "commit_fix": 20,
    "commit_refactor": 15,
    "test_run": 10,
    "qa_pass": 15,
    "tool_read": 2,
    "tool_write": 3,
    "streak_bonus": 5,
}

# Titles by level range
_TITLES = [
    (1, "Junior Developer"),
    (5, "Developer"),
    (10, "Senior Developer"),
    (15, "Staff Engineer"),
    (20, "Principal Engineer"),
    (30, "Distinguished Engineer"),
    (40, "Fellow"),
    (50, "Legendary Architect"),
]


def get_stat_for_file(filename: str) -> str | None:
    name = Path(filename).name.lower()
    for pattern in _TEST_PATTERNS:
        if pattern in name:
            return "con"
    ext = Path(filename).suffix.lower()
    if ext == "" and filename.lower() == "dockerfile":
        return "str"
    return _EXT_TO_STAT.get(ext)


def get_xp_for_action(action: str) -> int:
    return _XP_TABLE.get(action, 0)


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    return int(math.floor(100 * (level ** 1.5)))


def calculate_level(total_xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


def get_title(level: int) -> str:
    title = "Junior Developer"
    for min_level, t in _TITLES:
        if level >= min_level:
            title = t
    return title
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_constants.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/gamification/constants.py tests/gamification/test_constants.py
git commit -m "feat(gamification): add constants — XP table, stat mapping, level formula"
```

---

### Task 4: Gamification Repository

**Files:**
- Create: `src/gamification/repository.py`
- Create: `tests/gamification/test_repository.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/gamification/test_repository.py
"""Tests for GamificationRepository."""

import pytest
import aiosqlite
from pathlib import Path

from src.storage.database import DatabaseManager
from src.gamification.repository import GamificationRepository
from src.gamification.models import RpgProfile, XpLogEntry, Achievement


@pytest.fixture
async def db():
    """Create in-memory database with migrations."""
    manager = DatabaseManager("sqlite:///:memory:")
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def repo(db):
    return GamificationRepository(db)


@pytest.fixture
async def seeded_db(db):
    """DB with a test user."""
    async with db.get_connection() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, telegram_username, is_allowed) VALUES (1, 'test', 1)"
        )
        await conn.commit()
    return db


@pytest.mark.asyncio
class TestGetProfile:
    async def test_returns_none_for_missing_user(self, repo):
        assert await repo.get_profile(999) is None

    async def test_returns_profile_after_creation(self, repo, seeded_db):
        await repo.create_profile(1)
        profile = await repo.get_profile(1)
        assert profile is not None
        assert profile.user_id == 1
        assert profile.level == 1


@pytest.mark.asyncio
class TestUpdateProfile:
    async def test_updates_xp_and_level(self, repo, seeded_db):
        await repo.create_profile(1)
        await repo.update_profile(1, total_xp=500, level=3, str_points=10)
        profile = await repo.get_profile(1)
        assert profile.total_xp == 500
        assert profile.level == 3
        assert profile.str_points == 10


@pytest.mark.asyncio
class TestXpLog:
    async def test_add_and_retrieve(self, repo, seeded_db):
        await repo.create_profile(1)
        entry = XpLogEntry(user_id=1, xp_amount=10, source="commit", stat_type="str")
        await repo.add_xp_log(entry)
        history = await repo.get_xp_history(1, limit=10)
        assert len(history) == 1
        assert history[0].xp_amount == 10


@pytest.mark.asyncio
class TestAchievements:
    async def test_get_active_definitions(self, repo, seeded_db):
        definitions = await repo.get_active_definitions()
        assert len(definitions) == 17  # 17 seeded

    async def test_unlock_and_retrieve(self, repo, seeded_db):
        await repo.create_profile(1)
        ach = Achievement(user_id=1, achievement_id="first_blood")
        await repo.unlock_achievement(ach)
        unlocked = await repo.get_user_achievements(1)
        assert len(unlocked) == 1
        assert unlocked[0].achievement_id == "first_blood"

    async def test_no_duplicate_unlock(self, repo, seeded_db):
        await repo.create_profile(1)
        ach = Achievement(user_id=1, achievement_id="first_blood")
        await repo.unlock_achievement(ach)
        await repo.unlock_achievement(ach)  # should not raise
        unlocked = await repo.get_user_achievements(1)
        assert len(unlocked) == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_repository.py -v`

- [ ] **Step 3: Implement repository**

```python
# src/gamification/repository.py
"""Repository for gamification data access."""

import json
from typing import Optional

import structlog

from ..storage.database import DatabaseManager
from .models import Achievement, AchievementDefinition, RpgProfile, XpLogEntry

logger = structlog.get_logger()


class GamificationRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get_profile(self, user_id: int) -> Optional[RpgProfile]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM rpg_profile WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return RpgProfile.from_row(row) if row else None

    async def create_profile(self, user_id: int) -> RpgProfile:
        async with self.db.get_connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO rpg_profile (user_id) VALUES (?)", (user_id,)
            )
            await conn.commit()
        return await self.get_profile(user_id)

    async def update_profile(self, user_id: int, **kwargs) -> None:
        if not kwargs:
            return
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]
        async with self.db.get_connection() as conn:
            await conn.execute(
                f"UPDATE rpg_profile SET {set_clause} WHERE user_id = ?", values
            )
            await conn.commit()

    async def add_xp_log(self, entry: XpLogEntry) -> int:
        async with self.db.get_connection() as conn:
            details_json = json.dumps(entry.details) if entry.details else None
            cursor = await conn.execute(
                """INSERT INTO xp_log (user_id, xp_amount, stat_type, source, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (entry.user_id, entry.xp_amount, entry.stat_type, entry.source, details_json),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_xp_history(self, user_id: int, limit: int = 50) -> list[XpLogEntry]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM xp_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [XpLogEntry.from_row(row) for row in rows]

    async def get_active_definitions(self) -> list[AchievementDefinition]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM achievement_definitions WHERE is_active = 1"
            )
            rows = await cursor.fetchall()
            return [AchievementDefinition.from_row(row) for row in rows]

    async def get_user_achievements(self, user_id: int) -> list[Achievement]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM achievements WHERE user_id = ? ORDER BY unlocked_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [Achievement.from_row(row) for row in rows]

    async def unlock_achievement(self, achievement: Achievement) -> None:
        async with self.db.get_connection() as conn:
            await conn.execute(
                """INSERT OR IGNORE INTO achievements (user_id, achievement_id, data)
                   VALUES (?, ?, ?)""",
                (achievement.user_id, achievement.achievement_id,
                 json.dumps(achievement.data) if achievement.data else None),
            )
            await conn.commit()

    async def get_counter(self, user_id: int, counter_key: str) -> int:
        """Get a counter value for achievement checking."""
        queries = {
            "commit_count": "SELECT COUNT(*) FROM xp_log WHERE user_id = ? AND source LIKE 'commit%'",
            "fix_commits": "SELECT COUNT(*) FROM xp_log WHERE user_id = ? AND source = 'commit_fix'",
            "refactor_commits": "SELECT COUNT(*) FROM xp_log WHERE user_id = ? AND source = 'commit_refactor'",
            "test_runs": "SELECT COUNT(*) FROM xp_log WHERE user_id = ? AND source = 'test_run'",
            "qa_clean_runs": "SELECT COUNT(*) FROM xp_log WHERE user_id = ? AND source = 'qa_pass'",
            "unique_tools": "SELECT COUNT(DISTINCT json_extract(details, '$.tool_name')) FROM xp_log WHERE user_id = ? AND source LIKE 'tool_%'",
        }
        query = queries.get(counter_key)
        if not query:
            return 0
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, (user_id,))
            row = await cursor.fetchone()
            return row[0] if row else 0
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_repository.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/gamification/repository.py tests/gamification/test_repository.py
git commit -m "feat(gamification): add GamificationRepository with TDD"
```

---

### Task 5: Streak Tracker

**Files:**
- Create: `src/gamification/streak.py`
- Create: `tests/gamification/test_streak.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/gamification/test_streak.py
"""Tests for StreakTracker."""

import pytest
from datetime import date

from src.gamification.streak import StreakTracker


class TestStreakUpdate:
    def test_first_activity_starts_streak_at_1(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=None, current_streak=0, longest_streak=0, today=date(2026, 3, 10)
        )
        assert current_streak == 1
        assert longest == 1

    def test_consecutive_day_increments(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 9), current_streak=5, longest_streak=5,
            today=date(2026, 3, 10),
        )
        assert current_streak == 6
        assert longest == 6

    def test_same_day_no_change(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 10), current_streak=5, longest_streak=10,
            today=date(2026, 3, 10),
        )
        assert current_streak == 5
        assert longest == 10

    def test_gap_resets_streak(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 8), current_streak=5, longest_streak=5,
            today=date(2026, 3, 10),
        )
        assert current_streak == 1
        assert longest == 5  # longest preserved

    def test_longest_streak_preserved(self):
        current_streak, longest = StreakTracker.calculate_streak(
            last_date=date(2026, 3, 9), current_streak=3, longest_streak=20,
            today=date(2026, 3, 10),
        )
        assert current_streak == 4
        assert longest == 20
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/gamification/streak.py
"""Streak tracking logic."""

from datetime import date


class StreakTracker:
    @staticmethod
    def calculate_streak(
        last_date: date | None,
        current_streak: int,
        longest_streak: int,
        today: date | None = None,
    ) -> tuple[int, int]:
        """Calculate updated streak values. Returns (current_streak, longest_streak)."""
        if today is None:
            today = date.today()

        if last_date is None:
            return 1, max(longest_streak, 1)

        delta = (today - last_date).days

        if delta == 0:
            return current_streak, longest_streak
        elif delta == 1:
            new_streak = current_streak + 1
            return new_streak, max(longest_streak, new_streak)
        else:
            return 1, longest_streak
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/gamification/streak.py tests/gamification/test_streak.py
git commit -m "feat(gamification): add StreakTracker with TDD"
```

---

### Task 6: Event Types + Event Bus Integration

**Files:**
- Modify: `src/events/types.py`
- Modify: `src/storage/facade.py`

- [ ] **Step 1: Add new event types to `src/events/types.py`**

Add after the existing `AgentResponseEvent` class:

```python
@dataclass
class ToolUsageSavedEvent(Event):
    """Published after tool usage is saved to DB."""
    user_id: int = 0
    session_id: str = ""
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    source: str = "storage"


@dataclass
class XpGainedEvent(Event):
    """Published when XP is awarded."""
    user_id: int = 0
    xp_amount: int = 0
    stat_type: Optional[str] = None
    xp_source: str = ""
    new_total_xp: int = 0
    source: str = "gamification"


@dataclass
class LevelUpEvent(Event):
    """Published on level up."""
    user_id: int = 0
    new_level: int = 0
    title: str = ""
    previous_level: int = 0
    source: str = "gamification"


@dataclass
class AchievementUnlockedEvent(Event):
    """Published when achievement is unlocked."""
    user_id: int = 0
    achievement_id: str = ""
    name: str = ""
    rarity: str = ""
    xp_reward: int = 0
    source: str = "gamification"
```

- [ ] **Step 2: Publish ToolUsageSavedEvent in `src/storage/facade.py`**

In `save_claude_interaction()`, after the `save_tool_usage` call (around line 110), add event publishing. The facade needs an optional `event_bus` parameter.

Add `event_bus` to `__init__` and publish after each tool save:

```python
# In Storage.__init__ or StorageFacade — add event_bus parameter
# After: await self.tools.save_tool_usage(tool_usage)
# Add:
if self.event_bus:
    from ..events.types import ToolUsageSavedEvent
    await self.event_bus.publish(ToolUsageSavedEvent(
        user_id=user_id,
        session_id=session_id,
        tool_name=tool["name"],
        tool_input=tool.get("input", {}),
        success=not response.is_error,
    ))
```

- [ ] **Step 3: Commit**

```bash
git add src/events/types.py src/storage/facade.py
git commit -m "feat(gamification): add RPG events and publish ToolUsageSavedEvent"
```

---

## Chunk 2: Gamification Service + Bot Integration (Tasks 7-11)

### Task 7: GamificationService

**Files:**
- Create: `src/gamification/service.py`
- Create: `tests/gamification/test_service.py`

- [ ] **Step 1: Write failing tests**

Test core behaviors: on_tool_usage awards XP, commit detection, level up triggers event, achievement check works.

```python
# tests/gamification/test_service.py
"""Tests for GamificationService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from src.gamification.service import GamificationService
from src.gamification.models import RpgProfile, AchievementDefinition
from src.events.types import ToolUsageSavedEvent, LevelUpEvent


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_profile.return_value = RpgProfile(user_id=1, total_xp=90, level=1)
    repo.get_active_definitions.return_value = [
        AchievementDefinition(
            achievement_id="first_blood", name="First Blood",
            description="First commit", condition_type="counter",
            condition_key="commit_count", condition_value=1,
            xp_reward=10, rarity="common",
        ),
    ]
    repo.get_user_achievements.return_value = []
    repo.get_counter.return_value = 0
    return repo


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def service(mock_repo, mock_event_bus):
    return GamificationService(repo=mock_repo, event_bus=mock_event_bus)


@pytest.mark.asyncio
class TestOnToolUsage:
    async def test_git_commit_awards_xp(self, service, mock_repo):
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Bash",
            tool_input={"command": "git commit -m 'feat: add feature'"},
        )
        await service.on_tool_usage(event)
        mock_repo.add_xp_log.assert_called_once()
        mock_repo.update_profile.assert_called()

    async def test_non_commit_bash_awards_nothing(self, service, mock_repo):
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Bash",
            tool_input={"command": "ls -la"},
        )
        await service.on_tool_usage(event)
        mock_repo.add_xp_log.assert_not_called()

    async def test_read_tool_awards_int_xp(self, service, mock_repo):
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Read",
            tool_input={"file_path": "/some/file.py"},
        )
        await service.on_tool_usage(event)
        mock_repo.add_xp_log.assert_called_once()
        call_args = mock_repo.add_xp_log.call_args[0][0]
        assert call_args.stat_type == "int"

    async def test_level_up_publishes_event(self, service, mock_repo, mock_event_bus):
        mock_repo.get_profile.return_value = RpgProfile(
            user_id=1, total_xp=95, level=1
        )
        event = ToolUsageSavedEvent(
            user_id=1, session_id="s1", tool_name="Bash",
            tool_input={"command": "git commit -m 'feat: something'"},
        )
        await service.on_tool_usage(event)
        # After +30 XP (feat commit), total=125 → level 2
        published_events = [
            call.args[0] for call in mock_event_bus.publish.call_args_list
        ]
        level_ups = [e for e in published_events if isinstance(e, LevelUpEvent)]
        assert len(level_ups) >= 1
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement GamificationService**

```python
# src/gamification/service.py
"""Core gamification service — XP engine, achievement checker, event publisher."""

import re

import structlog

from ..events.bus import EventBus
from ..events.types import (
    AchievementUnlockedEvent,
    Event,
    LevelUpEvent,
    ToolUsageSavedEvent,
    XpGainedEvent,
)
from .constants import (
    calculate_level,
    get_stat_for_file,
    get_title,
    get_xp_for_action,
)
from .models import RpgProfile, XpLogEntry
from .repository import GamificationRepository
from .streak import StreakTracker
from datetime import date

logger = structlog.get_logger()

# Tools that award INT XP (exploration/analysis)
_READ_TOOLS = {"Read", "Grep", "Glob", "LS"}
# Tools that award XP based on file type (creation/modification)
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit"}
# Commit message pattern
_COMMIT_RE = re.compile(r"git commit.*-m\s+['\"](\w+)[:!]")


class GamificationService:
    def __init__(self, repo: GamificationRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    def register(self) -> None:
        self.event_bus.subscribe(ToolUsageSavedEvent, self.on_tool_usage)

    async def on_tool_usage(self, event: Event) -> None:
        if not isinstance(event, ToolUsageSavedEvent):
            return

        user_id = event.user_id
        profile = await self._ensure_profile(user_id)

        tool = event.tool_name
        tool_input = event.tool_input or {}
        command = tool_input.get("command", "")

        xp = 0
        stat = None
        source = ""

        if tool == "Bash" and "git commit" in command:
            xp, stat, source = self._parse_commit(command, tool_input)
        elif tool == "Bash" and ("pytest" in command or "bats" in command):
            xp = get_xp_for_action("test_run")
            stat = "con"
            source = "test_run"
        elif tool in _READ_TOOLS:
            xp = get_xp_for_action("tool_read")
            stat = "int"
            source = "tool_read"
        elif tool in _WRITE_TOOLS:
            file_path = tool_input.get("file_path", "")
            stat = get_stat_for_file(file_path) if file_path else None
            xp = get_xp_for_action("tool_write")
            source = "tool_write"

        if xp <= 0:
            return

        await self._award_xp(profile, xp, stat, source, tool_input)

    def _parse_commit(self, command: str, tool_input: dict) -> tuple[int, str | None, str]:
        match = _COMMIT_RE.search(command)
        prefix = match.group(1).lower() if match else ""

        if prefix == "feat":
            action = "commit_feat"
        elif prefix == "fix":
            action = "commit_fix"
        elif prefix == "refactor":
            action = "commit_refactor"
        else:
            action = "commit"

        xp = get_xp_for_action(action)
        stat = "int" if prefix == "refactor" else None
        return xp, stat, action

    async def _award_xp(
        self, profile: RpgProfile, xp: int, stat: str | None,
        source: str, details: dict,
    ) -> None:
        user_id = profile.user_id

        entry = XpLogEntry(
            user_id=user_id, xp_amount=xp, stat_type=stat,
            source=source, details=details,
        )
        await self.repo.add_xp_log(entry)

        new_total = profile.total_xp + xp
        update_kwargs: dict = {"total_xp": new_total}

        if stat:
            stat_field = f"{stat}_points"
            current = getattr(profile, stat_field, 0)
            update_kwargs[stat_field] = current + xp

        # Streak
        today = date.today()
        last_date = date.fromisoformat(profile.last_activity_date) if profile.last_activity_date else None
        new_streak, new_longest = StreakTracker.calculate_streak(
            last_date, profile.current_streak, profile.longest_streak, today,
        )
        update_kwargs["current_streak"] = new_streak
        update_kwargs["longest_streak"] = new_longest
        update_kwargs["last_activity_date"] = today.isoformat()

        # Level
        new_level = calculate_level(new_total)
        old_level = profile.level
        if new_level != old_level:
            update_kwargs["level"] = new_level
            update_kwargs["title"] = get_title(new_level)

        await self.repo.update_profile(user_id, **update_kwargs)

        # Publish XP event
        await self.event_bus.publish(XpGainedEvent(
            user_id=user_id, xp_amount=xp, stat_type=stat,
            xp_source=source, new_total_xp=new_total,
        ))

        # Level up event
        if new_level > old_level:
            await self.event_bus.publish(LevelUpEvent(
                user_id=user_id, new_level=new_level,
                title=get_title(new_level), previous_level=old_level,
            ))

        # Check achievements
        await self._check_achievements(user_id)

    async def _check_achievements(self, user_id: int) -> None:
        unlocked = await self.repo.get_user_achievements(user_id)
        unlocked_ids = {a.achievement_id for a in unlocked}
        definitions = await self.repo.get_active_definitions()
        profile = await self.repo.get_profile(user_id)

        for defn in definitions:
            if defn.achievement_id in unlocked_ids:
                continue

            value = await self._resolve_condition(user_id, profile, defn)
            if value >= defn.condition_value:
                from .models import Achievement
                ach = Achievement(user_id=user_id, achievement_id=defn.achievement_id)
                await self.repo.unlock_achievement(ach)

                # Award achievement XP
                new_total = profile.total_xp + defn.xp_reward
                await self.repo.update_profile(user_id, total_xp=new_total)

                await self.event_bus.publish(AchievementUnlockedEvent(
                    user_id=user_id, achievement_id=defn.achievement_id,
                    name=defn.name, rarity=defn.rarity, xp_reward=defn.xp_reward,
                ))

    async def _resolve_condition(
        self, user_id: int, profile: RpgProfile, defn,
    ) -> int:
        key = defn.condition_key
        if key == "streak_days":
            return profile.current_streak
        elif key == "level":
            return profile.level
        elif key == "max_stat":
            return max(
                profile.str_points, profile.int_points, profile.dex_points,
                profile.con_points, profile.wis_points,
            )
        elif key == "min_stat":
            return min(
                profile.str_points, profile.int_points, profile.dex_points,
                profile.con_points, profile.wis_points,
            )
        else:
            return await self.repo.get_counter(user_id, key)

    async def _ensure_profile(self, user_id: int) -> RpgProfile:
        profile = await self.repo.get_profile(user_id)
        if not profile:
            profile = await self.repo.create_profile(user_id)
        return profile
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_service.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/gamification/service.py tests/gamification/test_service.py
git commit -m "feat(gamification): add GamificationService — XP engine and achievement checker"
```

---

### Task 8: Feature Flag

**Files:**
- Modify: `src/config/settings.py`
- Modify: `src/config/features.py`

- [ ] **Step 1: Add flag to settings.py**

After the last `enable_*` field, add:

```python
    enable_gamification: bool = Field(False, description="Enable RPG gamification system")
```

- [ ] **Step 2: Add property to features.py**

In `FeatureFlags` class, add:

```python
    @property
    def gamification_enabled(self) -> bool:
        return self.settings.enable_gamification
```

And add to `is_feature_enabled` map:

```python
            "gamification": self.gamification_enabled,
```

- [ ] **Step 3: Commit**

```bash
git add src/config/settings.py src/config/features.py
git commit -m "feat(gamification): add ENABLE_GAMIFICATION feature flag"
```

---

### Task 9: Service Wiring in main.py

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Wire GamificationService**

In `create_application()`, after event_bus and storage initialization, add:

```python
    # Gamification (RPG system)
    gamification_service = None
    if config.enable_gamification:
        from src.gamification.repository import GamificationRepository
        from src.gamification.service import GamificationService

        gamification_repo = GamificationRepository(storage.db_manager)
        gamification_service = GamificationService(
            repo=gamification_repo, event_bus=event_bus,
        )
        gamification_service.register()
        logger.info("Gamification service enabled")
```

Add `gamification_service` to the `dependencies` dict passed to bot.

- [ ] **Step 2: Pass event_bus to storage facade**

In the storage facade initialization, pass `event_bus` so it can publish `ToolUsageSavedEvent`. This depends on how facade.py was modified in Task 6.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat(gamification): wire service into main application lifecycle"
```

---

### Task 10: Bot Commands (/stats, /achievements)

**Files:**
- Modify: `src/bot/handlers/command.py`
- Modify: `src/bot/orchestrator.py` (register commands)

- [ ] **Step 1: Add /stats command**

In `command.py`, add:

```python
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats — show RPG profile card."""
    user_id = update.effective_user.id
    gamification = context.bot_data.get("gamification_service")
    if not gamification:
        await update.message.reply_text("Gamification is not enabled.")
        return

    profile = await gamification.repo.get_profile(user_id)
    if not profile:
        await update.message.reply_text("No RPG profile yet. Start coding to earn XP!")
        return

    from src.gamification.constants import xp_for_level
    next_level_xp = xp_for_level(profile.level + 1)
    progress = profile.total_xp - xp_for_level(profile.level)
    needed = next_level_xp - xp_for_level(profile.level)
    bar_len = 16
    filled = int(bar_len * progress / needed) if needed > 0 else bar_len
    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)

    text = (
        f"<b>{update.effective_user.first_name}</b> \u00b7 Lv.{profile.level}\n"
        f"<i>{profile.title}</i>\n\n"
        f"XP: <code>{bar}</code> {profile.total_xp}/{next_level_xp}\n\n"
        f"STR {profile.str_points:>3}  \u00b7  Backend, Shell\n"
        f"INT {profile.int_points:>3}  \u00b7  Architecture\n"
        f"DEX {profile.dex_points:>3}  \u00b7  Frontend, Swift\n"
        f"CON {profile.con_points:>3}  \u00b7  Tests, QA\n"
        f"WIS {profile.wis_points:>3}  \u00b7  Docs, Planning\n\n"
        f"Streak: {profile.current_streak} days (best: {profile.longest_streak})"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Open Dashboard", web_app={"url": f"{context.bot_data.get('mini_app_url', '')}/"}),
    ]]) if context.bot_data.get("mini_app_url") else None

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
```

- [ ] **Step 2: Add /achievements command**

```python
async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /achievements — show recent achievements."""
    user_id = update.effective_user.id
    gamification = context.bot_data.get("gamification_service")
    if not gamification:
        await update.message.reply_text("Gamification is not enabled.")
        return

    unlocked = await gamification.repo.get_user_achievements(user_id)
    all_defs = await gamification.repo.get_active_definitions()
    total = len(all_defs)
    count = len(unlocked)

    if not unlocked:
        text = f"No achievements yet (0/{total}). Keep coding!"
    else:
        lines = [f"<b>Achievements</b> ({count}/{total})\n"]
        for ach in unlocked[:5]:
            defn = next((d for d in all_defs if d.achievement_id == ach.achievement_id), None)
            if defn:
                rarity_tag = f"[{defn.rarity.upper()}]"
                lines.append(f"{defn.icon} <b>{defn.name}</b> {rarity_tag}\n  <i>{defn.description}</i>")
        if count > 5:
            lines.append(f"\n... and {count - 5} more")
        text = "\n".join(lines)

    await update.message.reply_text(text, parse_mode="HTML")
```

- [ ] **Step 3: Register commands in orchestrator.py**

Add CommandHandler entries for "stats" and "achievements" in the appropriate registration method.

- [ ] **Step 4: Commit**

```bash
git add src/bot/handlers/command.py src/bot/orchestrator.py
git commit -m "feat(gamification): add /stats and /achievements bot commands"
```

---

### Task 11: FastAPI RPG Endpoints

**Files:**
- Modify: `src/api/server.py`

- [ ] **Step 1: Add RPG API routes**

```python
    # RPG Gamification API (for Mini App)
    @app.get("/api/rpg/profile")
    async def rpg_profile(user_id: int) -> Dict[str, Any]:
        if not gamification_repo:
            return {"error": "Gamification not enabled"}
        profile = await gamification_repo.get_profile(user_id)
        if not profile:
            return {"error": "No profile"}
        from src.gamification.constants import xp_for_level
        return {
            **profile.to_dict(),
            "xp_for_next_level": xp_for_level(profile.level + 1),
            "xp_for_current_level": xp_for_level(profile.level),
        }

    @app.get("/api/rpg/achievements")
    async def rpg_achievements(user_id: int) -> Dict[str, Any]:
        if not gamification_repo:
            return {"error": "Gamification not enabled"}
        definitions = await gamification_repo.get_active_definitions()
        unlocked = await gamification_repo.get_user_achievements(user_id)
        unlocked_ids = {a.achievement_id for a in unlocked}
        return {
            "definitions": [d.to_dict() for d in definitions],
            "unlocked": [a.to_dict() for a in unlocked],
            "unlocked_ids": list(unlocked_ids),
        }

    @app.get("/api/rpg/timeline")
    async def rpg_timeline(user_id: int, limit: int = 50) -> Dict[str, Any]:
        if not gamification_repo:
            return {"error": "Gamification not enabled"}
        history = await gamification_repo.get_xp_history(user_id, limit=limit)
        return {"entries": [e.to_dict() for e in history]}

    @app.get("/api/rpg/stats/chart")
    async def rpg_stats_chart(user_id: int) -> Dict[str, Any]:
        if not gamification_repo:
            return {"error": "Gamification not enabled"}
        profile = await gamification_repo.get_profile(user_id)
        if not profile:
            return {"error": "No profile"}
        return {
            "stats": [
                {"name": "STR", "value": profile.str_points},
                {"name": "INT", "value": profile.int_points},
                {"name": "DEX", "value": profile.dex_points},
                {"name": "CON", "value": profile.con_points},
                {"name": "WIS", "value": profile.wis_points},
            ]
        }
```

- [ ] **Step 2: Pass gamification_repo to create_api_app**

Add `gamification_repo` as optional parameter to `create_api_app()`.

- [ ] **Step 3: Commit**

```bash
git add src/api/server.py
git commit -m "feat(gamification): add /api/rpg/* FastAPI endpoints for Mini App"
```

---

## Chunk 3: Mini App (Tasks 12-17)

### Task 12: Mini App Scaffold

**Files:**
- Create: `mini-app/package.json`, `mini-app/vite.config.ts`, `mini-app/tsconfig.json`, `mini-app/index.html`
- Create: `mini-app/src/main.tsx`, `mini-app/src/App.tsx`

- [ ] **Step 1: Initialize project**

```bash
cd ~/Projects/claude-code-telegram/mini-app
npm create vite@latest . -- --template react-ts
npm install @twa-dev/sdk
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Configure Tailwind in vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
})
```

- [ ] **Step 3: Create API client**

```typescript
// mini-app/src/api/client.ts
const BASE = '/api/rpg';

export async function fetchProfile(userId: number) {
  const res = await fetch(`${BASE}/profile?user_id=${userId}`);
  return res.json();
}

export async function fetchAchievements(userId: number) {
  const res = await fetch(`${BASE}/achievements?user_id=${userId}`);
  return res.json();
}

export async function fetchTimeline(userId: number, limit = 50) {
  const res = await fetch(`${BASE}/timeline?user_id=${userId}&limit=${limit}`);
  return res.json();
}

export async function fetchStatsChart(userId: number) {
  const res = await fetch(`${BASE}/stats/chart?user_id=${userId}`);
  return res.json();
}
```

- [ ] **Step 4: Create Telegram hook**

```typescript
// mini-app/src/hooks/useTelegram.ts
import WebApp from '@twa-dev/sdk';

export function useTelegram() {
  const user = WebApp.initDataUnsafe?.user;
  const colorScheme = WebApp.colorScheme;
  const themeParams = WebApp.themeParams;

  return { user, colorScheme, themeParams, WebApp };
}
```

- [ ] **Step 5: Set up App.tsx with routing**

```typescript
// mini-app/src/App.tsx
import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import Achievements from './pages/Achievements';
import Timeline from './pages/Timeline';

type Page = 'dashboard' | 'achievements' | 'timeline';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color,#1a1a2e)] text-[var(--tg-theme-text-color,#e0e0e0)]">
      <nav className="flex gap-2 p-3 border-b border-white/10">
        {(['dashboard', 'achievements', 'timeline'] as Page[]).map((p) => (
          <button
            key={p}
            onClick={() => setPage(p)}
            className={`px-3 py-1 rounded text-sm capitalize ${
              page === p ? 'bg-white/20 font-bold' : 'opacity-60'
            }`}
          >
            {p}
          </button>
        ))}
      </nav>
      {page === 'dashboard' && <Dashboard />}
      {page === 'achievements' && <Achievements />}
      {page === 'timeline' && <Timeline />}
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add mini-app/
git commit -m "feat(gamification): scaffold Mini App with React + Tailwind + Vite"
```

---

### Task 13: Dashboard Page + Components

**Files:**
- Create: `mini-app/src/pages/Dashboard.tsx`
- Create: `mini-app/src/components/AvatarCard.tsx`, `XpProgressBar.tsx`, `StatBar.tsx`, `StreakBadge.tsx`
- Create: `mini-app/src/hooks/useProfile.ts`

- [ ] **Step 1: Create useProfile hook**

```typescript
// mini-app/src/hooks/useProfile.ts
import { useEffect, useState } from 'react';
import { fetchProfile } from '../api/client';
import { useTelegram } from './useTelegram';

export function useProfile() {
  const { user } = useTelegram();
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user?.id) return;
    fetchProfile(user.id)
      .then(setProfile)
      .finally(() => setLoading(false));
  }, [user?.id]);

  return { profile, loading };
}
```

- [ ] **Step 2: Create components**

Create AvatarCard, XpProgressBar, StatBar, StreakBadge as separate .tsx files. Each is a focused presentational component receiving props.

- [ ] **Step 3: Compose Dashboard page**

```typescript
// mini-app/src/pages/Dashboard.tsx
import { useProfile } from '../hooks/useProfile';
import AvatarCard from '../components/AvatarCard';
import XpProgressBar from '../components/XpProgressBar';
import StatBar from '../components/StatBar';
import StreakBadge from '../components/StreakBadge';

const STATS = ['str', 'int', 'dex', 'con', 'wis'] as const;
const STAT_LABELS: Record<string, string> = {
  str: 'STR', int: 'INT', dex: 'DEX', con: 'CON', wis: 'WIS',
};

export default function Dashboard() {
  const { profile, loading } = useProfile();
  if (loading) return <div className="p-6 text-center opacity-50">Loading...</div>;
  if (!profile) return <div className="p-6 text-center">No profile yet</div>;

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto">
      <AvatarCard level={profile.level} title={profile.title} />
      <XpProgressBar
        current={profile.total_xp - profile.xp_for_current_level}
        max={profile.xp_for_next_level - profile.xp_for_current_level}
        totalXp={profile.total_xp}
      />
      <div className="space-y-2">
        {STATS.map((s) => (
          <StatBar key={s} label={STAT_LABELS[s]} value={profile[`${s}_points`]} />
        ))}
      </div>
      <StreakBadge current={profile.current_streak} longest={profile.longest_streak} />
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add mini-app/src/
git commit -m "feat(gamification): add Dashboard page with RPG stat components"
```

---

### Task 14: Achievements Page

**Files:**
- Create: `mini-app/src/pages/Achievements.tsx`
- Create: `mini-app/src/components/AchievementCard.tsx`
- Create: `mini-app/src/styles/rarity.ts`

- [ ] **Step 1: Create rarity styles**

```typescript
// mini-app/src/styles/rarity.ts
export const rarityStyles: Record<string, string> = {
  common: 'border-gray-500/30',
  rare: 'border-blue-500/50 shadow-blue-500/20 shadow-md',
  epic: 'border-purple-500/50 shadow-purple-500/20 shadow-lg',
  legendary: 'border-yellow-500/50 shadow-yellow-500/30 shadow-lg animate-pulse',
};
```

- [ ] **Step 2: Create AchievementCard and Achievements page**

- [ ] **Step 3: Commit**

```bash
git add mini-app/src/
git commit -m "feat(gamification): add Achievements page with rarity-styled cards"
```

---

### Task 15: Timeline Page

**Files:**
- Create: `mini-app/src/pages/Timeline.tsx`

- [ ] **Step 1: Implement Timeline with day grouping**

- [ ] **Step 2: Commit**

```bash
git add mini-app/src/pages/Timeline.tsx
git commit -m "feat(gamification): add Timeline page with day-grouped XP history"
```

---

### Task 16: Mini App Serving

**Files:**
- Modify: `src/api/server.py`

- [ ] **Step 1: Add static file serving for production**

In `create_api_app()`, add:

```python
    # Serve Mini App static files (production build)
    mini_app_path = Path(__file__).parent.parent.parent / "mini-app" / "dist"
    if mini_app_path.exists():
        from starlette.staticfiles import StaticFiles
        app.mount("/mini-app", StaticFiles(directory=str(mini_app_path), html=True))
```

- [ ] **Step 2: Build Mini App**

```bash
cd ~/Projects/claude-code-telegram/mini-app && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add src/api/server.py
git commit -m "feat(gamification): serve Mini App static files from FastAPI"
```

---

### Task 17: Integration Test

**Files:**
- Create: `tests/gamification/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/gamification/test_integration.py
"""Integration test: tool_usage → XP → level up → achievement."""

import pytest
from unittest.mock import AsyncMock

from src.storage.database import DatabaseManager
from src.gamification.repository import GamificationRepository
from src.gamification.service import GamificationService
from src.events.bus import EventBus
from src.events.types import ToolUsageSavedEvent, LevelUpEvent, AchievementUnlockedEvent


@pytest.fixture
async def setup():
    db = DatabaseManager("sqlite:///:memory:")
    await db.initialize()
    async with db.get_connection() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, telegram_username, is_allowed) VALUES (1, 'test', 1)"
        )
        await conn.commit()

    event_bus = EventBus()
    await event_bus.start()
    repo = GamificationRepository(db)
    service = GamificationService(repo=repo, event_bus=event_bus)
    service.register()

    yield {"db": db, "event_bus": event_bus, "repo": repo, "service": service}

    await event_bus.stop()
    await db.close()


@pytest.mark.asyncio
async def test_commit_awards_xp_and_creates_profile(setup):
    s = setup
    event = ToolUsageSavedEvent(
        user_id=1, session_id="s1", tool_name="Bash",
        tool_input={"command": "git commit -m 'feat: add RPG system'"},
    )
    await s["service"].on_tool_usage(event)

    profile = await s["repo"].get_profile(1)
    assert profile is not None
    assert profile.total_xp >= 30  # feat commit = 30 XP
    assert profile.current_streak >= 1


@pytest.mark.asyncio
async def test_first_commit_unlocks_first_blood(setup):
    s = setup
    event = ToolUsageSavedEvent(
        user_id=1, session_id="s1", tool_name="Bash",
        tool_input={"command": "git commit -m 'feat: init'"},
    )
    await s["service"].on_tool_usage(event)

    achievements = await s["repo"].get_user_achievements(1)
    ids = {a.achievement_id for a in achievements}
    assert "first_blood" in ids
```

- [ ] **Step 2: Run integration tests**

Run: `cd ~/Projects/claude-code-telegram && uv run pytest tests/gamification/test_integration.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/gamification/test_integration.py
git commit -m "test(gamification): add integration test for XP → achievement flow"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|------------------|
| **1: Backend Core** | 1-6 | DB tables, models, repository, constants, streak, events |
| **2: Service + Bot** | 7-11 | XP engine, feature flag, wiring, /stats, /achievements, API |
| **3: Mini App** | 12-17 | React dashboard, achievements, timeline, serving, integration test |

**Total: 17 tasks, ~50 commits, TDD throughout.**
