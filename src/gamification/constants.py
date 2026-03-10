"""Gamification constants: XP tables, stat mappings, level formula, titles."""

from pathlib import Path

# File extension -> stat mapping
_EXT_TO_STAT: dict[str, str] = {
    ".py": "str", ".sh": "str", ".sql": "str", ".toml": "str",
    ".dockerfile": "str", ".yml": "str", ".yaml": "str",
    ".tsx": "dex", ".jsx": "dex", ".css": "dex", ".html": "dex",
    ".svelte": "dex", ".vue": "dex",
    ".swift": "dex", ".xib": "dex", ".storyboard": "dex",
    ".md": "wis",
    ".bats": "con",
}

# Filename patterns for tests -> CON
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
    return 100 * (level - 1)


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
