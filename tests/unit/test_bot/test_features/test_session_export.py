"""Tests for session export feature."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.bot.features.session_export import (
    ExportFormat,
    ExportedSession,
    SessionExporter,
)
from src.storage.facade import Storage


@pytest.fixture
def mock_storage():
    """Create mock storage."""
    storage = Mock(spec=Storage)
    return storage


@pytest.fixture
def session_exporter(mock_storage):
    """Create session exporter instance."""
    return SessionExporter(mock_storage)


@pytest.fixture
def sample_session():
    """Create sample session data."""
    return {
        "id": "test-session-123",
        "user_id": 12345,
        "created_at": datetime(2024, 1, 1, 10, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0),
        "project_path": "/test/project",
    }


@pytest.fixture
def sample_messages():
    """Create sample messages."""
    return [
        {
            "id": "msg1",
            "role": "user",
            "content": "Hello, can you help me?",
            "created_at": datetime(2024, 1, 1, 10, 5, 0),
        },
        {
            "id": "msg2",
            "role": "assistant",
            "content": "Of course! I'd be happy to help.",
            "created_at": datetime(2024, 1, 1, 10, 6, 0),
        },
        {
            "id": "msg3",
            "role": "user",
            "content": "Can you explain async functions?",
            "created_at": datetime(2024, 1, 1, 10, 7, 0),
        },
    ]


class TestExportFormatEnum:
    """Test ExportFormat enum."""

    def test_export_format_values(self):
        """Test export format enum values."""
        assert ExportFormat.MARKDOWN.value == "markdown"
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.HTML.value == "html"


class TestExportedSessionDataClass:
    """Test ExportedSession dataclass."""

    def test_exported_session_creation(self):
        """Test creating ExportedSession object."""
        exported = ExportedSession(
            format=ExportFormat.MARKDOWN,
            content="# Test Content",
            filename="session_123.md",
            mime_type="text/markdown",
            size_bytes=100,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        assert exported.format == ExportFormat.MARKDOWN
        assert exported.content == "# Test Content"
        assert exported.filename == "session_123.md"
        assert exported.mime_type == "text/markdown"
        assert exported.size_bytes == 100
        assert isinstance(exported.created_at, datetime)


class TestSessionExporterInitialization:
    """Test SessionExporter initialization."""

    def test_initialization(self, session_exporter, mock_storage):
        """Test exporter is properly initialized."""
        assert session_exporter.storage == mock_storage


class TestExportMarkdown:
    """Test Markdown export functionality."""

    @pytest.mark.asyncio
    async def test_export_session_markdown(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test exporting session as Markdown."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert isinstance(exported, ExportedSession)
        assert exported.format == ExportFormat.MARKDOWN
        assert exported.mime_type == "text/markdown"
        assert exported.filename.endswith(".md")
        assert "Claude Code Session Export" in exported.content
        assert "test-session-123" in exported.content

    @pytest.mark.asyncio
    async def test_markdown_export_includes_metadata(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test Markdown export includes session metadata."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert "Session ID:" in exported.content
        assert "Created:" in exported.content
        assert "Last Updated:" in exported.content
        assert "Message Count:" in exported.content

    @pytest.mark.asyncio
    async def test_markdown_export_includes_messages(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test Markdown export includes all messages."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        # Check all messages are present
        assert "Hello, can you help me?" in exported.content
        assert "Of course! I'd be happy to help." in exported.content
        assert "Can you explain async functions?" in exported.content

    @pytest.mark.asyncio
    async def test_markdown_export_distinguishes_roles(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test Markdown export distinguishes between user and assistant."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert "### You -" in exported.content
        assert "### Claude -" in exported.content

    @pytest.mark.asyncio
    async def test_markdown_export_without_updated_at(
        self, session_exporter, mock_storage, sample_messages
    ):
        """Test Markdown export when session has no updated_at."""
        session_no_update = {
            "id": "test-session-123",
            "user_id": 12345,
            "created_at": datetime(2024, 1, 1, 10, 0, 0),
            "updated_at": None,
        }

        mock_storage.get_session = AsyncMock(return_value=session_no_update)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        # Should not crash
        assert isinstance(exported, ExportedSession)


class TestExportJSON:
    """Test JSON export functionality."""

    @pytest.mark.asyncio
    async def test_export_session_json(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test exporting session as JSON."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.JSON
        )

        assert isinstance(exported, ExportedSession)
        assert exported.format == ExportFormat.JSON
        assert exported.mime_type == "application/json"
        assert exported.filename.endswith(".json")

        # Parse JSON to verify structure
        data = json.loads(exported.content)
        assert "session" in data
        assert "messages" in data

    @pytest.mark.asyncio
    async def test_json_export_session_structure(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test JSON export session structure."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.JSON
        )

        data = json.loads(exported.content)

        assert data["session"]["id"] == "test-session-123"
        assert data["session"]["user_id"] == 12345
        assert "created_at" in data["session"]
        assert data["session"]["message_count"] == 3

    @pytest.mark.asyncio
    async def test_json_export_messages_structure(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test JSON export messages structure."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.JSON
        )

        data = json.loads(exported.content)

        assert len(data["messages"]) == 3
        for msg in data["messages"]:
            assert "id" in msg
            assert "role" in msg
            assert "content" in msg
            assert "created_at" in msg

    @pytest.mark.asyncio
    async def test_json_export_datetime_serialization(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test JSON export properly serializes datetime objects."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.JSON
        )

        data = json.loads(exported.content)

        # Datetime should be ISO format strings
        assert isinstance(data["session"]["created_at"], str)
        assert "T" in data["session"]["created_at"]  # ISO format marker

    @pytest.mark.asyncio
    async def test_json_export_unicode_support(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test JSON export supports unicode characters."""
        unicode_messages = [
            {
                "id": "msg1",
                "role": "user",
                "content": "Hello 世界 🌍",
                "created_at": datetime(2024, 1, 1, 10, 0, 0),
            }
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=unicode_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.JSON
        )

        data = json.loads(exported.content)
        assert "世界" in data["messages"][0]["content"]
        assert "🌍" in data["messages"][0]["content"]


