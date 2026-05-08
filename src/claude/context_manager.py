"""Foundation utilities for managing Claude conversation context by topic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

GENERAL_TOPIC_SENTINEL = 1


def topic_key(chat_id: int, message_thread_id: Optional[int]) -> str:
    """Build a stable context key for a Telegram chat/topic pair."""
    normalized_thread_id = message_thread_id or GENERAL_TOPIC_SENTINEL
    return f"{chat_id}:{normalized_thread_id}"


def estimate_tokens(text: str) -> int:
    """Conservatively estimate token usage from raw text length."""
    if not text:
        return 0

    return max(1, int((len(text) / 3.5) * 1.15))


@dataclass
class ContextTurn:
    """A single user/assistant exchange tracked for context accounting."""

    user_text: str
    assistant_text: str
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def estimated_tokens(self) -> int:
        """Estimated token usage for this exchange."""
        return estimate_tokens(self.user_text) + estimate_tokens(self.assistant_text)


@dataclass
class TopicContextState:
    """Mutable context state for one Telegram topic."""

    topic_key: str
    tokens_used: int = 0
    message_count: int = 0
    compaction_count: int = 0
    last_summary_at: Optional[datetime] = None
    last_summary_text: Optional[str] = None
    turns: list[ContextTurn] = field(default_factory=list)


class ContextManager:
    """Track per-topic context usage and summary prompt inputs."""

    def __init__(
        self,
        token_threshold: int,
        keep_last: int,
        summary_target_tokens: int,
    ) -> None:
        """Initialize context manager configuration and state storage."""
        self.token_threshold = token_threshold
        self.keep_last = keep_last
        self.summary_target_tokens = summary_target_tokens
        self._states: dict[str, TopicContextState] = {}

    def get_state(self, key: str) -> TopicContextState:
        """Return existing state for a topic key, creating it when needed."""
        if key not in self._states:
            self._states[key] = TopicContextState(topic_key=key)
        return self._states[key]

    def would_exceed_limit(self, key: str, next_user_text: str) -> bool:
        """Return whether adding the next user text would exceed threshold."""
        state = self.get_state(key)
        projected_tokens = state.tokens_used + estimate_tokens(next_user_text)
        return projected_tokens >= self.token_threshold

    def record_turn(
        self,
        key: str,
        user_text: str,
        assistant_text: str,
        session_id: str,
    ) -> TopicContextState:
        """Record one completed exchange under a topic key."""
        state = self.get_state(key)
        turn = ContextTurn(
            user_text=user_text,
            assistant_text=assistant_text,
            session_id=session_id,
        )
        state.turns.append(turn)
        state.message_count += 1
        state.tokens_used += turn.estimated_tokens
        return state

    def recent_turns(self, key: str) -> list[ContextTurn]:
        """Return the most recent turns retained for summary context."""
        state = self.get_state(key)
        if self.keep_last <= 0:
            return []
        return state.turns[-self.keep_last :]

    def build_summary_prompt(self, key: str) -> str:
        """Build a prompt for summarizing retained topic context."""
        state = self.get_state(key)
        prior_summary = state.last_summary_text or "Nenhum resumo anterior."
        turns = state.turns if state.last_summary_text is None else self.recent_turns(key)
        turns_text = self._format_turns(turns)

        return (
            "Resuma o contexto desta conversa para continuidade futura.\n"
            f"Topic key: {state.topic_key}\n"
            f"Resumo anterior:\n{prior_summary}\n\n"
            f"Últimas mensagens preservadas:\n{turns_text}\n\n"
            "Produza um resumo conciso em português com fatos, decisões, "
            "pendências e preferências relevantes. "
            f"Alvo: aproximadamente {self.summary_target_tokens} tokens."
        )

    @staticmethod
    def _format_turns(turns: list[ContextTurn]) -> str:
        """Format turns for inclusion in a summary prompt."""
        if not turns:
            return "Nenhuma mensagem recente."

        formatted_turns = []
        for index, turn in enumerate(turns, start=1):
            formatted_turns.append(
                f"Turno {index} ({turn.session_id}, {turn.created_at.isoformat()}):\n"
                f"Usuário: {turn.user_text}\n"
                f"Assistente: {turn.assistant_text}"
            )
        return "\n\n".join(formatted_turns)
