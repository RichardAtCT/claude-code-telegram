"""Concrete event types for the event bus."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

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
class AlertEvent(Event):
    """An alert triggered by a threshold breach or security violation."""

    alert_type: str = ""
    severity: Literal["info", "warning", "critical"] = "info"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    source: str = "alert_manager"
