# Audio Response Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add text-to-speech capability so the bot can send Claude's responses as Telegram voice messages using Mistral's Voxtral TTS API, with per-user toggle and graceful fallback.

**Architecture:** Extend the existing `VoiceHandler` class with a `synthesize_speech()` method that calls Mistral's `client.audio.speech.complete()`. Add a `/voice on|off` command persisted per-user in SQLite. The orchestrator's `agentic_text()` method gains a `_maybe_send_voice_response()` helper that intercepts responses before the text-sending block, synthesizes audio, and sends via `reply_voice()`. Long responses trigger a summarization step before TTS.

**Tech Stack:** Python 3.10+, mistralai SDK (^1.0.0), python-telegram-bot, aiosqlite, pytest-asyncio

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/config/settings.py` | Add TTS settings (model, voice, format, max length, enable flag) |
| Modify | `src/config/features.py` | Add `voice_responses_enabled` feature flag |
| Modify | `src/storage/database.py` | Migration 5: add `voice_responses_enabled` column to users table |
| Modify | `src/storage/models.py` | Add `voice_responses_enabled` field to `UserModel` |
| Modify | `src/storage/repositories.py` | Add get/set methods for voice response preference |
| Modify | `src/bot/features/voice_handler.py` | Add `synthesize_speech()` TTS method |
| Modify | `src/bot/orchestrator.py` | Add `/voice` command handler + `_maybe_send_voice_response()` |
| Create | `tests/unit/test_voice_tts.py` | Tests for TTS synthesis |
| Create | `tests/unit/test_voice_command.py` | Tests for `/voice` toggle command |
| Create | `tests/unit/test_voice_response_flow.py` | Tests for orchestrator voice response flow |

---

### Task 1: Configuration — Add TTS Settings

**Files:**
- Modify: `src/config/settings.py` (add fields after line ~197, add computed property after line ~525)
- Test: `tests/unit/test_config.py` (existing file, add test)

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_config.py`, add:

```python
def test_voice_response_settings_defaults():
    """Voice response settings have correct defaults."""
    from src.config.settings import Settings

    config = Settings(
        telegram_bot_token="test:token",
        telegram_bot_username="testbot",
        approved_directory="/tmp/test",
    )
    assert config.enable_voice_responses is False
    assert config.voice_response_model == "voxtral-4b-tts-2603"
    assert config.voice_response_voice == "jessica"
    assert config.voice_response_format == "opus"
    assert config.voice_response_max_length == 2000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_config.py::test_voice_response_settings_defaults -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'enable_voice_responses'`

- [ ] **Step 3: Add TTS settings to Settings class**

In `src/config/settings.py`, after the `voice_max_file_size_mb` field (around line 197), add:

```python
    # Voice response (TTS) settings
    enable_voice_responses: bool = Field(
        False, description="Enable text-to-speech voice responses"
    )
    voice_response_model: str = Field(
        "voxtral-4b-tts-2603",
        description="Mistral TTS model for voice responses",
    )
    voice_response_voice: str = Field(
        "jessica",
        description="Mistral TTS voice preset name",
    )
    voice_response_format: str = Field(
        "opus",
        description="TTS output audio format (opus for Telegram voice compatibility)",
    )
    voice_response_max_length: int = Field(
        2000,
        description="Character threshold above which responses are summarized before TTS",
        ge=100,
        le=10000,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_config.py::test_voice_response_settings_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/config/settings.py tests/unit/test_config.py
git commit -m "feat: add TTS voice response settings"
```

---

### Task 2: Feature Flag — Add voice_responses_enabled

**Files:**
- Modify: `src/config/features.py` (add property, update maps)
- Test: `tests/unit/test_config.py` (add feature flag test)

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_config.py`, add:

```python
def test_voice_responses_feature_flag_enabled():
    """voice_responses_enabled is True when enable_voice_responses and mistral_api_key set."""
    from unittest.mock import MagicMock

    from src.config.features import FeatureFlags

    settings = MagicMock()
    settings.enable_voice_responses = True
    settings.mistral_api_key = MagicMock()  # not None = key is set
    flags = FeatureFlags(settings)
    assert flags.voice_responses_enabled is True


