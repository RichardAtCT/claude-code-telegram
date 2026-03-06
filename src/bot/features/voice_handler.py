"""Handle voice message transcription.

Supported providers (VOICE_PROVIDER):
  parakeet  — local GPU inference via NVIDIA NeMo (default, free, requires CUDA)
  mistral   — Mistral Voxtral API (cloud, requires MISTRAL_API_KEY)
  openai    — OpenAI Whisper API (cloud, requires OPENAI_API_KEY)
"""

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import structlog
from telegram import Voice

from src.config.settings import Settings

logger = structlog.get_logger(__name__)


@dataclass
class ProcessedVoice:
    """Result of voice message processing."""

    transcription: str
    prompt: str
    duration: int = 0


class VoiceHandler:
    """Transcribe Telegram voice/audio messages.

    Delegates to one of three backends based on config.voice_provider:
    - 'parakeet': local NVIDIA NeMo model (no API key required)
    - 'mistral':  Mistral Voxtral cloud API
    - 'openai':   OpenAI Whisper cloud API
    """

    def __init__(self, config: Settings):
        self.config = config
        self._parakeet_model = None  # lazy-loaded on first use
        self._mistral_client: Optional[Any] = None
        self._openai_client: Optional[Any] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def process_voice_message(
        self, voice: Voice, caption: Optional[str] = None
    ) -> ProcessedVoice:
        """Download and transcribe a Telegram voice message."""
        self._check_file_size(getattr(voice, "file_size", None))

        file = await voice.get_file()
        self._check_file_size(getattr(file, "file_size", None))

        voice_bytes = bytes(await file.download_as_bytearray())
        self._check_file_size(len(voice_bytes))

        provider = self.config.voice_provider
        logger.info("Transcribing voice message", provider=provider, duration=voice.duration)

        if provider == "parakeet":
            transcription = await self._transcribe_parakeet(voice_bytes)
        elif provider == "openai":
            transcription = await self._transcribe_openai(voice_bytes)
        else:
            transcription = await self._transcribe_mistral(voice_bytes)

        logger.info("Voice transcription complete", length=len(transcription))

        label = caption if caption else "Voice message transcription:"
        dur = voice.duration
        duration_secs = int(dur.total_seconds()) if isinstance(dur, timedelta) else (dur or 0)

        return ProcessedVoice(
            transcription=transcription,
            prompt=f"{label}\n\n{transcription}",
            duration=duration_secs,
        )

    # ------------------------------------------------------------------
    # Parakeet (local)
    # ------------------------------------------------------------------

    @property
    def _parakeet(self):
        """Lazy-load the Parakeet TDT 0.6B v3 model on first use."""
        if self._parakeet_model is None:
            try:
                import nemo.collections.asr as nemo_asr
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "Optional dependency 'nemo_toolkit' is missing for Parakeet transcription. "
                    "Install parakeet extras: "
                    'pip install "claude-code-telegram[parakeet]"'
                ) from exc

            logger.info("Loading Parakeet TDT 0.6B v3 model (first use)…")
            self._parakeet_model = nemo_asr.models.ASRModel.from_pretrained(
                "nvidia/parakeet-tdt-0.6b-v3"
            )
            logger.info("Parakeet model loaded")
        return self._parakeet_model

    async def _transcribe_parakeet(self, voice_bytes: bytes) -> str:
        """Transcribe using local Parakeet model (runs in thread pool to avoid blocking)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_parakeet, voice_bytes)

    def _run_parakeet(self, voice_bytes: bytes) -> str:
        """CPU-bound transcription — called from executor."""
        ffmpeg = self.config.resolved_ffmpeg_path
        with tempfile.TemporaryDirectory() as tmp:
            ogg_path = Path(tmp) / "voice.ogg"
            wav_path = Path(tmp) / "voice.wav"
            ogg_path.write_bytes(voice_bytes)

            subprocess.run(
                [ffmpeg, "-y", "-i", str(ogg_path), "-ar", "16000", "-ac", "1", str(wav_path)],
                check=True,
                capture_output=True,
            )

            output = self._parakeet.transcribe([str(wav_path)])
            text = output[0].text.strip()

        if not text:
            raise ValueError("Parakeet transcription returned an empty result.")
        return text

    # ------------------------------------------------------------------
    # Mistral (cloud)
    # ------------------------------------------------------------------

    async def _transcribe_mistral(self, voice_bytes: bytes) -> str:
        client = self._get_mistral_client()
        try:
            response = await client.audio.transcriptions.complete_async(
                model="voxtral-mini-2507",
                file={"content": voice_bytes, "file_name": "voice.ogg"},
            )
        except Exception as exc:
            logger.warning("Mistral transcription failed", error_type=type(exc).__name__)
            raise RuntimeError("Mistral transcription request failed.") from exc

        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise ValueError("Mistral transcription returned an empty response.")
        return text

    def _get_mistral_client(self) -> Any:
        if self._mistral_client is not None:
            return self._mistral_client
        try:
            from mistralai import Mistral
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Optional dependency 'mistralai' is missing. "
                'Install voice extras: pip install "claude-code-telegram[voice]"'
            ) from exc

        api_key = self.config.mistral_api_key_str
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY is not configured.")
        self._mistral_client = Mistral(api_key=api_key)
        return self._mistral_client

    # ------------------------------------------------------------------
    # OpenAI Whisper (cloud)
    # ------------------------------------------------------------------

    async def _transcribe_openai(self, voice_bytes: bytes) -> str:
        client = self._get_openai_client()
        try:
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=("voice.ogg", voice_bytes),
            )
        except Exception as exc:
            logger.warning("OpenAI transcription failed", error_type=type(exc).__name__)
            raise RuntimeError("OpenAI transcription request failed.") from exc

        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise ValueError("OpenAI transcription returned an empty response.")
        return text

    def _get_openai_client(self) -> Any:
        if self._openai_client is not None:
            return self._openai_client
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Optional dependency 'openai' is missing. "
                'Install voice extras: pip install "claude-code-telegram[voice]"'
            ) from exc

        api_key = self.config.openai_api_key_str
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        self._openai_client = AsyncOpenAI(api_key=api_key)
        return self._openai_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_file_size(self, size: Optional[int]) -> None:
        if isinstance(size, int) and size > self.config.voice_max_file_size_bytes:
            raise ValueError(
                f"Voice message too large ({size / 1024 / 1024:.1f} MB). "
                f"Max: {self.config.voice_max_file_size_mb} MB."
            )
