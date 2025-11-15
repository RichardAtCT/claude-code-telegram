"""Tests for conversation enhancement feature."""

from unittest.mock import Mock

import pytest
from telegram import InlineKeyboardMarkup

from src.bot.features.conversation_mode import (
    ConversationContext,
    ConversationEnhancer,
)
from src.claude.integration import ClaudeResponse


@pytest.fixture
def enhancer():
    """Create conversation enhancer instance."""
    return ConversationEnhancer()


@pytest.fixture
def sample_response():
    """Create sample Claude response."""
    response = Mock(spec=ClaudeResponse)
    response.session_id = "session_123"
    response.content = "I've updated the code as requested."
    response.is_error = False
    response.tools_used = [{"name": "Edit", "input": {"file": "test.py"}}]
    response.cost = 0.05
    return response


@pytest.fixture
def error_response():
    """Create error Claude response."""
    response = Mock(spec=ClaudeResponse)
    response.session_id = "session_456"
    response.content = "Error: Failed to execute command"
    response.is_error = True
    response.tools_used = []
    response.cost = 0.01
    return response


class TestConversationContextCreation:
    """Test ConversationContext creation and initialization."""

    def test_context_creation(self):
        """Test creating a conversation context."""
        context = ConversationContext(user_id=123456)

        assert context.user_id == 123456
        assert context.session_id is None
        assert context.project_path is None
        assert context.last_tools_used == []
        assert context.last_response_content == ""
        assert context.conversation_turn == 0
        assert context.has_errors is False
        assert context.active_files == []
        assert context.todo_count == 0

    def test_context_with_initial_values(self):
        """Test creating context with initial values."""
        context = ConversationContext(
            user_id=789012,
            session_id="test_session",
            project_path="/home/user/project",
        )

        assert context.user_id == 789012
        assert context.session_id == "test_session"
        assert context.project_path == "/home/user/project"


class TestContextUpdateFromResponse:
    """Test updating context from Claude responses."""

    def test_update_from_success_response(self, sample_response):
        """Test updating context from successful response."""
        context = ConversationContext(user_id=123456)
        context.update_from_response(sample_response)

        assert context.session_id == "session_123"
        assert context.conversation_turn == 1
        assert context.has_errors is False
        assert "updated" in context.last_response_content
        assert "Edit" in context.last_tools_used

    def test_update_from_error_response(self, error_response):
        """Test updating context from error response."""
        context = ConversationContext(user_id=123456)
        context.update_from_response(error_response)

        assert context.session_id == "session_456"
        assert context.conversation_turn == 1
        assert context.has_errors is True
        assert "error" in context.last_response_content

    def test_update_increments_turn(self, sample_response):
        """Test that update increments conversation turn."""
        context = ConversationContext(user_id=123456)

        context.update_from_response(sample_response)
        assert context.conversation_turn == 1

        context.update_from_response(sample_response)
        assert context.conversation_turn == 2

        context.update_from_response(sample_response)
        assert context.conversation_turn == 3

    def test_update_extracts_tool_names(self):
        """Test extraction of tool names from response."""
        response = Mock(spec=ClaudeResponse)
        response.session_id = "test"
        response.content = "Test content"
        response.is_error = False
        response.tools_used = [
            {"name": "Edit"},
            {"name": "Bash"},
            {"name": "Read"},
        ]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        context.update_from_response(response)

        assert "Edit" in context.last_tools_used
        assert "Bash" in context.last_tools_used
        assert "Read" in context.last_tools_used
        assert len(context.last_tools_used) == 3

    def test_update_detects_todos(self):
        """Test detection of TODO items in response."""
        response = Mock(spec=ClaudeResponse)
        response.session_id = "test"
        response.content = "TODO: Add tests. FIXME: Fix issue. NOTE: Important. HACK: Workaround."
        response.is_error = False
        response.tools_used = []
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        context.update_from_response(response)

        # Count includes todo, fixme, note, hack (keywords are checked individually)
        assert context.todo_count == 4

    def test_update_with_no_tools(self):
        """Test update with response containing no tools."""
        response = Mock(spec=ClaudeResponse)
        response.session_id = "test"
        response.content = "Simple response"
        response.is_error = False
        response.tools_used = []
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        context.update_from_response(response)

        assert context.last_tools_used == []


