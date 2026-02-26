"""Tests for SessionMemoryService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.claude.memory import _MAX_TRANSCRIPT_CHARS, SessionMemoryService
from src.storage.models import MessageModel, SessionMemoryModel


def _make_message(
    prompt: str,
    response: str = "ok",
    session_id: str = "sess-1",
    user_id: int = 123,
) -> MessageModel:
    """Create a MessageModel for testing."""
    return MessageModel(
        session_id=session_id,
        user_id=user_id,
        timestamp=datetime.now(UTC),
        prompt=prompt,
        response=response,
    )


def _make_memory(
    summary: str,
    session_id: str = "sess-1",
    user_id: int = 123,
    project_path: str = "/test/project",
    created_at: datetime = None,
) -> SessionMemoryModel:
    """Create a SessionMemoryModel for testing."""
    return SessionMemoryModel(
        user_id=user_id,
        project_path=project_path,
        session_id=session_id,
        summary=summary,
        is_active=True,
        created_at=created_at or datetime.now(UTC),
        id=1,
    )


@pytest.fixture
def mock_storage():
    """Create mock storage with session_memories and messages repositories."""
    storage = MagicMock()
    storage.messages = MagicMock()
    storage.messages.get_session_messages = AsyncMock()
    storage.session_memories = MagicMock()
    storage.session_memories.save_memory = AsyncMock(return_value=1)
    storage.session_memories.get_active_memories = AsyncMock(return_value=[])
    storage.session_memories.deactivate_old_memories = AsyncMock(return_value=0)
    return storage


@pytest.fixture
def mock_sdk_manager():
    """Create mock SDK manager."""
    sdk = MagicMock()
    response = MagicMock()
    response.content = "- User worked on feature X\n- Decided to use approach Y"
    sdk.execute_command = AsyncMock(return_value=response)
    return sdk


@pytest.fixture
def mock_config(tmp_path):
    """Create mock config with session memory settings."""
    config = MagicMock()
    config.session_memory_min_messages = 3
    config.session_memory_max_count = 5
    config.approved_directory = str(tmp_path)
    return config


@pytest.fixture
def service(mock_storage, mock_sdk_manager, mock_config):
    """Create SessionMemoryService with mocked dependencies."""
    return SessionMemoryService(
        storage=mock_storage,
        sdk_manager=mock_sdk_manager,
        config=mock_config,
    )


class TestSummarizeSession:
    """Tests for summarize_session method."""

    @pytest.mark.asyncio
    async def test_summarize_session_generates_and_stores_summary(
        self, service, mock_storage, mock_sdk_manager
    ):
        """When session has enough messages, generates summary and stores it."""
        messages = [
            _make_message("How do I fix the bug?", "Try checking the logs."),
            _make_message("What about tests?", "Add unit tests for coverage."),
            _make_message("Thanks!", "You're welcome."),
        ]
        mock_storage.messages.get_session_messages.return_value = messages

        result = await service.summarize_session(
            session_id="sess-1",
            user_id=123,
            project_path="/test/project",
        )

        assert result is not None
        assert result == mock_sdk_manager.execute_command.return_value.content

        # Verify storage calls
        mock_storage.messages.get_session_messages.assert_awaited_once_with(
            "sess-1", limit=50
        )
        mock_storage.session_memories.save_memory.assert_awaited_once_with(
            user_id=123,
            project_path="/test/project",
            session_id="sess-1",
            summary=result,
        )
        mock_storage.session_memories.deactivate_old_memories.assert_awaited_once_with(
            user_id=123,
            project_path="/test/project",
            keep_count=5,
        )

        # Verify SDK was called to generate summary
        mock_sdk_manager.execute_command.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_summarize_session_too_few_messages_returns_none(
        self, service, mock_storage, mock_sdk_manager
    ):
        """When session has fewer messages than min threshold, returns None."""
        messages = [
            _make_message("Hello", "Hi there."),
            _make_message("Bye", "Goodbye."),
        ]
        mock_storage.messages.get_session_messages.return_value = messages

        result = await service.summarize_session(
            session_id="sess-1",
            user_id=123,
            project_path="/test/project",
        )

        assert result is None

        # Should NOT call SDK or save anything
        mock_sdk_manager.execute_command.assert_not_awaited()
        mock_storage.session_memories.save_memory.assert_not_awaited()
        mock_storage.session_memories.deactivate_old_memories.assert_not_awaited()


class TestGetMemoryContext:
    """Tests for get_memory_context method."""

    @pytest.mark.asyncio
    async def test_get_memory_context_formats_memories(self, service, mock_storage):
        """When memories exist, formats them into system prompt text."""
        ts = datetime(2025, 6, 15, 10, 30, 0)
        memories = [
            _make_memory(
                "User worked on authentication module.",
                session_id="sess-1",
                created_at=ts,
            ),
            _make_memory(
                "User refactored database layer.",
                session_id="sess-2",
                created_at=ts,
            ),
        ]
        mock_storage.session_memories.get_active_memories.return_value = memories

        result = await service.get_memory_context(
            user_id=123,
            project_path="/test/project",
        )

        assert result is not None
        assert "Previous Session Context" in result
        assert "User worked on authentication module." in result
        assert "User refactored database layer." in result
        assert ts.isoformat() in result

        mock_storage.session_memories.get_active_memories.assert_awaited_once_with(
            user_id=123,
            project_path="/test/project",
            limit=5,
        )

    @pytest.mark.asyncio
    async def test_get_memory_context_returns_none_when_no_memories(
        self, service, mock_storage
    ):
        """When no memories exist, returns None."""
        mock_storage.session_memories.get_active_memories.return_value = []

        result = await service.get_memory_context(
            user_id=123,
            project_path="/test/project",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_memory_context_truncates_long_output(
        self, service, mock_storage
    ):
        """When combined memory text exceeds 2000 chars, truncates it."""
        long_summary = "A" * 1500
        memories = [
            _make_memory(long_summary, session_id="sess-1"),
            _make_memory(long_summary, session_id="sess-2"),
        ]
        mock_storage.session_memories.get_active_memories.return_value = memories

        result = await service.get_memory_context(
            user_id=123,
            project_path="/test/project",
        )

        assert result is not None
        assert result.endswith("... (truncated)")
        # 2000 chars + the "... (truncated)" suffix
        assert len(result) == 2000 + len("\n... (truncated)")


class TestBuildTranscript:
    """Tests for _build_transcript method."""

    def test_build_transcript_chronological_order(self, service):
        """Messages are reversed to chronological order in transcript."""
        # Messages come newest-first from DB
        messages = [
            _make_message("Third question", "Third answer"),
            _make_message("Second question", "Second answer"),
            _make_message("First question", "First answer"),
        ]

        transcript = service._build_transcript(messages)

        # Should be in chronological order (reversed)
        lines = transcript.split("\n\n")
        assert "First question" in lines[0]
        assert "Second question" in lines[1]
        assert "Third question" in lines[2]

    def test_build_transcript_truncates_long_responses(self, service):
        """Responses longer than 500 chars are truncated."""
        long_response = "x" * 600
        messages = [
            _make_message("Question", long_response),
        ]

        transcript = service._build_transcript(messages)

        # The response should be truncated at 500 chars + "..."
        assert "x" * 500 + "..." in transcript
        assert "x" * 501 not in transcript

    def test_build_transcript_respects_char_limit(self, service):
        """Transcript stops adding messages when char limit is reached."""
        # Create enough messages to exceed _MAX_TRANSCRIPT_CHARS
        messages = []
        for i in range(100):
            messages.append(
                _make_message(
                    f"Question {i} " + "padding" * 50,
                    f"Answer {i} " + "padding" * 50,
                )
            )
        # Reverse so they appear newest-first (DB order)
        messages = list(reversed(messages))

        transcript = service._build_transcript(messages)

        assert len(transcript) <= _MAX_TRANSCRIPT_CHARS

    def test_build_transcript_handles_none_response(self, service):
        """Messages with no response only include the prompt."""
        messages = [
            _make_message("Question", response=None),
        ]
        # MessageModel has response as Optional[str], set to None
        messages[0].response = None

        transcript = service._build_transcript(messages)

        assert "User: Question" in transcript
        assert "Assistant:" not in transcript
