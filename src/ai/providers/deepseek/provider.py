"""DeepSeek AI Provider implementation.

DeepSeek provides DeepSeek Coder and DeepSeek Chat models with excellent
code generation capabilities at competitive pricing.

For production use:
1. Sign up at https://platform.deepseek.com/
2. Create API key
3. Set DEEPSEEK_API_KEY in environment

Note: DeepSeek API is OpenAI-compatible!
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


class DeepSeekProvider(BaseAIProvider):
    """DeepSeek AI provider.

    DeepSeek specializes in code generation with models like:
    - deepseek-coder (specialized for coding)
    - deepseek-chat (general purpose)

    Very cost-effective with OpenAI-compatible API.
    """

    def __init__(self, config: Settings):
        """Initialize DeepSeek provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self._config = config
        self._api_key = None
        self._api_url = "https://api.deepseek.com/v1/chat/completions"
        self._session: Optional[aiohttp.ClientSession] = None
        self._model = "deepseek-coder"  # Default model

    @property
    def name(self) -> str:
        """Get provider name."""
        return "deepseek"

    async def initialize(self) -> bool:
        """Initialize DeepSeek provider.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing DeepSeek provider")

            # Get API key from config
            self._api_key = getattr(self._config, "deepseek_api_key", None)
            if self._api_key:
                # Unwrap SecretStr if needed
                if hasattr(self._api_key, "get_secret_value"):
                    self._api_key = self._api_key.get_secret_value()

            if not self._api_key:
                logger.warning(
                    "DeepSeek API key not configured. "
                    "Set DEEPSEEK_API_KEY environment variable. "
                    "Get one from: https://platform.deepseek.com/"
                )
                self.status = ProviderStatus.OFFLINE
                return False

            # Get model preference
            self._model = getattr(self._config, "deepseek_model", "deepseek-coder")

            # Create aiohttp session
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
            )

            self.status = ProviderStatus.READY
            logger.info(f"DeepSeek provider initialized with model: {self._model}")
            return True

        except Exception as e:
            logger.error("Failed to initialize DeepSeek provider", error=str(e))
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
        """Send message to DeepSeek and get response.

        Args:
            prompt: User message
            working_directory: Working directory (for context)
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Returns:
            AI response from DeepSeek
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"DeepSeek provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("DeepSeek session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build messages array (OpenAI-compatible format)
            messages = []

            # Add system prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                # Default system prompt optimized for coding
                messages.append({
                    "role": "system",
                    "content": (
                        f"You are DeepSeek Coder, an expert AI programming assistant. "
                        f"Working directory: {working_directory}\n"
                        f"Provide high-quality, well-documented code that is:\n"
                        f"- Correct and efficient\n"
                        f"- Following best practices\n"
                        f"- Well-commented\n"
                        f"- Production-ready"
                    ),
                })

            # Add user message
            messages.append({"role": "user", "content": prompt})

            # Prepare request payload (OpenAI-compatible)
            payload = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.95),
            }

            # Send request to DeepSeek
            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 401:
                    raise RuntimeError(
                        "Invalid DeepSeek API key. Get one from https://platform.deepseek.com/"
                    )
                elif response.status == 429:
                    raise RuntimeError(
                        "DeepSeek rate limit exceeded. Please try again later."
                    )
                elif response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"DeepSeek API returned status {response.status}: {error_text}"
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

                # Calculate cost (DeepSeek is very affordable)
                cost = self._calculate_cost(prompt_tokens, completion_tokens)

                # Create universal response
                ai_response = AIResponse(
                    content=content,
                    session_id=session_id or f"deepseek_{id(self)}",
                    tokens_used=tokens_used,
                    cost=cost,
                    provider_name="deepseek",
                    model_name=self._model,
                    metadata={
                        "working_directory": str(working_directory),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "finish_reason": choice.get("finish_reason"),
                    },
                )

                self.status = ProviderStatus.READY
                return ai_response

        except Exception as e:
            logger.error("Error sending message to DeepSeek", error=str(e))
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
        """Stream response from DeepSeek.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Yields:
            Stream updates from DeepSeek
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"DeepSeek provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("DeepSeek session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({
                    "role": "system",
                    "content": f"You are DeepSeek Coder. Working directory: {working_directory}",
                })
            messages.append({"role": "user", "content": prompt})

            # Prepare streaming request
            payload = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
                "stream": True,
            }

            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"DeepSeek streaming failed: {response.status} - {error_text}"
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
            logger.error("Error streaming from DeepSeek", error=str(e))
            self.status = ProviderStatus.ERROR
            raise

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get DeepSeek capabilities.

        Returns:
            Provider capabilities
        """
        return ProviderCapabilities(
            name="deepseek",
            supports_streaming=True,
            supports_tools=False,  # DeepSeek doesn't support function calling yet
            supports_vision=False,
            supports_code_execution=False,
            max_tokens=4096,
            max_context_window=16384,  # DeepSeek Coder context
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
                "r",
                "julia",
                "dart",
                "lua",
                "perl",
                "shell",
            ],
            cost_per_1k_input_tokens=0.0014,  # Very affordable!
            cost_per_1k_output_tokens=0.0028,
            rate_limit_requests_per_minute=60,
            metadata={
                "model": self._model,
                "provider": "deepseek",
                "api_compatible": "openai",
                "specialized": "code_generation",
            },
        )

    async def health_check(self) -> bool:
        """Check if DeepSeek is accessible.

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
            logger.error("DeepSeek health check failed", error=str(e))
            return False

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost based on token usage.

        DeepSeek pricing (as of 2025):
        - Input: $0.14 per 1M tokens ($0.0014 per 1K)
        - Output: $0.28 per 1M tokens ($0.0028 per 1K)

        Args:
            prompt_tokens: Input tokens
            completion_tokens: Output tokens

        Returns:
            Cost in USD
        """
        return (prompt_tokens / 1000 * 0.0014) + (completion_tokens / 1000 * 0.0028)

    async def shutdown(self) -> None:
        """Shutdown DeepSeek provider."""
        logger.info("Shutting down DeepSeek provider")

        if self._session:
            await self._session.close()
            self._session = None

        await super().shutdown()
