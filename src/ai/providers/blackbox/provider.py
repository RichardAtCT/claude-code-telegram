"""Blackbox AI Provider implementation.

This provides integration with Blackbox AI code generation platform.

Note: Blackbox AI doesn't have an official public API yet. This implementation
uses HTTP requests to their service. For production use, wait for official API
or use their web interface.
"""

import structlog
import json
import asyncio
from pathlib import Path
from typing import AsyncIterator, Optional
import aiohttp

from ...base_provider import (
    AIMessage,
    AIResponse,
    AIStreamUpdate,
    BaseAIProvider,
    ProviderCapabilities,
    ProviderStatus,
)
from ....config.settings import Settings

logger = structlog.get_logger()


class BlackboxProvider(BaseAIProvider):
    """Blackbox AI provider.

    Note: This is a minimal implementation using Blackbox's web endpoints.
    For production use:
    1. Monitor for official API release
    2. Consider rate limiting
    3. Handle authentication if required
    """

    def __init__(self, config: Settings):
        """Initialize Blackbox provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self._config = config
        self._api_url = "https://www.blackbox.ai/api/chat"
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        """Get provider name."""
        return "blackbox"

    async def initialize(self) -> bool:
        """Initialize Blackbox provider.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing Blackbox provider")

            # Create aiohttp session
            self._session = aiohttp.ClientSession()

            # Check if Blackbox is accessible
            try:
                async with self._session.get(
                    "https://www.blackbox.ai",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.status = ProviderStatus.READY
                        logger.info("Blackbox provider initialized successfully")
                        return True
                    else:
                        logger.warning(
                            f"Blackbox returned status {response.status}"
                        )
                        self.status = ProviderStatus.OFFLINE
                        return False

            except asyncio.TimeoutError:
                logger.warning("Blackbox connection timeout")
                self.status = ProviderStatus.OFFLINE
                return False

        except Exception as e:
            logger.error("Failed to initialize Blackbox provider", error=str(e))
            self.status = ProviderStatus.ERROR
            return False

    async def send_message(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Send message to Blackbox and get response.

        Args:
            prompt: User message
            working_directory: Working directory (for context)
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Returns:
            AI response from Blackbox
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Blackbox provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("Blackbox session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build context-aware prompt
            full_prompt = self._build_prompt(
                prompt, working_directory, system_prompt
            )

            # Prepare request payload
            # Note: This is based on reverse-engineering Blackbox's web interface
            # May need updates if their API changes
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ],
                "previewToken": None,
                "codeModelMode": True,  # Enable code-focused mode
                "agentMode": {},
                "trendingAgentMode": {},
                "isMicMode": False,
                "isChromeExt": False,
                "githubToken": None,
            }

            # Send request
            async with self._session.post(
                self._api_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; ClaudeCodeBot/1.0)",
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Blackbox API returned status {response.status}"
                    )

                # Parse response
                response_text = await response.text()

                # Blackbox returns text responses
                content = response_text.strip()

                if not content:
                    content = "I couldn't generate a response. Please try again."

            # Estimate tokens (rough)
            tokens_used = len(content.split()) * 1.3

            # Blackbox pricing (estimated - they don't have public pricing)
            # Assume free tier or minimal cost
            cost = 0.0

            # Create universal response
            ai_response = AIResponse(
                content=content,
                session_id=session_id or f"blackbox_{id(self)}",
                tokens_used=int(tokens_used),
                cost=cost,
                provider_name="blackbox",
                model_name="blackbox-code",
                metadata={
                    "working_directory": str(working_directory),
                    "code_mode": True,
                },
            )

            self.status = ProviderStatus.READY
            return ai_response

        except Exception as e:
            logger.error("Error sending message to Blackbox", error=str(e))
            self.status = ProviderStatus.ERROR
            raise

    async def stream_message(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[AIStreamUpdate]:
        """Stream response from Blackbox.

        Note: Blackbox may not support streaming. Falls back to complete response.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Yields:
            Stream updates
        """
        # Blackbox doesn't publicly support streaming yet
        # Return complete response as single update
        response = await self.send_message(
            prompt=prompt,
            working_directory=working_directory,
            session_id=session_id,
            system_prompt=system_prompt,
            **kwargs,
        )

        yield AIStreamUpdate(
            content_delta=response.content,
            is_complete=True,
            metadata=response.metadata,
        )

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get Blackbox capabilities.

        Returns:
            Provider capabilities
        """
        return ProviderCapabilities(
            name="blackbox",
            supports_streaming=False,  # Not publicly available
            supports_tools=False,  # Not in current version
            supports_vision=False,
            supports_code_execution=False,
            max_tokens=4096,  # Estimated
            max_context_window=8192,  # Estimated
            supported_languages=[
                "python",
                "javascript",
                "typescript",
                "java",
                "cpp",
                "csharp",
                "go",
                "rust",
                "ruby",
                "php",
                "swift",
                "kotlin",
                "sql",
                "html",
                "css",
            ],
            cost_per_1k_input_tokens=0.0,  # Unknown/Free tier
            cost_per_1k_output_tokens=0.0,
            rate_limit_requests_per_minute=20,  # Conservative estimate
            metadata={
                "model": "blackbox-code",
                "provider": "blackbox.ai",
                "note": "Using web API - may be unstable",
                "code_focused": True,
            },
        )

    async def health_check(self) -> bool:
        """Check if Blackbox is accessible.

        Returns:
            True if healthy
        """
        try:
            if self.status == ProviderStatus.OFFLINE:
                return False

            if not self._session:
                return False

            # Quick connectivity check
            async with self._session.get(
                "https://www.blackbox.ai",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200

        except Exception as e:
            logger.error("Blackbox health check failed", error=str(e))
            return False

    def _build_prompt(
        self,
        prompt: str,
        working_directory: Path,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Build context-aware prompt for Blackbox.

        Args:
            prompt: User message
            working_directory: Current directory
            system_prompt: Optional system instructions

        Returns:
            Full prompt with context
        """
        parts = []

        # Add system prompt if provided
        if system_prompt:
            parts.append(f"System: {system_prompt}\n")

        # Add context
        parts.append(f"Working Directory: {working_directory}\n")
        parts.append(
            "You are a code generation AI assistant. "
            "Provide concise, working code solutions.\n"
        )

        # Add user prompt
        parts.append(f"\n{prompt}")

        return "\n".join(parts)

    async def shutdown(self) -> None:
        """Shutdown Blackbox provider."""
        logger.info("Shutting down Blackbox provider")

        if self._session:
            await self._session.close()
            self._session = None

        await super().shutdown()
