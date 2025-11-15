"""Comprehensive tests for message handlers."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import Document, PhotoSize, Update, User

from src.bot.handlers.message import (
    _estimate_file_processing_cost,
    _estimate_text_processing_cost,
    _format_error_message,
    _format_progress_update,
    handle_document,
    handle_photo,
    handle_text_message,
)
from src.claude.exceptions import ClaudeToolValidationError
from src.config.settings import Settings


@pytest.fixture
def temp_approved_dir():
    """Create temporary approved directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        approved_dir = Path(temp_dir) / "approved"
        approved_dir.mkdir()
        yield approved_dir


@pytest.fixture
def mock_settings(temp_approved_dir):
    """Create mock settings."""
    settings = Mock(spec=Settings)
    settings.approved_directory = temp_approved_dir
    settings.claude_max_cost_per_user = 10.0
    settings.enable_quick_actions = True
    return settings


@pytest.fixture
def mock_update():
    """Create mock Telegram update."""
    update = AsyncMock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 123456789
    update.effective_user.first_name = "TestUser"
    update.message = AsyncMock()
    update.message.message_id = 1
    update.message.text = "Hello Claude"
    update.message.chat = AsyncMock()
    return update


@pytest.fixture
def mock_context(mock_settings):
    """Create mock context."""
    context = AsyncMock()
    context.bot_data = {
        "settings": mock_settings,
        "audit_logger": AsyncMock(),
        "security_validator": AsyncMock(),
        "rate_limiter": AsyncMock(),
        "claude_integration": AsyncMock(),
        "storage": AsyncMock(),
        "features": AsyncMock(),
    }
    context.user_data = {}
    context.args = []
    return context


class TestFormatProgressUpdate:
    """Tests for _format_progress_update function."""

    @pytest.mark.asyncio
    async def test_format_tool_result_success(self):
        """Test formatting successful tool result."""
        update_obj = Mock()
        update_obj.type = "tool_result"
        update_obj.metadata = {"tool_name": "Read"}
        update_obj.is_error.return_value = False

        result = await _format_progress_update(update_obj)

        assert "Read completed" in result
        assert "✅" in result

    @pytest.mark.asyncio
    async def test_format_tool_result_error(self):
        """Test formatting failed tool result."""
        update_obj = Mock()
        update_obj.type = "tool_result"
        update_obj.metadata = {"tool_name": "Write"}
        update_obj.is_error.return_value = True
        update_obj.get_error_message.return_value = "File not found"

        result = await _format_progress_update(update_obj)

        assert "Write failed" in result
        assert "❌" in result
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_format_progress_update(self):
        """Test formatting progress update."""
        update_obj = Mock()
        update_obj.type = "progress"
        update_obj.content = "Processing files..."
        update_obj.get_progress_percentage.return_value = 50
        update_obj.progress = {"step": 3, "total_steps": 6}

        result = await _format_progress_update(update_obj)

        assert "Processing files" in result
        assert "50%" in result
        assert "Step 3 of 6" in result

    @pytest.mark.asyncio
    async def test_format_error_update(self):
        """Test formatting error update."""
        update_obj = Mock()
        update_obj.type = "error"
        update_obj.get_error_message.return_value = "Connection failed"

        result = await _format_progress_update(update_obj)

        assert "Error" in result
        assert "Connection failed" in result

    @pytest.mark.asyncio
    async def test_format_assistant_with_tools(self):
        """Test formatting assistant update with tool calls."""
        update_obj = Mock()
        update_obj.type = "assistant"
        update_obj.tool_calls = [Mock()]
        update_obj.get_tool_names.return_value = ["Read", "Write"]
        update_obj.content = None

        result = await _format_progress_update(update_obj)

        assert "Using tools" in result
        assert "Read" in result
        assert "Write" in result

    @pytest.mark.asyncio
    async def test_format_assistant_content(self):
        """Test formatting assistant content update."""
        update_obj = Mock()
        update_obj.type = "assistant"
        update_obj.tool_calls = None
        update_obj.content = "This is a long response " * 10

        result = await _format_progress_update(update_obj)

        assert "Claude is working" in result
        assert len(result) < 200  # Should be truncated

    @pytest.mark.asyncio
    async def test_format_system_init(self):
        """Test formatting system initialization update."""
        update_obj = Mock()
        update_obj.type = "system"
        update_obj.metadata = {
            "subtype": "init",
            "model": "Claude 3.5",
            "tools": ["Read", "Write", "Bash"],
        }
        update_obj.content = None
        update_obj.tool_calls = None

        result = await _format_progress_update(update_obj)

        assert "Starting" in result
        assert "Claude 3.5" in result
        assert "3 tools" in result

    @pytest.mark.asyncio
    async def test_format_unknown_type(self):
        """Test formatting unknown update type."""
        update_obj = Mock()
        update_obj.type = "unknown"
        update_obj.content = None
        update_obj.tool_calls = None
        update_obj.metadata = None

        result = await _format_progress_update(update_obj)

        assert result is None


