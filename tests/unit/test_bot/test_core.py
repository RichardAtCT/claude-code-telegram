"""Comprehensive tests for the main bot orchestrator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from telegram import BotCommand, Update, User
from telegram.ext import Application, CommandHandler, MessageHandler

from src.bot.core import ClaudeCodeBot
from src.config.settings import Settings
from src.exceptions import (
    AuthenticationError,
    ClaudeCodeTelegramError,
    ConfigurationError,
    RateLimitExceeded,
    SecurityError,
)


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock(spec=Settings)
    settings.telegram_token_str = "test_token_123"
    settings.webhook_url = None
    settings.webhook_port = 8443
    settings.webhook_path = "/webhook"
    return settings


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies."""
    return {
        "storage": AsyncMock(),
        "security": AsyncMock(),
        "audit_logger": AsyncMock(),
    }


@pytest.fixture
def bot(mock_settings, mock_dependencies):
    """Create bot instance."""
    return ClaudeCodeBot(mock_settings, mock_dependencies)


@pytest.fixture
def mock_application():
    """Create mock Telegram application."""
    app = AsyncMock(spec=Application)
    app.bot = AsyncMock()
    app.bot.set_my_commands = AsyncMock()
    app.bot.get_me = AsyncMock()
    app.updater = AsyncMock()
    app.updater.running = True
    app.add_handler = Mock()
    app.add_error_handler = Mock()
    return app


