"""VESPER Voice Activity Detection (WebRTC VAD) Engine.

Lightweight, pure-C audio segmentation designed to run on low-power devices
(Orange Pi PC Plus). Detects speech boundaries and segments continuous microphone
audio into clean, complete utterances for single-turn STT requests.
"""

from __future__ import annotations

import collections
import enum
import logging
from typing import Optional, Tuple

import webrtcvad

logger = logging.getLogger("vesper.voice.vad")


class VadState(str, enum.Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SPEAKING = "SPEAKING"


class VadEvent(str, enum.Enum):
    SILENCE = "SILENCE"
    SPEECH_START = "SPEECH_START"
    SPEECH_CONTINUE = "SPEECH_CONTINUE"
    UTTERANCE_COMPLETE = "UTTERANCE_COMPLETE"


class UtteranceSegmenter:
    """Segments continuous 16kHz PCM audio frames into discrete utterances using WebRTC VAD.

    Attributes:
        sample_rate: Audio sampling rate in Hz (must be 8000, 16000, 32000, or 48000).
        frame_duration_ms: Frame length in ms (10, 20, or 30).
        vad_mode: Aggressiveness 0 (least aggressive) to 3 (most aggressive).
        silence_threshold_ms: Milliseconds of consecutive silence before finalizing speech.
        min_speech_duration_ms: Minimum speech length to avoid false-trigger clicks.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        vad_mode: int = 2,
        silence_threshold_ms: int = 400,
        min_speech_duration_ms: int = 250,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.vad = webrtcvad.Vad(vad_mode)
        self.silence_threshold_ms = silence_threshold_ms
        self.min_speech_duration_ms = min_speech_duration_ms

        # Compute number of frames needed to satisfy thresholds
        self.silence_frames_needed = max(1, silence_threshold_ms // frame_duration_ms)
        self.min_speech_frames = max(1, min_speech_duration_ms // frame_duration_ms)

        # Pre-speech ring buffer (to preserve initial unvoiced consonants like 'p', 't', 's')
        self.ring_buffer_size = max(4, 150 // frame_duration_ms)
        self._ring_buffer: collections.deque[bytes] = collections.deque(maxlen=self.ring_buffer_size)

        # State tracking
        self.state = VadState.IDLE
        self._speech_buffer: bytearray = bytearray()
        self._consecutive_silence_count = 0
        self._speech_frame_count = 0

    def reset(self) -> None:
        """Resets the segmenter state and clears all buffers."""
        self.state = VadState.IDLE
        self._ring_buffer.clear()
        self._speech_buffer.clear()
        self._consecutive_silence_count = 0
        self._speech_frame_count = 0

    def process_frame(self, pcm_frame: bytes) -> Tuple[VadEvent, Optional[bytes]]:
        """Processes a single 10/20/30ms PCM frame.

        Returns:
            Tuple of (VadEvent, utterance_pcm_bytes if UTTERANCE_COMPLETE else None)
        """
        is_speech = self.vad.is_speech(pcm_frame, self.sample_rate)

        if self.state == VadState.IDLE:
            if is_speech:
                self.state = VadState.SPEAKING
                self._speech_buffer.clear()
                # Prepend buffered pre-speech audio
                for prev_frame in self._ring_buffer:
                    self._speech_buffer.extend(prev_frame)
                self._speech_buffer.extend(pcm_frame)
                self._speech_frame_count = 1
                self._consecutive_silence_count = 0
                return VadEvent.SPEECH_START, None
            else:
                self._ring_buffer.append(pcm_frame)
                return VadEvent.SILENCE, None

        elif self.state == VadState.SPEAKING:
            self._speech_buffer.extend(pcm_frame)

            if is_speech:
                self._speech_frame_count += 1
                self._consecutive_silence_count = 0
                return VadEvent.SPEECH_CONTINUE, None
            else:
                self._consecutive_silence_count += 1

                if self._consecutive_silence_count >= self.silence_frames_needed:
                    # Trailing silence detected: finalize utterance
                    if self._speech_frame_count >= self.min_speech_frames:
                        completed_audio = bytes(self._speech_buffer)
                        self.reset()
                        return VadEvent.UTTERANCE_COMPLETE, completed_audio
                    else:
                        # Too short (click or cough) — discard
                        self.reset()
                        return VadEvent.SILENCE, None

                return VadEvent.SPEECH_CONTINUE, None

        return VadEvent.SILENCE, None