def test_voice_responses_feature_flag_disabled_no_key():
    """voice_responses_enabled is False when mistral_api_key is None."""
    from unittest.mock import MagicMock

    from src.config.features import FeatureFlags

    settings = MagicMock()
    settings.enable_voice_responses = True
    settings.mistral_api_key = None
    flags = FeatureFlags(settings)
    assert flags.voice_responses_enabled is False


def test_voice_responses_feature_flag_disabled_not_enabled():
    """voice_responses_enabled is False when enable_voice_responses is False."""
    from unittest.mock import MagicMock

    from src.config.features import FeatureFlags

    settings = MagicMock()
    settings.enable_voice_responses = False
    settings.mistral_api_key = MagicMock()
    flags = FeatureFlags(settings)
    assert flags.voice_responses_enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_config.py -k "voice_responses_feature_flag" -v`
Expected: FAIL with `AttributeError: 'FeatureFlags' object has no attribute 'voice_responses_enabled'`

- [ ] **Step 3: Add voice_responses_enabled property to FeatureFlags**

In `src/config/features.py`, after the `voice_messages_enabled` property (after line 81), add:

```python
    @property
    def voice_responses_enabled(self) -> bool:
        """Check if text-to-speech voice responses are enabled."""
        if not self.settings.enable_voice_responses:
            return False
        return self.settings.mistral_api_key is not None
```

Update the `is_feature_enabled` map (inside the method around line 100) — add this entry:

```python
            "voice_responses": self.voice_responses_enabled,
```

Update `get_enabled_features()` (around line 131) — add before the `return`:

```python
        if self.voice_responses_enabled:
            features.append("voice_responses")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_config.py -k "voice_responses_feature_flag" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/config/features.py tests/unit/test_config.py
git commit -m "feat: add voice_responses_enabled feature flag"
```

---

### Task 3: Storage — Migration and Repository Methods

**Files:**
- Modify: `src/storage/database.py` (add migration 5)
- Modify: `src/storage/models.py` (add field to UserModel)
- Modify: `src/storage/repositories.py` (add get/set methods to UserRepository)
- Test: `tests/unit/test_storage.py` (or create `tests/unit/test_voice_preference.py`)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_voice_preference.py`:

```python
"""Tests for voice response preference storage."""

import pytest

from src.storage.database import DatabaseManager
from src.storage.repositories import UserRepository
from src.storage.models import UserModel


@pytest.fixture
async def db_manager(tmp_path):
    """Create an in-memory database manager."""
    db_path = str(tmp_path / "test.db")
    manager = DatabaseManager(db_path)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def user_repo(db_manager):
    """Create a UserRepository with initialized DB."""
    return UserRepository(db_manager)


async def test_get_voice_responses_default_false(user_repo):
    """New users have voice_responses_enabled = False by default."""
    user = UserModel(user_id=123, telegram_username="testuser")
    await user_repo.create_user(user)
    result = await user_repo.get_voice_responses_enabled(123)
    assert result is False


async def test_set_voice_responses_enabled(user_repo):
    """Setting voice_responses_enabled to True persists."""
    user = UserModel(user_id=456, telegram_username="testuser2")
    await user_repo.create_user(user)
    await user_repo.set_voice_responses_enabled(456, True)
    result = await user_repo.get_voice_responses_enabled(456)
    assert result is True


async def test_set_voice_responses_disabled(user_repo):
    """Setting voice_responses_enabled back to False persists."""
    user = UserModel(user_id=789, telegram_username="testuser3")
    await user_repo.create_user(user)
    await user_repo.set_voice_responses_enabled(789, True)
    await user_repo.set_voice_responses_enabled(789, False)
    result = await user_repo.get_voice_responses_enabled(789)
    assert result is False


async def test_get_voice_responses_nonexistent_user(user_repo):
    """Nonexistent user returns False."""
    result = await user_repo.get_voice_responses_enabled(999)
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_voice_preference.py -v`
Expected: FAIL with `AttributeError: 'UserRepository' object has no attribute 'get_voice_responses_enabled'`

