"""Tests for quick actions feature."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.bot.features.quick_actions import QuickAction, QuickActionManager
from src.storage.models import SessionModel


@pytest.fixture
def quick_action_manager():
    """Create quick action manager instance."""
    return QuickActionManager()


@pytest.fixture
def sample_session():
    """Create sample session for testing."""
    session = Mock(spec=SessionModel)
    session.id = "test-session-123"
    session.user_id = 12345
    session.project_path = "/test/project"
    session.context = {
        "recent_messages": [
            {"role": "user", "content": "Run the tests"},
            {"role": "assistant", "content": "Running pytest..."},
        ]
    }
    return session


@pytest.fixture
def empty_session():
    """Create session with no context."""
    session = Mock(spec=SessionModel)
    session.id = "empty-session"
    session.user_id = 12345
    session.context = {}
    return session


class TestQuickActionDataClass:
    """Test QuickAction dataclass."""

    def test_quick_action_creation(self):
        """Test creating QuickAction object."""
        action = QuickAction(
            id="test",
            name="Test Action",
            description="Test description",
            command="test_command",
            icon="🧪",
            category="testing",
            context_required=["has_tests"],
            priority=10,
        )

        assert action.id == "test"
        assert action.name == "Test Action"
        assert action.description == "Test description"
        assert action.command == "test_command"
        assert action.icon == "🧪"
        assert action.category == "testing"
        assert action.context_required == ["has_tests"]
        assert action.priority == 10


class TestQuickActionManagerInitialization:
    """Test QuickActionManager initialization."""

    def test_initialization(self, quick_action_manager):
        """Test manager is properly initialized."""
        assert quick_action_manager.actions is not None
        assert len(quick_action_manager.actions) > 0
        assert quick_action_manager.logger is not None

    def test_default_actions_created(self, quick_action_manager):
        """Test default actions are created."""
        expected_actions = [
            "test",
            "install",
            "format",
            "lint",
            "security",
            "optimize",
            "document",
            "refactor",
        ]

        for action_id in expected_actions:
            assert action_id in quick_action_manager.actions
            action = quick_action_manager.actions[action_id]
            assert isinstance(action, QuickAction)
            assert action.id == action_id
            assert len(action.name) > 0
            assert len(action.description) > 0
            assert len(action.command) > 0
            assert len(action.icon) > 0
            assert len(action.category) > 0

    def test_actions_have_priorities(self, quick_action_manager):
        """Test all actions have priority values."""
        for action in quick_action_manager.actions.values():
            assert isinstance(action.priority, int)
            assert action.priority >= 0

    def test_actions_have_context_requirements(self, quick_action_manager):
        """Test all actions have context requirements."""
        for action in quick_action_manager.actions.values():
            assert isinstance(action.context_required, list)
            assert len(action.context_required) > 0


class TestGetSuggestions:
    """Test getting quick action suggestions."""

    @pytest.mark.asyncio
    async def test_get_suggestions_with_test_context(
        self, quick_action_manager, sample_session
    ):
        """Test getting suggestions when tests are detected."""
        # Session mentions tests
        sample_session.context = {
            "recent_messages": [
                {"role": "user", "content": "Run pytest on the project"}
            ]
        }

        suggestions = await quick_action_manager.get_suggestions(sample_session)

        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        # Test action should be suggested
        assert any(s.id == "test" for s in suggestions)

    @pytest.mark.asyncio
    async def test_get_suggestions_with_package_manager_context(
        self, quick_action_manager, sample_session
    ):
        """Test suggestions when package manager is detected."""
        sample_session.context = {
            "recent_messages": [{"role": "user", "content": "Install dependencies with npm"}]
        }

        suggestions = await quick_action_manager.get_suggestions(sample_session)

        # Install action should be suggested
        assert any(s.id == "install" for s in suggestions)

    @pytest.mark.asyncio
    async def test_get_suggestions_with_formatter_context(
        self, quick_action_manager, sample_session
    ):
        """Test suggestions when formatter is detected."""
        sample_session.context = {
            "recent_messages": [{"role": "user", "content": "Format code with black"}]
        }

        suggestions = await quick_action_manager.get_suggestions(sample_session)

        # Format action should be suggested
        assert any(s.id == "format" for s in suggestions)

    @pytest.mark.asyncio
    async def test_get_suggestions_with_linter_context(
        self, quick_action_manager, sample_session
    ):
        """Test suggestions when linter is detected."""
        sample_session.context = {
            "recent_messages": [{"role": "user", "content": "Run flake8 to check code"}]
        }

        suggestions = await quick_action_manager.get_suggestions(sample_session)

        # Lint action should be suggested
        assert any(s.id == "lint" for s in suggestions)

    @pytest.mark.asyncio
    async def test_get_suggestions_respects_limit(
        self, quick_action_manager, sample_session
    ):
        """Test that suggestions respect the limit parameter."""
        suggestions = await quick_action_manager.get_suggestions(sample_session, limit=3)

        assert len(suggestions) <= 3

    @pytest.mark.asyncio
    async def test_get_suggestions_sorted_by_priority(
        self, quick_action_manager, sample_session
    ):
        """Test that suggestions are sorted by priority."""
        # Set up context that matches multiple actions
        sample_session.context = {
            "recent_messages": [
                {
                    "role": "user",
                    "content": "Run tests with pytest, format with black, and run flake8",
                }
            ]
        }

        suggestions = await quick_action_manager.get_suggestions(sample_session)

        # Verify sorted by priority (descending)
        priorities = [s.priority for s in suggestions]
        assert priorities == sorted(priorities, reverse=True)

    @pytest.mark.asyncio
    async def test_get_suggestions_with_empty_context(
        self, quick_action_manager, empty_session
    ):
        """Test suggestions with empty context."""
        suggestions = await quick_action_manager.get_suggestions(empty_session)

        # Should still return some suggestions (actions with minimal requirements)
        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_get_suggestions_error_handling(self, quick_action_manager):
        """Test error handling in get_suggestions."""
        # Pass invalid session
        invalid_session = Mock()
        invalid_session.context = None  # Will cause error

        # Should not raise, returns empty list on error
        suggestions = await quick_action_manager.get_suggestions(invalid_session)
        assert suggestions == []


class TestContextAnalysis:
    """Test session context analysis."""

    @pytest.mark.asyncio
    async def test_analyze_context_default_values(
        self, quick_action_manager, empty_session
    ):
        """Test default context values."""
        context = await quick_action_manager._analyze_context(empty_session)

        assert context["has_code"] is True  # Default assumption
        assert context["has_tests"] is False
        assert context["has_package_manager"] is False
        assert context["has_formatter"] is False
        assert context["has_linter"] is False
        assert context["has_dependencies"] is False

    @pytest.mark.asyncio
    async def test_analyze_context_detects_tests(
        self, quick_action_manager, sample_session
    ):
        """Test detection of test indicators."""
        test_keywords = ["test", "pytest", "unittest", "jest", "mocha"]

        for keyword in test_keywords:
            sample_session.context = {
                "recent_messages": [{"role": "user", "content": f"Run {keyword}"}]
            }

            context = await quick_action_manager._analyze_context(sample_session)
            assert context["has_tests"] is True

    @pytest.mark.asyncio
    async def test_analyze_context_detects_package_managers(
        self, quick_action_manager, sample_session
    ):
        """Test detection of package manager indicators."""
        package_managers = ["pip", "poetry", "npm", "yarn"]

        for pm in package_managers:
            sample_session.context = {
                "recent_messages": [{"role": "user", "content": f"Install with {pm}"}]
            }

            context = await quick_action_manager._analyze_context(sample_session)
            assert context["has_package_manager"] is True
            assert context["has_dependencies"] is True

    @pytest.mark.asyncio
    async def test_analyze_context_detects_formatters(
        self, quick_action_manager, sample_session
    ):
        """Test detection of formatter indicators."""
        formatters = ["black", "prettier", "format"]

        for formatter in formatters:
            sample_session.context = {
                "recent_messages": [{"role": "user", "content": f"Run {formatter}"}]
            }

            context = await quick_action_manager._analyze_context(sample_session)
            assert context["has_formatter"] is True

    @pytest.mark.asyncio
    async def test_analyze_context_detects_linters(
        self, quick_action_manager, sample_session
    ):
        """Test detection of linter indicators."""
        linters = ["flake8", "pylint", "eslint", "mypy"]

        for linter in linters:
            sample_session.context = {
                "recent_messages": [{"role": "user", "content": f"Check with {linter}"}]
            }

            context = await quick_action_manager._analyze_context(sample_session)
            assert context["has_linter"] is True

    @pytest.mark.asyncio
    async def test_analyze_context_case_insensitive(
        self, quick_action_manager, sample_session
    ):
        """Test context analysis is case insensitive."""
        sample_session.context = {
            "recent_messages": [{"role": "user", "content": "Run PYTEST tests"}]
        }

        context = await quick_action_manager._analyze_context(sample_session)
        assert context["has_tests"] is True

    @pytest.mark.asyncio
    async def test_analyze_context_multiple_indicators(
        self, quick_action_manager, sample_session
    ):
        """Test detection of multiple indicators."""
        sample_session.context = {
            "recent_messages": [
                {
                    "role": "user",
                    "content": "Install dependencies with pip and run pytest",
                }
            ]
        }

        context = await quick_action_manager._analyze_context(sample_session)
        assert context["has_tests"] is True
        assert context["has_package_manager"] is True
        assert context["has_dependencies"] is True


class TestActionAvailability:
    """Test checking if actions are available."""

    def test_is_action_available_all_requirements_met(self, quick_action_manager):
        """Test action is available when all requirements are met."""
        action = QuickAction(
            id="test",
            name="Test",
            description="Test",
            command="test",
            icon="🧪",
            category="testing",
            context_required=["has_tests", "has_code"],
            priority=10,
        )

        context = {"has_tests": True, "has_code": True, "has_formatter": False}

        assert quick_action_manager._is_action_available(action, context) is True

    def test_is_action_available_missing_requirement(self, quick_action_manager):
        """Test action is not available when requirement is missing."""
        action = QuickAction(
            id="test",
            name="Test",
            description="Test",
            command="test",
            icon="🧪",
            category="testing",
            context_required=["has_tests"],
            priority=10,
        )

        context = {"has_tests": False, "has_code": True}

        assert quick_action_manager._is_action_available(action, context) is False

    def test_is_action_available_no_requirements(self, quick_action_manager):
        """Test action with no requirements is always available."""
        action = QuickAction(
            id="test",
            name="Test",
            description="Test",
            command="test",
            icon="🧪",
            category="testing",
            context_required=[],
            priority=10,
        )

        context = {}

        assert quick_action_manager._is_action_available(action, context) is True

    def test_is_action_available_context_key_missing(self, quick_action_manager):
        """Test action is not available when context key is missing."""
        action = QuickAction(
            id="test",
            name="Test",
            description="Test",
            command="test",
            icon="🧪",
            category="testing",
            context_required=["has_something"],
            priority=10,
        )

        context = {"has_other_thing": True}

        # Missing key should be treated as False
        assert quick_action_manager._is_action_available(action, context) is False


class TestInlineKeyboardCreation:
    """Test creating inline keyboard for actions."""

    def test_create_inline_keyboard_basic(self, quick_action_manager):
        """Test creating basic inline keyboard."""
        actions = [
            QuickAction(
                id="test1",
                name="Test 1",
                description="Desc",
                command="cmd1",
                icon="🧪",
                category="cat",
                context_required=[],
                priority=10,
            ),
            QuickAction(
                id="test2",
                name="Test 2",
                description="Desc",
                command="cmd2",
                icon="📦",
                category="cat",
                context_required=[],
                priority=9,
            ),
        ]

        keyboard = quick_action_manager.create_inline_keyboard(actions)

        # Verify keyboard structure
        assert keyboard.inline_keyboard is not None
        assert len(keyboard.inline_keyboard) > 0

    def test_create_inline_keyboard_with_columns(self, quick_action_manager):
        """Test creating keyboard with specific column count."""
        actions = [
            QuickAction(
                id=f"test{i}",
                name=f"Test {i}",
                description="Desc",
                command=f"cmd{i}",
                icon="🧪",
                category="cat",
                context_required=[],
                priority=10 - i,
            )
            for i in range(6)
        ]

        # Create with 3 columns
        keyboard = quick_action_manager.create_inline_keyboard(actions, columns=3)

        # Should have 2 rows (6 actions / 3 columns)
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 3
        assert len(keyboard.inline_keyboard[1]) == 3

    def test_create_inline_keyboard_button_format(self, quick_action_manager):
        """Test button format includes icon and name."""
        action = QuickAction(
            id="test",
            name="Run Tests",
            description="Desc",
            command="test",
            icon="🧪",
            category="testing",
            context_required=[],
            priority=10,
        )

        keyboard = quick_action_manager.create_inline_keyboard([action])

        button = keyboard.inline_keyboard[0][0]
        assert "🧪" in button.text
        assert "Run Tests" in button.text
        assert button.callback_data == "quick_action:test"

    def test_create_inline_keyboard_empty_actions(self, quick_action_manager):
        """Test creating keyboard with no actions."""
        keyboard = quick_action_manager.create_inline_keyboard([])

        # Should create empty keyboard
        assert len(keyboard.inline_keyboard) == 0

    def test_create_inline_keyboard_single_action(self, quick_action_manager):
        """Test creating keyboard with single action."""
        action = QuickAction(
            id="test",
            name="Test",
            description="Desc",
            command="test",
            icon="🧪",
            category="cat",
            context_required=[],
            priority=10,
        )

        keyboard = quick_action_manager.create_inline_keyboard([action])

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1

    def test_create_inline_keyboard_odd_number_actions(self, quick_action_manager):
        """Test creating keyboard with odd number of actions."""
        actions = [
            QuickAction(
                id=f"test{i}",
                name=f"Test {i}",
                description="Desc",
                command=f"cmd{i}",
                icon="🧪",
                category="cat",
                context_required=[],
                priority=10,
            )
            for i in range(5)
        ]

        keyboard = quick_action_manager.create_inline_keyboard(actions, columns=2)

        # 5 actions with 2 columns = 3 rows (2, 2, 1)
        assert len(keyboard.inline_keyboard) == 3
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2
        assert len(keyboard.inline_keyboard[2]) == 1


class TestExecuteAction:
    """Test action execution."""

    @pytest.mark.asyncio
    async def test_execute_action_success(self, quick_action_manager, sample_session):
        """Test successful action execution."""
        command = await quick_action_manager.execute_action("test", sample_session)

        assert command == "test"  # Returns the command

    @pytest.mark.asyncio
    async def test_execute_action_unknown_id(self, quick_action_manager, sample_session):
        """Test executing unknown action."""
        with pytest.raises(ValueError, match="Unknown action"):
            await quick_action_manager.execute_action("unknown_action", sample_session)

    @pytest.mark.asyncio
    async def test_execute_action_with_callback(self, quick_action_manager, sample_session):
        """Test executing action with callback."""
        callback = AsyncMock()

        command = await quick_action_manager.execute_action(
            "test", sample_session, callback=callback
        )

        # Command should still be returned
        assert command == "test"

    @pytest.mark.asyncio
    async def test_execute_all_default_actions(
        self, quick_action_manager, sample_session
    ):
        """Test executing all default actions."""
        for action_id in quick_action_manager.actions.keys():
            command = await quick_action_manager.execute_action(
                action_id, sample_session
            )

            # Each should return its command
            expected_command = quick_action_manager.actions[action_id].command
            assert command == expected_command


class TestCompleteWorkflow:
    """Test complete workflows."""

    @pytest.mark.asyncio
    async def test_full_suggestion_workflow(self, quick_action_manager, sample_session):
        """Test complete workflow from context to suggestions to execution."""
        # Set up session with test context
        sample_session.context = {
            "recent_messages": [
                {"role": "user", "content": "Run pytest and format with black"}
            ]
        }

        # Get suggestions
        suggestions = await quick_action_manager.get_suggestions(sample_session)

        assert len(suggestions) > 0

        # Create keyboard
        keyboard = quick_action_manager.create_inline_keyboard(suggestions)
        assert keyboard.inline_keyboard is not None

        # Execute first suggestion
        first_action = suggestions[0]
        command = await quick_action_manager.execute_action(
            first_action.id, sample_session
        )

        assert isinstance(command, str)
        assert len(command) > 0

    @pytest.mark.asyncio
    async def test_suggestions_for_different_project_types(self, quick_action_manager):
        """Test suggestions adapt to different project types."""
        # Python project
        python_session = Mock(spec=SessionModel)
        python_session.id = "python-session"
        python_session.user_id = 123
        python_session.context = {
            "recent_messages": [
                {"role": "user", "content": "Run pytest and check with mypy"}
            ]
        }

        python_suggestions = await quick_action_manager.get_suggestions(python_session)

        # JavaScript project
        js_session = Mock(spec=SessionModel)
        js_session.id = "js-session"
        js_session.user_id = 123
        js_session.context = {
            "recent_messages": [
                {"role": "user", "content": "Install with npm and run jest"}
            ]
        }

        js_suggestions = await quick_action_manager.get_suggestions(js_session)

        # Both should get suggestions, may differ based on context
        assert len(python_suggestions) > 0
        assert len(js_suggestions) > 0


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_session_with_none_context(self, quick_action_manager):
        """Test handling session with None context."""
        session = Mock(spec=SessionModel)
        session.id = "test"
        session.context = None

        # Should not crash
        suggestions = await quick_action_manager.get_suggestions(session)
        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_context_with_none_messages(self, quick_action_manager):
        """Test handling context with None messages."""
        session = Mock(spec=SessionModel)
        session.id = "test"
        session.context = {"recent_messages": None}

        # Should not crash
        context = await quick_action_manager._analyze_context(session)
        assert isinstance(context, dict)

    @pytest.mark.asyncio
    async def test_messages_with_missing_content(self, quick_action_manager):
        """Test handling messages with missing content."""
        session = Mock(spec=SessionModel)
        session.id = "test"
        session.context = {
            "recent_messages": [
                {"role": "user"},  # No content
                {"role": "user", "content": None},  # None content
            ]
        }

        # Should not crash
        context = await quick_action_manager._analyze_context(session)
        assert isinstance(context, dict)

    def test_action_with_empty_context_required(self, quick_action_manager):
        """Test action with empty context requirements."""
        action = QuickAction(
            id="test",
            name="Test",
            description="Desc",
            command="test",
            icon="🧪",
            category="cat",
            context_required=[],
            priority=10,
        )

        # Should be available in any context
        assert quick_action_manager._is_action_available(action, {}) is True
        assert (
            quick_action_manager._is_action_available(
                action, {"has_anything": True}
            )
            is True
        )
