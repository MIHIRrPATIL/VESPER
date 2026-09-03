"""VESPER Primary Google Cloud Text-to-Speech (Neural2 / WaveNet) Provider.

Default voice: en-GB-Neural2-B (deep, articulate British J.A.R.V.I.S. cadence)
Tuning: SSML <prosody pitch="-2st" rate="1.02">
Capacity: 4M characters/month free (Neural2 / WaveNet tier)
"""

from __future__ import annotations

import html
import logging
from typing import AsyncGenerator, Optional

import httpx

from backend.shared.config import (
    GOOGLE_APPLICATION_CREDENTIALS,
    GOOGLE_CLOUD_API_KEY,
    VOICE_PRIMARY_VOICE,
)
from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.google")


class GoogleTTSProvider(BaseTTSProvider):
    """Google Cloud Text-to-Speech provider with SSML deep-pitch tuning."""

    def __init__(
        self,
        voice_name: Optional[str] = None,
        api_key: Optional[str] = None,
        credentials_path: Optional[str] = None,
        pitch: str = "-2st",
        speaking_rate: float = 1.02,
    ) -> None:
        self.voice_name = voice_name or VOICE_PRIMARY_VOICE or "en-GB-Neural2-B"
        self.api_key = api_key or GOOGLE_CLOUD_API_KEY
        self.credentials_path = credentials_path or GOOGLE_APPLICATION_CREDENTIALS
        self.pitch = pitch
        self.speaking_rate = speaking_rate
        self.language_code = "-".join(self.voice_name.split("-")[:2])  # e.g., "en-GB"

    @property
    def name(self) -> str:
        return "google_cloud_tts"

    def is_available(self) -> bool:
        """Available if an API key or service account credential path is provided."""
        return bool(self.api_key or self.credentials_path)

    def _build_ssml(self, text: str) -> str:
        """Escapes raw text and wraps in SSML prosody tags for JARVIS persona."""
        escaped_text = html.escape(text)
        return (
            f'<speak>'
            f'<prosody pitch="{self.pitch}" rate="{self.speaking_rate}">'
            f'{escaped_text}'
            f'</prosody>'
            f'</speak>'
        )

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesizes text via Google Cloud TTS API and yields audio chunks."""
        if not text.strip():
            return

        ssml = self._build_ssml(text)

        # 1. Direct REST API via API Key
        if self.api_key:
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.api_key}"
            payload = {
                "input": {"ssml": ssml},
                "voice": {
                    "languageCode": self.language_code,
                    "name": self.voice_name,
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "sampleRateHertz": 24000,
                },
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Google TTS API returned HTTP {res.status_code}: {res.text}")
                data = res.json()
                import base64
                audio_content = base64.b64decode(data.get("audioContent", ""))
                # Yield in streaming frames
                chunk_size = 4096
                for i in range(0, len(audio_content), chunk_size):
                    yield audio_content[i : i + chunk_size]
            return

        # 2. Service Account Client SDK
        try:
            from google.cloud import texttospeech
            client = texttospeech.TextToSpeechAsyncClient()
            s_input = texttospeech.SynthesisInput(ssml=ssml)
            voice = texttospeech.VoiceSelectionParams(
                language_code=self.language_code,
                name=self.voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                sample_rate_hertz=24000,
            )
            response = await client.synthesize_speech(
                input=s_input,
                voice=voice,
                audio_config=audio_config,
            )
            audio_content = response.audio_content
            chunk_size = 4096
            for i in range(0, len(audio_content), chunk_size):
                yield audio_content[i : i + chunk_size]
        except Exception as e:
            logger.error(f"[TTS.Google] Synthesis error: {e}", exc_info=True)
            raise
