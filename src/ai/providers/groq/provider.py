"""Groq AI Provider implementation.

Groq provides ultra-fast AI inference with models like Llama, Mixtral, and Gemma.
Known for exceptional speed powered by LPU (Language Processing Unit) technology.

For production use:
1. Sign up at https://console.groq.com/
2. Create API key
3. Set GROQ_API_KEY in environment

Note: Groq API is OpenAI-compatible!
"""

import structlog
from pathlib import Path
from typing import AsyncIterator, Optional
import aiohttp
import json

from ...base_provider import (
    AIMessage,
    AIResponse,
    AIStreamUpdate,
    BaseAIProvider,
    ProviderCapabilities,
    ProviderStatus,
    ToolCall,
)
from ....config.settings import Settings

logger = structlog.get_logger()


class GroqProvider(BaseAIProvider):
    """Groq AI provider.

    Groq specializes in ultra-fast inference with models:
    - llama3-70b-8192 (Llama 3, 70B params)
    - mixtral-8x7b-32768 (Mixtral MoE)
    - gemma-7b-it (Google's Gemma)

    Known for incredible speed powered by LPU technology.
    """

    def __init__(self, config: Settings):
        """Initialize Groq provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self._config = config
        self._api_key = None
        self._api_url = "https://api.groq.com/openai/v1/chat/completions"
        self._session: Optional[aiohttp.ClientSession] = None
        self._model = "llama3-70b-8192"  # Default model

    @property
    def name(self) -> str:
        """Get provider name."""
        return "groq"

    async def initialize(self) -> bool:
        """Initialize Groq provider.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing Groq provider")

            # Get API key from config
            self._api_key = getattr(self._config, "groq_api_key", None)
            if self._api_key:
                # Unwrap SecretStr if needed
                if hasattr(self._api_key, "get_secret_value"):
                    self._api_key = self._api_key.get_secret_value()

            if not self._api_key:
                logger.warning(
                    "Groq API key not configured. "
                    "Set GROQ_API_KEY environment variable. "
                    "Get one from: https://console.groq.com/"
                )
                self.status = ProviderStatus.OFFLINE
                return False

            # Get model preference
            self._model = getattr(self._config, "groq_model", "llama3-70b-8192")

            # Create aiohttp session
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
            )

            self.status = ProviderStatus.READY
            logger.info(f"Groq provider initialized with model: {self._model}")
            return True

        except Exception as e:
            logger.error("Failed to initialize Groq provider", error=str(e))
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
        """Send message to Groq and get response.

        Args:
            prompt: User message
            working_directory: Working directory (for context)
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Returns:
            AI response from Groq
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Groq provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("Groq session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build messages array (OpenAI-compatible format)
            messages = []

            # Add system prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                # Default system prompt
                messages.append({
                    "role": "system",
                    "content": (
                        f"You are a helpful AI coding assistant. "
                        f"Working directory: {working_directory}\n"
                        f"Provide clear, concise, and high-quality code solutions."
                    ),
                })

            # Add user message
            messages.append({"role": "user", "content": prompt})

            # Prepare request payload (OpenAI-compatible)
            payload = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 8192),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 1.0),
            }

            # Send request to Groq
            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 401:
                    raise RuntimeError(
                        "Invalid Groq API key. Get one from https://console.groq.com/"
                    )
                elif response.status == 429:
                    raise RuntimeError(
                        "Groq rate limit exceeded. Please try again later."
                    )
                elif response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Groq API returned status {response.status}: {error_text}"
                    )

                # Parse response (OpenAI-compatible format)
                data = await response.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "")

                if not content:
                    content = "No response generated. Please try again."

                # Extract usage stats
                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens", 0)
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                # Groq is currently FREE in beta
                cost = 0.0

                # Create universal response
                ai_response = AIResponse(
                    content=content,
                    session_id=session_id or f"groq_{id(self)}",
                    tokens_used=tokens_used,
                    cost=cost,
                    provider_name="groq",
                    model_name=self._model,
                    metadata={
                        "working_directory": str(working_directory),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "finish_reason": choice.get("finish_reason"),
                        "ultra_fast": True,
                    },
                )

                self.status = ProviderStatus.READY
                return ai_response

        except Exception as e:
            logger.error("Error sending message to Groq", error=str(e))
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
        """Stream response from Groq.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Yields:
            Stream updates from Groq
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Groq provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("Groq session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({
                    "role": "system",
                    "content": f"You are a helpful AI assistant. Working directory: {working_directory}",
                })
            messages.append({"role": "user", "content": prompt})

            # Prepare streaming request
            payload = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 8192),
                "temperature": kwargs.get("temperature", 0.7),
                "stream": True,
            }

            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Groq streaming failed: {response.status} - {error_text}"
                    )

                # Process SSE stream (OpenAI-compatible)
                async for line in response.content:
                    line = line.decode("utf-8").strip()

                    if not line or line == "data: [DONE]":
                        continue

                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content_delta = delta.get("content", "")

                            if content_delta:
                                yield AIStreamUpdate(
                                    content_delta=content_delta,
                                    is_complete=False,
                                )

                            # Check if done
                            if choice.get("finish_reason"):
                                yield AIStreamUpdate(
                                    content_delta="",
                                    is_complete=True,
                                )
                                break

                        except json.JSONDecodeError:
                            continue

            self.status = ProviderStatus.READY

        except Exception as e:
            logger.error("Error streaming from Groq", error=str(e))
            self.status = ProviderStatus.ERROR
            raise

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get Groq capabilities.

        Returns:
            Provider capabilities
        """
        # Context window varies by model
        context_window = 8192
        if "32768" in self._model:
            context_window = 32768
        elif "128k" in self._model:
            context_window = 131072

        return ProviderCapabilities(
            name="groq",
            supports_streaming=True,
            supports_tools=True,  # Groq supports function calling
            supports_vision=False,
            supports_code_execution=False,
            max_tokens=context_window,
            max_context_window=context_window,
            supported_languages=[
                "python",
                "javascript",
                "typescript",
                "java",
                "cpp",
                "c",
                "csharp",
                "go",
                "rust",
                "ruby",
                "php",
                "swift",
                "kotlin",
                "scala",
            ],
            cost_per_1k_input_tokens=0.0,  # FREE during beta
            cost_per_1k_output_tokens=0.0,
            rate_limit_requests_per_minute=30,  # Conservative estimate
            metadata={
                "model": self._model,
                "provider": "groq",
                "api_compatible": "openai",
                "lpu_powered": True,
                "ultra_fast": True,
                "free_beta": True,
            },
        )

    async def health_check(self) -> bool:
        """Check if Groq is accessible.

        Returns:
            True if healthy
        """
        try:
            if self.status == ProviderStatus.OFFLINE:
                return False

            if not self._session or not self._api_key:
                return False

            # Simple health check
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
            }

            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status in [200, 429]

        except Exception as e:
            logger.error("Groq health check failed", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Shutdown Groq provider."""
        logger.info("Shutting down Groq provider")

        if self._session:
            await self._session.close()
            self._session = None

        await super().shutdown()
