"""VESPER Speech-to-Text (STT) Client via Groq Whisper Cloud.

Leverages Groq's high-speed LPU infrastructure (whisper-large-v3-turbo)
to transcribe utterances in ~150ms. Strictly sends ONE request per completed
utterance after VAD silence segmentation to respect Groq's 20 RPM limit.
"""

from __future__ import annotations

import io
import logging
import os
import struct
from typing import Optional

import httpx
from groq import AsyncGroq

from backend.shared.config import GROQ_API_KEY
from backend.voice.audio_utils import pack_pcm_to_wav

logger = logging.getLogger("vesper.voice.stt")

# RMS energy threshold for 16-bit PCM. Anything below this is silence/ambient noise.
# 16-bit PCM range: -32768 to 32767. Typical speech RMS is 1000-10000+.
# Fan / AC / keyboard noise sits around 50-120. Default 150 is safe.
_RMS_ENERGY_THRESHOLD = int(os.getenv("VESPER_STT_RMS_THRESHOLD", "150"))


def _compute_rms_energy(pcm_bytes: bytes) -> float:
    """Computes RMS energy of 16-bit signed PCM audio."""
    if len(pcm_bytes) < 2:
        return 0.0
    n_samples = len(pcm_bytes) // 2
    if n_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes[: n_samples * 2])
    sum_sq = sum(s * s for s in samples)
    return (sum_sq / n_samples) ** 0.5


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

        # Energy gate: skip near-silent audio before wasting a Groq API call
        rms = _compute_rms_energy(pcm_bytes)
        if rms < _RMS_ENERGY_THRESHOLD:
            logger.debug(f"[STT] Rejected low-energy audio (RMS={rms:.0f} < {_RMS_ENERGY_THRESHOLD})")
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

            # Filter out known Whisper silence / background noise hallucinations.
            # These are common outputs when Whisper receives non-speech audio.
            hallucination_phrases = {
                "thank you.", "thank you", "thank you!", "thank you very much.",
                "thanks for watching!", "thanks for watching.", "please subscribe.",
                "you", "bye.", "bye", "thank you so much.", "thank you so much",
                "[music]", "[applause]", "subtitles by", "translated by",
                # Common short-utterance hallucinations from ambient noise
                "it's a big question.", "it's", "yes.", "yeah.", "okay.", "ok.",
                "i'm sorry.", "sorry.", "hmm.", "um.", "uh.", "so,", "so.",
                "the end.", "thanks.", "right.", "good.", "oh.", "ah.",
                "one.", "two.", "and.", "what?", "huh.", "hello.", "hi.",
                "please.", "no.", "hmm", "mm-hmm.", "mm.", "...",
            }
            if text.lower() in hallucination_phrases:
                logger.info(f"[STT] Filtered Whisper silence hallucination: \"{text}\"")
                return ""

            # Also filter very short transcripts (1-2 chars) which are almost always noise
            if len(text) <= 2:
                logger.info(f"[STT] Filtered ultra-short transcript: \"{text}\"")
                return ""

            logger.info(f"[STT] Transcribed: \"{text}\" ({len(wav_bytes)} bytes audio)")
            return text

        except Exception as e:
            logger.error(f"[STT] Groq transcription failed: {e}", exc_info=True)
            raise
