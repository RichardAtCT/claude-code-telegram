"""Enhanced conversation features.

This module implements the Conversation Enhancement feature from TODO-7, providing:

Features:
- Context preservation across conversation turns
- Intelligent follow-up suggestions based on tools used and content
- Code execution tracking and analysis
- Interactive conversation controls with inline keyboards
- Smart suggestion prioritization

Core Components:
- ConversationContext: Tracks conversation state and metadata
- ConversationEnhancer: Main class for generating suggestions and formatting responses

The implementation analyzes Claude's responses to generate contextually relevant
follow-up suggestions, making it easier for users to continue productive conversations
with actionable next steps.

Usage:
    enhancer = ConversationEnhancer()
    enhancer.update_context(user_id, claude_response)
    suggestions = enhancer.generate_follow_up_suggestions(response, context)
    keyboard = enhancer.create_follow_up_keyboard(suggestions)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ...claude.integration import ClaudeResponse

logger = structlog.get_logger()


@dataclass
class ConversationContext:
    """Context information for a conversation."""

    user_id: int
    session_id: Optional[str] = None
    project_path: Optional[str] = None
    last_tools_used: List[str] = field(default_factory=list)
    last_response_content: str = ""
    conversation_turn: int = 0
    has_errors: bool = False
    active_files: List[str] = field(default_factory=list)
    todo_count: int = 0

    def update_from_response(self, response: ClaudeResponse) -> None:
        """Update context from Claude response."""
        self.session_id = response.session_id
        self.last_response_content = response.content.lower()
        self.conversation_turn += 1
        self.has_errors = response.is_error or "error" in self.last_response_content

        # Extract tools used
        self.last_tools_used = [tool.get("name", "") for tool in response.tools_used]

        # Update active files if file tools were used
        if any(tool in self.last_tools_used for tool in ["Edit", "Write", "Read"]):
            # In a real implementation, we'd parse the tool outputs to get file names
            # For now, we'll track that file operations occurred
            pass

        # Count TODOs/FIXMEs in response
        todo_keywords = ["todo", "fixme", "note", "hack", "bug"]
        self.todo_count = sum(
            1 for keyword in todo_keywords if keyword in self.last_response_content
        )


class ConversationEnhancer:
    """Enhance conversation experience."""

    def __init__(self) -> None:
        """Initialize conversation enhancer."""
        self.conversation_contexts: Dict[int, ConversationContext] = {}

    def get_or_create_context(self, user_id: int) -> ConversationContext:
        """Get or create conversation context for user."""
        if user_id not in self.conversation_contexts:
            self.conversation_contexts[user_id] = ConversationContext(user_id=user_id)

        return self.conversation_contexts[user_id]

    def update_context(self, user_id: int, response: ClaudeResponse) -> None:
        """Update conversation context with response."""
        context = self.get_or_create_context(user_id)
        context.update_from_response(response)

        logger.debug(
            "Updated conversation context",
            user_id=user_id,
            session_id=context.session_id,
            turn=context.conversation_turn,
            tools_used=context.last_tools_used,
        )

    def generate_follow_up_suggestions(
        self, response: ClaudeResponse, context: ConversationContext
    ) -> List[str]:
        """Generate relevant follow-up suggestions."""
        suggestions = []

        # Based on tools used
        tools_used = [tool.get("name", "") for tool in response.tools_used]

        if "Write" in tools_used or "MultiEdit" in tools_used:
            suggestions.extend(
                [
                    "Add tests for the new code",
                    "Create documentation for this",
                    "Review the implementation",
                ]
            )

        if "Edit" in tools_used:
            suggestions.extend(
                [
                    "Review the changes made",
                    "Run tests to verify changes",
                    "Check for any side effects",
                ]
            )

        if "Read" in tools_used:
            suggestions.extend(
                [
                    "Explain how this code works",
                    "Suggest improvements",
                    "Add error handling",
                ]
            )

        if "Bash" in tools_used:
            suggestions.extend(
                [
                    "Explain the command output",
                    "Run additional related commands",
                    "Check for any issues",
                ]
            )

        if "Glob" in tools_used or "Grep" in tools_used:
            suggestions.extend(
                [
                    "Analyze the search results",
                    "Look into specific files found",
                    "Create a summary of findings",
                ]
            )

        # Based on response content analysis
        content_lower = response.content.lower()

        if "error" in content_lower or "failed" in content_lower:
            suggestions.extend(
                [
                    "Help me debug this error",
                    "Suggest alternative approaches",
                    "Check the logs for more details",
                ]
            )

        if "todo" in content_lower or "fixme" in content_lower:
            suggestions.extend(
                [
                    "Complete the TODO items",
                    "Prioritize the tasks",
                    "Create an action plan",
                ]
            )

        if "test" in content_lower and (
            "fail" in content_lower or "error" in content_lower
        ):
            suggestions.extend(
                [
                    "Fix the failing tests",
                    "Update test expectations",
                    "Add more test coverage",
                ]
            )

        if "install" in content_lower or "dependency" in content_lower:
            suggestions.extend(
                [
                    "Verify the installation",
                    "Check for version conflicts",
                    "Update package documentation",
                ]
            )

        if "git" in content_lower:
            suggestions.extend(
                [
                    "Review the git status",
                    "Check commit history",
                    "Create a commit with changes",
                ]
            )

        # Based on conversation context
        if context.conversation_turn > 1:
            suggestions.append("Continue with the next step")

        if context.has_errors:
            suggestions.extend(
                ["Investigate the error further", "Try a different approach"]
            )

        if context.todo_count > 0:
            suggestions.append("Address the TODO items")

        # General suggestions based on development patterns
        if any(keyword in content_lower for keyword in ["function", "class", "method"]):
            suggestions.extend(
                ["Add unit tests", "Improve documentation", "Add type hints"]
            )

        if "performance" in content_lower or "optimize" in content_lower:
            suggestions.extend(
                [
                    "Profile the performance",
                    "Benchmark the changes",
                    "Monitor resource usage",
                ]
            )

        # Remove duplicates and limit to most relevant
        unique_suggestions = list(dict.fromkeys(suggestions))

        # Prioritize based on tools used and content
        prioritized = []

        # High priority: error handling and fixes
        for suggestion in unique_suggestions:
            if any(
                keyword in suggestion.lower() for keyword in ["error", "debug", "fix"]
            ):
                prioritized.append(suggestion)

        # Medium priority: development workflow
        for suggestion in unique_suggestions:
            if suggestion not in prioritized and any(
                keyword in suggestion.lower()
                for keyword in ["test", "review", "verify"]
            ):
                prioritized.append(suggestion)

        # Lower priority: enhancements
        for suggestion in unique_suggestions:
            if suggestion not in prioritized:
                prioritized.append(suggestion)

        # Return top 3-4 most relevant suggestions
        return prioritized[:4]

    def create_follow_up_keyboard(self, suggestions: List[str]) -> InlineKeyboardMarkup:
        """Create keyboard with follow-up suggestions."""
        if not suggestions:
            return InlineKeyboardMarkup([])

        keyboard = []

        # Add suggestion buttons (max 4, in rows of 1 for better mobile experience)
        for suggestion in suggestions[:4]:
            # Create a shorter hash for callback data
            suggestion_hash = str(hash(suggestion) % 1000000)
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"💡 {suggestion}", callback_data=f"followup:{suggestion_hash}"
                    )
                ]
            )

        # Add control buttons
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✅ Continue Coding", callback_data="conversation:continue"
                ),
                InlineKeyboardButton(
                    "🛑 End Session", callback_data="conversation:end"
                ),
            ]
        )

        return InlineKeyboardMarkup(keyboard)

    def should_show_suggestions(self, response: ClaudeResponse) -> bool:
        """Determine if follow-up suggestions should be shown."""
        # Don't show suggestions for errors
        if response.is_error:
            return False

        # Show suggestions if tools were used
        if response.tools_used:
            return True

        # Show suggestions for longer responses (likely more substantial)
        if len(response.content) > 200:
            return True

        # Show suggestions if response contains actionable content
        actionable_keywords = [
            "todo",
            "fixme",
            "next",
            "consider",
            "you can",
            "you could",
            "try",
            "test",
            "check",
            "verify",
            "review",
        ]

        content_lower = response.content.lower()
        return any(keyword in content_lower for keyword in actionable_keywords)

    def format_response_with_suggestions(
        self,
        response: ClaudeResponse,
        context: ConversationContext,
        max_content_length: int = 3000,
    ) -> tuple[str, Optional[InlineKeyboardMarkup]]:
        """Format response with follow-up suggestions."""
        # Truncate content if too long for Telegram
        content = response.content
        if len(content) > max_content_length:
            content = (
                content[:max_content_length] + "\n\n... <i>(response truncated)</i>"
            )

        # Add session info if this is a new session
        if context.conversation_turn == 1 and response.session_id:
            session_info = (
                f"\n\n🆔 <b>Session:</b> <code>{response.session_id[:8]}...</code>"
            )
            content += session_info

        # Add cost info if significant
        if response.cost > 0.01:
            cost_info = f"\n\n💰 <b>Cost:</b> ${response.cost:.4f}"
            content += cost_info

        # Generate follow-up suggestions
        keyboard = None
        if self.should_show_suggestions(response):
            suggestions = self.generate_follow_up_suggestions(response, context)
            if suggestions:
                keyboard = self.create_follow_up_keyboard(suggestions)
                logger.debug(
                    "Generated follow-up suggestions",
                    user_id=context.user_id,
                    suggestions=suggestions,
                )

        return content, keyboard

    def clear_context(self, user_id: int) -> None:
        """Clear conversation context for user."""
        if user_id in self.conversation_contexts:
            del self.conversation_contexts[user_id]
            logger.debug("Cleared conversation context", user_id=user_id)

    def get_context_summary(self, user_id: int) -> Optional[Dict]:
        """Get summary of conversation context."""
        context = self.conversation_contexts.get(user_id)
        if not context:
            return None

        return {
            "session_id": context.session_id,
            "project_path": context.project_path,
            "conversation_turn": context.conversation_turn,
            "last_tools_used": context.last_tools_used,
            "has_errors": context.has_errors,
            "todo_count": context.todo_count,
            "active_files_count": len(context.active_files),
        }
