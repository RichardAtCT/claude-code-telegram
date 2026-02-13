"""Main entry point for Claude Code Telegram Bot."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from src import __version__
from src.bot.core import ClaudeCodeBot
from src.claude import (
    ClaudeIntegration,
    ClaudeProcessManager,
    SessionManager,
    ToolMonitor,
)
from src.claude.sdk_integration import ClaudeSDKManager
from src.config.features import FeatureFlags
from src.config.settings import Settings
from src.events.bus import EventBus
from src.events.handlers import AgentHandler
from src.events.middleware import EventSecurityMiddleware
from src.exceptions import ConfigurationError
from src.notifications.service import NotificationService
from src.scheduler.scheduler import JobScheduler
from src.security.audit import AuditLogger, InMemoryAuditStorage
from src.security.auth import (
    AuthenticationManager,
    InMemoryTokenStorage,
    TokenAuthProvider,
    WhitelistAuthProvider,
)
from src.security.rate_limiter import RateLimiter
from src.security.validators import SecurityValidator
from src.storage.facade import Storage
from src.storage.session_storage import SQLiteSessionStorage


def setup_logging(debug: bool = False) -> None:
    """Configure structured logging."""
    level = logging.DEBUG if debug else logging.INFO

    # Configure standard logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            (
                structlog.processors.JSONRenderer()
                if not debug
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Claude Code Telegram Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version", action="version", version=f"Claude Code Telegram Bot {__version__}"
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("--config-file", type=Path, help="Path to configuration file")

    return parser.parse_args()


async def create_application(config: Settings) -> Dict[str, Any]:
    """Create and configure the application components."""
    logger = structlog.get_logger()
    logger.info("Creating application components")

    features = FeatureFlags(config)

    # Initialize storage system
    storage = Storage(config.database_url)
    await storage.initialize()

    # Create security components
    providers = []

    # Add whitelist provider if users are configured
    if config.allowed_users:
        providers.append(WhitelistAuthProvider(config.allowed_users))

    # Add token provider if enabled
    if config.enable_token_auth:
        token_storage = InMemoryTokenStorage()  # TODO: Use database storage
        providers.append(TokenAuthProvider(config.auth_token_secret, token_storage))

    # Fall back to allowing all users in development mode
    if not providers and config.development_mode:
        logger.warning(
            "No auth providers configured"
            " - creating development-only allow-all provider"
        )
        providers.append(WhitelistAuthProvider([], allow_all_dev=True))
    elif not providers:
        raise ConfigurationError("No authentication providers configured")

    auth_manager = AuthenticationManager(providers)
    security_validator = SecurityValidator(config.approved_directory)
    rate_limiter = RateLimiter(config)

    # Create audit storage and logger
    audit_storage = InMemoryAuditStorage()  # TODO: Use database storage in production
    audit_logger = AuditLogger(audit_storage)

    # Create Claude integration components with persistent storage
    session_storage = SQLiteSessionStorage(storage.db_manager)
    session_manager = SessionManager(config, session_storage)
    tool_monitor = ToolMonitor(config, security_validator)

    # Create Claude manager based on configuration
    if config.use_sdk:
        logger.info("Using Claude Python SDK integration")
        sdk_manager = ClaudeSDKManager(config)
        process_manager = None
    else:
        logger.info("Using Claude CLI subprocess integration")
        process_manager = ClaudeProcessManager(config)
        sdk_manager = None

    # Create main Claude integration facade
    claude_integration = ClaudeIntegration(
        config=config,
        process_manager=process_manager,
        sdk_manager=sdk_manager,
        session_manager=session_manager,
        tool_monitor=tool_monitor,
    )

    # --- Event bus and agentic platform components ---
    event_bus = EventBus()

    # Event security middleware
    event_security = EventSecurityMiddleware(
        event_bus=event_bus,
        security_validator=security_validator,
        auth_manager=auth_manager,
    )
    event_security.register()

    # Agent handler — translates events into Claude executions
    agent_handler = AgentHandler(
        event_bus=event_bus,
        claude_integration=claude_integration,
        default_working_directory=config.approved_directory,
        default_user_id=config.allowed_users[0] if config.allowed_users else 0,
    )
    agent_handler.register()

    # Create bot with all dependencies
    dependencies = {
        "auth_manager": auth_manager,
        "security_validator": security_validator,
        "rate_limiter": rate_limiter,
        "audit_logger": audit_logger,
        "claude_integration": claude_integration,
        "storage": storage,
        "event_bus": event_bus,
    }

    bot = ClaudeCodeBot(config, dependencies)

    # Notification service and scheduler need the bot's Telegram Bot instance,
    # which is only available after bot.initialize(). We store placeholders
    # and wire them up in run_application() after initialization.

    logger.info("Application components created successfully")

    return {
        "bot": bot,
        "claude_integration": claude_integration,
        "storage": storage,
        "config": config,
        "features": features,
        "event_bus": event_bus,
        "agent_handler": agent_handler,
        "auth_manager": auth_manager,
        "security_validator": security_validator,
    }


async def run_application(app: Dict[str, Any]) -> None:
    """Run the application with graceful shutdown handling."""
    logger = structlog.get_logger()
    bot: ClaudeCodeBot = app["bot"]
    claude_integration: ClaudeIntegration = app["claude_integration"]
    storage: Storage = app["storage"]
    config: Settings = app["config"]
    features: FeatureFlags = app["features"]
    event_bus: EventBus = app["event_bus"]

    notification_service: Optional[NotificationService] = None
    scheduler: Optional[JobScheduler] = None

    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum: int, frame: Any) -> None:
        logger.info("Shutdown signal received", signal=signum)
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("Starting Claude Code Telegram Bot")

        # Initialize the bot first (creates the Telegram Application)
        await bot.initialize()

        # Now wire up components that need the Telegram Bot instance
        telegram_bot = bot.app.bot

        # Start event bus
        await event_bus.start()

        # Notification service
        notification_service = NotificationService(
            event_bus=event_bus,
            bot=telegram_bot,
            default_chat_ids=config.notification_chat_ids or [],
        )
        notification_service.register()
        await notification_service.start()

        # Collect concurrent tasks
        tasks = []

        # Bot task — use start() which handles its own initialization check
        bot_task = asyncio.create_task(bot.start())
        tasks.append(bot_task)

        # API server (if enabled)
        if features.api_server_enabled:
            from src.api.server import run_api_server

            api_task = asyncio.create_task(
                run_api_server(event_bus, config, storage.db_manager)
            )
            tasks.append(api_task)
            logger.info("API server enabled", port=config.api_server_port)

        # Scheduler (if enabled)
        if features.scheduler_enabled:
            scheduler = JobScheduler(
                event_bus=event_bus,
                db_manager=storage.db_manager,
                default_working_directory=config.approved_directory,
            )
            await scheduler.start()
            logger.info("Job scheduler enabled")

        # Shutdown task
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        tasks.append(shutdown_task)

        # Wait for any task to complete or shutdown signal
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # Check completed tasks for exceptions
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                logger.error(
                    "Task failed",
                    task=task.get_name(),
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error("Application error", error=str(e))
        raise
    finally:
        # Ordered shutdown: scheduler -> API -> notification -> bot -> claude -> storage
        logger.info("Shutting down application")

        try:
            if scheduler:
                await scheduler.stop()
            if notification_service:
                await notification_service.stop()
            await event_bus.stop()
            await bot.stop()
            await claude_integration.shutdown()
            await storage.close()
        except Exception as e:
            logger.error("Error during shutdown", error=str(e))

        logger.info("Application shutdown complete")


async def main() -> None:
    """Main application entry point."""
    args = parse_args()
    setup_logging(debug=args.debug)

    logger = structlog.get_logger()
    logger.info("Starting Claude Code Telegram Bot", version=__version__)

    try:
        # Load configuration
        from src.config import FeatureFlags, load_config

        config = load_config(config_file=args.config_file)
        features = FeatureFlags(config)

        logger.info(
            "Configuration loaded",
            environment="production" if config.is_production else "development",
            enabled_features=features.get_enabled_features(),
            debug=config.debug,
        )

        # Initialize bot and Claude integration
        app = await create_application(config)
        await run_application(app)

    except ConfigurationError as e:
        logger.error("Configuration error", error=str(e))
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)


def run() -> None:
    """Synchronous entry point for setuptools."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)


if __name__ == "__main__":
    run()
