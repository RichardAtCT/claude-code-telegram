# Long Context Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram-topic-scoped long-conversation runtime so the Claude bot keeps continuity through long chats by compacting context automatically instead of breaking or silently forgetting.

**Architecture:** Add a focused `ContextManager` between `MessageOrchestrator.agentic_text()` and `ClaudeIntegration.run_command()`. It tracks estimated tokens per `chat_id:message_thread_id`, persists summaries in SQLite, compacts old transcript into structured summaries before context pressure becomes dangerous, and starts a fresh Claude session with `summary + last N turns` when needed. Orchestrator gets a per-topic lock plus `/context` and `/compact` commands so long conversations are observable and recoverable.

**Tech Stack:** Python 3.14, python-telegram-bot, Claude Agent SDK/OAuth via existing `ClaudeIntegration`, SQLite/aiosqlite, pytest/pytest-asyncio.

---

## File Structure

- Create: `src/claude/context_manager.py`
  - Owns token estimation, topic keys, context state, compaction prompts, summary creation, fallback prompt building, and lightweight per-topic in-memory state.
- Create: `tests/unit/test_claude/test_context_manager.py`
  - Unit tests for token estimation, threshold checks, compaction decisions, summary prompt shape, fallback behavior, and topic isolation.
- Modify: `src/storage/database.py`
  - Add migration 5 with `conversation_summaries` table and indexes.
- Modify: `src/storage/models.py`
  - Add `ConversationSummaryModel` dataclass.
- Modify: `src/storage/repositories.py`
  - Add `ConversationSummaryRepository` with create/list/latest methods.
- Modify: `src/storage/facade.py`
  - Wire `self.conversation_summaries` into `Storage`.
- Modify: `src/config/settings.py`
  - Add context-runtime configuration fields.
- Modify: `src/utils/constants.py`
  - Add context-runtime defaults.
- Modify: `.env.example`
  - Document context-runtime environment variables.
- Modify: `src/bot/orchestrator.py`
  - Initialize `ContextManager`, add per-topic locks, call compaction before Claude, record turns after Claude, add `/context` and `/compact` command handling.
- Modify: `tests/unit/test_orchestrator.py`
  - Cover integration path: auto-compaction, command responses, and per-topic lock serialization.
- Modify: `tests/unit/test_storage/test_database.py`, `tests/unit/test_storage/test_repositories.py`, `tests/unit/test_storage/test_facade.py`
  - Cover schema migration and repository/facade wiring.

---

### Task 1: Add context-runtime defaults and settings

**Files:**
- Modify: `src/utils/constants.py`
- Modify: `src/config/settings.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing settings test**

Add this test to `tests/unit/test_config.py`:

```python
def test_context_runtime_settings_defaults(monkeypatch):
    """Context runtime settings have production-safe defaults."""
    from src.config.settings import Settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "test_bot")
    monkeypatch.setenv("APPROVED_DIRECTORY", "/tmp")

    settings = Settings()

    assert settings.context_runtime_enabled is True
    assert settings.context_token_threshold == 150_000
    assert settings.context_compact_keep_last == 8
    assert settings.context_summary_max_turns == 3
    assert settings.context_hard_trim_fallback is True
    assert settings.context_summary_target_tokens == 1_200
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_config.py::test_context_runtime_settings_defaults -q
```

Expected: FAIL with `AttributeError` or pydantic validation error because the new fields do not exist.

- [ ] **Step 3: Add constants**

Append to `src/utils/constants.py` after retry defaults:

```python
# Long-context runtime defaults
DEFAULT_CONTEXT_TOKEN_THRESHOLD = 150_000
DEFAULT_CONTEXT_COMPACT_KEEP_LAST = 8
DEFAULT_CONTEXT_SUMMARY_MAX_TURNS = 3
DEFAULT_CONTEXT_SUMMARY_TARGET_TOKENS = 1_200
DEFAULT_CONTEXT_LOCK_TIMEOUT_SECONDS = 30
DEFAULT_CONTEXT_MAX_QUEUE_DEPTH = 5
```

- [ ] **Step 4: Add settings fields**

In `src/config/settings.py`, extend the constants import with:

```python
    DEFAULT_CONTEXT_COMPACT_KEEP_LAST,
    DEFAULT_CONTEXT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_CONTEXT_MAX_QUEUE_DEPTH,
    DEFAULT_CONTEXT_SUMMARY_MAX_TURNS,
    DEFAULT_CONTEXT_SUMMARY_TARGET_TOKENS,
    DEFAULT_CONTEXT_TOKEN_THRESHOLD,
