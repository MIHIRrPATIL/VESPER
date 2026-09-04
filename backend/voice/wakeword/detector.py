from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Callable, List, Optional
import numpy as np
from pydantic import BaseModel, Field

from backend.voice.audio_utils import pack_pcm_to_wav

logger = logging.getLogger("vesper.voice.wakeword.detector")

try:
    import webrtcvad
    _HAS_WEBRTC_VAD = True
except ImportError:
    _HAS_WEBRTC_VAD = False


class WakeWordEvent(BaseModel):
    """Event emitted when a wake phrase is triggered or sampled."""

    detected: bool = False
    wake_word: str = "hey_alfred"
    confidence: float = 0.0
    is_speech: bool = False
    peak_amplitude: float = 0.0
    rms_amplitude: float = 0.0
    timestamp: float = Field(default_factory=time.time)


class WakeWordDetector:
    """Detects 'Hey Alfred' / 'Alfred' from streaming 16kHz, 16-bit mono PCM audio."""

    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        vad_mode: int = 2,
        on_wake_word: Optional[Callable[[WakeWordEvent], None]] = None,
    ) -> None:
        self.wake_words = wake_words or ["hey_alfred", "alfred", "hey_jarvis"]
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.vad_mode = vad_mode
        self.on_wake_word = on_wake_word

        # Real-time telemetry exposed to listener and UI meters
        self.last_peak: float = 0.0
        self.last_rms: float = 0.0
        self.last_is_speech: bool = False
        self.last_score: float = 0.0

        # Initialize WebRTC VAD for fast silence gating
        self.vad = webrtcvad.Vad(vad_mode) if _HAS_WEBRTC_VAD else None

        # Sliding window buffer: stores last 1.5 seconds of audio
        self.buffer_duration_sec = 1.5
        self.max_buffer_bytes = int(self.sample_rate * 2 * self.buffer_duration_sec)
        self._audio_buffer = bytearray()

        # openWakeWord accumulator (minimum 1280 samples = 2560 bytes = 80ms)
        self._oww_accumulator = bytearray()
        self.oww_model = None
        self._init_oww()

        # Speech utterance tracker for Whisper verification ("Hey Alfred" / "Alfred")
        self._speech_utterance_buffer = bytearray()
        self._silence_frames_after_speech: int = 0
        self._last_wake_time: float = 0.0

    def _init_oww(self) -> None:
        """Attempts to load openWakeWord model instances safely."""
        try:
            import openwakeword
            import openwakeword.model
            all_paths = openwakeword.get_pretrained_model_paths()
            paths = [p for p in all_paths if any(k in p for k in ["jarvis", "alexa", "mycroft"])]
            if paths:
                self.oww_model = openwakeword.model.Model(wakeword_model_paths=paths)
            else:
                self.oww_model = openwakeword.model.Model()
            logger.info(f"[WakeWordDetector] Loaded openWakeWord acoustic model engine: {list(self.oww_model.models.keys())}")
        except Exception as e:
            logger.warning(f"[WakeWordDetector] openWakeWord unavailable ({e}); running heuristic/cloud pipeline.")
            self.oww_model = None

    def process_frame(self, pcm_chunk: bytes) -> WakeWordEvent:
        """Processes a 16kHz 16-bit mono PCM chunk and emits real-time telemetry."""
        if not pcm_chunk:
            return WakeWordEvent(
                detected=False,
                confidence=0.0,
                is_speech=False,
                peak_amplitude=0.0,
                rms_amplitude=0.0,
            )

        # 1. Compute acoustic metrics (Peak & RMS amplitude)
        audio_np = np.frombuffer(pcm_chunk, dtype=np.int16)
        if len(audio_np) > 0:
            peak = float(np.max(np.abs(audio_np)))
            rms = float(np.sqrt(np.mean(audio_np.astype(float) ** 2)))
        else:
            peak = 0.0
            rms = 0.0

        self.last_peak = peak
        self.last_rms = rms

        # 2. Tier 1: WebRTC VAD Silence Gating
        is_speech = False
        if self.vad is not None:
            # Sliced in 20ms (640-byte) or 30ms (960-byte) slices
            frame_size = 640
            if len(pcm_chunk) % frame_size == 0 and len(pcm_chunk) >= frame_size:
                for offset in range(0, len(pcm_chunk), frame_size):
                    sub = pcm_chunk[offset : offset + frame_size]
                    try:
                        if self.vad.is_speech(sub, self.sample_rate):
                            is_speech = True
                            break
                    except Exception:
                        is_speech = rms > 250
            else:
                # Direct single frame test or fallback
                try:
                    is_speech = self.vad.is_speech(pcm_chunk, self.sample_rate)
                except Exception:
                    is_speech = rms > 250
        else:
            is_speech = rms > 250 or peak > 800

        self.last_is_speech = is_speech

        # Track speech utterances for secondary Whisper verification
        self._track_speech_utterance(pcm_chunk, is_speech)

        # Drop pure silence early when buffer is empty to save cycles
        if not is_speech and len(self._audio_buffer) == 0 and peak < 100:
            self.last_score = 0.0
            return WakeWordEvent(
                detected=False,
                confidence=0.0,
                is_speech=False,
                peak_amplitude=peak,
                rms_amplitude=rms,
            )

        # Append to circular audio buffer
        self._audio_buffer.extend(pcm_chunk)
        if len(self._audio_buffer) > self.max_buffer_bytes:
            overflow = len(self._audio_buffer) - self.max_buffer_bytes
            del self._audio_buffer[:overflow]

        # 3. Tier 2: Evaluate openWakeWord ONNX model
        curr_score = 0.0
        detected = False
        triggered_word = "hey_alfred"

        if self.oww_model is not None:
            self._oww_accumulator.extend(pcm_chunk)
            # openWakeWord expects >= 1280 samples (2560 bytes = 80ms)
            chunk_bytes = 2560
            while len(self._oww_accumulator) >= chunk_bytes:
                eval_slice = bytes(self._oww_accumulator[:chunk_bytes])
                del self._oww_accumulator[:chunk_bytes]
                try:
                    slice_np = np.frombuffer(eval_slice, dtype=np.int16)
                    prediction = self.oww_model.predict(slice_np)
                    for ww, score in prediction.items():
                        s_float = float(score)
                        if s_float > curr_score:
                            curr_score = s_float
                        if s_float >= self.threshold and (time.time() - self._last_wake_time > 2.0):
                            detected = True
                            triggered_word = ww
                            self._last_wake_time = time.time()
                            logger.info(f"[WakeWordDetector] ONNX model triggered: {ww} (score={s_float:.2f})")
                            break
                except Exception as e:
                    logger.debug(f"[WakeWordDetector] openWakeWord error: {e}")

        self.last_score = curr_score

        if detected:
            self.reset()
            evt = WakeWordEvent(
                detected=True,
                wake_word=triggered_word,
                confidence=curr_score,
                is_speech=True,
                peak_amplitude=peak,
                rms_amplitude=rms,
                timestamp=time.time(),
            )
            if self.on_wake_word:
                self.on_wake_word(evt)
            return evt

        return WakeWordEvent(
            detected=False,
            confidence=curr_score,
            is_speech=is_speech,
            peak_amplitude=peak,
            rms_amplitude=rms,
            timestamp=time.time(),
        )

    def _track_speech_utterance(self, pcm_chunk: bytes, is_speech: bool) -> None:
        """Accumulates continuous speech bursts and verifies wake phrase via Whisper upon pause."""
        if is_speech:
            self._speech_utterance_buffer.extend(pcm_chunk)
            self._silence_frames_after_speech = 0
            # Cap maximum speech buffer to 3.5 seconds to prevent unbounded growth
            if len(self._speech_utterance_buffer) > 112000:
                del self._speech_utterance_buffer[:len(pcm_chunk)]
        else:
            if len(self._speech_utterance_buffer) > 0:
                self._silence_frames_after_speech += 1
                # If ~320ms of silence observed after speech (approx 4 frames of 80ms)
                if self._silence_frames_after_speech >= 3:
                    utterance_len = len(self._speech_utterance_buffer)
                    # If duration is between 0.3s and 2.5s (9,600 to 80,000 bytes at 16kHz 16-bit mono)
                    if 9600 <= utterance_len <= 80000:
                        candidate_pcm = bytes(self._speech_utterance_buffer)
                        self._speech_utterance_buffer.clear()
                        self._silence_frames_after_speech = 0
                        self._dispatch_utterance_verification(candidate_pcm)
                    else:
                        self._speech_utterance_buffer.clear()
                        self._silence_frames_after_speech = 0

    def _dispatch_utterance_verification(self, candidate_pcm: bytes) -> None:
        """Asynchronously verifies if a short speech utterance contains 'Alfred' or 'Vesper'."""
        if time.time() - self._last_wake_time < 2.0:
            return

        def _worker():
            try:
                import asyncio
                from backend.voice.stt import GroqSpeechToText
                wav = pack_pcm_to_wav(candidate_pcm, sample_rate=self.sample_rate)
                stt = GroqSpeechToText()
                transcript = asyncio.run(stt.transcribe_wav(wav))
                if transcript:
                    cleaned = transcript.lower().strip()
                    logger.debug(f"[WakeWordDetector] Utterance verified text: \"{cleaned}\"")
                    wake_terms = ["alfred", "hey alfred", "vesper", "hey vesper", "jarvis", "wake up"]
                    if any(term in cleaned for term in wake_terms):
                        logger.info(f"[WakeWordDetector] Wake word confirmed via speech recognition: '{cleaned}'")
                        self._last_wake_time = time.time()
                        evt = WakeWordEvent(
                            detected=True,
                            wake_word="hey_alfred",
                            confidence=0.98,
                            is_speech=True,
                            peak_amplitude=self.last_peak,
                            rms_amplitude=self.last_rms,
                            timestamp=time.time(),
                        )
                        if self.on_wake_word:
                            self.on_wake_word(evt)
            except Exception as e:
                logger.debug(f"[WakeWordDetector] Background utterance verification notice: {e}")

        threading.Thread(target=_worker, daemon=True, name="vesper-utterance-verifier").start()

    def trigger_manual_wake(self, phrase: str = "hey_alfred") -> WakeWordEvent:
        """Manually fires a wake event (useful for UI button triggers or integration tests)."""
        self.reset()
        evt = WakeWordEvent(
            detected=True,
            wake_word=phrase,
            confidence=1.0,
            is_speech=True,
            peak_amplitude=self.last_peak,
            rms_amplitude=self.last_rms,
            timestamp=time.time(),
        )
        if self.on_wake_word:
            self.on_wake_word(evt)
        return evt

    def reset(self) -> None:
        """Clears internal audio and prediction buffers."""
        self._audio_buffer.clear()
        self._oww_accumulator.clear()
        self._speech_utterance_buffer.clear()
        self._silence_frames_after_speech = 0
        if self.oww_model is not None:
            try:
                self.oww_model.reset()
            except Exception:
                pass