class TestExportHTML:
    """Test HTML export functionality."""

    @pytest.mark.asyncio
    async def test_export_session_html(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test exporting session as HTML."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.HTML
        )

        assert isinstance(exported, ExportedSession)
        assert exported.format == ExportFormat.HTML
        assert exported.mime_type == "text/html"
        assert exported.filename.endswith(".html")

    @pytest.mark.asyncio
    async def test_html_export_structure(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test HTML export has proper HTML structure."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.HTML
        )

        # Check HTML structure
        assert "<!DOCTYPE html>" in exported.content
        assert "<html" in exported.content
        assert "<head>" in exported.content
        assert "<body>" in exported.content
        assert "</html>" in exported.content

    @pytest.mark.asyncio
    async def test_html_export_includes_styles(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test HTML export includes CSS styles."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.HTML
        )

        assert "<style>" in exported.content
        assert "font-family" in exported.content
        assert "color" in exported.content

    @pytest.mark.asyncio
    async def test_html_export_responsive_meta(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test HTML export includes responsive viewport meta tag."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.HTML
        )

        assert 'name="viewport"' in exported.content

    @pytest.mark.asyncio
    async def test_html_export_includes_content(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test HTML export includes message content."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.HTML
        )

        # Messages should be in HTML (possibly with tags)
        assert "Hello" in exported.content or "help" in exported.content


class TestMarkdownToHTML:
    """Test Markdown to HTML conversion."""

    def test_markdown_to_html_headers(self, session_exporter):
        """Test conversion of markdown headers."""
        markdown = "# Main Header\n### Sub Header"
        html = session_exporter._markdown_to_html(markdown)

        assert "<h1>" in html
        assert "</h1>" in html
        assert "<h3>" in html
        assert "</h3>" in html

    def test_markdown_to_html_bold(self, session_exporter):
        """Test conversion of bold text."""
        markdown = "**bold text**"
        html = session_exporter._markdown_to_html(markdown)

        assert "<strong>bold text</strong>" in html

    def test_markdown_to_html_code(self, session_exporter):
        """Test conversion of inline code."""
        markdown = "`code snippet`"
        html = session_exporter._markdown_to_html(markdown)

        assert "<code>code snippet</code>" in html

    def test_markdown_to_html_horizontal_rule(self, session_exporter):
        """Test conversion of horizontal rules."""
        markdown = "Text\n\n---\n\nMore text"
        html = session_exporter._markdown_to_html(markdown)

        assert "<hr>" in html

    def test_markdown_to_html_paragraphs(self, session_exporter):
        """Test conversion creates paragraphs."""
        markdown = "First paragraph\n\nSecond paragraph"
        html = session_exporter._markdown_to_html(markdown)

        assert "<p>" in html
        assert "</p>" in html


