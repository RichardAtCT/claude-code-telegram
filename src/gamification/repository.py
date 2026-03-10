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
                (
                    achievement.user_id,
                    achievement.achievement_id,
                    json.dumps(achievement.data) if achievement.data else None,
                ),
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
