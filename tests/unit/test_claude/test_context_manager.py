"""Tests for Claude context manager foundation."""

from datetime import UTC, datetime

from src.claude.context_manager import (
    GENERAL_TOPIC_SENTINEL,
    ContextManager,
    ContextTurn,
    TopicContextState,
    estimate_tokens,
    topic_key,
)


class TestTopicKey:
    """Test Telegram topic key normalization."""

    def test_topic_key_uses_chat_and_thread(self):
        """Topic key should include chat id and explicit thread id."""
        assert topic_key(12345, 67890) == "12345:67890"

    def test_topic_key_normalizes_none_to_general_topic(self):
        """Missing thread id should map to the general topic sentinel."""
        assert GENERAL_TOPIC_SENTINEL == 1
        assert topic_key(12345, None) == "12345:1"

    def test_topic_key_normalizes_zero_to_general_topic(self):
        """Falsy thread id should map to the general topic sentinel."""
        assert topic_key(12345, 0) == "12345:1"


class TestEstimateTokens:
    """Test conservative token estimation."""

    def test_empty_text_is_zero_tokens(self):
        """Empty text should not consume tokens."""
        assert estimate_tokens("") == 0

    def test_non_empty_text_has_minimum_one_token(self):
        """Any non-empty text should count as at least one token."""
        assert estimate_tokens("a") >= 1

    def test_estimate_is_conservative_for_portuguese_text(self):
        """Portuguese text estimate should be at least len(text)//4."""
        text = (
            "Olá, preciso que você analise este contexto longo com acentuação "
            "e responda de forma objetiva para manter a conversa organizada."
        )

        assert estimate_tokens(text) >= len(text) // 4
        assert estimate_tokens(text) == int((len(text) / 3.5) * 1.15)


class TestContextTurn:
    """Test individual context turns."""

    def test_defaults_to_timezone_aware_utc_timestamp(self):
        """created_at should default to an aware UTC datetime."""
        turn = ContextTurn(
            user_text="pergunta",
            assistant_text="resposta",
            session_id="session-1",
        )

        assert isinstance(turn.created_at, datetime)
        assert turn.created_at.tzinfo == UTC

    def test_estimated_tokens_includes_user_and_assistant_text(self):
        """A turn should estimate tokens from both sides of the exchange."""
        turn = ContextTurn(
            user_text="pergunta em português",
            assistant_text="resposta detalhada em português",
            session_id="session-1",
        )

        assert turn.estimated_tokens == estimate_tokens(
            "pergunta em português"
        ) + estimate_tokens("resposta detalhada em português")


class TestTopicContextState:
    """Test topic context state defaults."""

    def test_default_state_values(self):
        """Topic state should start empty with independent turn storage."""
        first = TopicContextState(topic_key="1:1")
        second = TopicContextState(topic_key="2:1")

        first.turns.append(
            ContextTurn(
                user_text="u",
                assistant_text="a",
                session_id="s",
            )
        )

        assert first.tokens_used == 0
        assert first.message_count == 0
        assert first.compaction_count == 0
        assert first.last_summary_at is None
        assert first.last_summary_text is None
        assert len(first.turns) == 1
        assert second.turns == []


class TestContextManager:
    """Test context manager state and threshold behavior."""

    def test_get_state_reuses_state_by_key_and_keeps_topics_independent(self):
        """Each topic key should have an independent state object."""
        manager = ContextManager(token_threshold=100, keep_last=2, summary_target_tokens=50)

        state_a = manager.get_state("10:1")
        state_b = manager.get_state("10:2")

        assert state_a is manager.get_state("10:1")
        assert state_a is not state_b
        assert state_a.topic_key == "10:1"
        assert state_b.topic_key == "10:2"

    def test_record_turn_updates_state_and_recent_turns_keep_last(self):
        """Recorded turns should update counters and recent turns should be bounded."""
        manager = ContextManager(token_threshold=1000, keep_last=2, summary_target_tokens=50)

        returned_state = manager.record_turn(
            "10:1", "primeira", "resposta 1", "session-1"
        )
        manager.record_turn("10:1", "segunda", "resposta 2", "session-2")
        manager.record_turn("10:1", "terceira", "resposta 3", "session-3")
        state = manager.get_state("10:1")

        assert returned_state is state
        assert [turn.user_text for turn in state.turns] == [
            "primeira",
            "segunda",
            "terceira",
        ]
        assert state.message_count == 3
        assert state.tokens_used == sum(turn.estimated_tokens for turn in state.turns)
        assert manager.recent_turns("10:1") == state.turns[1:]

    def test_would_exceed_limit_uses_topic_state_and_next_user_text(self):
        """Threshold checks should include existing topic usage and next user text."""
        manager = ContextManager(token_threshold=20, keep_last=2, summary_target_tokens=10)
        manager.record_turn("10:1", "mensagem anterior", "resposta anterior", "session-1")

        state_tokens = manager.get_state("10:1").tokens_used
        remaining = 20 - state_tokens
        short_text = "a" if remaining >= estimate_tokens("a") else ""
        long_text = "x" * 200

        assert manager.would_exceed_limit("10:1", short_text) is False
        assert manager.would_exceed_limit("10:1", long_text) is True
        assert manager.would_exceed_limit("10:2", short_text) is False

    def test_would_exceed_limit_is_true_when_projected_equals_threshold(self):
        """Threshold equality should trigger context compaction."""
        manager = ContextManager(token_threshold=10, keep_last=2, summary_target_tokens=10)
        manager.get_state("10:1").tokens_used = 10 - estimate_tokens("a")

        assert manager.would_exceed_limit("10:1", "a") is True

    def test_build_summary_prompt_contains_prior_summary_and_recent_turns(self):
        """Summary prompt should include current state information for compaction."""
        manager = ContextManager(token_threshold=1000, keep_last=2, summary_target_tokens=25)
        state = manager.get_state("10:1")
        state.last_summary_text = "Resumo anterior"
        manager.record_turn("10:1", "primeira", "resposta 1", "session-1")
        manager.record_turn("10:1", "segunda", "resposta 2", "session-2")
        manager.record_turn("10:1", "terceira", "resposta 3", "session-3")

        prompt = manager.build_summary_prompt("10:1")

        assert "Resumo anterior" in prompt
        assert "segunda" in prompt
        assert "resposta 2" in prompt
        assert "terceira" in prompt
        assert "resposta 3" in prompt
        assert "primeira" not in prompt
        assert "25 tokens" in prompt

    def test_build_summary_prompt_includes_all_turns_on_first_summary(self):
        """First summary prompt should include every available turn, not only keep_last."""
        manager = ContextManager(token_threshold=1000, keep_last=2, summary_target_tokens=25)
        manager.record_turn("10:1", "turno antigo", "resposta antiga", "session-1")
        manager.record_turn("10:1", "turno intermediário", "resposta 2", "session-2")
        manager.record_turn("10:1", "turno recente", "resposta recente", "session-3")

        prompt = manager.build_summary_prompt("10:1")

        assert "Nenhum resumo anterior" in prompt
        assert "turno antigo" in prompt
        assert "resposta antiga" in prompt
        assert "turno recente" in prompt
        assert "resposta recente" in prompt
