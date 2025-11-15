"""Base provider interface for AI assistants.

This module defines the abstract base class and data structures that all
AI providers must implement to work with the multi-AI system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional


class ProviderStatus(Enum):
    """Status of an AI provider."""

    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class ToolCall:
    """Represents a tool/function call made by the AI."""

    name: str
    input: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class ToolResult:
    """Result from a tool execution."""

    tool_call_id: str
    output: str
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class AIMessage:
    """Universal message format across all providers."""

    role: str  # 'user', 'assistant', 'system'
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AIStreamUpdate:
    """Real-time update during streaming response."""

    content_delta: str = ""
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None
    is_complete: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    """Universal response format from AI providers."""

    content: str
    session_id: str
    tokens_used: int
    cost: float
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    provider_name: str = "unknown"
    model_name: str = "unknown"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProviderCapabilities:
    """Capabilities and limits of an AI provider."""

    name: str
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_code_execution: bool = False
    max_tokens: int = 4096
    max_context_window: int = 8192
    supported_languages: List[str] = field(default_factory=list)
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    rate_limit_requests_per_minute: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAIProvider(ABC):
    """Abstract base class for all AI providers.

    All AI providers (Claude, Gemini, Copilot, etc.) must implement this
    interface to work with the multi-AI system.
    """

    def __init__(self, config: Any):
        """Initialize the provider with configuration.

        Args:
            config: Provider-specific configuration object
        """
        self.config = config
        self.status = ProviderStatus.INITIALIZING
        self._sessions: Dict[str, Any] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the provider name (e.g., 'claude', 'gemini', 'copilot')."""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the provider and verify it's ready to use.

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    async def send_message(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Send a message and get complete response.

        Args:
            prompt: The user's message/prompt
            working_directory: Current working directory for file operations
            session_id: Optional session ID to continue conversation
            system_prompt: Optional system prompt to set context
            **kwargs: Provider-specific additional parameters

        Returns:
            Complete AI response with metadata

        Raises:
            ProviderError: If the provider encounters an error
        """
        pass

    @abstractmethod
    async def stream_message(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[AIStreamUpdate]:
        """Stream response in real-time.

        Args:
            prompt: The user's message/prompt
            working_directory: Current working directory
            session_id: Optional session ID to continue conversation
            system_prompt: Optional system prompt
            **kwargs: Provider-specific parameters

        Yields:
            Stream updates with incremental content

        Raises:
            ProviderError: If streaming fails
        """
        pass

    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities and limits.

        Returns:
            Provider capabilities including tokens, cost, features
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is accessible and healthy.

        Returns:
            True if provider is healthy and accessible
        """
        pass

    async def create_session(
        self,
        working_directory: Path,
        user_id: int,
        **kwargs,
    ) -> str:
        """Create a new conversation session.

        Args:
            working_directory: Working directory for the session
            user_id: User ID owning this session
            **kwargs: Provider-specific session parameters

        Returns:
            Session ID
        """
        # Default implementation - providers can override
        session_id = f"{self.name}_{user_id}_{datetime.utcnow().timestamp()}"
        self._sessions[session_id] = {
            "working_directory": working_directory,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            **kwargs,
        }
        return session_id

    async def end_session(self, session_id: str) -> None:
        """End a conversation session.

        Args:
            session_id: Session ID to end
        """
        # Default implementation - providers can override
        if session_id in self._sessions:
            del self._sessions[session_id]

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data.

        Args:
            session_id: Session ID

        Returns:
            Session data or None if not found
        """
        return self._sessions.get(session_id)

    async def shutdown(self) -> None:
        """Shutdown the provider and cleanup resources.

        Default implementation clears sessions. Providers should override
        to add provider-specific cleanup (close connections, etc.).
        """
        self._sessions.clear()
        self.status = ProviderStatus.OFFLINE