@pytest.fixture
def mock_update():
    """Create mock Telegram update."""
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 123456789
    update.effective_user.first_name = "TestUser"
    update.effective_message = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create mock context."""
    context = AsyncMock()
    context.bot_data = {}
    context.error = None
    return context


class TestBotInitialization:
    """Test bot initialization and setup."""

    def test_init(self, mock_settings, mock_dependencies):
        """Test bot __init__."""
        bot = ClaudeCodeBot(mock_settings, mock_dependencies)

        assert bot.settings == mock_settings
        assert bot.deps == mock_dependencies
        assert bot.app is None
        assert bot.is_running is False
        assert bot.feature_registry is None

    @pytest.mark.asyncio
    async def test_initialize_success(self, bot, mock_application):
        """Test successful bot initialization."""
        with patch("src.bot.core.Application") as mock_app_class:
            # Setup Application builder mock
            mock_builder = MagicMock()
            mock_app_class.builder.return_value = mock_builder
            mock_builder.token.return_value = mock_builder
            mock_builder.connect_timeout.return_value = mock_builder
            mock_builder.read_timeout.return_value = mock_builder
            mock_builder.write_timeout.return_value = mock_builder
            mock_builder.pool_timeout.return_value = mock_builder
            mock_builder.build.return_value = mock_application

            # Mock FeatureRegistry
            with patch("src.bot.core.FeatureRegistry") as mock_feature_registry:
                mock_registry_instance = Mock()
                mock_feature_registry.return_value = mock_registry_instance

                await bot.initialize()

                # Verify Application was built correctly
                mock_builder.token.assert_called_once_with("test_token_123")
                mock_builder.connect_timeout.assert_called_once_with(30)
                mock_builder.read_timeout.assert_called_once_with(30)
                mock_builder.write_timeout.assert_called_once_with(30)
                mock_builder.pool_timeout.assert_called_once_with(30)

                # Verify app was set
                assert bot.app == mock_application

                # Verify feature registry was created
                assert bot.feature_registry == mock_registry_instance
                assert bot.deps["features"] == mock_registry_instance

                # Verify handlers were added
                assert mock_application.add_handler.called
                assert mock_application.add_error_handler.called

                # Verify bot commands were set
                mock_application.bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_bot_commands(self, bot, mock_application):
        """Test bot commands are set correctly."""
        bot.app = mock_application

        await bot._set_bot_commands()

        # Verify set_my_commands was called
        mock_application.bot.set_my_commands.assert_called_once()

        # Verify commands list
        commands_arg = mock_application.bot.set_my_commands.call_args[0][0]
        assert isinstance(commands_arg, list)
        assert len(commands_arg) > 0

        # Check specific commands
        command_names = [cmd.command for cmd in commands_arg]
        assert "start" in command_names
        assert "help" in command_names
        assert "new" in command_names
        assert "continue" in command_names
        assert "ls" in command_names
        assert "cd" in command_names
        assert "pwd" in command_names
        assert "projects" in command_names
        assert "status" in command_names
        assert "export" in command_names
        assert "actions" in command_names
        assert "git" in command_names

        # Verify they are BotCommand instances
        for cmd in commands_arg:
            assert isinstance(cmd, BotCommand)
            assert cmd.command
            assert cmd.description


class TestHandlerRegistration:
    """Test handler registration."""

    @pytest.mark.asyncio
    async def test_register_handlers(self, bot, mock_application):
        """Test all handlers are registered."""
        bot.app = mock_application

        with patch("src.bot.handlers.command") as mock_command:
            with patch("src.bot.handlers.message") as mock_message:
                with patch("src.bot.handlers.callback") as mock_callback:
                    # Mock handler functions
                    mock_command.start_command = AsyncMock()
                    mock_command.help_command = AsyncMock()
                    mock_command.new_session = AsyncMock()
                    mock_command.continue_session = AsyncMock()
                    mock_command.end_session = AsyncMock()
                    mock_command.list_files = AsyncMock()
                    mock_command.change_directory = AsyncMock()
                    mock_command.print_working_directory = AsyncMock()
                    mock_command.show_projects = AsyncMock()
                    mock_command.session_status = AsyncMock()
                    mock_command.export_session = AsyncMock()
                    mock_command.quick_actions = AsyncMock()
                    mock_command.git_command = AsyncMock()
                    mock_message.handle_text_message = AsyncMock()
                    mock_message.handle_document = AsyncMock()
                    mock_message.handle_photo = AsyncMock()
                    mock_callback.handle_callback_query = AsyncMock()

                    bot._register_handlers()

                    # Verify handlers were added
                    assert mock_application.add_handler.call_count >= 16

                    # Verify CommandHandler was used for commands
                    command_handler_calls = [
                        call for call in mock_application.add_handler.call_args_list
                        if isinstance(call[0][0], CommandHandler)
                    ]
                    assert len(command_handler_calls) == 13  # 13 command handlers

                    # Verify MessageHandler was used for messages
                    message_handler_calls = [
                        call for call in mock_application.add_handler.call_args_list
                        if isinstance(call[0][0], MessageHandler)
                    ]
                    assert len(message_handler_calls) >= 3  # text, document, photo

    @pytest.mark.asyncio
    async def test_inject_deps(self, bot, mock_update, mock_context):
        """Test dependency injection wrapper."""
        # Create a simple handler
        mock_handler = AsyncMock(return_value="handler_result")

        # Create wrapped handler
        wrapped = bot._inject_deps(mock_handler)

        # Call wrapped handler
        result = await wrapped(mock_update, mock_context)

        # Verify dependencies were injected
        assert "settings" in mock_context.bot_data
        assert mock_context.bot_data["settings"] == bot.settings
        for key, value in bot.deps.items():
            assert mock_context.bot_data[key] == value

        # Verify original handler was called
        mock_handler.assert_called_once_with(mock_update, mock_context)
        assert result == "handler_result"


class TestMiddleware:
    """Test middleware functionality."""

    @pytest.mark.asyncio
    async def test_add_middleware(self, bot, mock_application):
        """Test middleware is added correctly."""
        bot.app = mock_application

        with patch("src.bot.middleware.security.security_middleware") as mock_security:
            with patch("src.bot.middleware.auth.auth_middleware") as mock_auth:
                with patch("src.bot.middleware.rate_limit.rate_limit_middleware") as mock_rate_limit:
                    bot._add_middleware()

                    # Verify middleware handlers were added with correct groups
                    add_handler_calls = mock_application.add_handler.call_args_list

                    # Should have 3 middleware handlers
                    middleware_calls = [
                        call for call in add_handler_calls
                        if len(call[1]) > 0 and "group" in call[1]
                    ]
                    assert len(middleware_calls) == 3

                    # Verify groups (security=-3, auth=-2, rate_limit=-1)
                    groups = [call[1]["group"] for call in middleware_calls]
                    assert -3 in groups  # security
                    assert -2 in groups  # auth
                    assert -1 in groups  # rate_limit

    @pytest.mark.asyncio
    async def test_create_middleware_handler(self, bot, mock_update, mock_context):
        """Test middleware handler wrapper."""
        # Create a mock middleware function
        mock_middleware = AsyncMock(return_value="middleware_result")

        # Create middleware handler
        handler = bot._create_middleware_handler(mock_middleware)

        # Call handler
        result = await handler(mock_update, mock_context)

        # Verify dependencies were injected
        assert mock_context.bot_data["settings"] == bot.settings
        for key, value in bot.deps.items():
            assert mock_context.bot_data[key] == value

        # Verify middleware was called
        mock_middleware.assert_called_once()
        args = mock_middleware.call_args[0]
        assert callable(args[0])  # dummy handler
        assert args[1] == mock_update
        assert args[2] == mock_context.bot_data


class TestBotLifecycle:
    """Test bot start and stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_polling_mode(self, bot, mock_application):
        """Test starting bot in polling mode."""
        bot.settings.webhook_url = None

        async def mock_initialize():
            bot.app = mock_application

        async def mock_sleep(seconds):
            # Stop the bot immediately without actually sleeping
            bot.is_running = False

        with patch.object(bot, "initialize", side_effect=mock_initialize) as mock_init:
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await bot.start()

                # Verify initialization was called
                mock_init.assert_called_once()

                # Verify polling was started
                mock_application.initialize.assert_called_once()
                mock_application.start.assert_called_once()
                mock_application.updater.start_polling.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_webhook_mode(self, bot, mock_application):
        """Test starting bot in webhook mode."""
        bot.settings.webhook_url = "https://example.com/webhook"
        bot.settings.webhook_port = 8443
        bot.settings.webhook_path = "/webhook"

        # Mock run_webhook to return immediately
        mock_application.run_webhook = AsyncMock()

        async def mock_initialize():
            bot.app = mock_application

        with patch.object(bot, "initialize", side_effect=mock_initialize) as mock_init:
            await bot.start()

            # Verify initialization was called
            mock_init.assert_called_once()

            # Verify webhook was started with correct parameters
            mock_application.run_webhook.assert_called_once()
            call_kwargs = mock_application.run_webhook.call_args[1]
            assert call_kwargs["listen"] == "0.0.0.0"
            assert call_kwargs["port"] == 8443
            assert call_kwargs["url_path"] == "/webhook"
            assert call_kwargs["webhook_url"] == "https://example.com/webhook"
            assert call_kwargs["drop_pending_updates"] is True

    @pytest.mark.asyncio
    async def test_start_already_running(self, bot):
        """Test starting bot when already running."""
        bot.is_running = True

        with patch.object(bot, "initialize") as mock_init:
            await bot.start()

            # Verify initialization was not called
            mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_with_error(self, bot, mock_application):
        """Test bot start with initialization error."""
        # Initialize happens before try block, so error in app.start() is what gets wrapped
        async def mock_initialize():
            bot.app = mock_application

        mock_application.start.side_effect = Exception("Start failed")

        with patch.object(bot, "initialize", side_effect=mock_initialize):
            with pytest.raises(ClaudeCodeTelegramError) as exc_info:
                await bot.start()

            assert "Failed to start bot" in str(exc_info.value)
            assert bot.is_running is False

    @pytest.mark.asyncio
    async def test_stop_success(self, bot, mock_application):
        """Test graceful bot shutdown."""
        bot.app = mock_application
        bot.is_running = True
        bot.feature_registry = Mock()
        bot.feature_registry.shutdown = Mock()

        await bot.stop()

        # Verify shutdown sequence
        bot.feature_registry.shutdown.assert_called_once()
        mock_application.updater.stop.assert_called_once()
        mock_application.stop.assert_called_once()
        mock_application.shutdown.assert_called_once()
        assert bot.is_running is False

    @pytest.mark.asyncio
    async def test_stop_not_running(self, bot):
        """Test stopping bot when not running."""
        bot.is_running = False

        await bot.stop()

        # Should return without error

    @pytest.mark.asyncio
    async def test_stop_with_error(self, bot, mock_application):
        """Test bot stop with error."""
        bot.app = mock_application
        bot.is_running = True
        mock_application.stop.side_effect = Exception("Stop failed")

        with pytest.raises(ClaudeCodeTelegramError) as exc_info:
            await bot.stop()

        assert "Failed to stop bot" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stop_without_updater_running(self, bot, mock_application):
        """Test stopping bot when updater is not running."""
        bot.app = mock_application
        bot.is_running = True
        bot.app.updater.running = False

        await bot.stop()

        # Verify updater.stop was not called since it's not running
        mock_application.updater.stop.assert_not_called()
        mock_application.stop.assert_called_once()