- [ ] **Step 3: Add migration 5 to database.py**

In `src/storage/database.py`, in the `_get_migrations()` method, after migration 4 (around line 312), add:

```python
            (
                5,
                """
                -- Add voice response preference to users
                ALTER TABLE users ADD COLUMN voice_responses_enabled BOOLEAN DEFAULT FALSE;
                """,
            ),
```

- [ ] **Step 4: Add field to UserModel**

In `src/storage/models.py`, add to the `UserModel` dataclass (after `session_count`):

```python
    voice_responses_enabled: bool = False
```

- [ ] **Step 5: Add repository methods to UserRepository**

In `src/storage/repositories.py`, add to the `UserRepository` class (after `get_all_users`, around line 115):

```python
    async def get_voice_responses_enabled(self, user_id: int) -> bool:
        """Get voice response preference for a user."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT voice_responses_enabled FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return bool(row[0]) if row else False

    async def set_voice_responses_enabled(self, user_id: int, enabled: bool) -> None:
        """Set voice response preference for a user."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE users SET voice_responses_enabled = ? WHERE user_id = ?",
                (enabled, user_id),
            )
            await conn.commit()
            logger.info(
                "Updated voice response preference",
                user_id=user_id,
                enabled=enabled,
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_voice_preference.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/storage/database.py src/storage/models.py src/storage/repositories.py tests/unit/test_voice_preference.py
git commit -m "feat: add voice_responses_enabled column and repository methods"
```

---

### Task 4: TTS Synthesis — Add synthesize_speech() to VoiceHandler

**Files:**
- Modify: `src/bot/features/voice_handler.py` (add method + dataclass)
- Create: `tests/unit/test_voice_tts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_voice_tts.py`:

```python
"""Tests for VoiceHandler TTS synthesis."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.features.voice_handler import VoiceHandler


@pytest.fixture
def tts_config():
    """Create a mock config with TTS settings."""
    cfg = MagicMock()
    cfg.voice_provider = "mistral"
    cfg.mistral_api_key_str = "test-api-key"
    cfg.voice_response_model = "voxtral-4b-tts-2603"
    cfg.voice_response_voice = "jessica"
    cfg.voice_response_format = "opus"
    cfg.resolved_voice_model = "voxtral-mini-latest"
    cfg.voice_max_file_size_mb = 20
    cfg.voice_max_file_size_bytes = 20 * 1024 * 1024
    return cfg


@pytest.fixture
def voice_handler(tts_config):
    return VoiceHandler(config=tts_config)


async def test_synthesize_speech_calls_mistral(voice_handler):
    """synthesize_speech calls Mistral TTS API with correct params."""
    fake_audio = b"fake-audio-bytes"

    mock_speech = MagicMock()
    mock_speech.complete_async = AsyncMock(return_value=fake_audio)

    mock_audio = MagicMock()
    mock_audio.speech = mock_speech

    mock_client = MagicMock()
    mock_client.audio = mock_audio
    mistral_ctor = MagicMock(return_value=mock_client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "mistralai", SimpleNamespace(Mistral=mistral_ctor))
        result = await voice_handler.synthesize_speech("Hello world")

    assert result == fake_audio
    mock_speech.complete_async.assert_called_once()
    call_kwargs = mock_speech.complete_async.call_args.kwargs
    assert call_kwargs["model"] == "voxtral-4b-tts-2603"
    assert call_kwargs["voice"] == "jessica"
    assert call_kwargs["input"] == "Hello world"
    assert call_kwargs["response_format"] == "opus"


async def test_synthesize_speech_api_failure(voice_handler):
    """synthesize_speech raises RuntimeError on API failure."""
    mock_speech = MagicMock()
    mock_speech.complete_async = AsyncMock(side_effect=Exception("API down"))

    mock_audio = MagicMock()
    mock_audio.speech = mock_speech

    mock_client = MagicMock()
    mock_client.audio = mock_audio
    mistral_ctor = MagicMock(return_value=mock_client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "mistralai", SimpleNamespace(Mistral=mistral_ctor))
        with pytest.raises(RuntimeError, match="Mistral TTS request failed"):
            await voice_handler.synthesize_speech("Hello world")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_voice_tts.py -v`
