"""VESPER Multi-Provider TTS Manager with Fallback & Sentence Streaming.

Orchestrates the speech synthesis fallback chain:
  Primary:  Google Cloud TTS (en-GB-Neural2-B, 4M chars/mo free)
  Fallback: Azure Speech (en-GB-RyanNeural, 500k chars/mo free)
  Offline:  Piper TTS (~30MB RAM local ONNX, zero network dependency)
  Opt-in:   ElevenLabs (when ELEVENLABS_API_KEY is configured)

Implements sentence-level chunk streaming to deliver <400ms time-to-first-sound.
"""

from __future__ import annotations

import logging
import re
from typing import AsyncGenerator, List, Optional

from backend.shared.config import VOICE_TTS_PROVIDER
from backend.voice.tts.azure_tts import AzureTTSProvider
from backend.voice.tts.base import BaseTTSProvider
from backend.voice.tts.elevenlabs_tts import ElevenLabsTTSProvider
from backend.voice.tts.google_tts import GoogleTTSProvider
from backend.voice.tts.groq_tts import GroqTTSProvider
from backend.voice.tts.piper_tts import PiperTTSProvider

logger = logging.getLogger("vesper.voice.tts.manager")


class TTSManager:
    """Manages TTS provider fallback and sentence-level audio streaming."""

    def __init__(
        self,
        providers: Optional[List[BaseTTSProvider]] = None,
        preferred_provider: Optional[str] = None,
    ) -> None:
        self.preferred_provider = preferred_provider or VOICE_TTS_PROVIDER

        if providers:
            self.providers = providers
        else:
            # Construct default fallback priority chain
            self.providers = [
                GroqTTSProvider(),
                GoogleTTSProvider(),
                AzureTTSProvider(),
                ElevenLabsTTSProvider(),
                PiperTTSProvider(),
            ]

    def get_active_providers(self) -> List[BaseTTSProvider]:
        """Returns list of currently available providers ordered by priority."""
        if self.preferred_provider and self.preferred_provider != "auto":
            # If a specific provider is pinned, test it first
            pinned = [p for p in self.providers if p.name.startswith(self.preferred_provider)]
            others = [p for p in self.providers if not p.name.startswith(self.preferred_provider)]
            ordered = pinned + others
        else:
            ordered = self.providers

        return [p for p in ordered if p.is_available()]

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """Splits paragraph text into sentences on terminal punctuation (. ! ?)."""
        clean_text = text.strip()
        if not clean_text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", clean_text)
        return [s.strip() for s in sentences if s.strip()]

    async def stream_speech(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesizes text sentence-by-sentence, streaming audio chunks as they arrive.

        If a primary provider fails, automatically falls back to the next available provider.
        """
        sentences = self.split_sentences(text)
        if not sentences:
            return

        active_providers = self.get_active_providers()

        # If no cloud provider has credentials set, warn and attempt any available
        if not active_providers:
            logger.warning("[TTS.Manager] No configured TTS providers found with valid credentials.")
            active_providers = self.providers  # Attempt default anyway

        for sentence in sentences:
            synthesized = False
            last_error: Optional[Exception] = None

            for provider in active_providers:
                try:
                    logger.debug(f"[TTS.Manager] Synthesizing sentence via {provider.name}: \"{sentence}\"")
                    async for chunk in provider.synthesize_stream(sentence):
                        if chunk:
                            yield chunk
                    synthesized = True
                    break  # Sentence finished successfully, move to next sentence
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"[TTS.Manager] Provider '{provider.name}' failed on sentence (falling back): {e}"
                    )
                    continue

            if not synthesized and last_error:
                logger.error(f"[TTS.Manager] All providers failed for sentence: \"{sentence}\": {last_error}")
