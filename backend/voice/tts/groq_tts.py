"""VESPER Groq Cloud Text-to-Speech (Orpheus) Provider.

Leverages Groq's high-speed LPU infrastructure using `canopylabs/orpheus-v1-english`.
Ultra-low latency, zero credit card required (uses existing GROQ_API_KEY).
Supports vocal direction annotations like [calm], [authoritative], [formal].
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from groq import AsyncGroq

from backend.shared.config import GROQ_API_KEY
from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.groq")


class GroqTTSProvider(BaseTTSProvider):
    """Groq Cloud LPU Text-to-Speech provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "canopylabs/orpheus-v1-english",
        voice: str = "troy",
    ) -> None:
        self.api_key = api_key or GROQ_API_KEY
        self.model = model
        self.voice = voice
        self._client: Optional[AsyncGroq] = None

    @property
    def name(self) -> str:
        return "groq_cloud_tts"

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GROQ_API_KEY is not configured.")
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        if not self.is_available():
            raise ValueError("GROQ_API_KEY is not configured.")

        try:
            # Prefix with tone direction if not already present
            clean_text = text.strip()
            if not clean_text.startswith("["):
                prompt_text = f"[calm] {clean_text}"
            else:
                prompt_text = clean_text

            response = await self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=prompt_text,
                response_format="wav",
            )

            async for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk

        except Exception as e:
            logger.warning(f"[TTS.Groq] Groq TTS synthesis error: {e}")
            raise