class TestErrorHandler:
    """Test global error handler."""

    @pytest.mark.asyncio
    async def test_error_handler_authentication_error(
        self, bot, mock_update, mock_context
    ):
        """Test error handler with AuthenticationError."""
        mock_context.error = AuthenticationError("Auth failed")

        await bot._error_handler(mock_update, mock_context)

        # Verify user was notified
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Authentication required" in message
        assert "🔒" in message

    @pytest.mark.asyncio
    async def test_error_handler_security_error(self, bot, mock_update, mock_context):
        """Test error handler with SecurityError."""
        mock_context.error = SecurityError("Security violation")

        await bot._error_handler(mock_update, mock_context)

        # Verify user was notified
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Security violation" in message
        assert "🛡️" in message

    @pytest.mark.asyncio
    async def test_error_handler_rate_limit_error(
        self, bot, mock_update, mock_context
    ):
        """Test error handler with RateLimitExceeded."""
        mock_context.error = RateLimitExceeded("Too many requests")

        await bot._error_handler(mock_update, mock_context)

        # Verify user was notified
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Rate limit exceeded" in message
        assert "⏱️" in message

    @pytest.mark.asyncio
    async def test_error_handler_config_error(self, bot, mock_update, mock_context):
        """Test error handler with ConfigurationError."""
        mock_context.error = ConfigurationError("Bad config")

        await bot._error_handler(mock_update, mock_context)

        # Verify user was notified
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Configuration error" in message
        assert "⚙️" in message

    @pytest.mark.asyncio
    async def test_error_handler_timeout_error(self, bot, mock_update, mock_context):
        """Test error handler with TimeoutError."""
        mock_context.error = asyncio.TimeoutError()

        await bot._error_handler(mock_update, mock_context)

        # Verify user was notified
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "timed out" in message
        assert "⏰" in message

    @pytest.mark.asyncio
    async def test_error_handler_unknown_error(self, bot, mock_update, mock_context):
        """Test error handler with unknown error type."""
        mock_context.error = ValueError("Unknown error")

        await bot._error_handler(mock_update, mock_context)

        # Verify generic error message
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "unexpected error" in message
        assert "❌" in message

    @pytest.mark.asyncio
    async def test_error_handler_no_update(self, bot, mock_context):
        """Test error handler with no update."""
        mock_context.error = Exception("Error")

        # Should not raise exception
        await bot._error_handler(None, mock_context)

    @pytest.mark.asyncio
    async def test_error_handler_with_audit_logger(self, bot, mock_update, mock_context):
        """Test error handler logs to audit system."""
        mock_audit_logger = AsyncMock()
        mock_context.bot_data["audit_logger"] = mock_audit_logger
        mock_context.error = SecurityError("Security issue")

        await bot._error_handler(mock_update, mock_context)

        # Verify audit log was created
        mock_audit_logger.log_security_violation.assert_called_once()
        call_kwargs = mock_audit_logger.log_security_violation.call_args[1]
        assert call_kwargs["user_id"] == 123456789
        assert call_kwargs["violation_type"] == "system_error"
        assert "SecurityError" in call_kwargs["details"]

    @pytest.mark.asyncio
    async def test_error_handler_audit_logging_fails(
        self, bot, mock_update, mock_context
    ):
        """Test error handler when audit logging fails."""
        mock_audit_logger = AsyncMock()
        mock_audit_logger.log_security_violation.side_effect = Exception("Log failed")
        mock_context.bot_data["audit_logger"] = mock_audit_logger
        mock_context.error = SecurityError("Security issue")

        # Should not raise exception
        await bot._error_handler(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_error_handler_reply_fails(self, bot, mock_update, mock_context):
        """Test error handler when replying to user fails."""
        mock_context.error = Exception("Test error")
        mock_update.effective_message.reply_text.side_effect = Exception("Reply failed")

        # Should not raise exception
        await bot._error_handler(mock_update, mock_context)


class TestBotInfo:
    """Test bot information and health check."""

    @pytest.mark.asyncio
    async def test_get_bot_info_not_initialized(self, bot):
        """Test get_bot_info when bot not initialized."""
        info = await bot.get_bot_info()

        assert info["status"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_get_bot_info_initialized(self, bot, mock_application):
        """Test get_bot_info when bot is initialized."""
        bot.app = mock_application
        bot.is_running = False

        # Mock bot.get_me() response
        mock_me = Mock()
        mock_me.username = "test_bot"
        mock_me.first_name = "Test Bot"
        mock_me.id = 987654321
        mock_me.can_join_groups = True
        mock_me.can_read_all_group_messages = True
        mock_me.supports_inline_queries = False
        mock_application.bot.get_me.return_value = mock_me

        info = await bot.get_bot_info()

        assert info["status"] == "initialized"
        assert info["username"] == "test_bot"
        assert info["first_name"] == "Test Bot"
        assert info["id"] == 987654321
        assert info["can_join_groups"] is True
        assert info["can_read_all_group_messages"] is True
        assert info["supports_inline_queries"] is False
        assert info["webhook_url"] is None

    @pytest.mark.asyncio
    async def test_get_bot_info_running(self, bot, mock_application):
        """Test get_bot_info when bot is running."""
        bot.app = mock_application
        bot.is_running = True

        mock_me = Mock()
        mock_me.username = "test_bot"
        mock_me.first_name = "Test Bot"
        mock_me.id = 987654321
        mock_me.can_join_groups = True
        mock_me.can_read_all_group_messages = True
        mock_me.supports_inline_queries = False
        mock_application.bot.get_me.return_value = mock_me

        info = await bot.get_bot_info()

        assert info["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_bot_info_with_webhook(self, bot, mock_application):
        """Test get_bot_info with webhook configuration."""
        bot.app = mock_application
        bot.settings.webhook_url = "https://example.com/webhook"
        bot.settings.webhook_port = 8443

        mock_me = Mock()
        mock_me.username = "test_bot"
        mock_me.first_name = "Test Bot"
        mock_me.id = 987654321
        mock_me.can_join_groups = True
        mock_me.can_read_all_group_messages = True
        mock_me.supports_inline_queries = False
        mock_application.bot.get_me.return_value = mock_me

        info = await bot.get_bot_info()

        assert info["webhook_url"] == "https://example.com/webhook"
        assert info["webhook_port"] == 8443

    @pytest.mark.asyncio
    async def test_get_bot_info_error(self, bot, mock_application):
        """Test get_bot_info when API call fails."""
        bot.app = mock_application
        mock_application.bot.get_me.side_effect = Exception("API error")

        info = await bot.get_bot_info()

        assert info["status"] == "error"
        assert "error" in info

    @pytest.mark.asyncio
    async def test_health_check_success(self, bot, mock_application):
        """Test successful health check."""
        bot.app = mock_application
        mock_application.bot.get_me.return_value = Mock()

        result = await bot.health_check()

        assert result is True
        mock_application.bot.get_me.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_no_app(self, bot):
        """Test health check when app not initialized."""
        bot.app = None

        result = await bot.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self, bot, mock_application):
        """Test health check failure."""
        bot.app = mock_application
        mock_application.bot.get_me.side_effect = Exception("API error")

        result = await bot.health_check()

        assert result is False


class TestEdgeCases:
    """Test edge cases and integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_initialization_sequence(self, bot):
        """Test complete initialization sequence."""
        with patch("src.bot.core.Application") as mock_app_class:
            mock_builder = MagicMock()
            mock_app = AsyncMock()
            mock_app.bot = AsyncMock()
            mock_app.bot.set_my_commands = AsyncMock()
            mock_app.add_handler = Mock()
            mock_app.add_error_handler = Mock()

            mock_app_class.builder.return_value = mock_builder
            mock_builder.token.return_value = mock_builder
            mock_builder.connect_timeout.return_value = mock_builder
            mock_builder.read_timeout.return_value = mock_builder
            mock_builder.write_timeout.return_value = mock_builder
            mock_builder.pool_timeout.return_value = mock_builder
            mock_builder.build.return_value = mock_app

            with patch("src.bot.core.FeatureRegistry"):
                await bot.initialize()

                # Verify complete initialization
                assert bot.app is not None
                assert bot.feature_registry is not None
                assert "features" in bot.deps

                # Verify all setup methods were called
                mock_app.bot.set_my_commands.assert_called_once()
                assert mock_app.add_handler.called
                assert mock_app.add_error_handler.called

    @pytest.mark.asyncio
    async def test_dependency_injection_preserves_order(self, bot):
        """Test that dependency injection doesn't lose dependencies."""
        bot.deps["custom_dep"] = "custom_value"
        bot.deps["another_dep"] = 12345

        mock_handler = AsyncMock()
        wrapped = bot._inject_deps(mock_handler)

        mock_update = Mock()
        mock_context = AsyncMock()
        mock_context.bot_data = {}

        await wrapped(mock_update, mock_context)

        # Verify all dependencies are present
        assert mock_context.bot_data["custom_dep"] == "custom_value"
        assert mock_context.bot_data["another_dep"] == 12345
        assert mock_context.bot_data["settings"] == bot.settings

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self, bot, mock_application):
        """Test multiple start/stop cycles."""
        bot.app = mock_application

        # First cycle
        bot.is_running = True
        await bot.stop()
        assert bot.is_running is False

        # Second cycle
        with patch.object(bot, "initialize"):
            bot.settings.webhook_url = "http://test"
            mock_application.run_webhook = AsyncMock()
            await bot.start()

        bot.is_running = True
        await bot.stop()
        assert bot.is_running is False