```

Add these fields after the Claude retry settings block:

```python
    # Long-context runtime
    context_runtime_enabled: bool = Field(
        True,
        description="Enable topic-scoped long-context tracking and compaction",
    )
    context_token_threshold: int = Field(
        DEFAULT_CONTEXT_TOKEN_THRESHOLD,
        ge=10_000,
        description="Estimated token threshold that triggers context compaction",
    )
    context_compact_keep_last: int = Field(
        DEFAULT_CONTEXT_COMPACT_KEEP_LAST,
        ge=1,
        description="Number of recent turns to keep verbatim after compaction",
    )
    context_summary_max_turns: int = Field(
        DEFAULT_CONTEXT_SUMMARY_MAX_TURNS,
        ge=1,
        description="Max Claude turns for context summary generation",
    )
    context_summary_target_tokens: int = Field(
        DEFAULT_CONTEXT_SUMMARY_TARGET_TOKENS,
        ge=200,
        description="Target maximum size for generated context summaries",
    )
    context_hard_trim_fallback: bool = Field(
        True,
        description="Fall back to last-N-turn context if summary generation fails",
    )
    context_lock_timeout_seconds: int = Field(
        DEFAULT_CONTEXT_LOCK_TIMEOUT_SECONDS,
        ge=5,
        description="Seconds to wait for per-topic context lock before failing safely",
    )
    context_max_queue_depth: int = Field(
        DEFAULT_CONTEXT_MAX_QUEUE_DEPTH,
        ge=1,
        description="Maximum active/queued requests allowed per topic",
    )
```

- [ ] **Step 5: Document env variables**

Append to `.env.example` near Claude settings:

```bash
# Long-context runtime
CONTEXT_RUNTIME_ENABLED=true
CONTEXT_TOKEN_THRESHOLD=150000
CONTEXT_COMPACT_KEEP_LAST=8
CONTEXT_SUMMARY_MAX_TURNS=3
CONTEXT_SUMMARY_TARGET_TOKENS=1200
CONTEXT_HARD_TRIM_FALLBACK=true
CONTEXT_LOCK_TIMEOUT_SECONDS=30
CONTEXT_MAX_QUEUE_DEPTH=5
```

- [ ] **Step 6: Run settings test**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_config.py::test_context_runtime_settings_defaults -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/utils/constants.py src/config/settings.py .env.example tests/unit/test_config.py
git commit -m "feat: add long-context runtime settings"
```

---

### Task 2: Add conversation summary storage

**Files:**
- Modify: `src/storage/database.py`
- Modify: `src/storage/models.py`
- Modify: `src/storage/repositories.py`
- Modify: `src/storage/facade.py`
- Test: `tests/unit/test_storage/test_database.py`
- Test: `tests/unit/test_storage/test_repositories.py`
- Test: `tests/unit/test_storage/test_facade.py`

- [ ] **Step 1: Write failing migration test**

Add to `tests/unit/test_storage/test_database.py`:

```python
@pytest.mark.asyncio
async def test_migration_5_creates_conversation_summaries(tmp_path):
    from src.storage.database import DatabaseManager

    db_path = tmp_path / "bot.db"
    manager = DatabaseManager(f"sqlite:///{db_path}")
    await manager.initialize()

    async with manager.get_connection() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_summaries'"
        )
        row = await cursor.fetchone()
        assert row is not None

        cursor = await conn.execute("PRAGMA table_info(conversation_summaries)")
        columns = {row[1] for row in await cursor.fetchall()}

    await manager.close()

    assert {
        "id",
        "topic_key",
        "session_id",
        "summary_text",
        "messages_included",
        "tokens_before",
        "tokens_after",
        "created_at",
    }.issubset(columns)
```

- [ ] **Step 2: Run migration test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_storage/test_database.py::test_migration_5_creates_conversation_summaries -q
```

Expected: FAIL because table is missing.

- [ ] **Step 3: Add migration 5**

In `src/storage/database.py`, add this tuple after migration 4 in `_get_migrations()`:

```python
            (
                5,
                """
                -- Persist compacted long-conversation context by Telegram topic.
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_key TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    messages_included INTEGER NOT NULL,
                    tokens_before INTEGER NOT NULL,
                    tokens_after INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_summaries_topic_created
                    ON conversation_summaries(topic_key, created_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_summaries_session
                    ON conversation_summaries(session_id);
                """,
            ),
```

- [ ] **Step 4: Add model**

Add to `src/storage/models.py` after `MessageModel`:

```python
@dataclass
class ConversationSummaryModel:
    """Persisted compacted context for one Telegram topic."""

    topic_key: str
    session_id: str
    summary_text: str
    messages_included: int
    tokens_before: int
    tokens_after: int
    created_at: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if data["created_at"]:
            data["created_at"] = data["created_at"].isoformat()
        return data

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "ConversationSummaryModel":
        data = dict(row)
        data["created_at"] = _parse_datetime(data.get("created_at"))
        return cls(**data)
