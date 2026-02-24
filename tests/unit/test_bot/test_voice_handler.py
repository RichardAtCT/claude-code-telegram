"""Tests for voice handler feature."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.features.voice_handler import ProcessedVoice, VoiceHandler


@pytest.fixture
def config():
    """Create a mock config with Mistral settings."""
    cfg = MagicMock()
    cfg.mistral_api_key_str = "test-api-key"
    cfg.voice_transcription_model = "voxtral-mini-latest"
    return cfg


@pytest.fixture
def voice_handler(config):
    """Create a VoiceHandler instance."""
    return VoiceHandler(config=config)


def test_processed_voice_dataclass():
    """ProcessedVoice stores prompt, transcription, and duration."""
    pv = ProcessedVoice(prompt="hello", transcription="world", duration=5)
    assert pv.prompt == "hello"
    assert pv.transcription == "world"
    assert pv.duration == 5


async def test_process_voice_message(voice_handler):
    """process_voice_message downloads, transcribes, and builds prompt."""
    # Mock Telegram Voice object
    voice = MagicMock()
    voice.duration = 7
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake-ogg"))
    voice.get_file = AsyncMock(return_value=mock_file)

    # Mock Mistral client
    mock_response = MagicMock()
    mock_response.text = "  Hello, this is a test.  "

    mock_transcriptions = MagicMock()
    mock_transcriptions.complete_async = AsyncMock(return_value=mock_response)

    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions

    mock_client = MagicMock()
    mock_client.audio = mock_audio

    with patch("mistralai.Mistral", return_value=mock_client):
        result = await voice_handler.process_voice_message(voice, caption=None)

    assert isinstance(result, ProcessedVoice)
    assert result.transcription == "Hello, this is a test."
    assert result.duration == 7
    assert "Voice message transcription:" in result.prompt
    assert "Hello, this is a test." in result.prompt

    # Verify Mistral was called correctly
    mock_transcriptions.complete_async.assert_called_once()
    call_kwargs = mock_transcriptions.complete_async.call_args
    assert call_kwargs.kwargs["model"] == "voxtral-mini-latest"


async def test_process_voice_message_with_caption(voice_handler):
    """process_voice_message uses caption as prompt label when provided."""
    voice = MagicMock()
    voice.duration = 3
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"ogg-data"))
    voice.get_file = AsyncMock(return_value=mock_file)

    mock_response = MagicMock()
    mock_response.text = "Transcribed text"

    mock_transcriptions = MagicMock()
    mock_transcriptions.complete_async = AsyncMock(return_value=mock_response)

    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions

    mock_client = MagicMock()
    mock_client.audio = mock_audio

    with patch("mistralai.Mistral", return_value=mock_client):
        result = await voice_handler.process_voice_message(
            voice, caption="Please summarize:"
        )

    assert result.prompt == "Please summarize:\n\nTranscribed text"


async def test_process_voice_message_timedelta_duration(voice_handler):
    """process_voice_message handles timedelta duration from Telegram."""
    voice = MagicMock()
    voice.duration = timedelta(seconds=15)
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"ogg"))
    voice.get_file = AsyncMock(return_value=mock_file)

    mock_response = MagicMock()
    mock_response.text = "Test"

    mock_transcriptions = MagicMock()
    mock_transcriptions.complete_async = AsyncMock(return_value=mock_response)

    mock_audio = MagicMock()
    mock_audio.transcriptions = mock_transcriptions

    mock_client = MagicMock()
    mock_client.audio = mock_audio

    with patch("mistralai.Mistral", return_value=mock_client):
        result = await voice_handler.process_voice_message(voice)

    assert result.duration == 15
