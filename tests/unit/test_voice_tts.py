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
