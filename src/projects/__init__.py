"""Project registry and Telegram thread management."""

from .registry import ProjectDefinition, ProjectRegistry, load_project_registry
from .thread_manager import (
    PrivateTopicsUnavailableError,
    ProjectThreadManager,
)

__all__ = [
    "ProjectDefinition",
    "ProjectRegistry",
    "load_project_registry",
    "ProjectThreadManager",
    "PrivateTopicsUnavailableError",
]
