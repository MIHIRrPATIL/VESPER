"""VESPER Groq Cloud Text-to-Speech (Orpheus) Provider.

Leverages Groq's high-speed LPU infrastructure using `canopylabs/orpheus-v1-english`.
Ultra-low latency, zero credit card required (uses existing GROQ_API_KEY).
Supports vocal direction annotations like [calm], [authoritative], [formal].
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from groq import AsyncGroq

from backend.shared.config import GROQ_API_KEY, GROQ_API_KEYS
from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.groq")


class GroqTTSProvider(BaseTTSProvider):
    """Groq Cloud LPU Text-to-Speech provider with automatic multi-key rotation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "canopylabs/orpheus-v1-english",
        voice: str = "troy",
    ) -> None:
        if api_key:
            self._api_keys = [api_key]
        elif GROQ_API_KEYS:
            self._api_keys = list(GROQ_API_KEYS)
        elif GROQ_API_KEY:
            self._api_keys = [GROQ_API_KEY]
        else:
            self._api_keys = []

        self._key_index = 0
        self.model = model
        self.voice = voice
        self._client: Optional[AsyncGroq] = None

    @property
    def name(self) -> str:
        return "groq_cloud_tts"

    @property
    def api_key(self) -> str:
        return self._api_keys[self._key_index] if self._api_keys else ""

    def is_available(self) -> bool:
        return bool(self._api_keys)

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GROQ_API_KEY is not configured.")
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    def _rotate_key(self) -> bool:
        """Rotates to next available Groq key in pool."""
        next_idx = self._key_index + 1
        if next_idx < len(self._api_keys):
            logger.warning(
                f"[TTS.Groq] Groq TTS key #{self._key_index + 1} rate limited. "
                f"Rotating to key #{next_idx + 1} of {len(self._api_keys)}."
            )
            self._key_index = next_idx
            self._client = None
            return True
        return False

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        if not self.is_available():
            raise ValueError("GROQ_API_KEY is not configured.")

        # Prefix with tone direction if not already present
        clean_text = text.strip()
        if not clean_text.startswith("["):
            prompt_text = f"[calm, articulate] {clean_text}"
        else:
            prompt_text = clean_text

        while True:
            try:
                response = await self.client.audio.speech.create(
                    model=self.model,
                    voice=self.voice,
                    input=prompt_text,
                    response_format="wav",
                )

                async for chunk in response.iter_bytes(chunk_size=4096):
                    yield chunk
                return

            except Exception as e:
                err_str = str(e).lower()
                if "model_terms_required" in err_str:
                    logger.warning(
                        "[TTS.Groq] Groq model terms acceptance required for 'canopylabs/orpheus-v1-english'. "
                        "Visit https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english to accept terms."
                    )
                    raise
                if ("429" in err_str or "rate limit" in err_str or "quota" in err_str or "tokens per day" in err_str) and self._rotate_key():
                    continue
                logger.warning(f"[TTS.Groq] Groq TTS synthesis error: {e}")
                raise
