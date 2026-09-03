"""VESPER Azure Speech Services (Cloud Fallback) TTS Provider.

Official Microsoft Cognitive Services REST API.
Default Voice: en-GB-RyanNeural (deep British butler tone)
Quota: 500,000 characters/month free forever (F0 Free Tier)
"""

from __future__ import annotations

import html
import logging
from typing import AsyncGenerator, Optional

import httpx

from backend.shared.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.azure")


class AzureTTSProvider(BaseTTSProvider):
    """Official Azure Cognitive Services Speech REST API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        region: Optional[str] = None,
        voice_name: str = "en-GB-RyanNeural",
        pitch: str = "-8Hz",
        rate: str = "0%",
    ) -> None:
        self.api_key = api_key or AZURE_SPEECH_KEY
        self.region = region or AZURE_SPEECH_REGION or "eastus"
        self.voice_name = voice_name
        self.pitch = pitch
        self.rate = rate

    @property
    def name(self) -> str:
        return "azure_speech_tts"

    def is_available(self) -> bool:
        return bool(self.api_key and self.region)

    def _build_ssml(self, text: str) -> str:
        escaped_text = html.escape(text)
        return (
            f"<speak version='1.0' xml:lang='en-GB'>"
            f"<voice xml:lang='en-GB' xml:gender='Male' name='{self.voice_name}'>"
            f"<prosody pitch='{self.pitch}' rate='{self.rate}'>"
            f"{escaped_text}"
            f"</prosody>"
            f"</voice>"
            f"</speak>"
        )

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        if not self.is_available():
            raise ValueError("AZURE_SPEECH_KEY or AZURE_SPEECH_REGION not configured.")

        url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "VESPER-DeskCompanion/2.0",
        }
        ssml = self._build_ssml(text)

        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("POST", url, headers=headers, content=ssml.encode("utf-8")) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise RuntimeError(f"Azure Speech returned HTTP {response.status_code}: {error_body.decode('utf-8', errors='ignore')}")

                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