```

- [ ] **Step 5: Write failing repository test**

Add to `tests/unit/test_storage/test_repositories.py`:

```python
@pytest.mark.asyncio
async def test_conversation_summary_repository_create_and_latest(storage_db):
    from datetime import UTC, datetime
    from src.storage.models import ConversationSummaryModel, SessionModel, UserModel
    from src.storage.repositories import ConversationSummaryRepository, SessionRepository, UserRepository

    users = UserRepository(storage_db)
    sessions = SessionRepository(storage_db)
    summaries = ConversationSummaryRepository(storage_db)

    await users.create_user(UserModel(user_id=123, telegram_username="ferd", first_seen=datetime.now(UTC), last_active=datetime.now(UTC), is_allowed=True))
    await sessions.create_session(SessionModel(session_id="claude-1", user_id=123, project_path="/tmp", created_at=datetime.now(UTC), last_used=datetime.now(UTC)))

    created_id = await summaries.create_summary(
        ConversationSummaryModel(
            topic_key="-100:54",
            session_id="claude-1",
            summary_text="Decisions: keep context isolated.",
            messages_included=12,
            tokens_before=151000,
            tokens_after=900,
        )
    )

    latest = await summaries.get_latest_for_topic("-100:54")
    assert created_id > 0
    assert latest is not None
    assert latest.summary_text == "Decisions: keep context isolated."
    assert latest.messages_included == 12
```

- [ ] **Step 6: Run repository test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_storage/test_repositories.py::test_conversation_summary_repository_create_and_latest -q
```

Expected: FAIL because `ConversationSummaryRepository` does not exist.

- [ ] **Step 7: Add repository**

In `src/storage/repositories.py`, import `ConversationSummaryModel` and add this class after `MessageRepository`:

```python
class ConversationSummaryRepository:
    """Data access for compacted long-context summaries."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create_summary(self, summary: ConversationSummaryModel) -> int:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO conversation_summaries
                (topic_key, session_id, summary_text, messages_included,
                 tokens_before, tokens_after, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.topic_key,
                    summary.session_id,
                    summary.summary_text,
                    summary.messages_included,
                    summary.tokens_before,
                    summary.tokens_after,
                    summary.created_at or datetime.now(UTC),
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    async def get_latest_for_topic(self, topic_key: str) -> Optional[ConversationSummaryModel]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM conversation_summaries
                WHERE topic_key = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (topic_key,),
            )
            row = await cursor.fetchone()
            return ConversationSummaryModel.from_row(row) if row else None

    async def list_for_topic(self, topic_key: str, limit: int = 20) -> List[ConversationSummaryModel]:
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM conversation_summaries
                WHERE topic_key = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (topic_key, limit),
            )
            rows = await cursor.fetchall()
            return [ConversationSummaryModel.from_row(row) for row in rows]
```

- [ ] **Step 8: Wire facade**

In `src/storage/facade.py`, import `ConversationSummaryRepository` and add this line in `Storage.__init__` after `self.messages`:

```python
        self.conversation_summaries = ConversationSummaryRepository(self.db_manager)
```

- [ ] **Step 9: Run storage tests**

```bash
.venv/bin/python -m pytest tests/unit/test_storage/test_database.py::test_migration_5_creates_conversation_summaries tests/unit/test_storage/test_repositories.py::test_conversation_summary_repository_create_and_latest -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/storage/database.py src/storage/models.py src/storage/repositories.py src/storage/facade.py tests/unit/test_storage/test_database.py tests/unit/test_storage/test_repositories.py tests/unit/test_storage/test_facade.py
git commit -m "feat: persist long-context summaries"
```

---

### Task 3: Create ContextManager foundation

**Files:**
- Create: `src/claude/context_manager.py`
- Test: `tests/unit/test_claude/test_context_manager.py`

- [ ] **Step 1: Write failing token tests**

Create `tests/unit/test_claude/test_context_manager.py` with:

```python
import pytest

from src.claude.context_manager import ContextManager, ContextTurn, TopicContextState, estimate_tokens, topic_key


def test_topic_key_uses_chat_and_thread():
    assert topic_key(-1003937326698, 54) == "-1003937326698:54"


def test_topic_key_normalizes_general_topic():
    assert topic_key(-1003937326698, None) == "-1003937326698:1"


def test_estimate_tokens_is_conservative_for_portuguese():
    text = "Ferd quer conversas longas com contexto por tópico." * 20
    assert estimate_tokens(text) >= len(text) // 4


def test_state_accumulates_turns_independently():
    manager = ContextManager(token_threshold=100, keep_last=2, summary_target_tokens=500)

    manager.record_turn("chat:10", user_text="a" * 120, assistant_text="b" * 120, session_id="s1")
    manager.record_turn("chat:20", user_text="curto", assistant_text="ok", session_id="s2")

    assert manager.get_state("chat:10").message_count == 1
    assert manager.get_state("chat:20").message_count == 1
    assert manager.would_exceed_limit("chat:10", "c" * 300) is True
    assert manager.would_exceed_limit("chat:20", "c" * 10) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/test_claude/test_context_manager.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement ContextManager foundation**

Create `src/claude/context_manager.py`:

```python
"""Long-context tracking and compaction helpers.

This module is intentionally independent from Telegram so it can be tested
without python-telegram-bot objects. Telegram-specific code should pass a
stable topic key such as "chat_id:message_thread_id".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Dict, List, Optional


GENERAL_TOPIC_SENTINEL = 1


def topic_key(chat_id: int, message_thread_id: Optional[int]) -> str:
    """Return the canonical state key for a Telegram chat/topic."""
    return f"{chat_id}:{message_thread_id or GENERAL_TOPIC_SENTINEL}"


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for Portuguese/English/code mixed text."""
    if not text:
        return 0
    # 3.5 chars/token is intentionally conservative for PT-BR and code.
    return max(1, int((len(text) / 3.5) * 1.15))


