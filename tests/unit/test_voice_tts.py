"""Tests for VoiceHandler TTS synthesis."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.features.voice_handler import VoiceHandler


@pytest.fixture
def tts_config():
    """Create a mock config with TTS settings."""
    cfg = MagicMock()
    cfg.voice_provider = "mistral"
    cfg.mistral_api_key_str = "test-api-key"
    cfg.voice_response_model = "voxtral-mini-tts-2603"
    cfg.voice_response_voice = "c69964a6-ab8b-4f8a-9465-ec0925096ec8"
    cfg.voice_response_format = "mp3"
    cfg.resolved_voice_model = "voxtral-mini-latest"
    cfg.voice_max_file_size_mb = 20
    cfg.voice_max_file_size_bytes = 20 * 1024 * 1024
    return cfg


@pytest.fixture
def voice_handler(tts_config):
    return VoiceHandler(config=tts_config)


async def test_synthesize_speech_calls_mistral(voice_handler):
    """synthesize_speech calls Mistral TTS REST API with correct params."""
    fake_audio = b"fake-audio-bytes"
    fake_b64 = base64.b64encode(fake_audio).decode()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"audio_data": fake_b64})

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client_instance):
        result = await voice_handler.synthesize_speech("Hello world")

    assert result == fake_audio
    mock_client_instance.post.assert_called_once()
    call_args = mock_client_instance.post.call_args
    assert call_args[0][0] == "https://api.mistral.ai/v1/audio/speech"
    payload = call_args[1]["json"]
    assert payload["model"] == "voxtral-mini-tts-2603"
    assert payload["voice_id"] == "c69964a6-ab8b-4f8a-9465-ec0925096ec8"
    assert payload["input"] == "Hello world"
    assert payload["response_format"] == "mp3"
    assert call_args[1]["headers"]["Authorization"] == "Bearer test-api-key"


async def test_synthesize_speech_api_failure(voice_handler):
    """synthesize_speech raises RuntimeError on API failure."""
    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(side_effect=Exception("API down"))
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client_instance):
        with pytest.raises(RuntimeError, match="Mistral TTS request failed"):
            await voice_handler.synthesize_speech("Hello world")
