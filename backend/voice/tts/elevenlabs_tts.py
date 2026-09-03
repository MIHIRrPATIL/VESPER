"""VESPER Optional Premium TTS Provider (ElevenLabs).

Activated only when ELEVENLABS_API_KEY is configured in backend/.env.
Supports custom cloned voices with ultra-low latency streaming.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from backend.shared.config import ELEVENLABS_API_KEY
from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.elevenlabs")


class ElevenLabsTTSProvider(BaseTTSProvider):
    """ElevenLabs REST streaming TTS provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: str = "eleven_flash_v2_5",
    ) -> None:
        self.api_key = api_key or ELEVENLABS_API_KEY
        # Default to Brian (deep British male) or user-configured
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "nPczCjzI2devNBz1zQrb")
        self.model_id = model_id

    @property
    def name(self) -> str:
        return "elevenlabs_tts"

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        if not self.is_available():
            raise ValueError("ELEVENLABS_API_KEY is not configured.")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise RuntimeError(f"ElevenLabs returned HTTP {response.status_code}: {error_body.decode('utf-8', errors='ignore')}")

                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
