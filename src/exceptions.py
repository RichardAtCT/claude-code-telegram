"""Custom exceptions for Claude Code Telegram Bot."""


class ClaudeCodeTelegramError(Exception):
    """Base exception for Claude Code Telegram Bot."""


class ConfigurationError(ClaudeCodeTelegramError):
    """Configuration-related errors."""


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""


class InvalidConfigError(ConfigurationError):
    """Configuration is invalid."""


class SecurityError(ClaudeCodeTelegramError):
    """Security-related errors."""


class AuthenticationError(SecurityError):
    """Authentication failed."""


class AuthorizationError(SecurityError):
    """Authorization failed."""


class DirectoryTraversalError(SecurityError):
    """Directory traversal attempt detected."""


class ClaudeError(ClaudeCodeTelegramError):
    """Claude Code-related errors."""


class ClaudeTimeoutError(ClaudeError):
    """Claude Code operation timed out."""


class ClaudeProcessError(ClaudeError):
    """Claude Code process execution failed."""


class ClaudeParsingError(ClaudeError):
    """Failed to parse Claude Code output."""


class StorageError(ClaudeCodeTelegramError):
    """Storage-related errors."""


class DatabaseConnectionError(StorageError):
    """Database connection failed."""


class DataIntegrityError(StorageError):
    """Data integrity check failed."""


class TelegramError(ClaudeCodeTelegramError):
    """Telegram API-related errors."""


class MessageTooLongError(TelegramError):
    """Message exceeds Telegram's length limit."""


class RateLimitError(TelegramError):
    """Rate limit exceeded."""


class RateLimitExceeded(RateLimitError):
    """Rate limit exceeded (alias for compatibility)."""
