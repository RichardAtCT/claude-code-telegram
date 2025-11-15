"""AI Provider Manager for orchestrating multiple AI providers.

This module manages multiple AI providers, handles routing, fallbacks,
and provides a unified interface for the bot to use.
"""

import structlog
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .base_provider import (
    AIMessage,
    AIResponse,
    AIStreamUpdate,
    BaseAIProvider,
    ProviderCapabilities,
    ProviderStatus,
)
from ..config.settings import Settings
from ..exceptions import ConfigurationError

logger = structlog.get_logger()


class AIProviderManager:
    """Manages multiple AI providers and provides unified interface."""

    def __init__(self, config: Settings):
        """Initialize the provider manager.

        Args:
            config: Application settings
        """
        self.config = config
        self.providers: Dict[str, BaseAIProvider] = {}
        self.default_provider: Optional[str] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all configured providers."""
        if self._initialized:
            logger.warning("Provider manager already initialized")
            return

        logger.info("Initializing AI provider manager")

        # For now, we'll set default provider to None since we haven't
        # registered any providers yet. This will be populated when
        # providers are registered.
        self.default_provider = getattr(self.config, "default_ai_provider", None)

        self._initialized = True
        logger.info(
            "AI provider manager initialized",
            default_provider=self.default_provider,
            provider_count=len(self.providers),
        )

    async def register_provider(
        self,
        provider: BaseAIProvider,
        set_as_default: bool = False,
    ) -> None:
        """Register a new AI provider.

        Args:
            provider: AI provider instance
            set_as_default: Whether to set this as default provider
        """
        provider_name = provider.name

        logger.info(f"Registering provider: {provider_name}")

        # Initialize the provider
        try:
            success = await provider.initialize()
            if not success:
                logger.error(f"Failed to initialize provider: {provider_name}")
                return
        except Exception as e:
            logger.error(
                f"Error initializing provider: {provider_name}",
                error=str(e),
            )
            return

        # Register the provider
        self.providers[provider_name] = provider

        # Set as default if requested or if it's the first provider
        if set_as_default or self.default_provider is None:
            self.default_provider = provider_name
            logger.info(f"Set default provider to: {provider_name}")

        logger.info(
            f"Provider registered successfully: {provider_name}",
            provider_count=len(self.providers),
        )

    def get_provider(self, provider_name: Optional[str] = None) -> BaseAIProvider:
        """Get a specific provider or the default.

        Args:
            provider_name: Name of provider to get, or None for default

        Returns:
            AI provider instance

        Raises:
            ConfigurationError: If provider not found
        """
        # Use default if no name specified
        if provider_name is None:
            provider_name = self.default_provider

        if provider_name is None:
            raise ConfigurationError("No default provider configured")

        if provider_name not in self.providers:
            raise ConfigurationError(
                f"Provider '{provider_name}' not found. "
                f"Available: {list(self.providers.keys())}"
            )

        return self.providers[provider_name]

    async def send_message(
        self,
        prompt: str,
        working_directory: Path,
        provider_name: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Send message using specified or default provider.

        Args:
            prompt: User message
            working_directory: Current working directory
            provider_name: Provider to use (None = default)
            session_id: Optional session ID
            **kwargs: Additional provider-specific parameters

        Returns:
            AI response

        Raises:
            ConfigurationError: If provider not available
        """
        provider = self.get_provider(provider_name)

        logger.info(
            "Sending message to AI provider",
            provider=provider.name,
            prompt_length=len(prompt),
            session_id=session_id,
        )

        try:
            response = await provider.send_message(
                prompt=prompt,
                working_directory=working_directory,
                session_id=session_id,
                **kwargs,
            )

            logger.info(
                "Received AI response",
                provider=provider.name,
                tokens=response.tokens_used,
                cost=response.cost,
            )

            return response

        except Exception as e:
            logger.error(
                "Error getting AI response",
                provider=provider.name,
                error=str(e),
            )
            raise

    async def stream_message(
        self,
        prompt: str,
        working_directory: Path,
        provider_name: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """Stream message using specified or default provider.

        Args:
            prompt: User message
            working_directory: Current working directory
            provider_name: Provider to use (None = default)
            session_id: Optional session ID
            **kwargs: Additional provider-specific parameters

        Yields:
            Stream updates from the AI

        Raises:
            ConfigurationError: If provider not available
        """
        provider = self.get_provider(provider_name)

        logger.info(
            "Starting message stream",
            provider=provider.name,
            prompt_length=len(prompt),
        )

        async for update in provider.stream_message(
            prompt=prompt,
            working_directory=working_directory,
            session_id=session_id,
            **kwargs,
        ):
            yield update

    async def get_capabilities(
        self,
        provider_name: Optional[str] = None,
    ) -> ProviderCapabilities:
        """Get capabilities of a provider.

        Args:
            provider_name: Provider name (None = default)

        Returns:
            Provider capabilities
        """
        provider = self.get_provider(provider_name)
        return await provider.get_capabilities()

    async def health_check(self, provider_name: Optional[str] = None) -> bool:
        """Check health of a provider.

        Args:
            provider_name: Provider name (None = default)

        Returns:
            True if provider is healthy
        """
        try:
            provider = self.get_provider(provider_name)
            return await provider.health_check()
        except Exception as e:
            logger.error(
                "Health check failed",
                provider=provider_name,
                error=str(e),
            )
            return False

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers.

        Returns:
            Dictionary mapping provider names to health status
        """
        results = {}
        for provider_name in self.providers.keys():
            results[provider_name] = await self.health_check(provider_name)
        return results

    def list_providers(self) -> List[str]:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return list(self.providers.keys())

    def get_provider_status(self, provider_name: Optional[str] = None) -> ProviderStatus:
        """Get status of a provider.

        Args:
            provider_name: Provider name (None = default)

        Returns:
            Provider status
        """
        provider = self.get_provider(provider_name)
        return provider.status

    async def shutdown(self) -> None:
        """Shutdown all providers and cleanup resources."""
        logger.info("Shutting down AI provider manager")

        for provider_name, provider in self.providers.items():
            try:
                logger.info(f"Shutting down provider: {provider_name}")
                await provider.shutdown()
            except Exception as e:
                logger.error(
                    f"Error shutting down provider: {provider_name}",
                    error=str(e),
                )

        self.providers.clear()
        self.default_provider = None
        self._initialized = False

        logger.info("AI provider manager shutdown complete")