Expected: FAIL with `AttributeError: 'VoiceHandler' object has no attribute 'synthesize_speech'`

- [ ] **Step 3: Add synthesize_speech() to VoiceHandler**

In `src/bot/features/voice_handler.py`, add this method to the `VoiceHandler` class (after `_transcribe_mistral`, around line 128):

```python
    async def synthesize_speech(self, text: str) -> bytes:
        """Synthesize text to audio using the Mistral TTS API.

        Returns raw audio bytes in the configured format.
        """
        client = self._get_mistral_client()
        try:
            response = await client.audio.speech.complete_async(
                model=self.config.voice_response_model,
                voice=self.config.voice_response_voice,
                input=text,
                response_format=self.config.voice_response_format,
            )
        except Exception as exc:
            logger.warning(
                "Mistral TTS request failed",
                error_type=type(exc).__name__,
            )
            raise RuntimeError("Mistral TTS request failed.") from exc

        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_voice_tts.py -v`
Expected: PASS

- [ ] **Step 5: Run existing voice handler tests to confirm no regression**

Run: `python -m pytest tests/unit/test_bot/test_voice_handler.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/bot/features/voice_handler.py tests/unit/test_voice_tts.py
git commit -m "feat: add synthesize_speech() TTS method to VoiceHandler"
```

---

### Task 5: /voice Command Handler

**Files:**
- Modify: `src/bot/orchestrator.py` (add handler + register)
- Create: `tests/unit/test_voice_command.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_voice_command.py`:

```python
"""Tests for /voice toggle command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_update_context(user_id=123, text="/voice"):
    """Create mock Update and Context for command testing."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.message_id = 1

    context = MagicMock()
    context.bot_data = {}
    context.user_data = {}

    storage = MagicMock()
    storage.users = MagicMock()
    context.bot_data["storage"] = storage
    context.bot_data["features"] = MagicMock()

    settings = MagicMock()
    settings.enable_voice_responses = True
    settings.mistral_api_key = MagicMock()  # not None

    return update, context, storage, settings


async def test_voice_on_enables(monkeypatch):
    """'/voice on' enables voice responses for the user."""
    update, context, storage, settings = _make_update_context(text="/voice on")
    storage.users.set_voice_responses_enabled = AsyncMock()

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    storage.users.set_voice_responses_enabled.assert_called_once_with(123, True)
    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "on" in reply_text.lower() or "enabled" in reply_text.lower()


async def test_voice_off_disables(monkeypatch):
    """'/voice off' disables voice responses for the user."""
    update, context, storage, settings = _make_update_context(text="/voice off")
    storage.users.set_voice_responses_enabled = AsyncMock()

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    storage.users.set_voice_responses_enabled.assert_called_once_with(123, False)
    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "off" in reply_text.lower() or "disabled" in reply_text.lower()


async def test_voice_no_args_shows_status():
    """'/voice' with no args shows current status."""
    update, context, storage, settings = _make_update_context(text="/voice")
    storage.users.get_voice_responses_enabled = AsyncMock(return_value=False)

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    storage.users.get_voice_responses_enabled.assert_called_once_with(123)
    update.message.reply_text.assert_called_once()


async def test_voice_disabled_at_admin_level():
    """'/voice' when feature disabled at admin level shows unavailable message."""
    update, context, storage, settings = _make_update_context(text="/voice on")
    settings.enable_voice_responses = False

    from src.bot.orchestrator import MessageOrchestrator

    deps = {"storage": storage}
    orch = MessageOrchestrator(settings, deps)
    await orch.agentic_voice_toggle(update, context)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "not enabled" in reply_text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_voice_command.py -v`
Expected: FAIL with `AttributeError: 'MessageOrchestrator' object has no attribute 'agentic_voice_toggle'`

- [ ] **Step 3: Add agentic_voice_toggle handler to orchestrator**

In `src/bot/orchestrator.py`, add the handler method (near the `agentic_verbose` method, around line 616):

