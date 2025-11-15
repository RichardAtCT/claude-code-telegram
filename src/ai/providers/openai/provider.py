"""OpenAI AI Provider implementation.

OpenAI provides GPT-4 and GPT-3.5-turbo models with excellent code generation
capabilities and strong reasoning.

For production use:
1. Sign up at https://platform.openai.com/
2. Create API key
3. Set OPENAI_API_KEY in environment
"""

import structlog
from pathlib import Path
from typing import AsyncIterator, Optional, List, Dict, Any
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


class OpenAIProvider(BaseAIProvider):
    """OpenAI AI provider.

    Supports GPT-4, GPT-4-turbo, and GPT-3.5-turbo models with
    function calling and code generation.
    """

    def __init__(self, config: Settings):
        """Initialize OpenAI provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self._config = config
        self._api_key = None
        self._api_url = "https://api.openai.com/v1/chat/completions"
        self._session: Optional[aiohttp.ClientSession] = None
        self._model = "gpt-4-turbo-preview"  # Default model

    @property
    def name(self) -> str:
        """Get provider name."""
        return "openai"

    async def initialize(self) -> bool:
        """Initialize OpenAI provider.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing OpenAI provider")

            # Get API key from config
            self._api_key = getattr(self._config, "openai_api_key", None)
            if self._api_key:
                # Unwrap SecretStr if needed
                if hasattr(self._api_key, "get_secret_value"):
                    self._api_key = self._api_key.get_secret_value()

            if not self._api_key:
                logger.warning(
                    "OpenAI API key not configured. "
                    "Set OPENAI_API_KEY environment variable. "
                    "Get one from: https://platform.openai.com/api-keys"
                )
                self.status = ProviderStatus.OFFLINE
                return False

            # Get model preference
            self._model = getattr(
                self._config, "openai_model", "gpt-4-turbo-preview"
            )

            # Create aiohttp session
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
            )

            self.status = ProviderStatus.READY
            logger.info(f"OpenAI provider initialized with model: {self._model}")
            return True

        except Exception as e:
            logger.error("Failed to initialize OpenAI provider", error=str(e))
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
        """Send message to OpenAI and get response.

        Args:
            prompt: User message
            working_directory: Working directory (for context)
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            AI response from OpenAI
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"OpenAI provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("OpenAI session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build messages array
            messages = []

            # Add system prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                # Default system prompt for coding
                messages.append({
                    "role": "system",
                    "content": (
                        f"You are an expert coding assistant. "
                        f"Working directory: {working_directory}\n"
                        f"Provide high-quality, well-documented code that follows best practices."
                    ),
                })

            # Add user message
            messages.append({"role": "user", "content": prompt})

            # Prepare request payload
            payload = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 2048),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 1.0),
            }

            # Add function calling if supported
            if kwargs.get("functions"):
                payload["functions"] = kwargs["functions"]

            # Send request to OpenAI
            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 401:
                    raise RuntimeError(
                        "Invalid OpenAI API key. Get one from https://platform.openai.com/api-keys"
                    )
                elif response.status == 429:
                    raise RuntimeError(
                        "OpenAI rate limit exceeded. Please try again later or upgrade your plan."
                    )
                elif response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"OpenAI API returned status {response.status}: {error_text}"
                    )

                # Parse response
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

                # Calculate cost based on model
                cost = self._calculate_cost(
                    self._model, prompt_tokens, completion_tokens
                )

                # Extract tool calls if present
                tool_calls = []
                if "function_call" in message:
                    func_call = message["function_call"]
                    tool_calls.append(
                        ToolCall(
                            name=func_call.get("name", "unknown"),
                            input=json.loads(func_call.get("arguments", "{}")),
                        )
                    )

                # Create universal response
                ai_response = AIResponse(
                    content=content,
                    session_id=session_id or f"openai_{id(self)}",
                    tokens_used=tokens_used,
                    cost=cost,
                    provider_name="openai",
                    model_name=self._model,
                    tool_calls=tool_calls if tool_calls else None,
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
            logger.error("Error sending message to OpenAI", error=str(e))
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
        """Stream response from OpenAI.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Yields:
            Stream updates from OpenAI
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"OpenAI provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("OpenAI session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({
                    "role": "system",
                    "content": f"You are an expert coding assistant. Working directory: {working_directory}",
                })
            messages.append({"role": "user", "content": prompt})

            # Prepare streaming request
            payload = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 2048),
                "temperature": kwargs.get("temperature", 0.7),
                "stream": True,
            }

            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"OpenAI streaming failed: {response.status} - {error_text}"
                    )

                # Process SSE stream
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
            logger.error("Error streaming from OpenAI", error=str(e))
            self.status = ProviderStatus.ERROR
            raise

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get OpenAI capabilities.

        Returns:
            Provider capabilities
        """
        # Adjust based on model
        if "gpt-4" in self._model:
            max_tokens = 4096
            context_window = 128000 if "turbo" in self._model else 8192
            cost_input = 0.01 if "turbo" in self._model else 0.03
            cost_output = 0.03 if "turbo" in self._model else 0.06
        else:  # gpt-3.5-turbo
            max_tokens = 4096
            context_window = 16385
            cost_input = 0.0005
            cost_output = 0.0015

        return ProviderCapabilities(
            name="openai",
            supports_streaming=True,
            supports_tools=True,
            supports_vision="vision" in self._model,
            supports_code_execution=False,
            max_tokens=max_tokens,
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
                "r",
                "julia",
                "dart",
                "lua",
                "perl",
                "shell",
            ],
            cost_per_1k_input_tokens=cost_input,
            cost_per_1k_output_tokens=cost_output,
            rate_limit_requests_per_minute=60,
            metadata={
                "model": self._model,
                "provider": "openai",
                "supports_function_calling": True,
                "organization": getattr(self._config, "openai_org_id", None),
            },
        )

    async def health_check(self) -> bool:
        """Check if OpenAI is accessible.

        Returns:
            True if healthy
        """
        try:
            if self.status == ProviderStatus.OFFLINE:
                return False

            if not self._session or not self._api_key:
                return False

            # Simple health check - try minimal request
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
            }

            async with self._session.post(
                self._api_url, json=payload, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status in [200, 429]  # 429 = rate limited but API is up

        except Exception as e:
            logger.error("OpenAI health check failed", error=str(e))
            return False

    def _calculate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Calculate cost based on model and token usage.

        Args:
            model: Model name
            prompt_tokens: Input tokens
            completion_tokens: Output tokens

        Returns:
            Cost in USD
        """
        # Pricing per 1K tokens (as of 2025)
        pricing = {
            "gpt-4-turbo-preview": (0.01, 0.03),
            "gpt-4-turbo": (0.01, 0.03),
            "gpt-4": (0.03, 0.06),
            "gpt-4-32k": (0.06, 0.12),
            "gpt-3.5-turbo": (0.0005, 0.0015),
            "gpt-3.5-turbo-16k": (0.003, 0.004),
        }

        # Find matching pricing
        cost_in = 0.01
        cost_out = 0.03
        for model_key, (in_price, out_price) in pricing.items():
            if model_key in model:
                cost_in = in_price
                cost_out = out_price
                break

        return (prompt_tokens / 1000 * cost_in) + (completion_tokens / 1000 * cost_out)

    async def shutdown(self) -> None:
        """Shutdown OpenAI provider."""
        logger.info("Shutting down OpenAI provider")

        if self._session:
            await self._session.close()
            self._session = None

        await super().shutdown()
