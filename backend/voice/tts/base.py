"""VESPER Base Text-to-Speech (TTS) Provider Interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseTTSProvider(ABC):
    """Abstract interface for all VESPER TTS providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is configured and ready to synthesize."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier."""
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesizes text into an asynchronous stream of raw audio bytes (MP3/PCM).

        Yields:
            Audio chunks as they arrive from the synthesizer.
        """
        if False:
            yield b""

    async def synthesize(self, text: str) -> bytes:
        """Synthesizes full audio for a given string and returns complete bytes."""
        chunks = []
        async for chunk in self.synthesize_stream(text):
            chunks.append(chunk)
        return b"".join(chunks)