@dataclass
class ContextTurn:
    """One persisted conversation turn used for compaction."""

    user_text: str
    assistant_text: str
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.user_text) + estimate_tokens(self.assistant_text)


@dataclass
class TopicContextState:
    """In-memory long-context state for one topic."""

    topic_key: str
    tokens_used: int = 0
    message_count: int = 0
    compaction_count: int = 0
    last_summary_at: Optional[datetime] = None
    last_summary_text: Optional[str] = None
    turns: List[ContextTurn] = field(default_factory=list)


class ContextManager:
    """Track and prepare long-context state per Telegram topic."""

    def __init__(
        self,
        token_threshold: int,
        keep_last: int,
        summary_target_tokens: int,
    ) -> None:
        self.token_threshold = token_threshold
        self.keep_last = keep_last
        self.summary_target_tokens = summary_target_tokens
        self._states: Dict[str, TopicContextState] = {}

    def get_state(self, key: str) -> TopicContextState:
        if key not in self._states:
            self._states[key] = TopicContextState(topic_key=key)
        return self._states[key]

    def would_exceed_limit(self, key: str, next_user_text: str) -> bool:
        state = self.get_state(key)
        projected = state.tokens_used + estimate_tokens(next_user_text)
        return projected >= self.token_threshold

    def record_turn(
        self,
        key: str,
        user_text: str,
        assistant_text: str,
        session_id: str,
    ) -> TopicContextState:
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

    def recent_turns(self, key: str) -> List[ContextTurn]:
        return self.get_state(key).turns[-self.keep_last :]

    def build_summary_prompt(self, key: str) -> str:
        state = self.get_state(key)
        turns = state.turns
        transcript = "\n\n".join(
            f"User: {turn.user_text}\nAssistant: {turn.assistant_text}"
            for turn in turns
        )
        return (
            "Summarize this long Telegram topic conversation for future Claude continuity.\n"
            "Preserve decisions, user preferences, files/commands mentioned, current task state, "
            "open questions, and anything needed to answer future follow-ups.\n"
            f"Target maximum: {self.summary_target_tokens} tokens.\n\n"
            f"Transcript:\n{transcript}"
        )
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_claude/test_context_manager.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/claude/context_manager.py tests/unit/test_claude/test_context_manager.py
git commit -m "feat: add context manager foundation"
```

---

### Task 4: Add compaction result and fallback prompt building

**Files:**
- Modify: `src/claude/context_manager.py`
- Test: `tests/unit/test_claude/test_context_manager.py`

- [ ] **Step 1: Write failing compaction tests**

Append to `tests/unit/test_claude/test_context_manager.py`:

```python
class FakeSummaryStore:
    def __init__(self):
        self.saved = []

    async def create_summary(self, summary):
        self.saved.append(summary)
        return 1


class FakeClaude:
    async def run_command(self, **kwargs):
        from src.claude.sdk_integration import ClaudeResponse
        return ClaudeResponse(
            content="Decisions: context stays per topic. Current state: implementing compaction.",
            session_id="summary-session",
            duration_ms=100,
            cost=0.0,
            num_turns=1,
            tools_used=[],
        )


@pytest.mark.asyncio
async def test_compact_saves_summary_and_returns_prompt():
    manager = ContextManager(token_threshold=100, keep_last=1, summary_target_tokens=500)
    manager.record_turn("-100:54", "first user", "first assistant", "s1")
    manager.record_turn("-100:54", "second user", "second assistant", "s1")

    result = await manager.compact(
        key="-100:54",
        claude=FakeClaude(),
        summary_store=FakeSummaryStore(),
        session_id="s1",
        working_directory="/tmp",
        user_id=123,
    )

    assert result.summary_text.startswith("Decisions:")
    assert "Conversation summary" in result.compacted_prompt
    assert "second user" in result.compacted_prompt
    assert result.force_new_session is True
    assert manager.get_state("-100:54").compaction_count == 1


@pytest.mark.asyncio
async def test_compact_fallback_keeps_recent_turn_when_summary_fails():
    class FailingClaude:
        async def run_command(self, **kwargs):
            raise RuntimeError("summary failed")

    manager = ContextManager(token_threshold=100, keep_last=1, summary_target_tokens=500)
    manager.record_turn("-100:54", "old user", "old assistant", "s1")
    manager.record_turn("-100:54", "recent user", "recent assistant", "s1")

    result = await manager.compact(
        key="-100:54",
        claude=FailingClaude(),
        summary_store=FakeSummaryStore(),
        session_id="s1",
        working_directory="/tmp",
        user_id=123,
    )

    assert result.summary_text == ""
    assert "recent user" in result.compacted_prompt
    assert "old user" not in result.compacted_prompt
    assert result.used_fallback is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/test_claude/test_context_manager.py::test_compact_saves_summary_and_returns_prompt tests/unit/test_claude/test_context_manager.py::test_compact_fallback_keeps_recent_turn_when_summary_fails -q
