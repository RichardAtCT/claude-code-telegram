"""GamificationService: XP engine and achievement checker."""

import re
from datetime import date
from typing import Optional

import structlog

from ..events.bus import EventBus
from ..events.types import (
    AchievementUnlockedEvent,
    LevelUpEvent,
    ToolUsageSavedEvent,
    XpGainedEvent,
)
from .constants import calculate_level, get_stat_for_file, get_title, get_xp_for_action
from .models import Achievement, AchievementDefinition, RpgProfile, XpLogEntry
from .repository import GamificationRepository
from .streak import StreakTracker

logger = structlog.get_logger()

_COMMIT_PREFIX_RE = re.compile(r"git commit.*-m\s+['\"](\w+)[:!]")

_READ_TOOLS = {"Read", "Grep", "Glob", "LS"}
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit"}
_TEST_COMMANDS = ("pytest", "bats")


def _parse_commit_action(command: str) -> Optional[str]:
    """Return the XP action key for a git commit command, or None if not a commit."""
    if "git commit" not in command:
        return None
    match = _COMMIT_PREFIX_RE.search(command)
    if match:
        prefix = match.group(1).lower()
        if prefix == "feat":
            return "commit_feat"
        elif prefix == "fix":
            return "commit_fix"
        elif prefix == "refactor":
            return "commit_refactor"
    return "commit"


def _resolve_tool_xp(
    tool_name: str, tool_input: dict
) -> Optional[tuple[int, Optional[str], str]]:
    """Return (xp_amount, stat_type, source) or None if no XP should be awarded."""
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        # Check for test runners
        for test_cmd in _TEST_COMMANDS:
            if test_cmd in command:
                return get_xp_for_action("test_run"), "con", "test_run"
        # Check for git commit
        action = _parse_commit_action(command)
        if action:
            return get_xp_for_action(action), "str", action
        return None

    if tool_name in _READ_TOOLS:
        return get_xp_for_action("tool_read"), "int", "tool_read"

    if tool_name in _WRITE_TOOLS:
        # Determine stat from file extension
        file_path = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or tool_input.get("new_path")
            or ""
        )
        stat = get_stat_for_file(file_path) if file_path else "str"
        return get_xp_for_action("tool_write"), stat, "tool_write"

    return None