```python
    async def agentic_voice_toggle(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Toggle voice responses: /voice [on|off]."""
        if not self.settings.enable_voice_responses:
            await update.message.reply_text(
                "Voice responses are not enabled on this instance.",
                parse_mode="HTML",
            )
            return

        user_id = update.effective_user.id
        storage = context.bot_data.get("storage")
        args = update.message.text.split()[1:] if update.message.text else []

        if not args:
            enabled = await storage.users.get_voice_responses_enabled(user_id)
            status = "on" if enabled else "off"
            await update.message.reply_text(
                f"Voice responses: <b>{status}</b>\n\n"
                "Usage: <code>/voice on</code> or <code>/voice off</code>",
                parse_mode="HTML",
            )
            return

        arg = args[0].lower()
        if arg not in ("on", "off"):
            await update.message.reply_text(
                "Please use: /voice on or /voice off",
                parse_mode="HTML",
            )
            return

        enabled = arg == "on"
        await storage.users.set_voice_responses_enabled(user_id, enabled)
        status = "enabled" if enabled else "disabled"
        await update.message.reply_text(
            f"Voice responses <b>{status}</b>",
            parse_mode="HTML",
        )
```

- [ ] **Step 4: Register the command**

In `_register_agentic_handlers()` (around line 320), add to the `handlers` list:

```python
        ("voice", self.agentic_voice_toggle),
```

In `get_bot_commands()` (around line 460), add to the agentic commands list:

```python
            BotCommand("voice", "Toggle voice responses (on/off)"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_voice_command.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_voice_command.py
git commit -m "feat: add /voice on|off toggle command"
```

---

### Task 6: Voice Response Flow in Orchestrator

**Files:**
- Modify: `src/bot/orchestrator.py` (add `_maybe_send_voice_response()`, modify `agentic_text()`)
- Create: `tests/unit/test_voice_response_flow.py`

- [ ] **Step 1: Write the failing test for short response path**

Create `tests/unit/test_voice_response_flow.py`:

```python
"""Tests for voice response flow in orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_orchestrator_with_voice():
    """Create orchestrator with voice responses enabled."""
    settings = MagicMock()
    settings.enable_voice_responses = True
    settings.mistral_api_key = MagicMock()
    settings.voice_response_max_length = 2000
    settings.agentic_mode = True

    storage = MagicMock()
    storage.users = MagicMock()

    deps = {"storage": storage}

    from src.bot.orchestrator import MessageOrchestrator

    orch = MessageOrchestrator(settings, deps)
    return orch, storage


def _make_update_context(storage):
    """Create mock Update and Context."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_voice = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.message_id = 1

    context = MagicMock()
    context.bot_data = {"storage": storage}
    return update, context


async def test_short_response_sends_voice():
    """Short response synthesizes and sends voice message."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(return_value=b"audio-data")

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Hello, this is a short response.",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is True
    voice_handler.synthesize_speech.assert_called_once_with(
        "Hello, this is a short response."
    )
    update.message.reply_voice.assert_called_once()
    # Should send a short label text too
    update.message.reply_text.assert_called_once()


async def test_voice_disabled_skips():
    """When user has voice off, returns False."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=False)
    voice_handler = MagicMock()

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Some response",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is False
    voice_handler.synthesize_speech.assert_not_called()


async def test_tts_failure_falls_back_to_text():
    """TTS failure returns False so text path runs, and sends note."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(
        side_effect=RuntimeError("TTS failed")
    )

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Some response",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_voice_response_flow.py -v`
Expected: FAIL with `AttributeError: 'MessageOrchestrator' object has no attribute '_maybe_send_voice_response'`

- [ ] **Step 3: Implement _maybe_send_voice_response()**

In `src/bot/orchestrator.py`, add this method to `MessageOrchestrator` (before `agentic_text`):