```

Expected: FAIL because `compact()` and result types do not exist.

- [ ] **Step 3: Add result dataclass and compaction methods**

In `src/claude/context_manager.py`, import `ConversationSummaryModel` and add:

```python
from src.storage.models import ConversationSummaryModel


@dataclass
class CompactionResult:
    """Result of compacting one topic conversation."""

    compacted_prompt: str
    summary_text: str
    messages_included: int
    tokens_before: int
    tokens_after: int
    force_new_session: bool = True
    used_fallback: bool = False
```

Add these methods to `ContextManager`:

```python
    def build_compacted_prompt(self, key: str, summary_text: str) -> str:
        recent = self.recent_turns(key)
        recent_block = "\n\n".join(
            f"User: {turn.user_text}\nAssistant: {turn.assistant_text}"
            for turn in recent
        )
        if summary_text:
            return (
                "Conversation summary from earlier messages:\n"
                f"{summary_text}\n\n"
                "Recent verbatim turns:\n"
                f"{recent_block}"
            )
        return "Recent verbatim turns:\n" + recent_block

    async def compact(
        self,
        key: str,
        claude,
        summary_store,
        session_id: str,
        working_directory: str,
        user_id: int,
    ) -> CompactionResult:
        state = self.get_state(key)
        tokens_before = state.tokens_used
        messages_included = len(state.turns)
        summary_text = ""
        used_fallback = False

        try:
            response = await claude.run_command(
                prompt=self.build_summary_prompt(key),
                working_directory=working_directory,
                user_id=user_id,
                session_id=None,
                force_new=True,
            )
            summary_text = response.content.strip()
            tokens_after = estimate_tokens(summary_text) + sum(
                turn.estimated_tokens for turn in self.recent_turns(key)
            )
            await summary_store.create_summary(
                ConversationSummaryModel(
                    topic_key=key,
                    session_id=session_id,
                    summary_text=summary_text,
                    messages_included=messages_included,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                )
            )
        except Exception:
            used_fallback = True
            tokens_after = sum(turn.estimated_tokens for turn in self.recent_turns(key))

        compacted_prompt = self.build_compacted_prompt(key, summary_text)
        state.turns = self.recent_turns(key)
        state.tokens_used = tokens_after
        state.compaction_count += 1
        state.last_summary_at = datetime.now(UTC)
        state.last_summary_text = summary_text or state.last_summary_text

        return CompactionResult(
            compacted_prompt=compacted_prompt,
            summary_text=summary_text,
            messages_included=messages_included,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            used_fallback=used_fallback,
        )
```

- [ ] **Step 4: Run compaction tests**

```bash
.venv/bin/python -m pytest tests/unit/test_claude/test_context_manager.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/claude/context_manager.py tests/unit/test_claude/test_context_manager.py
git commit -m "feat: add context compaction prompt builder"
```

---

### Task 5: Integrate ContextManager into agentic_text path

**Files:**
- Modify: `src/bot/orchestrator.py:138-142`, `src/bot/orchestrator.py:1003-1220`
- Test: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing orchestrator auto-compaction test**

Add to `tests/unit/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_agentic_text_compacts_before_claude_when_threshold_exceeded(orchestrator, telegram_update, telegram_context):
    class FakeContextManager:
        def __init__(self):
            self.recorded = []
            self.compacted = False

        def would_exceed_limit(self, key, text):
            assert key.endswith(":54")
            return True

        async def compact(self, **kwargs):
            self.compacted = True
            from src.claude.context_manager import CompactionResult
            return CompactionResult(
                compacted_prompt="Conversation summary from earlier messages:\nsummary\n\nRecent verbatim turns:\nUser: hi\nAssistant: hello",
                summary_text="summary",
                messages_included=20,
                tokens_before=151000,
                tokens_after=1200,
            )

        def record_turn(self, key, user_text, assistant_text, session_id):
            self.recorded.append((key, user_text, assistant_text, session_id))

    class FakeClaude:
        async def run_command(self, **kwargs):
            from src.claude.sdk_integration import ClaudeResponse
            assert kwargs["force_new"] is True
            assert kwargs["session_id"] is None
            assert kwargs["prompt"].startswith("Conversation summary")
            return ClaudeResponse(content="ok", session_id="new-session", duration_ms=10, cost=0.0, num_turns=1, tools_used=[])

    orchestrator.context_manager = FakeContextManager()
    telegram_context.bot_data["claude_integration"] = FakeClaude()
    telegram_context.bot_data["storage"] = type("Storage", (), {"conversation_summaries": object(), "save_claude_interaction": AsyncMock()})()
    telegram_context.user_data["_thread_context"] = {"state_key": "-100:54", "chat_id": -100, "message_thread_id": 54}

    await orchestrator.agentic_text(telegram_update, telegram_context)

    assert orchestrator.context_manager.compacted is True
    assert orchestrator.context_manager.recorded[0][0] == "-100:54"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py::test_agentic_text_compacts_before_claude_when_threshold_exceeded -q
