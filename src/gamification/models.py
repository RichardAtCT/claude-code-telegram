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