class TestConversationEnhancerContextManagement:
    """Test conversation enhancer context management."""

    def test_get_or_create_context_creates_new(self, enhancer):
        """Test creating new context."""
        context = enhancer.get_or_create_context(123456)

        assert context is not None
        assert context.user_id == 123456
        assert 123456 in enhancer.conversation_contexts

    def test_get_or_create_context_returns_existing(self, enhancer):
        """Test returning existing context."""
        context1 = enhancer.get_or_create_context(123456)
        context1.conversation_turn = 5

        context2 = enhancer.get_or_create_context(123456)

        assert context1 is context2
        assert context2.conversation_turn == 5

    def test_update_context(self, enhancer, sample_response):
        """Test updating context via enhancer."""
        enhancer.update_context(123456, sample_response)

        context = enhancer.conversation_contexts[123456]
        assert context.session_id == "session_123"
        assert context.conversation_turn == 1

    def test_clear_context(self, enhancer):
        """Test clearing context."""
        enhancer.get_or_create_context(123456)
        assert 123456 in enhancer.conversation_contexts

        enhancer.clear_context(123456)
        assert 123456 not in enhancer.conversation_contexts

    def test_clear_nonexistent_context(self, enhancer):
        """Test clearing context that doesn't exist."""
        # Should not raise error
        enhancer.clear_context(999999)


class TestGetContextSummary:
    """Test context summary generation."""

    def test_get_context_summary(self, enhancer, sample_response):
        """Test getting context summary."""
        enhancer.update_context(123456, sample_response)
        summary = enhancer.get_context_summary(123456)

        assert summary is not None
        assert summary["session_id"] == "session_123"
        assert summary["conversation_turn"] == 1
        assert summary["has_errors"] is False
        assert "last_tools_used" in summary
        assert "active_files_count" in summary

    def test_get_context_summary_nonexistent(self, enhancer):
        """Test getting summary for non-existent context."""
        summary = enhancer.get_context_summary(999999)
        assert summary is None


class TestFollowUpSuggestions:
    """Test follow-up suggestion generation."""

    def test_suggestions_for_write_tool(self, enhancer):
        """Test suggestions when Write tool was used."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Created new file"
        response.is_error = False
        response.tools_used = [{"name": "Write"}]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest testing new code
        assert any("test" in s.lower() for s in suggestions)

    def test_suggestions_for_edit_tool(self, enhancer):
        """Test suggestions when Edit tool was used."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Modified the function"
        response.is_error = False
        response.tools_used = [{"name": "Edit"}]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest reviewing or testing
        assert any("review" in s.lower() or "test" in s.lower() for s in suggestions)

    def test_suggestions_for_read_tool(self, enhancer):
        """Test suggestions when Read tool was used."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Here's the file content"
        response.is_error = False
        response.tools_used = [{"name": "Read"}]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest explaining or improving
        assert any("explain" in s.lower() or "improve" in s.lower() for s in suggestions)

    def test_suggestions_for_bash_tool(self, enhancer):
        """Test suggestions when Bash tool was used."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Command executed successfully"
        response.is_error = False
        response.tools_used = [{"name": "Bash"}]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest explaining output or checking issues
        assert any("explain" in s.lower() or "check" in s.lower() for s in suggestions)

    def test_suggestions_for_search_tools(self, enhancer):
        """Test suggestions when search tools were used."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Found 10 matching files"
        response.is_error = False
        response.tools_used = [{"name": "Grep"}]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest analyzing results
        assert any("analyze" in s.lower() or "summary" in s.lower() for s in suggestions)

    def test_suggestions_for_errors(self, enhancer, error_response):
        """Test suggestions when response contains errors."""
        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(error_response, context)

        assert len(suggestions) > 0
        # Should suggest debugging or alternative approaches
        assert any("debug" in s.lower() or "alternative" in s.lower() for s in suggestions)

    def test_suggestions_for_todo_content(self, enhancer):
        """Test suggestions when response mentions TODOs."""
        response = Mock(spec=ClaudeResponse)
        response.content = "TODO: Update documentation. FIXME: Refactor this code."
        response.is_error = False
        response.tools_used = []
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        context.todo_count = 2  # Set TODO count
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest completing/addressing TODOs, prioritizing tasks, or planning
        assert any(
            "complete" in s.lower()
            or "address" in s.lower()
            or "prioritize" in s.lower()
            or "plan" in s.lower()
            for s in suggestions
        )

    def test_suggestions_for_git_content(self, enhancer):
        """Test suggestions when response mentions git."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Made changes to the git repository"
        response.is_error = False
        response.tools_used = []
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) > 0
        # Should suggest git-related actions
        assert any("git" in s.lower() or "commit" in s.lower() for s in suggestions)

    def test_suggestions_limited_to_four(self, enhancer):
        """Test that suggestions are limited to 4."""
        response = Mock(spec=ClaudeResponse)
        response.content = "TODO error test git install performance function dependency"
        response.is_error = False
        response.tools_used = [
            {"name": "Write"},
            {"name": "Edit"},
            {"name": "Read"},
            {"name": "Bash"},
        ]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        assert len(suggestions) <= 4

    def test_suggestions_no_duplicates(self, enhancer):
        """Test that suggestions contain no duplicates."""
        response = Mock(spec=ClaudeResponse)
        response.content = "test test test"
        response.is_error = False
        response.tools_used = [{"name": "Edit"}, {"name": "Edit"}]
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        # Check for uniqueness
        assert len(suggestions) == len(set(suggestions))

    def test_suggestions_prioritize_errors(self, enhancer):
        """Test that error-related suggestions are prioritized."""
        response = Mock(spec=ClaudeResponse)
        response.content = "Error occurred. Also consider adding tests."
        response.is_error = False
        response.tools_used = []
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        suggestions = enhancer.generate_follow_up_suggestions(response, context)

        # Should have suggestions
        assert len(suggestions) > 0
        # At least one suggestion should be error-related (likely prioritized first)
        assert any("error" in s.lower() or "debug" in s.lower() or "fix" in s.lower() for s in suggestions)