```

Expected: FAIL because orchestrator does not use `context_manager`.

- [ ] **Step 3: Initialize ContextManager in orchestrator**

In `src/bot/orchestrator.py`, add import:

```python
from src.claude.context_manager import ContextManager, topic_key
```

In `MessageOrchestrator.__init__`, after `_active_requests`:

```python
        self.context_manager = ContextManager(
            token_threshold=settings.context_token_threshold,
            keep_last=settings.context_compact_keep_last,
            summary_target_tokens=settings.context_summary_target_tokens,
        )
        self._topic_locks: Dict[str, asyncio.Lock] = {}
        self._topic_active_counts: Dict[str, int] = {}
```

- [ ] **Step 4: Add helper methods to orchestrator**

Add near thread-state helper methods:

```python
    def _current_topic_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        thread_context = context.user_data.get("_thread_context") or {}
        if thread_context.get("state_key"):
            return thread_context["state_key"]
        message = update.effective_message
        return topic_key(message.chat_id, getattr(message, "message_thread_id", None))

    def _topic_lock(self, key: str) -> asyncio.Lock:
        if key not in self._topic_locks:
            self._topic_locks[key] = asyncio.Lock()
        return self._topic_locks[key]
```

- [ ] **Step 5: Wrap agentic_text Claude call with compaction check**

In `agentic_text()`, before the `try:` that calls `claude_integration.run_command`, add:

```python
        topic_state_key = self._current_topic_key(update, context)
        prompt_for_claude = message_text
        run_session_id = session_id
        run_force_new = force_new

        if self.settings.context_runtime_enabled and self.context_manager.would_exceed_limit(topic_state_key, message_text):
            storage = context.bot_data.get("storage")
            summary_store = getattr(storage, "conversation_summaries", None) if storage else None
            if summary_store:
                await progress_msg.edit_text("📎 Compacting topic context...", reply_markup=stop_kb)
                compaction = await self.context_manager.compact(
                    key=topic_state_key,
                    claude=claude_integration,
                    summary_store=summary_store,
                    session_id=session_id or "unknown-session",
                    working_directory=str(current_dir),
                    user_id=user_id,
                )
                prompt_for_claude = f"{compaction.compacted_prompt}\n\nNew user message:\n{message_text}"
                run_session_id = None
                run_force_new = True
```

Then change the run call arguments:

```python
                prompt=prompt_for_claude,
                session_id=run_session_id,
                force_new=run_force_new,
```

After successful `claude_response`, before formatting response, add:

```python
            if self.settings.context_runtime_enabled:
                self.context_manager.record_turn(
                    topic_state_key,
                    user_text=message_text,
                    assistant_text=claude_response.content or "",
                    session_id=claude_response.session_id,
                )
```

- [ ] **Step 6: Run targeted orchestrator test**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py::test_agentic_text_compacts_before_claude_when_threshold_exceeded -q
```

Expected: PASS.

- [ ] **Step 7: Run existing orchestrator tests**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py tests/unit/test_bot/test_orchestrator_thread_context.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat: compact long Telegram topic context before Claude"
```

---

### Task 6: Add per-topic lock and queue protection

**Files:**
- Modify: `src/bot/orchestrator.py`
- Test: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing lock serialization test**

Add to `tests/unit/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_agentic_text_uses_same_lock_for_same_topic(orchestrator, telegram_update, telegram_context):
    key = "-100:54"
    telegram_context.user_data["_thread_context"] = {"state_key": key, "chat_id": -100, "message_thread_id": 54}

    lock_one = orchestrator._topic_lock(key)
    lock_two = orchestrator._topic_lock(key)

    assert lock_one is lock_two
```

- [ ] **Step 2: Run lock test**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py::test_agentic_text_uses_same_lock_for_same_topic -q
```

Expected: PASS if Task 5 helper exists. If it fails, fix `_topic_lock` helper before continuing.

- [ ] **Step 3: Add lock around agentic_text body**

In `agentic_text()`, after `message_text = update.message.text`, compute:

```python
        topic_state_key = self._current_topic_key(update, context)
        lock = self._topic_lock(topic_state_key)
```

Wrap the Claude-processing section from rate limit through final sends with:

```python
        try:
            async with asyncio.timeout(self.settings.context_lock_timeout_seconds):
                async with lock:
                    await self._agentic_text_locked(update, context, topic_state_key, message_text)
        except TimeoutError:
            await update.message.reply_text(
                "⏳ Este tópico ainda está processando uma resposta longa. Tenta de novo em alguns segundos."
            )
```

Extract the old `agentic_text()` body into a new private method:

