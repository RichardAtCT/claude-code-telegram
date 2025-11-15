"""Claude AI Provider implementation.

This wraps the existing Claude integration (facade.py) to conform to the
BaseAIProvider interface, allowing Claude to work alongside other AI providers.
"""

import structlog
from pathlib import Path
from typing import AsyncIterator, Optional

from ...base_provider import (
    AIMessage,
    AIResponse,
    AIStreamUpdate,
    BaseAIProvider,
    ProviderCapabilities,
    ProviderStatus,
    ToolCall,
    ToolResult,
)
from ....claude.facade import ClaudeIntegration as ClaudeFacade
from ....claude.integration import ClaudeResponse, StreamUpdate
from ....config.settings import Settings

logger = structlog.get_logger()


class ClaudeProvider(BaseAIProvider):
    """Claude AI provider using existing Claude integration."""

    def __init__(self, config: Settings):
        """Initialize Claude provider.

        Args:
            config: Application settings
        """
        super().__init__(config)
        self.claude = ClaudeFacade(config)
        self._config = config

    @property
    def name(self) -> str:
        """Get provider name."""
        return "claude"

    async def initialize(self) -> bool:
        """Initialize Claude provider.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing Claude provider")

            # Claude facade doesn't need explicit initialization
            # It's initialized on first use
            self.status = ProviderStatus.READY

            logger.info("Claude provider initialized successfully")
            return True

        except Exception as e:
            logger.error("Failed to initialize Claude provider", error=str(e))
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
        """Send message to Claude and get response.

        Args:
            prompt: User message
            working_directory: Working directory for file operations
            session_id: Optional session ID to continue
            system_prompt: Not used (Claude uses system prompts internally)
            **kwargs: Additional parameters

        Returns:
            AI response from Claude
        """
        self.status = ProviderStatus.BUSY

        try:
            # Get user_id from kwargs or default
            user_id = kwargs.get("user_id", 0)

            # Call existing Claude integration
            claude_response: ClaudeResponse = await self.claude.run_command(
                prompt=prompt,
                working_directory=working_directory,
                user_id=user_id,
                session_id=session_id,
            )

            # Convert to universal AIResponse format
            response = self._convert_claude_response(claude_response)

            self.status = ProviderStatus.READY
            return response

        except Exception as e:
            logger.error("Error sending message to Claude", error=str(e))
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
        """Stream response from Claude.

        Note: Current Claude integration doesn't support streaming in the wrapper.
        This will return the complete response as a single update.

        Args:
            prompt: User message
            working_directory: Working directory
            session_id: Optional session ID
            system_prompt: Not used
            **kwargs: Additional parameters

        Yields:
            Stream updates (currently just one complete update)
        """
        # For now, just send complete message and yield as one update
        # TODO: Implement true streaming when Claude facade supports it
        response = await self.send_message(
            prompt=prompt,
            working_directory=working_directory,
            session_id=session_id,
            **kwargs,
        )

        # Yield complete response as single stream update
        yield AIStreamUpdate(
            content_delta=response.content,
            tool_calls=[],
            is_complete=True,
            metadata=response.metadata,
        )

    async def get_capabilities(self) -> ProviderCapabilities:
        """Get Claude's capabilities.

        Returns:
            Provider capabilities
        """
        return ProviderCapabilities(
            name="claude",
            supports_streaming=False,  # Not yet implemented in wrapper
            supports_tools=True,
            supports_vision=False,  # Requires vision API update
            supports_code_execution=True,
            max_tokens=4096,  # Claude Sonnet default
            max_context_window=200000,  # Claude 3.5 Sonnet context window
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
            ],
            cost_per_1k_input_tokens=0.003,  # Claude 3.5 Sonnet pricing
            cost_per_1k_output_tokens=0.015,
            rate_limit_requests_per_minute=50,
            metadata={
                "model": "claude-3-5-sonnet-20241022",
                "provider": "anthropic",
                "integration_type": "sdk" if self._config.use_sdk else "cli",
            },
        )

    async def health_check(self) -> bool:
        """Check if Claude is accessible.

        Returns:
            True if healthy
        """
        try:
            # Claude facade is healthy if it's initialized
            # We could add a ping/test request here if needed
            return self.status in [ProviderStatus.READY, ProviderStatus.BUSY]
        except Exception as e:
            logger.error("Claude health check failed", error=str(e))
            return False

    def _convert_claude_response(self, claude_response: ClaudeResponse) -> AIResponse:
        """Convert Claude-specific response to universal format.

        Args:
            claude_response: Response from Claude integration

        Returns:
            Universal AI response
        """
        # Extract tool calls if present
        tool_calls = []
        if hasattr(claude_response, "tool_uses") and claude_response.tool_uses:
            for tool_use in claude_response.tool_uses:
                tool_calls.append(
                    ToolCall(
                        name=tool_use.get("name", "unknown"),
                        input=tool_use.get("input", {}),
                        id=tool_use.get("id"),
                    )
                )

        # Calculate cost (rough estimate based on tokens)
        capabilities = None
        cost = 0.0
        if hasattr(claude_response, "tokens_used"):
            # Rough estimate: assume 50/50 input/output split
            input_tokens = claude_response.tokens_used // 2
            output_tokens = claude_response.tokens_used // 2
            cost = (input_tokens / 1000 * 0.003) + (output_tokens / 1000 * 0.015)

        return AIResponse(
            content=claude_response.content,
            session_id=claude_response.session_id,
            tokens_used=getattr(claude_response, "tokens_used", 0),
            cost=cost,
            tool_calls=tool_calls if tool_calls else None,
            metadata={
                "claude_specific": True,
                "raw_response": str(claude_response)[:500],  # Truncate for safety
            },
            provider_name="claude",
            model_name="claude-3-5-sonnet-20241022",
        )

    async def shutdown(self) -> None:
        """Shutdown Claude provider."""
        logger.info("Shutting down Claude provider")
        # Claude facade doesn't need explicit shutdown
        await super().shutdown()
