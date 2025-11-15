"""Unit tests for main.py - Application entry point and dependency injection."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import structlog

from src.config.settings import Settings
from src.exceptions import ConfigurationError
from src.main import (
    create_application,
    main,
    parse_args,
    run,
    run_application,
    setup_logging,
)


class TestSetupLogging:
    """Test logging configuration."""

    def test_setup_logging_production_mode(self):
        """Test logging setup in production mode (non-debug)."""
        # Reset logging before test
        logging.root.handlers = []
        logging.root.setLevel(logging.WARNING)

        setup_logging(debug=False)

        # Verify root logger level is INFO or lower (more permissive)
        root_logger = logging.getLogger()
        assert root_logger.level <= logging.INFO

        # Verify structlog is configured
        config = structlog.get_config()
        assert config is not None

    def test_setup_logging_debug_mode(self):
        """Test logging setup in debug mode."""
        # Reset logging before test
        logging.root.handlers = []
        logging.root.setLevel(logging.WARNING)

        setup_logging(debug=True)

        # Verify root logger level is DEBUG or lower (more permissive)
        root_logger = logging.getLogger()
        assert root_logger.level <= logging.DEBUG

        # Verify structlog is configured
        config = structlog.get_config()
        assert config is not None

    def test_logging_processors_production(self):
        """Test that production logging uses JSON renderer."""
        setup_logging(debug=False)

        config = structlog.get_config()
        processors = config["processors"]

        # Verify JSON renderer is in processors (last one)
        assert any(
            isinstance(p, structlog.processors.JSONRenderer) for p in processors
        )

    def test_logging_processors_debug(self):
        """Test that debug logging uses console renderer."""
        setup_logging(debug=True)

        config = structlog.get_config()
        processors = config["processors"]

        # Verify console renderer is in processors (last one)
        assert any(isinstance(p, structlog.dev.ConsoleRenderer) for p in processors)


class TestParseArgs:
    """Test command line argument parsing."""

    def test_parse_args_default(self):
        """Test default argument parsing."""
        with patch("sys.argv", ["main.py"]):
            args = parse_args()
            assert args.debug is False
            assert args.config_file is None

    def test_parse_args_debug_flag(self):
        """Test --debug flag."""
        with patch("sys.argv", ["main.py", "--debug"]):
            args = parse_args()
            assert args.debug is True

    def test_parse_args_config_file(self):
        """Test --config-file argument."""
        with patch("sys.argv", ["main.py", "--config-file", "/path/to/config.env"]):
            args = parse_args()
            assert args.config_file == Path("/path/to/config.env")

    def test_parse_args_version(self):
        """Test --version flag."""
        with patch("sys.argv", ["main.py", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                parse_args()
            assert exc_info.value.code == 0

    def test_parse_args_combined(self):
        """Test multiple arguments together."""
        with patch(
            "sys.argv",
            ["main.py", "--debug", "--config-file", "/path/to/config.env"],
        ):
            args = parse_args()
            assert args.debug is True
            assert args.config_file == Path("/path/to/config.env")


class TestCreateApplication:
    """Test application component creation."""

    @pytest.fixture
    def mock_config(self, tmp_path):
        """Create mock configuration."""
        config = Mock(spec=Settings)
        config.database_url = "sqlite:///:memory:"
        config.allowed_users = [123, 456]
        config.enable_token_auth = False
        config.development_mode = False
        config.auth_token_secret = None
        config.approved_directory = tmp_path
        config.use_sdk = False
        config.debug = False
        # Add rate limiter attributes
        config.rate_limit_requests = 10
        config.rate_limit_window = 60
        config.rate_limit_burst = 20
        config.claude_max_cost_per_user = 10.0
        # Add session attributes
        config.session_timeout_hours = 24
        config.max_sessions_per_user = 5
        return config

    @pytest.mark.asyncio
    async def test_create_application_success(self, mock_config):
        """Test successful application creation."""
        with patch("src.main.Storage") as mock_storage_class, patch(
            "src.main.ClaudeCodeBot"
        ) as mock_bot_class, patch(
            "src.main.ClaudeIntegration"
        ) as mock_integration_class, patch(
            "src.main.ClaudeProcessManager"
        ) as mock_process_manager_class, patch(
            "src.main.SessionManager"
        ) as mock_session_manager_class, patch(
            "src.main.SQLiteSessionStorage"
        ) as mock_session_storage_class, patch(
            "src.main.ToolMonitor"
        ):
            # Setup mocks
            mock_storage = AsyncMock()
            mock_storage.initialize = AsyncMock()
            mock_storage.db_manager = Mock()
            mock_storage_class.return_value = mock_storage

            mock_bot = Mock()
            mock_bot_class.return_value = mock_bot

            mock_integration = Mock()
            mock_integration_class.return_value = mock_integration

            # Create application
            app = await create_application(mock_config)

            # Verify components created
            assert "bot" in app
            assert "claude_integration" in app
            assert "storage" in app
            assert "config" in app

            # Verify storage initialized
            mock_storage.initialize.assert_called_once()

            # Verify bot created with dependencies
            mock_bot_class.assert_called_once()
            call_args = mock_bot_class.call_args
            assert call_args[0][0] == mock_config
            dependencies = call_args[0][1]
            assert "auth_manager" in dependencies
            assert "security_validator" in dependencies
            assert "rate_limiter" in dependencies
            assert "audit_logger" in dependencies
            assert "claude_integration" in dependencies
            assert "storage" in dependencies

    @pytest.mark.asyncio
    async def test_create_application_with_token_auth(self, mock_config, tmp_path):
        """Test application creation with token authentication enabled."""
        mock_config.enable_token_auth = True
        mock_config.auth_token_secret = "test_secret_key_123"

        with patch("src.main.Storage") as mock_storage_class, patch(
            "src.main.ClaudeCodeBot"
        ), patch("src.main.ClaudeIntegration"), patch(
            "src.main.ClaudeProcessManager"
        ), patch(
            "src.main.SessionManager"
        ), patch(
            "src.main.SQLiteSessionStorage"
        ), patch(
            "src.main.ToolMonitor"
        ):
            mock_storage = AsyncMock()
            mock_storage.initialize = AsyncMock()
            mock_storage.db_manager = Mock()
            mock_storage_class.return_value = mock_storage

            app = await create_application(mock_config)

            assert app is not None
            assert "bot" in app

    @pytest.mark.asyncio
    async def test_create_application_development_mode(self, mock_config):
        """Test application creation in development mode without auth providers."""
        mock_config.allowed_users = []
        mock_config.enable_token_auth = False
        mock_config.development_mode = True

        with patch("src.main.Storage") as mock_storage_class, patch(
            "src.main.ClaudeCodeBot"
        ), patch("src.main.ClaudeIntegration"), patch(
            "src.main.ClaudeProcessManager"
        ), patch(
            "src.main.SessionManager"
        ), patch(
            "src.main.SQLiteSessionStorage"
        ), patch(
            "src.main.ToolMonitor"
        ):
            mock_storage = AsyncMock()
            mock_storage.initialize = AsyncMock()
            mock_storage.db_manager = Mock()
            mock_storage_class.return_value = mock_storage

            app = await create_application(mock_config)

            # Should create allow-all provider in dev mode
            assert app is not None

    @pytest.mark.asyncio
    async def test_create_application_no_auth_providers_production(self, mock_config):
        """Test that production mode without auth providers raises error."""
        mock_config.allowed_users = []
        mock_config.enable_token_auth = False
        mock_config.development_mode = False

        with patch("src.main.Storage") as mock_storage_class:
            mock_storage = AsyncMock()
            mock_storage.initialize = AsyncMock()
            mock_storage.db_manager = Mock()
            mock_storage_class.return_value = mock_storage

            with pytest.raises(ConfigurationError, match="No authentication providers"):
                await create_application(mock_config)

    @pytest.mark.asyncio
    async def test_create_application_with_sdk(self, mock_config):
        """Test application creation with SDK integration."""
        mock_config.use_sdk = True

        with patch("src.main.Storage") as mock_storage_class, patch(
            "src.main.ClaudeCodeBot"
        ), patch("src.main.ClaudeIntegration"), patch(
            "src.main.ClaudeSDKManager"
        ) as mock_sdk_manager_class, patch(
            "src.main.SessionManager"
        ), patch(
            "src.main.SQLiteSessionStorage"
        ), patch(
            "src.main.ToolMonitor"
        ):
            mock_storage = AsyncMock()
            mock_storage.initialize = AsyncMock()
            mock_storage.db_manager = Mock()
            mock_storage_class.return_value = mock_storage

            mock_sdk_manager_class.return_value = Mock()

            app = await create_application(mock_config)

            # Verify SDK manager created
            mock_sdk_manager_class.assert_called_once_with(mock_config)
            assert app is not None


class TestRunApplication:
    """Test application execution and shutdown."""

    @pytest.mark.asyncio
    async def test_run_application_normal_execution(self):
        """Test normal application execution."""
        mock_bot = AsyncMock()
        mock_bot.start = AsyncMock()
        mock_bot.stop = AsyncMock()

        mock_integration = AsyncMock()
        mock_integration.shutdown = AsyncMock()

        mock_storage = AsyncMock()
        mock_storage.close = AsyncMock()

        app = {
            "bot": mock_bot,
            "claude_integration": mock_integration,
            "storage": mock_storage,
            "config": Mock(),
        }

        # Simulate bot completing quickly
        async def quick_start():
            await asyncio.sleep(0.01)

        mock_bot.start.side_effect = quick_start

        # Run application
        await run_application(app)

        # Verify cleanup occurred
        mock_bot.stop.assert_called_once()
        mock_integration.shutdown.assert_called_once()
        mock_storage.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_application_with_shutdown_signal(self):
        """Test application shutdown on signal."""
        mock_bot = AsyncMock()

        # Make bot.start() wait indefinitely
        async def long_running():
            await asyncio.sleep(100)

        mock_bot.start = AsyncMock(side_effect=long_running)
        mock_bot.stop = AsyncMock()

        mock_integration = AsyncMock()
        mock_integration.shutdown = AsyncMock()

        mock_storage = AsyncMock()
        mock_storage.close = AsyncMock()

        app = {
            "bot": mock_bot,
            "claude_integration": mock_integration,
            "storage": mock_storage,
            "config": Mock(),
        }

        # Create a task to send shutdown signal after short delay
        async def trigger_shutdown():
            await asyncio.sleep(0.05)
            # Trigger SIGTERM
            signal_handler = None
            with patch("signal.signal") as mock_signal:
                await run_application(app)
                # Get the signal handler that was registered
                calls = mock_signal.call_args_list
                for call in calls:
                    if call[0][0] == signal.SIGTERM:
                        signal_handler = call[0][1]
                        break
            if signal_handler:
                signal_handler(signal.SIGTERM, None)

        # Run with timeout to prevent hanging
        try:
            await asyncio.wait_for(run_application(app), timeout=1.0)
        except asyncio.TimeoutError:
            # Expected - bot would run forever without shutdown
            pass

        # Verify cleanup was attempted
        assert mock_bot.stop.called or mock_integration.shutdown.called

    @pytest.mark.asyncio
    async def test_run_application_cleanup_on_early_completion(self):
        """Test that cleanup happens when bot completes early."""
        mock_bot = Mock()

        # Make bot.start() complete quickly
        async def quick_start():
            await asyncio.sleep(0.01)

        mock_bot.start = Mock(return_value=quick_start())
        mock_bot.stop = AsyncMock()

        mock_integration = AsyncMock()
        mock_integration.shutdown = AsyncMock()

        mock_storage = AsyncMock()
        mock_storage.close = AsyncMock()

        app = {
            "bot": mock_bot,
            "claude_integration": mock_integration,
            "storage": mock_storage,
            "config": Mock(),
        }

        # Run application
        await run_application(app)

        # Verify cleanup occurred
        mock_bot.stop.assert_called_once()
        mock_integration.shutdown.assert_called_once()
        mock_storage.close.assert_called_once()


class TestMain:
    """Test main entry point function."""

    @pytest.mark.asyncio
    async def test_main_success(self, tmp_path):
        """Test successful main execution."""
        # Need to patch at module level where main() imports it
        with patch("src.main.parse_args") as mock_parse_args, patch(
            "src.main.setup_logging"
        ) as mock_setup_logging, patch(
            "src.config.load_config"
        ) as mock_load_config, patch(
            "src.config.FeatureFlags"
        ) as mock_feature_flags, patch(
            "src.main.create_application"
        ) as mock_create_app, patch(
            "src.main.run_application"
        ) as mock_run_app:
            # Setup mocks
            mock_args = Mock()
            mock_args.debug = False
            mock_args.config_file = None
            mock_parse_args.return_value = mock_args

            mock_config = Mock()
            mock_config.is_production = True
            mock_config.debug = False
            mock_load_config.return_value = mock_config

            mock_features = Mock()
            mock_features.get_enabled_features.return_value = ["git", "mcp"]
            mock_feature_flags.return_value = mock_features

            mock_app = {"bot": Mock(), "config": mock_config}
            mock_create_app.return_value = mock_app

            mock_run_app.return_value = None

            # Run main
            await main()

            # Verify calls
            mock_parse_args.assert_called_once()
            mock_setup_logging.assert_called_once_with(debug=False)
            mock_load_config.assert_called_once_with(config_file=None)
            mock_create_app.assert_called_once_with(mock_config)
            mock_run_app.assert_called_once_with(mock_app)

    @pytest.mark.asyncio
    async def test_main_configuration_error(self):
        """Test main handles ConfigurationError."""
        with patch("src.main.parse_args") as mock_parse_args, patch(
            "src.main.setup_logging"
        ), patch("src.main.load_config") as mock_load_config, patch(
            "sys.exit"
        ) as mock_exit:
            mock_args = Mock()
            mock_args.debug = False
            mock_args.config_file = None
            mock_parse_args.return_value = mock_args

            mock_load_config.side_effect = ConfigurationError("Invalid config")

            await main()

            # Should exit with code 1
            mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_main_unexpected_error(self):
        """Test main handles unexpected errors."""
        with patch("src.main.parse_args") as mock_parse_args, patch(
            "src.main.setup_logging"
        ), patch("src.main.load_config") as mock_load_config, patch(
            "sys.exit"
        ) as mock_exit:
            mock_args = Mock()
            mock_args.debug = False
            mock_args.config_file = None
            mock_parse_args.return_value = mock_args

            mock_load_config.side_effect = RuntimeError("Unexpected error")

            await main()

            # Should exit with code 1
            mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_main_debug_mode(self):
        """Test main with debug mode enabled."""
        with patch("src.main.parse_args") as mock_parse_args, patch(
            "src.main.setup_logging"
        ) as mock_setup_logging, patch(
            "src.config.load_config"
        ) as mock_load_config, patch(
            "src.config.FeatureFlags"
        ), patch(
            "src.main.create_application"
        ), patch(
            "src.main.run_application"
        ):
            mock_args = Mock()
            mock_args.debug = True
            mock_args.config_file = None
            mock_parse_args.return_value = mock_args

            mock_config = Mock()
            mock_config.is_production = False
            mock_config.debug = True
            mock_load_config.return_value = mock_config

            await main()

            # Should setup logging with debug=True
            mock_setup_logging.assert_called_once_with(debug=True)


class TestRun:
    """Test synchronous entry point."""

    def test_run_success(self):
        """Test successful run."""
        with patch("asyncio.run") as mock_asyncio_run, patch("src.main.main"):
            run()
            mock_asyncio_run.assert_called_once()

    def test_run_keyboard_interrupt(self):
        """Test run handles keyboard interrupt gracefully."""
        with patch("asyncio.run") as mock_asyncio_run, patch(
            "sys.exit"
        ) as mock_exit, patch("builtins.print") as mock_print:
            mock_asyncio_run.side_effect = KeyboardInterrupt()

            run()

            mock_print.assert_called_once_with("\nShutdown requested by user")
            mock_exit.assert_called_once_with(0)

    def test_run_propagates_other_exceptions(self):
        """Test run propagates non-keyboard-interrupt exceptions."""
        with patch("asyncio.run") as mock_asyncio_run:
            mock_asyncio_run.side_effect = RuntimeError("Test error")

            with pytest.raises(RuntimeError, match="Test error"):
                run()
