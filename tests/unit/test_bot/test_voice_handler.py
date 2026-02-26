"""Tests for voice handler feature."""

import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.features.voice_handler import ProcessedVoice, VoiceHandler


@pytest.fixture
def mistral_config():
    """Create a mock config with Mistral settings."""
    cfg = MagicMock()
    cfg.voice_provider = "mistral"
    cfg.mistral_api_key_str = "test-api-key"
    cfg.resolved_voice_model = "voxtral-mini-latest"
    cfg.voice_max_file_size_mb = 20
    cfg.voice_max_file_size_bytes = 20 * 1024 * 1024
    return cfg


@pytest.fixture
def openai_config():
    """Create a mock config with OpenAI settings."""
    cfg = MagicMock()
    cfg.voice_provider = "openai"
    cfg.openai_api_key_str = "test-openai-key"
    cfg.resolved_voice_model = "whisper-1"
    cfg.voice_max_file_size_mb = 20
    cfg.voice_max_file_size_bytes = 20 * 1024 * 1024
    return cfg


@pytest.fixture
def voice_handler(mistral_config):
    """Create a VoiceHandler instance with Mistral config."""
    return VoiceHandler(config=mistral_config)


@pytest.fixture
def openai_voice_handler(openai_config):
    """Create a VoiceHandler instance with OpenAI config."""
    return VoiceHandler(config=openai_config)


def _mock_voice(duration=7, file_size=1024):
    """Create a mock Telegram Voice object."""
    voice = MagicMock()
    voice.duration = duration
    voice.file_size = file_size
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake-ogg"))
    voice.get_file = AsyncMock(return_value=mock_file)
    return voice


def test_processed_voice_dataclass():
    """ProcessedVoice stores prompt, transcription, and duration."""
    pv = ProcessedVoice(prompt="hello", transcription="world", duration=5)
    assert pv.prompt == "hello"
    assert pv.transcription == "world"
    assert pv.duration == 5


# --- Mistral provider tests ---


async def test_process_voice_message_mistral(voice_handler):
    """process_voice_message transcribes via Mistral by default."""
    voice = _mock_voice(duration=7)

    mock_response = MagicMock()
    mock_response.text = "  Hello, this is a test.  "

    mock_transcriptions = MagicMock()
    mock_transcriptions.complete_async = AsyncMock(return_value=mock_response)

    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions

    mock_client = MagicMock()
    mock_client.audio = mock_audio
    mistral_ctor = MagicMock(return_value=mock_client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "mistralai", SimpleNamespace(Mistral=mistral_ctor))
        result = await voice_handler.process_voice_message(voice, caption=None)

    assert isinstance(result, ProcessedVoice)
    assert result.transcription == "Hello, this is a test."
    assert result.duration == 7
    assert "Voice message transcription:" in result.prompt
    assert "Hello, this is a test." in result.prompt

    mistral_ctor.assert_called_once_with(api_key="test-api-key")
    mock_transcriptions.complete_async.assert_called_once()
    call_kwargs = mock_transcriptions.complete_async.call_args
    assert call_kwargs.kwargs["model"] == "voxtral-mini-latest"


async def test_process_voice_message_with_caption(voice_handler):
    """process_voice_message uses caption as prompt label when provided."""
    voice = _mock_voice(duration=3)
    voice_handler._transcribe_mistral = AsyncMock(return_value="Transcribed text")

    result = await voice_handler.process_voice_message(
        voice, caption="Please summarize:"
    )

    assert result.prompt == "Please summarize:\n\nTranscribed text"


async def test_process_voice_message_timedelta_duration(voice_handler):
    """process_voice_message handles timedelta duration from Telegram."""
    voice = _mock_voice(duration=timedelta(seconds=15))
    voice_handler._transcribe_mistral = AsyncMock(return_value="Test")

    result = await voice_handler.process_voice_message(voice)

    assert result.duration == 15


async def test_process_voice_message_rejects_large_file(voice_handler):
    """Voice messages larger than configured limit are rejected before download."""
    voice = _mock_voice(file_size=25 * 1024 * 1024)

    with pytest.raises(ValueError, match="too large"):
        await voice_handler.process_voice_message(voice)

    voice.get_file.assert_not_awaited()


async def test_transcribe_mistral_missing_optional_dependency(voice_handler):
    """Missing mistralai package returns a clear install hint."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "mistralai", None)
        with pytest.raises(RuntimeError, match="Optional dependency 'mistralai'"):
            await voice_handler._transcribe_mistral(b"fake-ogg")


async def test_transcribe_mistral_network_error(voice_handler):
    """Network/API errors from Mistral are wrapped with provider context."""
    mock_transcriptions = MagicMock()
    mock_transcriptions.complete_async = AsyncMock(
        side_effect=Exception("network down")
    )
    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions
    mock_client = MagicMock()
    mock_client.audio = mock_audio
    mistral_ctor = MagicMock(return_value=mock_client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "mistralai", SimpleNamespace(Mistral=mistral_ctor))
        with pytest.raises(RuntimeError, match="Mistral transcription request failed"):
            await voice_handler._transcribe_mistral(b"fake-ogg")


# --- OpenAI provider tests ---


async def test_process_voice_message_openai(openai_voice_handler):
    """process_voice_message transcribes via OpenAI Whisper."""
    voice = _mock_voice(duration=10)

    mock_response = MagicMock()
    mock_response.text = "  Hello from Whisper.  "

    mock_transcriptions = MagicMock()
    mock_transcriptions.create = AsyncMock(return_value=mock_response)

    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions

    mock_client = MagicMock()
    mock_client.audio = mock_audio
    openai_ctor = MagicMock(return_value=mock_client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=openai_ctor))
        result = await openai_voice_handler.process_voice_message(voice, caption=None)

    assert isinstance(result, ProcessedVoice)
    assert result.transcription == "Hello from Whisper."
    assert result.duration == 10
    assert "Voice message transcription:" in result.prompt

    openai_ctor.assert_called_once_with(api_key="test-openai-key")
    mock_transcriptions.create.assert_called_once()
    call_kwargs = mock_transcriptions.create.call_args
    assert call_kwargs.kwargs["model"] == "whisper-1"
    assert call_kwargs.kwargs["file"] == ("voice.ogg", b"fake-ogg")


async def test_process_voice_message_openai_with_caption(openai_voice_handler):
    """OpenAI provider uses caption as prompt label when provided."""
    voice = _mock_voice(duration=5)
    openai_voice_handler._transcribe_openai = AsyncMock(
        return_value="Whisper transcription"
    )

    result = await openai_voice_handler.process_voice_message(
        voice, caption="Translate this:"
    )

    assert result.prompt == "Translate this:\n\nWhisper transcription"


async def test_transcribe_openai_empty_response(openai_voice_handler):
    """OpenAI empty transcriptions are rejected."""
    mock_response = MagicMock()
    mock_response.text = "   "

    mock_transcriptions = MagicMock()
    mock_transcriptions.create = AsyncMock(return_value=mock_response)

    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions

    mock_client = MagicMock()
    mock_client.audio = mock_audio
    openai_ctor = MagicMock(return_value=mock_client)

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=openai_ctor))
        with pytest.raises(ValueError, match="empty response"):
            await openai_voice_handler._transcribe_openai(b"fake-ogg")
