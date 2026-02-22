"""Quick Actions feature implementation.

Provides context-aware quick action suggestions for common development tasks.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.storage.models import SessionModel

logger = logging.getLogger(__name__)


@dataclass
class QuickAction:
    """Represents a quick action suggestion."""

    id: str
    name: str
    description: str
    command: str
    icon: str
    category: str
    context_required: List[str]  # Required context keys
    priority: int = 0  # Higher = more important


class QuickActionManager:
    """Manages quick action suggestions based on context."""

    def __init__(self) -> None:
        """Initialize the quick action manager."""
        self.actions = self._create_default_actions()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _create_default_actions(self) -> Dict[str, QuickAction]:
        """Create default quick actions."""
        return {
            "test": QuickAction(
                id="test",
                name="Run Tests",
                description="Run project tests",
                command="test",
                icon="🧪",
                category="testing",
                context_required=["has_tests"],
                priority=10,
            ),
            "install": QuickAction(
                id="install",
                name="Install Dependencies",
                description="Install project dependencies",
                command="install",
                icon="📦",
                category="setup",
                context_required=["has_package_manager"],
                priority=9,
            ),
            "format": QuickAction(
                id="format",
                name="Format Code",
                description="Format code with project formatter",
                command="format",
                icon="🎨",
                category="quality",
                context_required=["has_formatter"],
                priority=7,
            ),
            "lint": QuickAction(
                id="lint",
                name="Lint Code",
                description="Check code quality",
                command="lint",
                icon="🔍",
                category="quality",
                context_required=["has_linter"],
                priority=8,
            ),
            "security": QuickAction(
                id="security",
                name="Security Scan",
                description="Run security vulnerability scan",
                command="security",
                icon="🔒",
                category="security",
                context_required=["has_dependencies"],
                priority=6,
            ),
            "optimize": QuickAction(
                id="optimize",
                name="Optimize",
                description="Optimize code performance",
                command="optimize",
                icon="⚡",
                category="performance",
                context_required=["has_code"],
                priority=5,
            ),
            "document": QuickAction(
                id="document",
                name="Generate Docs",
                description="Generate documentation",
                command="document",
                icon="📝",
                category="documentation",
                context_required=["has_code"],
                priority=4,
            ),
            "refactor": QuickAction(
                id="refactor",
                name="Refactor",
                description="Suggest code improvements",
                command="refactor",
                icon="🔧",
                category="quality",
                context_required=["has_code"],
                priority=3,
            ),
        }

    async def get_suggestions(
        self, session: SessionModel, limit: int = 6
    ) -> List[QuickAction]:
        """Get quick action suggestions based on session context.

        Args:
            session: Current session
            limit: Maximum number of suggestions

        Returns:
            List of suggested actions
        """
        try:
            # Analyze context
            context = await self._analyze_context(session)

            # Filter actions based on context
            available_actions = []
            for action in self.actions.values():
                if self._is_action_available(action, context):
                    available_actions.append(action)

            # Sort by priority and return top N
            available_actions.sort(key=lambda x: x.priority, reverse=True)
            return available_actions[:limit]

        except Exception as e:
            self.logger.error(f"Error getting suggestions: {e}")
            return []

    async def _analyze_context(self, session: SessionModel) -> Dict[str, Any]:
        """Analyze session context to determine available actions.

        Args:
            session: Current session

        Returns:
            Context dictionary
        """
        context: Dict[str, Any] = {
            "has_code": True,  # Default assumption
            "has_tests": False,
            "has_package_manager": False,
            "has_formatter": False,
            "has_linter": False,
            "has_dependencies": False,
        }

        # Note: SessionModel does not currently have a 'context' field with
        # recent messages. File-based context analysis could be added here.
        # For now, we use heuristics based on session metadata.
        _ = session  # used for future context analysis

        return context

    def _is_action_available(
        self, action: QuickAction, context: Dict[str, Any]
    ) -> bool:
        """Check if an action is available in the given context.

        Args:
            action: The action to check
            context: Current context

        Returns:
            True if action is available
        """
        # Check all required context keys
        for key in action.context_required:
            if not context.get(key, False):
                return False
        return True

    def create_inline_keyboard(
        self, actions: List[QuickAction], columns: int = 2
    ) -> InlineKeyboardMarkup:
        """Create inline keyboard for quick actions.

        Args:
            actions: List of actions to display
            columns: Number of columns in keyboard

        Returns:
            Inline keyboard markup
        """
        keyboard = []
        row = []

        for i, action in enumerate(actions):
            button = InlineKeyboardButton(
                text=f"{action.icon} {action.name}",
                callback_data=f"quick_action:{action.id}",
            )
            row.append(button)

            # Add row when full or last item
            if len(row) >= columns or i == len(actions) - 1:
                keyboard.append(row)
                row = []

        return InlineKeyboardMarkup(keyboard)

    async def execute_action(
        self, action_id: str, session: SessionModel, callback: Optional[Callable] = None
    ) -> str:
        """Execute a quick action.

        Args:
            action_id: ID of action to execute
            session: Current session
            callback: Optional callback for command execution

        Returns:
            Command to execute
        """
        action = self.actions.get(action_id)
        if not action:
            raise ValueError(f"Unknown action: {action_id}")

        self.logger.info(
            f"Executing quick action: {action.name} for session {session.session_id}"
        )

        # Return the command - actual execution is handled by the bot
        return action.command
