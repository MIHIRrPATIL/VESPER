"""VESPER Speech-to-Text (STT) Client via Groq Whisper Cloud.

Leverages Groq's high-speed LPU infrastructure (whisper-large-v3-turbo)
to transcribe utterances in ~150ms. Strictly sends ONE request per completed
utterance after VAD silence segmentation to respect Groq's 20 RPM limit.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import httpx
from groq import AsyncGroq

from backend.shared.config import GROQ_API_KEY
from backend.voice.audio_utils import pack_pcm_to_wav

logger = logging.getLogger("vesper.voice.stt")


class GroqSpeechToText:
    """Asynchronous Groq Whisper STT transcriber."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3-turbo",
    ) -> None:
        self.api_key = api_key or GROQ_API_KEY
        self.model = model
        self._client: Optional[AsyncGroq] = None

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GROQ_API_KEY is not configured in backend/.env. "
                    "Cannot execute cloud speech transcription."
                )
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    async def transcribe_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        language: str = "en",
        prompt: Optional[str] = None,
    ) -> str:
        """Packages raw 16-bit mono PCM into a WAV container and transcribes via Groq Whisper.

        Args:
            pcm_bytes: Raw 16-bit 16kHz PCM audio bytes.
            sample_rate: Audio sample rate in Hz (default 16000).
            language: Expected language ISO code (default 'en').
            prompt: Optional prior context / terminology hints.

        Returns:
            Transcribed text string.
        """
        if not pcm_bytes:
            return ""

        wav_bytes = pack_pcm_to_wav(pcm_bytes, sample_rate=sample_rate)
        return await self.transcribe_wav(wav_bytes, language=language, prompt=prompt)

    async def transcribe_wav(
        self,
        wav_bytes: bytes,
        language: str = "en",
        prompt: Optional[str] = None,
    ) -> str:
        """Transcribes in-memory WAV bytes via Groq Cloud Whisper API."""
        try:
            audio_file = ("utterance.wav", wav_bytes, "audio/wav")

            kwargs: dict = {
                "file": audio_file,
                "model": self.model,
                "response_format": "json",
                "temperature": 0.0,
            }
            if language:
                kwargs["language"] = language
            if prompt:
                kwargs["prompt"] = prompt

            transcription = await self.client.audio.transcriptions.create(**kwargs)
            text = transcription.text.strip()

            # Filter out known Whisper silence / background noise hallucinations
            hallucination_phrases = {
                "thank you.", "thank you", "thank you!", "thank you very much.",
                "thanks for watching!", "thanks for watching.", "please subscribe.",
                "you", "bye.", "bye", "thank you so much.", "thank you so much",
                "[music]", "[applause]", "subtitles by", "translated by",
            }
            if text.lower() in hallucination_phrases:
                logger.info(f"[STT] Filtered Whisper silence hallucination: \"{text}\"")
                return ""

            logger.info(f"[STT] Transcribed: \"{text}\" ({len(wav_bytes)} bytes audio)")
            return text

        except Exception as e:
            logger.error(f"[STT] Groq transcription failed: {e}", exc_info=True)
            raise