class GamificationService:
    def __init__(self, repo: GamificationRepository, event_bus: EventBus) -> None:
        self.repo = repo
        self.event_bus = event_bus

    def register(self) -> None:
        """Subscribe to relevant events on the event bus."""
        self.event_bus.subscribe(ToolUsageSavedEvent, self.on_tool_usage)

    async def on_tool_usage(self, event: ToolUsageSavedEvent) -> None:
        """Handle a tool usage event: award XP, check level-up, check achievements."""
        result = _resolve_tool_xp(event.tool_name, event.tool_input)
        if result is None:
            return

        xp_amount, stat_type, source = result

        # Fetch or create profile
        profile = await self.repo.get_profile(event.user_id)
        if profile is None:
            profile = await self.repo.create_profile(event.user_id)

        previous_level = profile.level
        old_xp = profile.total_xp

        # Log XP entry
        log_entry = XpLogEntry(
            user_id=event.user_id,
            xp_amount=xp_amount,
            stat_type=stat_type,
            source=source,
            details={"tool_name": event.tool_name, "session_id": event.session_id},
        )
        await self.repo.add_xp_log(log_entry)

        # Update streak
        last_date = (
            date.fromisoformat(profile.last_activity_date)
            if profile.last_activity_date
            else None
        )
        new_streak, new_longest = StreakTracker.calculate_streak(
            last_date=last_date,
            current_streak=profile.current_streak,
            longest_streak=profile.longest_streak,
        )

        # Compute new totals
        new_total_xp = old_xp + xp_amount
        new_level = calculate_level(new_total_xp)
        new_title = get_title(new_level)

        # Build profile update kwargs
        update_kwargs: dict = {
            "total_xp": new_total_xp,
            "level": new_level,
            "title": new_title,
            "current_streak": new_streak,
            "longest_streak": new_longest,
            "last_activity_date": date.today().isoformat(),
        }
        if stat_type:
            stat_field = f"{stat_type}_points"
            current_stat = getattr(profile, stat_field, 0)
            update_kwargs[stat_field] = current_stat + 1

        await self.repo.update_profile(event.user_id, **update_kwargs)

        # Publish XpGainedEvent
        await self.event_bus.publish(
            XpGainedEvent(
                user_id=event.user_id,
                xp_amount=xp_amount,
                stat_type=stat_type,
                xp_source=source,
                new_total_xp=new_total_xp,
            )
        )

        # Publish LevelUpEvent if level changed
        if new_level > previous_level:
            await self.event_bus.publish(
                LevelUpEvent(
                    user_id=event.user_id,
                    new_level=new_level,
                    title=new_title,
                    previous_level=previous_level,
                )
            )
            logger.info(
                "Level up",
                user_id=event.user_id,
                previous_level=previous_level,
                new_level=new_level,
            )

        # Build updated profile snapshot for achievement checking
        updated_profile = RpgProfile(
            user_id=profile.user_id,
            level=new_level,
            total_xp=new_total_xp,
            str_points=profile.str_points + (1 if stat_type == "str" else 0),
            int_points=profile.int_points + (1 if stat_type == "int" else 0),
            dex_points=profile.dex_points + (1 if stat_type == "dex" else 0),
            con_points=profile.con_points + (1 if stat_type == "con" else 0),
            wis_points=profile.wis_points + (1 if stat_type == "wis" else 0),
            current_streak=new_streak,
            longest_streak=new_longest,
            title=new_title,
        )
        await self._check_achievements(event.user_id, updated_profile)

    async def _check_achievements(
        self, user_id: int, profile: RpgProfile
    ) -> None:
        """Check all active achievement definitions and unlock newly earned ones."""
        definitions = await self.repo.get_active_definitions()
        user_achievements = await self.repo.get_user_achievements(user_id)
        unlocked_ids = {a.achievement_id for a in user_achievements}

        for defn in definitions:
            if defn.achievement_id in unlocked_ids:
                continue

            current_value = await self._resolve_condition(user_id, defn.condition_key, profile)

            earned = False
            if defn.condition_type == "counter":
                earned = current_value >= defn.condition_value
            elif defn.condition_type == "threshold":
                earned = current_value >= defn.condition_value

            if not earned:
                continue

            achievement = Achievement(
                user_id=user_id,
                achievement_id=defn.achievement_id,
            )
            await self.repo.unlock_achievement(achievement)

            # Award bonus XP for the achievement
            if defn.xp_reward > 0:
                bonus_entry = XpLogEntry(
                    user_id=user_id,
                    xp_amount=defn.xp_reward,
                    stat_type=None,
                    source=f"achievement_{defn.achievement_id}",
                )
                await self.repo.add_xp_log(bonus_entry)
                await self.repo.update_profile(
                    user_id, total_xp=profile.total_xp + defn.xp_reward
                )

            await self.event_bus.publish(
                AchievementUnlockedEvent(
                    user_id=user_id,
                    achievement_id=defn.achievement_id,
                    name=defn.name,
                    rarity=defn.rarity,
                    xp_reward=defn.xp_reward,
                )
            )
            logger.info(
                "Achievement unlocked",
                user_id=user_id,
                achievement_id=defn.achievement_id,
            )

    async def _resolve_condition(
        self, user_id: int, condition_key: str, profile: RpgProfile
    ) -> int:
        """Map condition_key to its current numeric value."""
        if condition_key == "streak_days":
            return profile.current_streak
        if condition_key == "level":
            return profile.level
        if condition_key == "max_stat":
            return max(
                profile.str_points,
                profile.int_points,
                profile.dex_points,
                profile.con_points,
                profile.wis_points,
            )
        if condition_key == "min_stat":
            return min(
                profile.str_points,
                profile.int_points,
                profile.dex_points,
                profile.con_points,
                profile.wis_points,
            )
        return await self.repo.get_counter(user_id, condition_key)
