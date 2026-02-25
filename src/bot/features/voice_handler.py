"""Handle voice message transcription via Mistral (Voxtral) or OpenAI (Whisper)."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import structlog
from telegram import Voice

from src.config.settings import Settings

logger = structlog.get_logger(__name__)


@dataclass
class ProcessedVoice:
    """Result of voice message processing."""

    prompt: str
    transcription: str
    duration: int


class VoiceHandler:
    """Transcribe Telegram voice messages using Mistral or OpenAI."""

    def __init__(self, config: Settings):
        self.config = config

    async def process_voice_message(
        self, voice: Voice, caption: Optional[str] = None
    ) -> ProcessedVoice:
        """Download and transcribe a voice message.

        1. Download .ogg bytes from Telegram
        2. Call the configured transcription API (Mistral or OpenAI)
        3. Build a prompt combining caption + transcription
        """
        # Download voice data
        file = await voice.get_file()
        voice_bytes = bytes(await file.download_as_bytearray())

        logger.info(
            "Transcribing voice message",
            provider=self.config.voice_provider,
            duration=voice.duration,
            file_size=len(voice_bytes),
        )

        if self.config.voice_provider == "openai":
            transcription = await self._transcribe_openai(voice_bytes)
        else:
            transcription = await self._transcribe_mistral(voice_bytes)

        logger.info(
            "Voice transcription complete",
            transcription_length=len(transcription),
            duration=voice.duration,
        )

        # Build prompt
        label = caption if caption else "Voice message transcription:"
        prompt = f"{label}\n\n{transcription}"

        dur = voice.duration
        duration_secs = int(dur.total_seconds()) if isinstance(dur, timedelta) else dur

        return ProcessedVoice(
            prompt=prompt,
            transcription=transcription,
            duration=duration_secs,
        )

    async def _transcribe_mistral(self, voice_bytes: bytes) -> str:
        """Transcribe audio using the Mistral API (Voxtral)."""
        from mistralai import Mistral

        client = Mistral(api_key=self.config.mistral_api_key_str)
        response = await client.audio.transcriptions.complete_async(
            model=self.config.resolved_voice_model,
            file={
                "content": voice_bytes,
                "file_name": "voice.ogg",
            },
        )
        return response.text.strip()

    async def _transcribe_openai(self, voice_bytes: bytes) -> str:
        """Transcribe audio using the OpenAI Whisper API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.config.openai_api_key_str)
        response = await client.audio.transcriptions.create(
            model=self.config.resolved_voice_model,
            file=("voice.ogg", voice_bytes),
        )
        return response.text.strip()