class TestFollowUpKeyboard:
    """Test follow-up keyboard creation."""

    def test_create_keyboard_with_suggestions(self, enhancer):
        """Test creating keyboard with suggestions."""
        suggestions = ["Add tests", "Review code", "Check errors"]
        keyboard = enhancer.create_follow_up_keyboard(suggestions)

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Should have 3 suggestion rows + 1 control row
        assert len(keyboard.inline_keyboard) == 4

    def test_create_keyboard_limits_suggestions(self, enhancer):
        """Test keyboard limits suggestions to 4."""
        suggestions = ["S1", "S2", "S3", "S4", "S5", "S6"]
        keyboard = enhancer.create_follow_up_keyboard(suggestions)

        # Should have 4 suggestion rows + 1 control row = 5 total
        assert len(keyboard.inline_keyboard) == 5

    def test_create_keyboard_with_empty_suggestions(self, enhancer):
        """Test creating keyboard with no suggestions."""
        keyboard = enhancer.create_follow_up_keyboard([])

        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) == 0

    def test_keyboard_has_control_buttons(self, enhancer):
        """Test keyboard includes control buttons."""
        suggestions = ["Test suggestion"]
        keyboard = enhancer.create_follow_up_keyboard(suggestions)

        # Last row should have control buttons
        last_row = keyboard.inline_keyboard[-1]
        assert len(last_row) == 2  # Continue and End buttons

        # Check callback data
        assert any("continue" in btn.callback_data for btn in last_row)
        assert any("end" in btn.callback_data for btn in last_row)

    def test_keyboard_suggestion_callback_format(self, enhancer):
        """Test suggestion buttons have correct callback format."""
        suggestions = ["Add tests"]
        keyboard = enhancer.create_follow_up_keyboard(suggestions)

        # First button should be suggestion
        first_button = keyboard.inline_keyboard[0][0]
        assert first_button.callback_data.startswith("followup:")
        assert "💡" in first_button.text


class TestShouldShowSuggestions:
    """Test logic for when to show suggestions."""

    def test_show_suggestions_for_tool_usage(self, enhancer):
        """Test suggestions shown when tools were used."""
        response = Mock(spec=ClaudeResponse)
        response.is_error = False
        response.tools_used = [{"name": "Edit"}]
        response.content = "Short response"

        assert enhancer.should_show_suggestions(response) is True

    def test_hide_suggestions_for_errors(self, enhancer, error_response):
        """Test suggestions hidden for error responses."""
        assert enhancer.should_show_suggestions(error_response) is False

    def test_show_suggestions_for_long_responses(self, enhancer):
        """Test suggestions shown for long responses."""
        response = Mock(spec=ClaudeResponse)
        response.is_error = False
        response.tools_used = []
        response.content = "x" * 250  # Longer than 200 chars

        assert enhancer.should_show_suggestions(response) is True

    def test_hide_suggestions_for_short_responses(self, enhancer):
        """Test suggestions hidden for short responses without tools."""
        response = Mock(spec=ClaudeResponse)
        response.is_error = False
        response.tools_used = []
        response.content = "OK"

        assert enhancer.should_show_suggestions(response) is False

    def test_show_suggestions_for_actionable_content(self, enhancer):
        """Test suggestions shown for actionable content."""
        actionable_keywords = [
            "todo", "fixme", "next", "consider", "you can",
            "try", "test", "check", "verify", "review"
        ]

        for keyword in actionable_keywords:
            response = Mock(spec=ClaudeResponse)
            response.is_error = False
            response.tools_used = []
            response.content = f"Short {keyword} response"

            assert enhancer.should_show_suggestions(response) is True