class TestFormatErrorMessage:
    """Tests for _format_error_message function."""

    def test_format_usage_limit_error(self):
        """Test formatting usage limit error."""
        error = "usage limit reached"
        result = _format_error_message(error)

        assert error in result

    def test_format_tool_not_allowed_error(self):
        """Test formatting tool validation error."""
        error = "tool not allowed: dangerous_tool"
        result = _format_error_message(error)

        assert error in result

    def test_format_no_conversation_error(self):
        """Test formatting no conversation error."""
        error = "no conversation found"
        result = _format_error_message(error)

        assert "Session Not Found" in result
        assert "/new" in result

    def test_format_rate_limit_error(self):
        """Test formatting rate limit error."""
        error = "rate limit exceeded"
        result = _format_error_message(error)

        assert "Rate Limit" in result
        assert "Wait a moment" in result

    def test_format_timeout_error(self):
        """Test formatting timeout error."""
        error = "request timeout after 30 seconds"
        result = _format_error_message(error)

        assert "Timeout" in result
        assert "too long" in result

    def test_format_generic_error(self):
        """Test formatting generic error."""
        error = "Something went wrong"
        result = _format_error_message(error)

        assert "Claude Code Error" in result
        assert "Something went wrong" in result


class TestHandleTextMessage:
    """Tests for handle_text_message handler."""

    @pytest.mark.asyncio
    async def test_handle_text_message_success(
        self, mock_update, mock_context, mock_settings
    ):
        """Test successful text message handling."""
        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = "test_session_123"
        mock_response.content = "Hello! How can I help you?"
        mock_response.tools_used = []
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        # Mock rate limiter
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        await handle_text_message(mock_update, mock_context)

        # Verify Claude integration was called
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()

        # Verify session ID was stored
        assert mock_context.user_data["claude_session_id"] == "test_session_123"

        # Verify response was sent
        assert mock_update.message.reply_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_handle_text_message_rate_limited(self, mock_update, mock_context):
        """Test handling text message when rate limited."""
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (
            False,
            "Rate limit exceeded. Please wait.",
        )

        await handle_text_message(mock_update, mock_context)

        # Verify rate limit message was sent
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Rate limit" in call_args[0][0]

        # Verify Claude was not called
        mock_context.bot_data["claude_integration"].run_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_text_message_no_integration(self, mock_update, mock_context):
        """Test handling text message when Claude integration is not available."""
        mock_context.bot_data["claude_integration"] = None

        await handle_text_message(mock_update, mock_context)

        # Verify error message
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "not available" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_text_message_claude_error(
        self, mock_update, mock_context, mock_settings
    ):
        """Test error handling when Claude fails."""
        mock_context.bot_data["claude_integration"].run_command.side_effect = Exception(
            "Claude API error"
        )

        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        await handle_text_message(mock_update, mock_context)

        # Verify error message was sent
        assert mock_update.message.reply_text.call_count >= 1

        # Verify audit log
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_command.assert_called_with(
            user_id=123456789, command="text_message", args=["Hello Claude"], success=False
        )

    @pytest.mark.asyncio
    async def test_handle_text_message_tool_validation_error(
        self, mock_update, mock_context, mock_settings
    ):
        """Test handling tool validation error."""
        # Mock tool validation error
        error = ClaudeToolValidationError(
            "Tool not allowed",
            blocked_tools=["dangerous_tool"],
            allowed_tools=["Read", "Write"],
        )
        mock_context.bot_data["claude_integration"].run_command.side_effect = error

        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        await handle_text_message(mock_update, mock_context)

        # Verify error message was sent
        assert mock_update.message.reply_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_handle_text_message_with_existing_session(
        self, mock_update, mock_context, mock_settings
    ):
        """Test handling message with existing session."""
        # Set existing session
        mock_context.user_data["claude_session_id"] = "existing_session"

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = "existing_session"
        mock_response.content = "Continuing the conversation"
        mock_response.tools_used = []
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        await handle_text_message(mock_update, mock_context)

        # Verify Claude was called with existing session
        call_args = mock_context.bot_data["claude_integration"].run_command.call_args
        assert call_args[1]["session_id"] == "existing_session"

    @pytest.mark.asyncio
    async def test_handle_text_message_storage_logging(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that interaction is logged to storage."""
        mock_response = Mock()
        mock_response.session_id = "test_session"
        mock_response.content = "Response"
        mock_response.tools_used = []
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        await handle_text_message(mock_update, mock_context)

        # Verify storage was called
        storage = mock_context.bot_data["storage"]
        storage.save_claude_interaction.assert_called_once()


class TestHandleDocument:
    """Tests for handle_document handler."""

    @pytest.mark.asyncio
    async def test_handle_document_success(self, mock_update, mock_context, mock_settings):
        """Test successful document handling."""
        # Mock document
        document = Mock(spec=Document)
        document.file_name = "test.py"
        document.file_size = 1024
        mock_update.message.document = document
        mock_update.message.caption = "Review this code"

        # Mock file download
        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = b"print('hello world')"
        document.get_file.return_value = mock_file

        # Mock security validator
        validator = mock_context.bot_data["security_validator"]
        validator.validate_filename.return_value = (True, None)

        # Mock rate limiter
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = "test_session"
        mock_response.content = "This code looks good!"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        await handle_document(mock_update, mock_context)

        # Verify Claude was called with file content
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()
        call_args = mock_context.bot_data["claude_integration"].run_command.call_args
        assert "test.py" in call_args[1]["prompt"]
        assert "print('hello world')" in call_args[1]["prompt"]

    @pytest.mark.asyncio
    async def test_handle_document_invalid_filename(self, mock_update, mock_context):
        """Test handling document with invalid filename."""
        document = Mock(spec=Document)
        document.file_name = "malware.exe"
        document.file_size = 1024
        mock_update.message.document = document

        # Mock security validator to reject
        validator = mock_context.bot_data["security_validator"]
        validator.validate_filename.return_value = (False, "File type not allowed")

        await handle_document(mock_update, mock_context)

        # Verify rejection message
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Rejected" in call_args[0][0]

        # Verify security violation was logged
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_security_violation.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_document_too_large(self, mock_update, mock_context):
        """Test handling document that exceeds size limit."""
        document = Mock(spec=Document)
        document.file_name = "large.txt"
        document.file_size = 20 * 1024 * 1024  # 20MB

        mock_update.message.document = document

        # Mock security validator
        validator = mock_context.bot_data["security_validator"]
        validator.validate_filename.return_value = (True, None)

        await handle_document(mock_update, mock_context)

        # Verify size limit message
        call_args = mock_update.message.reply_text.call_args
        assert "Too Large" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_document_non_text_file(self, mock_update, mock_context):
        """Test handling non-text document."""
        document = Mock(spec=Document)
        document.file_name = "image.png"
        document.file_size = 1024
        mock_update.message.document = document

        # Mock file download (returns binary data that can't be decoded)
        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = b"\x89PNG\r\n\x1a\n"
        document.get_file.return_value = mock_file

        # Mock security validator
        validator = mock_context.bot_data["security_validator"]
        validator.validate_filename.return_value = (True, None)

        # Mock rate limiter
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        await handle_document(mock_update, mock_context)

        # Verify error message about unsupported format
        # The handler should send an error about UTF-8 encoding
        assert mock_update.message.reply_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_handle_document_rate_limited(self, mock_update, mock_context):
        """Test document handling when rate limited."""
        document = Mock(spec=Document)
        document.file_name = "test.py"
        document.file_size = 1024
        mock_update.message.document = document

        # Mock security validator
        validator = mock_context.bot_data["security_validator"]
        validator.validate_filename.return_value = (True, None)

        # Mock rate limiter to deny
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (False, "Rate limit exceeded")

        await handle_document(mock_update, mock_context)

        # Verify rate limit message
        call_args = mock_update.message.reply_text.call_args
        assert "Rate limit" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_document_with_enhanced_handler(
        self, mock_update, mock_context, mock_settings
    ):
        """Test document handling with enhanced file handler."""
        document = Mock(spec=Document)
        document.file_name = "test.py"
        document.file_size = 1024
        mock_update.message.document = document
        mock_update.message.caption = "Review this"

        # Mock security validator
        validator = mock_context.bot_data["security_validator"]
        validator.validate_filename.return_value = (True, None)

        # Mock rate limiter
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        # Mock enhanced file handler
        features = mock_context.bot_data["features"]
        mock_file_handler = AsyncMock()
        processed_file = Mock()
        processed_file.prompt = "Analyzed: test.py\nContent: print('hello')"
        processed_file.type = "python"
        mock_file_handler.handle_document_upload.return_value = processed_file
        features.get_file_handler.return_value = mock_file_handler

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = "test_session"
        mock_response.content = "Good code!"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        await handle_document(mock_update, mock_context)

        # Verify enhanced handler was called
        mock_file_handler.handle_document_upload.assert_called_once()


class TestHandlePhoto:
    """Tests for handle_photo handler."""

    @pytest.mark.asyncio
    async def test_handle_photo_not_available(self, mock_update, mock_context):
        """Test photo handling when feature is not available."""
        mock_context.bot_data["features"] = None

        await handle_photo(mock_update, mock_context)

        # Verify not supported message
        call_args = mock_update.message.reply_text.call_args
        assert "not yet supported" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_photo_no_handler(self, mock_update, mock_context):
        """Test photo handling when image handler is not available."""
        features = mock_context.bot_data["features"]
        features.get_image_handler.return_value = None

        await handle_photo(mock_update, mock_context)

        # Verify not supported message
        call_args = mock_update.message.reply_text.call_args
        assert "not yet supported" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_photo_success(self, mock_update, mock_context, mock_settings):
        """Test successful photo handling with enhanced handler."""
        # Mock photo
        photo = Mock(spec=PhotoSize)
        mock_update.message.photo = [photo]
        mock_update.message.caption = "What's in this image?"

        # Mock image handler
        features = mock_context.bot_data["features"]
        mock_image_handler = AsyncMock()
        processed_image = Mock()
        processed_image.prompt = "Analyze this image: [image data]"
        mock_image_handler.process_image.return_value = processed_image
        features.get_image_handler.return_value = mock_image_handler

        # Mock Claude response
        mock_response = Mock()
        mock_response.session_id = "test_session"
        mock_response.content = "I see a cat in the image"
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        await handle_photo(mock_update, mock_context)

        # Verify image handler was called
        mock_image_handler.process_image.assert_called_once()

        # Verify Claude was called
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()


class TestCostEstimation:
    """Tests for cost estimation functions."""

    def test_estimate_text_processing_cost_simple(self):
        """Test cost estimation for simple text."""
        text = "Hello Claude"
        cost = _estimate_text_processing_cost(text)

        assert cost > 0
        assert cost < 0.01  # Simple text should be cheap

    def test_estimate_text_processing_cost_complex(self):
        """Test cost estimation for complex text."""
        text = "analyze this code and generate a comprehensive solution"
        cost = _estimate_text_processing_cost(text)

        # Complex keywords should increase cost
        simple_cost = _estimate_text_processing_cost("hello")
        assert cost > simple_cost

    def test_estimate_text_processing_cost_long(self):
        """Test cost estimation for long text."""
        text = "test " * 1000  # Long text
        cost = _estimate_text_processing_cost(text)

        # Longer text should cost more
        short_cost = _estimate_text_processing_cost("test")
        assert cost > short_cost

    def test_estimate_file_processing_cost_small(self):
        """Test cost estimation for small file."""
        file_size = 1024  # 1KB
        cost = _estimate_file_processing_cost(file_size)

        assert cost > 0
        assert cost < 0.01

    def test_estimate_file_processing_cost_large(self):
        """Test cost estimation for large file."""
        file_size = 1024 * 1024  # 1MB
        cost = _estimate_file_processing_cost(file_size)

        # Larger files should cost more
        small_cost = _estimate_file_processing_cost(1024)
        assert cost > small_cost


class TestMessageIntegration:
    """Integration tests for message handlers."""

    @pytest.mark.asyncio
    async def test_message_workflow_complete(
        self, mock_update, mock_context, mock_settings
    ):
        """Test complete message handling workflow."""
        # Setup
        mock_update.message.text = "Create a Python hello world script"

        # Mock all dependencies
        rate_limiter = mock_context.bot_data["rate_limiter"]
        rate_limiter.check_rate_limit.return_value = (True, None)

        mock_response = Mock()
        mock_response.session_id = "new_session_123"
        mock_response.content = "I've created hello.py with print('Hello, World!')"
        mock_response.tools_used = ["Write"]
        mock_context.bot_data["claude_integration"].run_command.return_value = (
            mock_response
        )

        # Execute
        await handle_text_message(mock_update, mock_context)

        # Verify workflow
        # 1. Rate limit checked
        rate_limiter.check_rate_limit.assert_called_once()

        # 2. Claude called
        mock_context.bot_data["claude_integration"].run_command.assert_called_once()

        # 3. Session stored
        assert mock_context.user_data["claude_session_id"] == "new_session_123"

        # 4. Response sent
        assert mock_update.message.reply_text.call_count >= 1

        # 5. Audit logged
        audit_logger = mock_context.bot_data["audit_logger"]
        audit_logger.log_command.assert_called_once()
