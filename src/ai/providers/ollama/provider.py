"""Ollama AI Provider implementation.

Ollama provides local AI models that run on your own hardware.
Great for privacy, offline use, and no API costs.

For production use:
1. Install Ollama: https://ollama.ai/
2. Pull a model: `ollama pull codellama`
3. Set OLLAMA_MODEL in environment (default: codellama)
4. Optionally set OLLAMA_HOST (default: http://localhost:11434)
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
)
from ....config.settings import Settings

logger = structlog.get_logger()


class OllamaProvider(BaseAIProvider):
    """Ollama local AI provider.

    Supports running models locally including:
    - CodeLlama (code generation)
    - Llama 2/3 (general purpose)
    - Mistral (fast, efficient)
    - DeepSeek Coder (code-focused)
    - And many more...
    """

    def __init__(self, config: Settings):
        """Initialize Ollama provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self._config = config
        self._host = "http://localhost:11434"
        self._model = "codellama"
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        """Get provider name."""
        return "ollama"

    async def initialize(self) -> bool:
        """Initialize Ollama provider.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing Ollama provider")

            # Get host and model from config
            self._host = getattr(
                self._config, "ollama_host", "http://localhost:11434"
            )
            self._model = getattr(self._config, "ollama_model", "codellama")

            # Create aiohttp session
            self._session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json"}
            )

            # Check if Ollama is running
            try:
                async with self._session.get(
                    f"{self._host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Ollama not accessible at {self._host}")

                    # Check if model is available
                    data = await response.json()
                    models = [m["name"] for m in data.get("models", [])]

                    if not any(self._model in m for m in models):
                        logger.warning(
                            f"Model '{self._model}' not found. "
                            f"Available models: {', '.join(models)}. "
                            f"Pull it with: ollama pull {self._model}"
                        )
                        # Don't fail - model might still work
            except aiohttp.ClientError as e:
                logger.warning(
                    f"Ollama not accessible at {self._host}: {e}. "
                    f"Make sure Ollama is running: https://ollama.ai/"
                )
                self.status = ProviderStatus.OFFLINE
                return False

            self.status = ProviderStatus.READY
            logger.info(
                f"Ollama provider initialized with model: {self._model} at {self._host}"
            )
            return True

        except Exception as e:
            logger.error("Failed to initialize Ollama provider", error=str(e))
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
        """Send message to Ollama and get response.

        Args:
            prompt: User message
            working_directory: Working directory (for context)
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Returns:
            AI response from Ollama
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Ollama provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("Ollama session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build prompt with context
            full_prompt = self._build_prompt(
                prompt, working_directory, system_prompt
            )

            # Prepare request payload
            payload = {
                "model": kwargs.get("model", self._model),
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 2048),
                    "top_p": kwargs.get("top_p", 0.9),
                },
            }

            # Send request to Ollama
            async with self._session.post(
                f"{self._host}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),  # Local models can be slow
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Ollama API returned status {response.status}: {error_text}"
                    )

                # Parse response
                data = await response.json()
                content = data.get("response", "")

                if not content:
                    content = "No response generated. Please try again."

                # Extract stats (Ollama provides detailed metrics)
                total_duration = data.get("total_duration", 0)
                load_duration = data.get("load_duration", 0)
                eval_count = data.get("eval_count", 0)
                prompt_eval_count = data.get("prompt_eval_count", 0)

                # Estimate tokens (Ollama doesn't return exact tokens)
                tokens_used = eval_count + prompt_eval_count

                # Cost is $0 for local models
                cost = 0.0

                # Create universal response
                ai_response = AIResponse(
                    content=content,
                    session_id=session_id or f"ollama_{id(self)}",
                    tokens_used=tokens_used,
                    cost=cost,
                    provider_name="ollama",
                    model_name=self._model,
                    metadata={
                        "working_directory": str(working_directory),
                        "model": data.get("model"),
                        "total_duration_ms": total_duration / 1_000_000,  # ns to ms
                        "load_duration_ms": load_duration / 1_000_000,
                        "eval_count": eval_count,
                        "prompt_eval_count": prompt_eval_count,
                        "done": data.get("done", False),
                    },
                )

                self.status = ProviderStatus.READY
                return ai_response

        except Exception as e:
            logger.error("Error sending message to Ollama", error=str(e))
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
        """Stream response from Ollama.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Optional system instructions
            **kwargs: Additional parameters

        Yields:
            Stream updates from Ollama
        """
        if self.status != ProviderStatus.READY:
            raise RuntimeError(f"Ollama provider not ready: {self.status}")

        if not self._session:
            raise RuntimeError("Ollama session not initialized")

        self.status = ProviderStatus.BUSY

        try:
            # Build prompt
            full_prompt = self._build_prompt(
                prompt, working_directory, system_prompt
            )

            # Prepare streaming request
            payload = {
                "model": kwargs.get("model", self._model),
                "prompt": full_prompt,
                "stream": True,
                "options": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 2048),
                },
            }

            async with self._session.post(
                f"{self._host}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Ollama streaming failed: {response.status} - {error_text}"
                    )

                # Process newline-delimited JSON stream
                async for line in response.content:
                    if not line:
                        continue

                    try:
                        data = json.loads(line.decode("utf-8"))
                        content_delta = data.get("response", "")

                        if content_delta:
                            yield AIStreamUpdate(
                                content_delta=content_delta,
                                is_complete=False,
                            )

                        # Check if done
                        if data.get("done", False):
                            yield AIStreamUpdate(
                                content_delta="",
                                is_complete=True,
                                metadata={
                                    "total_duration": data.get("total_duration", 0),
                                    "eval_count": data.get("eval_count", 0),
                                },
                            )
                            break

                    except json.JSONDecodeError:
                        continue

            self.status = ProviderStatus.READY

        except Exception as e:
            logger.error("Error streaming from Ollama", error=str(e))
            self.status = ProviderStatus.ERROR
            raise

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get Ollama capabilities.

        Returns:
            Provider capabilities
        """
        # Capabilities vary by model
        # CodeLlama defaults shown here
        return ProviderCapabilities(
            name="ollama",
            supports_streaming=True,
            supports_tools=False,  # Depends on model
            supports_vision=False,  # LLaVA models support vision
            supports_code_execution=False,
            max_tokens=4096,
            max_context_window=4096,  # Varies by model
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
            cost_per_1k_input_tokens=0.0,  # FREE - runs locally
            cost_per_1k_output_tokens=0.0,
            rate_limit_requests_per_minute=0,  # No limit - local
            metadata={
                "model": self._model,
                "provider": "ollama",
                "host": self._host,
                "local": True,
                "privacy_focused": True,
                "offline_capable": True,
            },
        )

    async def health_check(self) -> bool:
        """Check if Ollama is accessible.

        Returns:
            True if healthy
        """
        try:
            if self.status == ProviderStatus.OFFLINE:
                return False

            if not self._session:
                return False

            # Check if Ollama is responding
            async with self._session.get(
                f"{self._host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200

        except Exception as e:
            logger.error("Ollama health check failed", error=str(e))
            return False

    def _build_prompt(
        self,
        prompt: str,
        working_directory: Path,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Build context-aware prompt for Ollama.

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
            parts.append(f"### System\n{system_prompt}\n\n")

        # Add context
        parts.append(f"### Context\nWorking Directory: {working_directory}\n\n")

        # Add instruction
        parts.append(f"### Instruction\n{prompt}\n\n")

        # Add response prefix
        parts.append("### Response\n")

        return "".join(parts)

    async def shutdown(self) -> None:
        """Shutdown Ollama provider."""
        logger.info("Shutting down Ollama provider")

        if self._session:
            await self._session.close()
            self._session = None

        await super().shutdown()