class TestFormatResponseWithSuggestions:
    """Test response formatting with suggestions."""

    def test_format_response_basic(self, enhancer, sample_response):
        """Test basic response formatting."""
        context = ConversationContext(user_id=123456, conversation_turn=0)
        content, keyboard = enhancer.format_response_with_suggestions(
            sample_response, context
        )

        assert isinstance(content, str)
        assert sample_response.content in content

    def test_format_response_truncates_long_content(self, enhancer):
        """Test that long content is truncated."""
        response = Mock(spec=ClaudeResponse)
        response.session_id = "test"
        response.is_error = False
        response.tools_used = []
        response.content = "x" * 5000
        response.cost = 0.01

        context = ConversationContext(user_id=123456)
        content, keyboard = enhancer.format_response_with_suggestions(
            response, context, max_content_length=100
        )

        assert len(content) <= 150  # Allow for truncation message
        assert "truncated" in content.lower()

    def test_format_response_adds_session_info_on_first_turn(self, enhancer, sample_response):
        """Test session info added on first turn."""
        context = ConversationContext(user_id=123456, conversation_turn=1)
        content, keyboard = enhancer.format_response_with_suggestions(
            sample_response, context
        )

        assert "Session:" in content or "session" in content.lower()

    def test_format_response_adds_cost_info(self, enhancer):
        """Test cost info added for significant costs."""
        response = Mock(spec=ClaudeResponse)
        response.session_id = "test"
        response.is_error = False
        response.tools_used = []
        response.content = "Response"
        response.cost = 0.05  # Significant cost

        context = ConversationContext(user_id=123456)
        content, keyboard = enhancer.format_response_with_suggestions(response, context)

        assert "Cost:" in content or "$" in content

    def test_format_response_no_cost_info_for_small_cost(self, enhancer):
        """Test no cost info for insignificant costs."""
        response = Mock(spec=ClaudeResponse)
        response.session_id = "test"
        response.is_error = False
        response.tools_used = []
        response.content = "Response"
        response.cost = 0.001  # Very small cost

        context = ConversationContext(user_id=123456)
        content, keyboard = enhancer.format_response_with_suggestions(response, context)

        # Should not include cost info for costs <= 0.01
        assert "$0.0010" not in content

    def test_format_response_includes_keyboard(self, enhancer, sample_response):
        """Test that keyboard is included when appropriate."""
        context = ConversationContext(user_id=123456)
        content, keyboard = enhancer.format_response_with_suggestions(
            sample_response, context
        )

        # Should have keyboard since tools were used
        assert keyboard is not None
        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_format_response_no_keyboard_for_errors(self, enhancer, error_response):
        """Test no keyboard for error responses."""
        context = ConversationContext(user_id=123456)
        content, keyboard = enhancer.format_response_with_suggestions(
            error_response, context
        )

        # Should not have keyboard for errors
        assert keyboard is None


class TestConversationEnhancerMultipleUsers:
    """Test enhancer with multiple users."""

    def test_separate_contexts_for_different_users(self, enhancer):
        """Test that different users have separate contexts."""
        context1 = enhancer.get_or_create_context(111111)
        context2 = enhancer.get_or_create_context(222222)

        assert context1 is not context2
        assert context1.user_id == 111111
        assert context2.user_id == 222222

    def test_clear_context_only_affects_target_user(self, enhancer):
        """Test clearing context only affects target user."""
        enhancer.get_or_create_context(111111)
        enhancer.get_or_create_context(222222)

        enhancer.clear_context(111111)

        assert 111111 not in enhancer.conversation_contexts
        assert 222222 in enhancer.conversation_contexts