```python
    async def _agentic_text_locked(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        topic_state_key: str,
        message_text: str,
    ) -> None:
        ...old body without first user_id/message_text assignment...
```

Use the `topic_state_key` parameter instead of recomputing it inside the old body.

- [ ] **Step 4: Run orchestrator tests**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py tests/unit/test_bot/test_orchestrator_thread_context.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat: serialize long-context work per Telegram topic"
```

---

### Task 7: Add `/context` and `/compact` commands

**Files:**
- Modify: `src/bot/orchestrator.py`
- Test: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing command tests**

Add to `tests/unit/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_context_command_reports_topic_usage(orchestrator, telegram_update, telegram_context):
    telegram_context.user_data["_thread_context"] = {"state_key": "-100:54", "chat_id": -100, "message_thread_id": 54}
    orchestrator.context_manager.record_turn("-100:54", "hello", "world", "s1")

    await orchestrator.context_status(telegram_update, telegram_context)

    telegram_update.message.reply_text.assert_awaited()
    text = telegram_update.message.reply_text.await_args.args[0]
    assert "Contexto do tópico" in text
    assert "mensagens" in text


@pytest.mark.asyncio
async def test_compact_command_forces_compaction(orchestrator, telegram_update, telegram_context):
    class FakeClaude:
        async def run_command(self, **kwargs):
            from src.claude.sdk_integration import ClaudeResponse
            return ClaudeResponse(content="Summary forced by command.", session_id="summary", duration_ms=1, cost=0, num_turns=1, tools_used=[])

    class FakeSummaryStore:
        async def create_summary(self, summary):
            return 1

    telegram_context.bot_data["claude_integration"] = FakeClaude()
    telegram_context.bot_data["storage"] = type("Storage", (), {"conversation_summaries": FakeSummaryStore()})()
    telegram_context.user_data["_thread_context"] = {"state_key": "-100:54", "chat_id": -100, "message_thread_id": 54}
    telegram_context.user_data["claude_session_id"] = "s1"
    orchestrator.context_manager.record_turn("-100:54", "hello", "world", "s1")

    await orchestrator.compact_context(telegram_update, telegram_context)

    telegram_update.message.reply_text.assert_awaited()
    assert "compactado" in telegram_update.message.reply_text.await_args.args[0].lower()
```

- [ ] **Step 2: Run command tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py::test_context_command_reports_topic_usage tests/unit/test_orchestrator.py::test_compact_command_forces_compaction -q
```

Expected: FAIL because command methods do not exist.

- [ ] **Step 3: Add command methods**

Add to `src/bot/orchestrator.py`:

```python
    async def context_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        key = self._current_topic_key(update, context)
        state = self.context_manager.get_state(key)
        pct = int((state.tokens_used / self.settings.context_token_threshold) * 100)
        await update.message.reply_text(
            "📊 Contexto do tópico\n"
            f"- chave: `{key}`\n"
            f"- mensagens rastreadas: {state.message_count}\n"
            f"- tokens estimados: {state.tokens_used}/{self.settings.context_token_threshold} ({pct}%)\n"
            f"- compactações: {state.compaction_count}",
            parse_mode="Markdown",
        )

    async def compact_context(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        key = self._current_topic_key(update, context)
        claude_integration = context.bot_data.get("claude_integration")
        storage = context.bot_data.get("storage")
        summary_store = getattr(storage, "conversation_summaries", None) if storage else None
        if not claude_integration or not summary_store:
            await update.message.reply_text("Context runtime indisponível neste momento.")
            return

        current_dir = context.user_data.get("current_directory", self.settings.approved_directory)
        session_id = context.user_data.get("claude_session_id") or "manual-compact"
        result = await self.context_manager.compact(
            key=key,
            claude=claude_integration,
            summary_store=summary_store,
            session_id=session_id,
            working_directory=str(current_dir),
            user_id=update.effective_user.id,
        )
        await update.message.reply_text(
            "📎 Contexto compactado.\n"
            f"- mensagens incluídas: {result.messages_included}\n"
            f"- tokens antes: {result.tokens_before}\n"
            f"- tokens depois: {result.tokens_after}\n"
            f"- fallback: {'sim' if result.used_fallback else 'não'}"
        )
```

- [ ] **Step 4: Register commands where existing command handlers are wired**

Find the existing application command registration in `src/bot/core.py` or handler registry. Add:

```python
CommandHandler("context", orchestrator.context_status)
CommandHandler("compact", orchestrator.compact_context)
```

If commands are centralized in `src/bot/handlers/registry.py`, add the same handlers there following the local pattern.

- [ ] **Step 5: Run command tests**

```bash
.venv/bin/python -m pytest tests/unit/test_orchestrator.py::test_context_command_reports_topic_usage tests/unit/test_orchestrator.py::test_compact_command_forces_compaction -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bot/orchestrator.py src/bot/core.py src/bot/handlers/registry.py tests/unit/test_orchestrator.py
git commit -m "feat: expose topic context controls"
```

