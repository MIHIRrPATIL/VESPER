"""VESPER Continuous Wake Word Audio Listener.

Runs a dedicated low-overhead audio input stream in a background thread or async task.
Captures 16kHz audio from the primary microphone, pre-gates with WebRTC VAD,
and triggers an asynchronous callback when 'Hey Alfred' or 'Alfred' is detected.

Features:
- Self-Trigger Protection: Can be paused while Alfred is synthesizing TTS.
- Hardware Fault Tolerance: Gracefully handles missing/disconnected microphones.
- Low CPU: Keeps stream overhead negligible.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Optional

from backend.voice.audio_utils import frame_pcm, get_best_input_device
from backend.voice.wakeword.detector import WakeWordDetector, WakeWordEvent

logger = logging.getLogger("vesper.voice.wakeword.listener")


class WakeWordListener:
    """Continuous microphone listener for local wake word detection."""

    def __init__(
        self,
        on_wake_word: Optional[Callable[[WakeWordEvent], None]] = None,
        on_utterance_complete: Optional[Callable[[bytes], None]] = None,
        on_audio_frame: Optional[Callable[[WakeWordEvent], None]] = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        device_index: Optional[int] = None,
        chunk_samples: int = 1280,
    ) -> None:
        self.on_wake_word = on_wake_word
        self.on_utterance_complete = on_utterance_complete
        self.on_audio_frame = on_audio_frame
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_samples = chunk_samples
        self.device_index = device_index if device_index is not None else get_best_input_device(sample_rate=sample_rate)
        self.detector = WakeWordDetector(
            threshold=threshold,
            sample_rate=sample_rate,
            on_wake_word=self._handle_detector_wake,
        )

        self.is_running = False
        self.is_paused = False  # Paused during TTS to prevent self-triggering
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _handle_detector_wake(self, evt: WakeWordEvent) -> None:
        """Callback triggered by detector (ONNX or speech utterance verification)."""
        if not self.is_paused and self.on_wake_word:
            try:
                self.on_wake_word(evt)
            except Exception as e:
                logger.error(f"[WakeWordListener] Error in wake callback: {e}")

    def start(self) -> bool:
        """Starts the continuous background listening thread."""
        if self.is_running:
            logger.warning("[WakeWordListener] Listener already running.")
            return True

        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._audio_loop, daemon=True, name="vesper-wakeword")
        self._thread.start()
        logger.info(f"[WakeWordListener] Continuous wake word listener active (sample_rate={self.sample_rate}Hz).")
        return True

    def stop(self) -> None:
        """Stops the audio listening thread cleanly."""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        logger.info("[WakeWordListener] Continuous wake word listener stopped.")

    def pause(self) -> None:
        """Pauses wake word evaluation (e.g. while Alfred is speaking TTS)."""
        self.is_paused = True
        self.detector.reset()
        logger.debug("[WakeWordListener] Paused wake word detection (TTS active).")

    def resume(self) -> None:
        """Resumes wake word evaluation."""
        self.detector.reset()
        self.is_paused = False
        logger.debug("[WakeWordListener] Resumed wake word detection.")

    def _audio_loop(self) -> None:
        """Audio streaming loop using sounddevice or fallback queue."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.warning("[WakeWordListener] sounddevice not available. Listener entering simulation mode.")
            self._simulated_loop()
            return

        chunk_samples = self.chunk_samples

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=chunk_samples,
                device=self.device_index,
                channels=1,
                dtype="int16",
            ) as stream:
                logger.info(f"[WakeWordListener] Raw audio stream opened successfully on device {self.device_index}.")
                while not self._stop_event.is_set():
                    if self.is_paused:
                        time.sleep(0.05)
                        continue

                    # Read audio chunk
                    data, overflowed = stream.read(chunk_samples)
                    if not data or len(data) == 0:
                        continue

                    # Process through detector
                    event = self.detector.process_frame(bytes(data))

                    # Emit real-time frame telemetry to UI / meter callback
                    if self.on_audio_frame:
                        try:
                            self.on_audio_frame(event)
                        except Exception:
                            pass

                    if event.detected and not self.is_paused:
                        logger.info(
                            f"[WakeWordListener] Wake word detected: '{event.wake_word}' "
                            f"(confidence: {event.confidence:.2f})"
                        )
                        if self.on_wake_word:
                            try:
                                self.on_wake_word(event)
                            except Exception as cb_err:
                                logger.error(f"[WakeWordListener] Error in wake callback: {cb_err}")

                        if self.on_utterance_complete:
                            utterance = self._collect_command_utterance(stream)
                            if utterance and len(utterance) >= int(self.sample_rate * 2 * 0.4):
                                try:
                                    self.on_utterance_complete(utterance)
                                except Exception as cb_err:
                                    logger.error(f"[WakeWordListener] Error in utterance complete callback: {cb_err}")
                            self.detector.reset()

        except Exception as e:
            logger.warning(
                f"[WakeWordListener] Unable to open audio hardware stream ({e}). "
                "Switching to standby mode."
            )
            self._simulated_loop()

    def _collect_command_utterance(self, stream) -> bytes:
        """Seamlessly captures the user's spoken command on the active stream using WebRTC VAD."""
        from backend.voice.vad import UtteranceSegmenter, VadEvent, VadState

        # 30ms frame: 16000 * 0.03 = 480 samples = 960 bytes
        frame_samples = int(self.sample_rate * 0.03)
        expected_bytes = frame_samples * 2
        segmenter = UtteranceSegmenter(
            sample_rate=self.sample_rate,
            frame_duration_ms=30,
            vad_mode=2,
            silence_threshold_ms=650,
            min_speech_duration_ms=200,
        )

        captured = bytearray()
        start_t = time.time()
        max_duration = 8.0  # seconds max speech window

        while not self._stop_event.is_set() and not self.is_paused and (time.time() - start_t < max_duration):
            try:
                data, _ = stream.read(frame_samples)
                if not data or len(data) == 0:
                    continue
                pcm_frame = bytes(data)
                if len(pcm_frame) != expected_bytes:
                    continue

                evt, completed_audio = segmenter.process_frame(pcm_frame)
                if evt == VadEvent.UTTERANCE_COMPLETE and completed_audio:
                    captured = bytearray(completed_audio)
                    break
                elif (time.time() - start_t > 3.5) and segmenter.state == VadState.IDLE:
                    # No speech detected within 3.5 seconds of wake word
                    break
            except Exception as read_err:
                logger.warning(f"[WakeWordListener] Stream read error during utterance collection: {read_err}")
                break

        if not captured and segmenter._speech_buffer:
            captured = segmenter._speech_buffer

        return bytes(captured)

    def _simulated_loop(self) -> None:
        """Standby loop when physical audio hardware is unavailable or in mock tests."""
        while not self._stop_event.is_set():
            time.sleep(0.1)

    def feed_pcm(self, pcm_bytes: bytes) -> Optional[WakeWordEvent]:
        """Directly feeds PCM audio bytes into the listener (for WebSocket/test input)."""
        if self.is_paused:
            return None

        # Slice into 20ms frames (640 bytes)
        frames = frame_pcm(pcm_bytes, frame_duration_ms=20, sample_rate=self.sample_rate)
        for frame in frames:
            event = self.detector.process_frame(frame)
            if self.on_audio_frame:
                try:
                    self.on_audio_frame(event)
                except Exception:
                    pass
            if event.detected:
                if self.on_wake_word:
                    try:
                        self.on_wake_word(event)
                    except Exception as e:
                        logger.error(f"[WakeWordListener] Callback error on fed frame: {e}")
                return event
        return None
