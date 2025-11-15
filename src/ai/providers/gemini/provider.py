"""Google Gemini AI Provider implementation.

This provides integration with Google's Gemini models through the
Google AI Studio API.
"""

import structlog
from pathlib import Path
from typing import AsyncIterator, Optional
import asyncio

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


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider.

    Note: This is a minimal implementation. For production use:
    1. Install: pip install google-generativeai
    2. Get API key from: https://aistudio.google.com/app/apikey
    3. Set GEMINI_API_KEY in environment
    """

    def __init__(self, config: Settings):
        """Initialize Gemini provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self._config = config
        self._model = None
        self._api_key = None

    @property
    def name(self) -> str:
        """Get provider name."""
        return "gemini"

    async def initialize(self) -> bool:
        """Initialize Gemini provider.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Initializing Gemini provider")

            # Get API key from config
            self._api_key = getattr(self._config, "gemini_api_key", None)

            if not self._api_key:
                logger.warning(
                    "Gemini API key not configured. "
                    "Set GEMINI_API_KEY environment variable."
                )
                self.status = ProviderStatus.OFFLINE
                return False

            try:
                import google.generativeai as genai

                # Configure Gemini
                genai.configure(api_key=self._api_key)

                # Initialize model
                model_name = getattr(
                    self._config, "gemini_model", "gemini-1.5-pro-latest"
                )
                self._model = genai.GenerativeModel(model_name)

                self.status = ProviderStatus.READY
                logger.info(
                    "Gemini provider initialized successfully", model=model_name
                )
                return True

            except ImportError:
                logger.error(
                    "google-generativeai package not installed. "
                    "Install with: pip install google-generativeai"
                )
                self.status = ProviderStatus.OFFLINE
                return False

        except Exception as e:
            logger.error("Failed to initialize Gemini provider", error=str(e))
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
        """Send message to Gemini and get response.

        Args:
            prompt: User message
            working_directory: Working directory (for context)
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Returns:
            AI response from Gemini
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Gemini provider not ready: {self.status}")

        self.status = ProviderStatus.BUSY

        try:
            # Build context-aware prompt
            full_prompt = self._build_prompt(
                prompt, working_directory, system_prompt
            )

            # Generate response
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self._model.generate_content, full_prompt
            )

            # Extract text
            content = response.text if hasattr(response, "text") else str(response)

            # Count tokens (rough estimate)
            tokens_used = len(content.split()) * 1.3  # Rough token estimate

            # Gemini free tier has no cost
            cost = 0.0

            # Create universal response
            ai_response = AIResponse(
                content=content,
                session_id=session_id or f"gemini_{id(self)}",
                tokens_used=int(tokens_used),
                cost=cost,
                provider_name="gemini",
                model_name=getattr(self._config, "gemini_model", "gemini-1.5-pro"),
                metadata={
                    "working_directory": str(working_directory),
                    "free_tier": True,
                },
            )

            self.status = ProviderStatus.READY
            return ai_response

        except Exception as e:
            logger.error("Error sending message to Gemini", error=str(e))
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
        """Stream response from Gemini.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Yields:
            Stream updates from Gemini
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Gemini provider not ready: {self.status}")

        self.status = ProviderStatus.BUSY

        try:
            # Build prompt
            full_prompt = self._build_prompt(
                prompt, working_directory, system_prompt
            )

            # Stream response
            loop = asyncio.get_event_loop()
            response_stream = await loop.run_in_executor(
                None,
                lambda: self._model.generate_content(full_prompt, stream=True),
            )

            # Yield chunks
            for chunk in response_stream:
                if hasattr(chunk, "text"):
                    yield AIStreamUpdate(
                        content_delta=chunk.text,
                        is_complete=False,
                    )

            # Final update
            yield AIStreamUpdate(
                content_delta="",
                is_complete=True,
            )

            self.status = ProviderStatus.READY

        except Exception as e:
            logger.error("Error streaming from Gemini", error=str(e))
            self.status = ProviderStatus.ERROR
            raise

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get Gemini capabilities.

        Returns:
            Provider capabilities
        """
        return ProviderCapabilities(
            name="gemini",
            supports_streaming=True,
            supports_tools=True,  # Gemini 1.5 supports function calling
            supports_vision=True,  # Gemini supports multimodal
            supports_code_execution=True,  # Gemini 1.5 has code execution
            max_tokens=8192,
            max_context_window=1000000,  # Gemini 1.5 has 1M token context!
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
            ],
            cost_per_1k_input_tokens=0.0,  # Free tier
            cost_per_1k_output_tokens=0.0,  # Free tier
            rate_limit_requests_per_minute=60,
            metadata={
                "model": "gemini-1.5-pro",
                "provider": "google",
                "free_tier": True,
                "max_context": "1M tokens",
            },
        )

    async def health_check(self) -> bool:
        """Check if Gemini is accessible.

        Returns:
            True if healthy
        """
        try:
            if self.status == ProviderStatus.OFFLINE:
                return False

            if not self._model:
                return False

            # Could do a test request here, but for now just check status
            return self.status in [ProviderStatus.READY, ProviderStatus.BUSY]

        except Exception as e:
            logger.error("Gemini health check failed", error=str(e))
            return False

    def _build_prompt(
        self,
        prompt: str,
        working_directory: Path,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Build context-aware prompt for Gemini.

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
            parts.append(f"System Instructions: {system_prompt}\n")

        # Add context
        parts.append(f"Working Directory: {working_directory}\n")
        parts.append(
            "You are an AI coding assistant helping via Telegram. "
            "Provide concise, practical code solutions.\n"
        )

        # Add user prompt
        parts.append(f"\nUser: {prompt}")

        return "\n".join(parts)

    async def shutdown(self) -> None:
        """Shutdown Gemini provider."""
        logger.info("Shutting down Gemini provider")
        self._model = None
        await super().shutdown()