---

### Task 8: Full validation and production smoke

**Files:**
- No source changes expected.
- Evidence: Linear comment on `JAR-74`.

- [ ] **Step 1: Run format/syntax checks**

```bash
.venv/bin/python -m compileall -q src tests
bash -n bin/run.sh
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run targeted unit suite**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_claude/test_context_manager.py \
  tests/unit/test_storage/test_database.py \
  tests/unit/test_storage/test_repositories.py \
  tests/unit/test_orchestrator.py \
  tests/unit/test_bot/test_orchestrator_thread_context.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run full suite with known voice setting controlled**

```bash
DISABLE_TOOL_VALIDATION=false VOICE_MODEL=base .venv/bin/python -m pytest -q
```

Expected: PASS. If only voice-model defaults fail without `VOICE_MODEL=base`, document as pre-existing local-env issue, not JAR-74 failure.

- [ ] **Step 4: Restart LaunchAgent**

```bash
LABEL="ai.jarvis.claude-code-telegram"
PLIST="/Users/jarvis/Library/LaunchAgents/${LABEL}.plist"
UIDN="$(id -u)"
launchctl bootout "gui/${UIDN}" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/${UIDN}" "$PLIST"
sleep 5
launchctl list | grep "$LABEL"
```

Expected: one running process for the label.

- [ ] **Step 5: Smoke Telegram API without leaking token**

```bash
set -a
source .env
set +a
python3 - <<'PY'
import os, urllib.request, json
TOKEN=os.environ['TELEGRAM_BOT_TOKEN']
base=f'https://api.telegram.org/bot{TOKEN}'
for method in ['getMe', 'deleteWebhook']:
    with urllib.request.urlopen(f'{base}/{method}', timeout=20) as r:
        data=json.load(r)
    print({'method': method, 'ok': data.get('ok')})
PY
```

Expected: both methods print `ok: True`.

- [ ] **Step 6: Manual Telegram smoke in two topics**

In the real Telegram forum group:

1. Topic A: send `/context`; expected token count and topic key for A.
2. Topic B: send `/context`; expected independent topic key for B.
3. Topic A: send `/compact`; expected compacted reply with stats.
4. Topic B: send `/context`; expected no compaction count change from Topic A.
5. Topic A: send a follow-up question referencing an old decision; expected answer uses summary continuity.

- [ ] **Step 7: Verify logs after smoke**

```bash
awk '/Long-context|Context|Compacting|Unexpected error|Traceback|429|502|Bad Gateway|Too Many/{print}' logs/stdout.log | tail -n 120
stat -f 'stderr_size=%z mtime=%Sm' logs/stderr.log
```

Expected: compaction logs present, no new traceback, no growing stderr.

- [ ] **Step 8: Comment evidence on Linear**

```bash
cat > /tmp/JAR-74-closeout.md <<'EOF'
JAR-74 validation evidence:
- compileall: PASS
- bash -n bin/run.sh: PASS
- git diff --check: PASS
- targeted context/storage/orchestrator tests: PASS
- full suite with controlled VOICE_MODEL=base: PASS
- LaunchAgent restart: PASS
- Telegram getMe/deleteWebhook: PASS
- Manual smokes:
  - Topic A /context: PASS
  - Topic B /context isolation: PASS
  - Topic A /compact: PASS
  - Topic B unaffected: PASS
  - follow-up after compaction: PASS
Known limits:
- Context is not literally infinite; runtime compacts before hitting limits.
- Summary quality determines continuity quality; monitor first production conversations.
EOF
/Users/jarvis/.npm-global/bin/linearctl issue comment JAR-74 --body "$(cat /tmp/JAR-74-closeout.md)" --json
```

Expected: Linear comment created.

- [ ] **Step 9: Commit validation docs if any were added**

```bash
git status --short
git add docs/superpowers/plans/2026-05-07-long-context-runtime.md
git commit -m "docs: plan long-context Telegram runtime"
```

---

## Self-Review

**Spec coverage:**
- Long conversations: covered by token tracking, compaction, summary persistence, and restart-safe storage.
- Better than ACP: covered by incremental summaries instead of sliding window, per-topic locks, topic-specific state, and observable `/context` controls.
- Topic isolation: covered by `topic_key(chat_id, message_thread_id)` and orchestrator tests.
- No Anthropic paid API: compaction uses existing `claude.run_command()` path, not direct Anthropic API.
- Recoverability: covered by fallback prompt, persisted summary table, and lock timeout message.

**Placeholder scan:** No placeholder tasks remain. Any implementation detail that depends on local handler registration names points to concrete files and exact `CommandHandler` code to add.

**Type consistency:**
- `ContextManager`, `ContextTurn`, `TopicContextState`, `CompactionResult`, and `ConversationSummaryModel` names are consistent across tests and implementation steps.
- `topic_key()` always returns string format `chat_id:message_thread_id` with general-topic sentinel `1`.
- Orchestrator uses `topic_state_key` consistently as the key passed into context manager.
