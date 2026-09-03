"""VESPER Voice Pipeline Session Coordinator.

Manages audio ingestion, WebRTC VAD utterance segmentation, single-turn
Groq Whisper STT dispatch, and sentence-level TTS streaming.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from backend.voice.audio_utils import frame_pcm
from backend.voice.stt import GroqSpeechToText
from backend.voice.tts.manager import TTSManager
from backend.voice.vad import UtteranceSegmenter, VadEvent

logger = logging.getLogger("vesper.voice.pipeline")


class VoicePipelineSession:
    """Stateful voice processing pipeline for a connected client session."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        stt_client: Optional[GroqSpeechToText] = None,
        tts_manager: Optional[TTSManager] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.segmenter = UtteranceSegmenter(
            sample_rate=sample_rate,
            frame_duration_ms=frame_duration_ms,
        )
        self.stt = stt_client or GroqSpeechToText()
        self.tts = tts_manager or TTSManager()
        self._interrupted = False

    def reset(self) -> None:
        """Resets session buffers and interruption state."""
        self.segmenter.reset()
        self._interrupted = False

    def interrupt(self) -> None:
        """Signals an immediate barge-in interruption."""
        self.segmenter.reset()
        self._interrupted = True
        logger.info("[PIPELINE] Voice session interrupted (barge-in)")

    async def ingest_audio_chunk(self, raw_pcm_bytes: bytes) -> Optional[str]:
        """Ingests raw 16kHz PCM audio chunk and transcribes when speech completes.

        Args:
            raw_pcm_bytes: Incoming PCM byte slice (e.g. from WebSocket frame).

        Returns:
            Transcribed command text if an utterance finished, else None.
        """
        for frame in frame_pcm(raw_pcm_bytes, self.sample_rate, self.frame_duration_ms):
            event, completed_utterance = self.segmenter.process_frame(frame)

            if event == VadEvent.UTTERANCE_COMPLETE and completed_utterance:
                logger.info(f"[PIPELINE] Utterance complete ({len(completed_utterance)} bytes), dispatching to Groq STT...")
                try:
                    transcript = await self.stt.transcribe_pcm(
                        completed_utterance,
                        sample_rate=self.sample_rate,
                    )
                    return transcript
                except Exception as e:
                    logger.error(f"[PIPELINE] Transcription error: {e}", exc_info=True)
                    return None

        return None

    async def stream_response(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesizes text through the TTS manager, yielding MP3 audio chunks."""
        self._interrupted = False
        async for chunk in self.tts.stream_speech(text):
            if self._interrupted:
                logger.info("[PIPELINE] TTS stream truncated by user interruption.")
                break
            yield chunk
