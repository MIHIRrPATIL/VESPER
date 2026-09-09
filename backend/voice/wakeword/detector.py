from __future__ import annotations

import collections
import logging
import os
import pickle
import re
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple
import numpy as np
from pydantic import BaseModel, Field

from backend.voice.audio_utils import pack_pcm_to_wav

logger = logging.getLogger("vesper.voice.wakeword.detector")

try:
    import webrtcvad
    _HAS_WEBRTC_VAD = True
except ImportError:
    _HAS_WEBRTC_VAD = False

MODELS_DIR = Path(__file__).parent / "models"


class WakeWordEvent(BaseModel):
    """Event emitted when a wake phrase is triggered or sampled."""

    detected: bool = False
    wake_word: str = "alfred"
    confidence: float = 0.0
    is_speech: bool = False
    peak_amplitude: float = 0.0
    rms_amplitude: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    transcript: Optional[str] = None
    remaining_command: Optional[str] = None
    command_pcm: Optional[bytes] = None
    matched_term: Optional[str] = None


class WakeWordDetector:
    """Detects 'Alfred' and 'Jarvis' (both single-word and hey-prefixed) from streaming 16kHz PCM audio."""

    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        threshold: float = 0.45,
        sample_rate: int = 16000,
        vad_mode: int = 1,
        on_wake_word: Optional[Callable[[WakeWordEvent], None]] = None,
    ) -> None:
        self.wake_words = wake_words or ["alfred", "hey_alfred", "jarvis"]
        env_th = os.getenv("WAKEWORD_THRESHOLD")
        self.threshold = float(env_th) if env_th else threshold
        self.alfred_threshold = float(os.getenv("ALFRED_THRESHOLD", self.threshold))
        self.jarvis_threshold = float(os.getenv("JARVIS_THRESHOLD", self.threshold))
        self.oww_threshold = float(os.getenv("OWW_THRESHOLD", 0.45))
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

        # Utterance tracking for secondary speech verification
        self._speech_utterance_buffer = bytearray()
        self._silence_frames_after_speech: int = 0
        self._pending_wake_event: Optional[WakeWordEvent] = None
        self._is_verifying_utterance: bool = False

        # Load optional acoustic verifiers
        self.alfred_verifier = self._load_verifier(MODELS_DIR / "alfred_verifier.joblib", "Alfred")
        self.jarvis_verifier = self._load_verifier(MODELS_DIR / "jarvis_verifier.joblib", "Jarvis")

        self._last_wake_time: float = 0.0

    def _load_verifier(self, path: Path, name: str):
        if path.exists():
            try:
                with open(path, "rb") as f:
                    verifier = pickle.load(f)
                logger.info(f"[WakeWordDetector] Loaded {name} acoustic verifier from {path.name}")
                return verifier
            except Exception as e:
                logger.warning(f"[WakeWordDetector] Failed to load {name} verifier: {e}")
        return None

    def _init_oww(self) -> None:
        """Loads openWakeWord acoustic model engine, strictly restricted to Jarvis."""
        try:
            import openwakeword
            import openwakeword.model
            all_paths = openwakeword.get_pretrained_model_paths()
            paths = [
                p for p in all_paths
                if "jarvis" in p.lower() and "alexa" not in p.lower() and "mycroft" not in p.lower()
            ]
            self.oww_model = openwakeword.model.Model(wakeword_model_paths=paths)
            logger.info(f"[WakeWordDetector] Loaded openWakeWord acoustic engine: {list(self.oww_model.models.keys())}")
        except Exception as e:
            logger.warning(f"[WakeWordDetector] openWakeWord unavailable ({e}); running fallback.")
            self.oww_model = None

    def process_frame(self, pcm_chunk: bytes) -> WakeWordEvent:
        """Processes a 16kHz 16-bit mono PCM chunk and evaluates wake words in real-time."""
        # Check if an asynchronous utterance verification confirmed a wake phrase
        if self._pending_wake_event is not None:
            evt = self._pending_wake_event
            self._pending_wake_event = None
            self.reset()
            return evt

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

        # 2. Tier 1: WebRTC VAD Silence Gating (mode 1 for gentle gating)
        is_speech = False
        if self.vad is not None:
            frame_size = 640  # 20ms frame
            if len(pcm_chunk) % frame_size == 0 and len(pcm_chunk) >= frame_size:
                for offset in range(0, len(pcm_chunk), frame_size):
                    sub = pcm_chunk[offset : offset + frame_size]
                    try:
                        if self.vad.is_speech(sub, self.sample_rate):
                            is_speech = True
                            break
                    except Exception:
                        is_speech = rms > 120
            else:
                try:
                    is_speech = self.vad.is_speech(pcm_chunk, self.sample_rate)
                except Exception:
                    is_speech = rms > 120
        else:
            is_speech = rms > 120 or peak > 300

        # Gentle speech sensitivity boost for quiet or distant voices
        if not is_speech and rms > 140 and peak > 350:
            is_speech = True

        self.last_is_speech = is_speech

        # Track speech utterances for secondary Whisper verification
        self._track_speech_utterance(pcm_chunk, is_speech)

        # Append to circular audio buffer
        self._audio_buffer.extend(pcm_chunk)
        if len(self._audio_buffer) > self.max_buffer_bytes:
            overflow = len(self._audio_buffer) - self.max_buffer_bytes
            del self._audio_buffer[:overflow]

        # 3. Fast Acoustic Engine (openWakeWord ONNX)
        curr_score = 0.0
        detected = False
        triggered_word = "alfred"

        if self.oww_model is not None:
            self._oww_accumulator.extend(pcm_chunk)
            chunk_bytes = 2560  # 1280 samples = 80ms
            while len(self._oww_accumulator) >= chunk_bytes:
                eval_slice = bytes(self._oww_accumulator[:chunk_bytes])
                del self._oww_accumulator[:chunk_bytes]
                try:
                    slice_np = np.frombuffer(eval_slice, dtype=np.int16)
                    prediction = self.oww_model.predict(slice_np)

                    # Stock openWakeWord Jarvis model prediction (Hey Jarvis)
                    oww_jarvis = float(prediction.get("hey_jarvis_v0.1", 0.0))
                    if oww_jarvis > curr_score:
                        curr_score = oww_jarvis

                    # Instant 0ms trigger on stock ONNX model
                    now = time.time()
                    if (now - self._last_wake_time) > 1.8:
                        if oww_jarvis >= self.oww_threshold:
                            detected = True
                            triggered_word = "jarvis"
                            self._last_wake_time = now
                            logger.info(f"[WakeWordDetector] 'Hey Jarvis' ONNX triggered (confidence={oww_jarvis:.2f})")
                            break
                except Exception as e:
                    logger.debug(f"[WakeWordDetector] Inference error: {e}")

        self.last_score = curr_score

        if detected:
            self.reset()
            return WakeWordEvent(
                detected=True,
                wake_word=triggered_word,
                confidence=curr_score,
                is_speech=True,
                peak_amplitude=peak,
                rms_amplitude=rms,
                timestamp=time.time(),
            )

        return WakeWordEvent(
            detected=False,
            confidence=curr_score,
            is_speech=is_speech,
            peak_amplitude=peak,
            rms_amplitude=rms,
            timestamp=time.time(),
        )

    def _track_speech_utterance(self, pcm_chunk: bytes, is_speech: bool) -> None:
        """Accumulates continuous speech bursts and verifies wake phrase via Groq Whisper upon pause."""
        if is_speech:
            self._speech_utterance_buffer.extend(pcm_chunk)
            self._silence_frames_after_speech = 0
            # Cap maximum speech buffer to 5.0 seconds to prevent unbounded growth
            if len(self._speech_utterance_buffer) > 160000:
                del self._speech_utterance_buffer[:len(pcm_chunk)]
        else:
            if len(self._speech_utterance_buffer) > 0:
                self._silence_frames_after_speech += 1
                # ~160ms of silence observed after speech (approx 2 frames of 80ms)
                if self._silence_frames_after_speech >= 2:
                    utterance_len = len(self._speech_utterance_buffer)
                    # Duration between 0.25s and 4.5s (8,000 to 144,000 bytes at 16kHz 16-bit mono)
                    if 8000 <= utterance_len <= 144000 and not self._is_verifying_utterance:
                        candidate_pcm = bytes(self._speech_utterance_buffer)
                        self._speech_utterance_buffer.clear()
                        self._silence_frames_after_speech = 0
                        self._dispatch_utterance_verification(candidate_pcm)
                    else:
                        self._speech_utterance_buffer.clear()
                        self._silence_frames_after_speech = 0

    def _dispatch_utterance_verification(self, candidate_pcm: bytes) -> None:
        """Asynchronously verifies if a short speech utterance contains 'Alfred', 'Jarvis', or 'Vesper'."""
        if time.time() - self._last_wake_time < 1.8:
            return

        self._is_verifying_utterance = True

        def _worker():
            try:
                import asyncio
                from backend.voice.stt import GroqSpeechToText
                wav = pack_pcm_to_wav(candidate_pcm, sample_rate=self.sample_rate)
                stt = GroqSpeechToText()
                transcript = asyncio.run(stt.transcribe_wav(wav))
                if transcript:
                    matched_term, canonical, remaining_cmd = self._parse_wake_phrase(transcript)
                    if matched_term:
                        logger.info(
                            f"[WakeWordDetector] Wake word confirmed via speech recognition: "
                            f"\"{transcript}\" -> term='{matched_term}', canonical='{canonical}'"
                        )
                        self._last_wake_time = time.time()
                        # If the phrase is a direct wake command (e.g. 'wake up alfred'), preserve it as wake_word
                        ww = matched_term if ("wake up" in matched_term) else (canonical or "alfred")
                        evt = WakeWordEvent(
                            detected=True,
                            wake_word=ww,
                            matched_term=matched_term,
                            confidence=0.98,
                            is_speech=True,
                            peak_amplitude=self.last_peak,
                            rms_amplitude=self.last_rms,
                            timestamp=time.time(),
                            transcript=transcript,
                            remaining_command=remaining_cmd,
                            command_pcm=candidate_pcm,
                        )
                        self._pending_wake_event = evt
                        if self.on_wake_word:
                            try:
                                self.on_wake_word(evt)
                            except Exception as cb_err:
                                logger.debug(f"[WakeWordDetector] on_wake_word notice: {cb_err}")
            except Exception as e:
                logger.debug(f"[WakeWordDetector] Background utterance verification notice: {e}")
            finally:
                self._is_verifying_utterance = False

        threading.Thread(target=_worker, daemon=True, name="vesper-utterance-verifier").start()

    @staticmethod
    def _parse_wake_phrase(text: str) -> Tuple[Optional[str], Optional[str], str]:
        """Parses a transcript to detect wake terms and extract any trailing command."""
        clean = text.lower().strip(" .!?,;:")
        clean = re.sub(r"[^\w\s]", " ", clean)
        clean = " ".join(clean.split())

        wake_terms = [
            "wake up alfred", "wake up jarvis", "wake up vesper",
            "hey alfred", "hey jarvis", "hey vesper",
            "alfred", "jarvis", "vesper", "wake up",
        ]

        matched_term: Optional[str] = None
        remaining_cmd: str = ""

        for term in sorted(wake_terms, key=len, reverse=True):
            if clean == term:
                matched_term = term
                remaining_cmd = ""
                break
            elif clean.startswith(term + " "):
                matched_term = term
                remaining_cmd = clean[len(term):].strip()
                break

        if not matched_term:
            tokens = clean.split()
            if len(tokens) >= 1 and tokens[0] in ("alfred", "jarvis", "vesper"):
                matched_term = tokens[0]
                remaining_cmd = " ".join(tokens[1:]).strip()
            elif len(tokens) >= 2 and tokens[0] == "hey" and tokens[1] in ("alfred", "jarvis", "vesper"):
                matched_term = f"hey {tokens[1]}"
                remaining_cmd = " ".join(tokens[2:]).strip()

        canonical: Optional[str] = None
        if matched_term:
            if "alfred" in matched_term:
                canonical = "alfred"
            elif "jarvis" in matched_term:
                canonical = "jarvis"
            elif "vesper" in matched_term:
                canonical = "vesper"
            else:
                canonical = "alfred"

        return matched_term, canonical, remaining_cmd

    def trigger_manual_wake(self, phrase: str = "alfred") -> WakeWordEvent:
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
        """Clears internal audio, utterance, and prediction buffers."""
        self._audio_buffer.clear()
        self._oww_accumulator.clear()
        self._speech_utterance_buffer.clear()
        self._silence_frames_after_speech = 0
        self._pending_wake_event = None
        if self.oww_model is not None:
            try:
                self.oww_model.reset()
                if hasattr(self.oww_model, "preprocessor"):
                    prep = self.oww_model.preprocessor
                    if hasattr(prep, "raw_data_buffer"):
                        prep.raw_data_buffer.clear()
                    if hasattr(prep, "melspectrogram_buffer"):
                        prep.melspectrogram_buffer = np.ones((76, 32))
                    if hasattr(prep, "accumulated_samples"):
                        prep.accumulated_samples = 0
                    if hasattr(prep, "feature_buffer"):
                        prep.feature_buffer = np.zeros((120, 96))
            except Exception:
                pass


