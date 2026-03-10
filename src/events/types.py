"""Concrete event types for the event bus."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bus import Event


@dataclass
class UserMessageEvent(Event):
    """A message from a Telegram user."""

    user_id: int = 0
    chat_id: int = 0
    text: str = ""
    working_directory: Path = field(default_factory=lambda: Path("."))
    source: str = "telegram"


@dataclass
class WebhookEvent(Event):
    """An external webhook delivery (GitHub, Notion, etc.)."""

    provider: str = ""
    event_type_name: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    delivery_id: str = ""
    source: str = "webhook"


@dataclass
class ScheduledEvent(Event):
    """A cron/scheduled trigger."""

    job_id: str = ""
    job_name: str = ""
    prompt: str = ""
    working_directory: Path = field(default_factory=lambda: Path("."))
    target_chat_ids: List[int] = field(default_factory=list)
    skill_name: Optional[str] = None
    source: str = "scheduler"


@dataclass
class AgentResponseEvent(Event):
    """An agent has produced a response to deliver."""

    chat_id: int = 0
    text: str = ""
    parse_mode: Optional[str] = "HTML"
    reply_to_message_id: Optional[int] = None
    source: str = "agent"
    originating_event_id: Optional[str] = None


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