```python
    async def _maybe_send_voice_response(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        response_text: str,
        user_id: int,
        voice_handler: Any,
    ) -> bool:
        """Try to send response as voice message.

        Returns True if voice was sent (caller should adjust text sending).
        Returns False if voice was not sent (caller sends text as normal).
        """
        if not self.settings.enable_voice_responses:
            return False

        storage = context.bot_data.get("storage")
        if not storage:
            return False

        try:
            enabled = await storage.users.get_voice_responses_enabled(user_id)
        except Exception:
            return False

        if not enabled:
            return False

        if not voice_handler:
            return False

        text_to_speak = response_text
        is_long = len(response_text) > self.settings.voice_response_max_length
        send_full_text = False

        if is_long:
            # Summarize for spoken delivery
            try:
                claude_integration = context.bot_data.get("claude_integration")
                if claude_integration:
                    from pathlib import Path

                    summary_prompt = (
                        "Summarize the following response in 2-3 sentences "
                        "suitable for being read aloud as a voice message. "
                        "Output ONLY the summary, nothing else.\n\n"
                        f"{response_text}"
                    )
                    summary_response = await claude_integration.run_command(
                        prompt=summary_prompt,
                        working_directory=Path(self.settings.approved_directory),
                        user_id=user_id,
                        force_new=True,
                    )
                    text_to_speak = summary_response.content or response_text
                    send_full_text = True
                else:
                    # No Claude integration, truncate instead
                    text_to_speak = response_text[
                        : self.settings.voice_response_max_length
                    ]
                    send_full_text = True
            except Exception as exc:
                logger.warning(
                    "Voice summary generation failed, falling back to text",
                    error=str(exc),
                )
                return False

        try:
            audio_bytes = await voice_handler.synthesize_speech(text_to_speak)
            await update.message.reply_voice(
                voice=audio_bytes,
                reply_to_message_id=update.message.message_id,
            )

            if send_full_text:
                # Long response: send full text alongside
                from .utils.formatting import ResponseFormatter

                formatter = ResponseFormatter(self.settings)
                formatted_messages = formatter.format_claude_response(response_text)
                for message in formatted_messages:
                    if message.text and message.text.strip():
                        try:
                            await update.message.reply_text(
                                message.text,
                                parse_mode=message.parse_mode,
                                reply_markup=None,
                            )
                        except Exception:
                            await update.message.reply_text(
                                message.text, reply_markup=None
                            )
            else:
                # Short response: just a label
                await update.message.reply_text(
                    "Voice response",
                    reply_markup=None,
                )

            return True

        except Exception as exc:
            logger.warning(
                "TTS failed, falling back to text",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_voice_response_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_voice_response_flow.py
git commit -m "feat: add _maybe_send_voice_response() to orchestrator"
```

---

### Task 7: Wire Voice Response Into agentic_text()

**Files:**
- Modify: `src/bot/orchestrator.py` (modify `agentic_text()` response-sending section)

- [ ] **Step 1: Modify agentic_text() to call _maybe_send_voice_response()**

In `src/bot/orchestrator.py`, in the `agentic_text()` method, find the block that starts sending text (around line 1094, the `# Send text messages` comment). Insert the voice response attempt **before** the text-sending block.

Replace this section (lines ~1094-1132):

```python
        # Send text messages (skip if caption was already embedded in photos)
        if not caption_sent:
            for i, message in enumerate(formatted_messages):
```

With:

```python
        # Try voice response first (if enabled and user toggled on)
        voice_sent = False
        if not caption_sent and response_content:
            features = context.bot_data.get("features")
            voice_handler = features.get_voice_handler() if features else None
            try:
                voice_sent = await self._maybe_send_voice_response(
                    update=update,
                    context=context,
                    response_text=response_content,
                    user_id=user_id,
                    voice_handler=voice_handler,
                )
            except Exception as voice_err:
                logger.warning("Voice response attempt failed", error=str(voice_err))

            if voice_sent and not caption_sent:
                # Voice was sent (with text handled inside _maybe_send_voice_response)
                # If TTS failure sent a note, voice_sent is False and we fall through
                pass

        # Send text messages (skip if caption or voice was already sent)
        if not caption_sent and not voice_sent:
            for i, message in enumerate(formatted_messages):
```

The rest of the text-sending block remains unchanged.

- [ ] **Step 2: Verify the existing orchestrator tests still pass**

