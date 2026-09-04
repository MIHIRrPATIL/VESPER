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
import logging
import re
import time
from typing import AsyncGenerator, Dict, List, Optional

from backend.shared.config import VOICE_TTS_PROVIDER
from backend.voice.tts.azure_tts import AzureTTSProvider
from backend.voice.tts.base import BaseTTSProvider
from backend.voice.tts.elevenlabs_tts import ElevenLabsTTSProvider
from backend.voice.tts.google_tts import GoogleTTSProvider
from backend.voice.tts.groq_tts import GroqTTSProvider
from backend.voice.tts.normalizer import SpeechNormalizer
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
        self._quarantined: Dict[str, float] = {}

        if providers:
            self.providers = providers
        else:
            # Construct default fallback priority chain (Piper local first for ~150ms instant TTS)
            self.providers = [
                PiperTTSProvider(),
                GroqTTSProvider(),
                GoogleTTSProvider(),
                AzureTTSProvider(),
                ElevenLabsTTSProvider(),
            ]

    def get_active_providers(self) -> List[BaseTTSProvider]:
        """Returns list of currently available providers ordered by priority, excluding quarantined ones."""
        now = time.time()
        if self.preferred_provider and self.preferred_provider != "auto":
            # If a specific provider is pinned, test it first
            pinned = [p for p in self.providers if p.name.startswith(self.preferred_provider)]
            others = [p for p in self.providers if not p.name.startswith(self.preferred_provider)]
            ordered = pinned + others
        else:
            ordered = self.providers

        return [
            p for p in ordered
            if p.is_available() and now > self._quarantined.get(p.name, 0.0)
        ]

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
        normalized_text = SpeechNormalizer.normalize_for_speech(text)
        sentences = self.split_sentences(normalized_text)
        if not sentences:
            return

        # For short-to-moderate responses (<= 250 characters or <= 2 sentences),
        # synthesize as a single audio unit instead of splitting into multiple rapid API calls.
        # This prevents Groq TPM rate limit rotation and produces smoother, natural speech.
        if len(sentences) <= 2 or len(normalized_text) < 250:
            units = [normalized_text]
        else:
            units = sentences

        active_providers = self.get_active_providers()

        # If no cloud provider has credentials set, warn and attempt any available
        if not active_providers:
            logger.warning("[TTS.Manager] No configured TTS providers found with valid credentials.")
            active_providers = self.providers  # Attempt default anyway

        for sentence in units:
            synthesized = False
            last_error: Optional[Exception] = None

            for provider in list(active_providers):
                try:
                    logger.debug(f"[TTS.Manager] Synthesizing sentence via {provider.name}: \"{sentence}\"")
                    async for chunk in provider.synthesize_stream(sentence):
                        if chunk:
                            yield chunk
                    synthesized = True
                    break  # Sentence finished successfully, move to next sentence
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    # If provider returned 429 Rate Limit or Quota Exceeded, quarantine it to prevent spamming
                    if "429" in err_str or "rate limit" in err_str or "quota" in err_str or "tokens per day" in err_str:
                        self._quarantined[provider.name] = time.time() + 600.0  # 10 minute cooldown
                        logger.warning(
                            f"[TTS.Manager] Provider '{provider.name}' hit rate limit (429/quota). Quarantined for 10 minutes. Falling back."
                        )
                        active_providers = [p for p in active_providers if p != provider]
                    else:
                        logger.warning(
                            f"[TTS.Manager] Provider '{provider.name}' failed on sentence (falling back): {e}"
                        )
                    continue

            if not synthesized and last_error:
                logger.error(f"[TTS.Manager] All providers failed for sentence: \"{sentence}\": {last_error}")