class TestFilenameGeneration:
    """Test filename generation."""

    @pytest.mark.asyncio
    async def test_filename_includes_session_id(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test filename includes session ID."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        # Filename should include first 8 chars of session ID
        assert "test-ses" in exported.filename

    @pytest.mark.asyncio
    async def test_filename_includes_timestamp(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test filename includes timestamp."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        # Filename should include timestamp in format YYYYMMDD_HHMMSS
        assert "_" in exported.filename
        # Should have numbers
        assert any(char.isdigit() for char in exported.filename)

    @pytest.mark.asyncio
    async def test_filename_correct_extension(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test filename has correct extension for each format."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        # Test each format
        formats_and_extensions = [
            (ExportFormat.MARKDOWN, ".md"),
            (ExportFormat.JSON, ".json"),
            (ExportFormat.HTML, ".html"),
        ]

        for export_format, expected_ext in formats_and_extensions:
            exported = await session_exporter.export_session(
                12345, "test-session-123", export_format
            )
            assert exported.filename.endswith(expected_ext)


class TestSizeCalculation:
    """Test file size calculation."""

    @pytest.mark.asyncio
    async def test_size_bytes_calculated(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test size_bytes is correctly calculated."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        # Size should match content length in bytes
        expected_size = len(exported.content.encode())
        assert exported.size_bytes == expected_size

    @pytest.mark.asyncio
    async def test_size_bytes_for_unicode(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test size calculation handles unicode correctly."""
        unicode_messages = [
            {
                "id": "msg1",
                "role": "user",
                "content": "日本語テスト 🎌",
                "created_at": datetime(2024, 1, 1, 10, 0, 0),
            }
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=unicode_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        # Size should be in bytes (not character count)
        assert exported.size_bytes > len(exported.content)  # UTF-8 encoding


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_session_not_found(self, session_exporter, mock_storage):
        """Test handling when session is not found."""
        mock_storage.get_session = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Session .* not found"):
            await session_exporter.export_session(
                12345, "nonexistent", ExportFormat.MARKDOWN
            )

    @pytest.mark.asyncio
    async def test_unsupported_format(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test handling unsupported export format."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        # Create invalid format by patching
        with pytest.raises(ValueError, match="Unsupported export format"):
            # Use a mock that's not a valid ExportFormat
            invalid_format = Mock()
            invalid_format.value = "invalid"
            await session_exporter.export_session(
                12345, "test-session-123", invalid_format
            )

    @pytest.mark.asyncio
    async def test_empty_messages_list(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test handling export with no messages."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=[])

        # Should not crash
        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert isinstance(exported, ExportedSession)
        assert "Message Count: 0" in exported.content


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_very_long_messages(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test handling very long messages."""
        long_messages = [
            {
                "id": "msg1",
                "role": "user",
                "content": "A" * 10000,  # 10,000 character message
                "created_at": datetime(2024, 1, 1, 10, 0, 0),
            }
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=long_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert isinstance(exported, ExportedSession)
        assert len(exported.content) > 10000

    @pytest.mark.asyncio
    async def test_special_characters_in_content(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test handling special characters in message content."""
        special_messages = [
            {
                "id": "msg1",
                "role": "user",
                "content": "Test with <html> & special chars: <>\"'&",
                "created_at": datetime(2024, 1, 1, 10, 0, 0),
            }
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=special_messages)

        # Should not crash for any format
        for export_format in [
            ExportFormat.MARKDOWN,
            ExportFormat.JSON,
            ExportFormat.HTML,
        ]:
            exported = await session_exporter.export_session(
                12345, "test-session-123", export_format
            )
            assert isinstance(exported, ExportedSession)

    @pytest.mark.asyncio
    async def test_messages_with_newlines(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test handling messages with newlines."""
        multiline_messages = [
            {
                "id": "msg1",
                "role": "user",
                "content": "Line 1\nLine 2\nLine 3",
                "created_at": datetime(2024, 1, 1, 10, 0, 0),
            }
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=multiline_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert "Line 1" in exported.content
        assert "Line 2" in exported.content
        assert "Line 3" in exported.content

    @pytest.mark.asyncio
    async def test_session_with_many_messages(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test handling session with many messages."""
        many_messages = [
            {
                "id": f"msg{i}",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "created_at": datetime(2024, 1, 1, 10, i, 0),
            }
            for i in range(100)
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=many_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.JSON
        )

        data = json.loads(exported.content)
        assert len(data["messages"]) == 100

    @pytest.mark.asyncio
    async def test_code_blocks_in_messages(
        self, session_exporter, mock_storage, sample_session
    ):
        """Test handling code blocks in messages."""
        code_messages = [
            {
                "id": "msg1",
                "role": "assistant",
                "content": "Here's some code:\n```python\ndef hello():\n    print('hi')\n```",
                "created_at": datetime(2024, 1, 1, 10, 0, 0),
            }
        ]

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=code_messages)

        exported = await session_exporter.export_session(
            12345, "test-session-123", ExportFormat.MARKDOWN
        )

        assert "```python" in exported.content or "def hello()" in exported.content


class TestIntegration:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_export_all_formats_for_same_session(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test exporting same session in all formats."""
        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        formats = [ExportFormat.MARKDOWN, ExportFormat.JSON, ExportFormat.HTML]
        exports = []

        for export_format in formats:
            exported = await session_exporter.export_session(
                12345, "test-session-123", export_format
            )
            exports.append(exported)

        # All should succeed
        assert len(exports) == 3

        # Each should have unique properties
        assert exports[0].mime_type == "text/markdown"
        assert exports[1].mime_type == "application/json"
        assert exports[2].mime_type == "text/html"

        # All should contain the message content
        for export in exports:
            assert len(export.content) > 0

    @pytest.mark.asyncio
    async def test_concurrent_exports(
        self, session_exporter, mock_storage, sample_session, sample_messages
    ):
        """Test handling concurrent export requests."""
        import asyncio

        mock_storage.get_session = AsyncMock(return_value=sample_session)
        mock_storage.get_session_messages = AsyncMock(return_value=sample_messages)

        # Export multiple times concurrently
        tasks = [
            session_exporter.export_session(12345, "test-session-123", ExportFormat.MARKDOWN)
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        for result in results:
            assert isinstance(result, ExportedSession)