Run: `python -m pytest tests/unit/test_orchestrator.py -v`
Expected: PASS (no regression)

- [ ] **Step 3: Run all voice-related tests**

Run: `python -m pytest tests/unit/test_voice_tts.py tests/unit/test_voice_command.py tests/unit/test_voice_response_flow.py tests/unit/test_voice_preference.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/bot/orchestrator.py
git commit -m "feat: wire voice response into agentic_text() flow"
```

---

### Task 8: Long Response Path Test

**Files:**
- Modify: `tests/unit/test_voice_response_flow.py` (add long response test)

- [ ] **Step 1: Add test for long response summarization path**

In `tests/unit/test_voice_response_flow.py`, add:

```python
async def test_long_response_summarizes_then_speaks():
    """Long response triggers summarization, sends audio of summary + full text."""
    orch, storage = _make_orchestrator_with_voice()
    orch.settings.voice_response_max_length = 50  # Low threshold for testing
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(return_value=b"audio-data")

    # Mock Claude integration for summarization
    mock_claude = MagicMock()
    mock_summary_response = MagicMock()
    mock_summary_response.content = "This is a brief summary."
    mock_claude.run_command = AsyncMock(return_value=mock_summary_response)
    context.bot_data["claude_integration"] = mock_claude

    long_text = "A" * 100  # Exceeds threshold of 50

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text=long_text,
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is True
    # Should synthesize the SUMMARY, not the full text
    voice_handler.synthesize_speech.assert_called_once_with("This is a brief summary.")
    # Should send voice + text messages (full text)
    update.message.reply_voice.assert_called_once()
    assert update.message.reply_text.call_count >= 1  # Full text sent
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/unit/test_voice_response_flow.py::test_long_response_summarizes_then_speaks -v`
Expected: PASS (implementation already handles this in Task 6)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_voice_response_flow.py
git commit -m "test: add long response summarization path test"
```

---

### Task 9: Fallback Note on TTS Failure

**Files:**
- Modify: `src/bot/orchestrator.py` (add note when falling back)
- Modify: `tests/unit/test_voice_response_flow.py` (update fallback test)

- [ ] **Step 1: Update the fallback test to check for note**

In `tests/unit/test_voice_response_flow.py`, update `test_tts_failure_falls_back_to_text`:

```python
async def test_tts_failure_falls_back_to_text():
    """TTS failure returns False and sends fallback note."""
    orch, storage = _make_orchestrator_with_voice()
    update, context = _make_update_context(storage)

    storage.users.get_voice_responses_enabled = AsyncMock(return_value=True)

    voice_handler = MagicMock()
    voice_handler.synthesize_speech = AsyncMock(
        side_effect=RuntimeError("TTS failed")
    )

    result = await orch._maybe_send_voice_response(
        update=update,
        context=context,
        response_text="Some response",
        user_id=123,
        voice_handler=voice_handler,
    )

    assert result is False
    # Should have sent a fallback note
    update.message.reply_text.assert_called_once()
    note = update.message.reply_text.call_args[0][0]
    assert "audio unavailable" in note.lower()
```

- [ ] **Step 2: Update _maybe_send_voice_response() to send the note on TTS failure**

In the `except` block at the end of `_maybe_send_voice_response()`, add the fallback note before returning False:

```python
        except Exception as exc:
            logger.warning(
                "TTS failed, falling back to text",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            try:
                await update.message.reply_text(
                    "(Audio unavailable, sent as text)",
                    reply_markup=None,
                )
            except Exception:
                pass
            return False
```

- [ ] **Step 3: Run the test**

Run: `python -m pytest tests/unit/test_voice_response_flow.py::test_tts_failure_falls_back_to_text -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_voice_response_flow.py
git commit -m "feat: add fallback note when TTS fails"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Run linting**

Run: `make lint`
Expected: No errors (run `make format` first if needed)

- [ ] **Step 3: Run type checking**

Run: `python -m mypy src`
Expected: No new type errors

- [ ] **Step 4: Final commit if any formatting changes**

```bash
git add -A
git commit -m "style: fix lint/formatting for voice response feature"
```
