"""Handle voice message transcription via Mistral API (Voxtral)."""

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
    """Transcribe Telegram voice messages using the Mistral API."""

    def __init__(self, config: Settings):
        self.config = config

    async def process_voice_message(
        self, voice: Voice, caption: Optional[str] = None
    ) -> ProcessedVoice:
        """Download and transcribe a voice message.

        1. Download .ogg bytes from Telegram
        2. Call Mistral audio transcription API
        3. Build a prompt combining caption + transcription
        """
        from mistralai import Mistral

        # Download voice data
        file = await voice.get_file()
        voice_bytes = bytes(await file.download_as_bytearray())

        logger.info(
            "Transcribing voice message",
            duration=voice.duration,
            file_size=len(voice_bytes),
        )

        # Call Mistral transcription API
        api_key = self.config.mistral_api_key_str
        client = Mistral(api_key=api_key)

        response = await client.audio.transcriptions.complete_async(
            model=self.config.voice_transcription_model,
            file={
                "content": voice_bytes,
                "file_name": "voice.ogg",
            },
        )

        transcription = response.text.strip()

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
