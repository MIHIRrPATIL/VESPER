from __future__ import annotations

import collections
import logging
import os
import pickle
import time
from pathlib import Path
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


class WakeWordDetector:
    """Detects 'Alfred' and 'Jarvis' (both single-word and hey-prefixed) from streaming 16kHz PCM audio."""

    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        threshold: float = 0.55,
        sample_rate: int = 16000,
        vad_mode: int = 1,
        on_wake_word: Optional[Callable[[WakeWordEvent], None]] = None,
    ) -> None:
        self.wake_words = wake_words or ["alfred", "hey_alfred", "jarvis"]
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

        # Load Alfred and Jarvis acoustic verifiers
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
            # Exclude alexa and mycroft completely; keep only jarvis
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
                        is_speech = rms > 150
            else:
                try:
                    is_speech = self.vad.is_speech(pcm_chunk, self.sample_rate)
                except Exception:
                    is_speech = rms > 150
        else:
            is_speech = rms > 150 or peak > 400

        self.last_is_speech = is_speech

        # Append to circular audio buffer
        self._audio_buffer.extend(pcm_chunk)
        if len(self._audio_buffer) > self.max_buffer_bytes:
            overflow = len(self._audio_buffer) - self.max_buffer_bytes
            del self._audio_buffer[:overflow]

        # 3. Tier 2: Real-time dual-verifier evaluation (Alfred & Jarvis)
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

                    # Extract 16-frame feature vector (16 x 96 = 1536 dims)
                    p_alfred = 0.0
                    p_jarvis = 0.0
                    if hasattr(self.oww_model, "preprocessor"):
                        feats = self.oww_model.preprocessor.get_features(16)
                        if feats is not None and feats.size >= 1536:
                            vec = feats.flatten()[-1536:].reshape(1, -1)
                            if self.alfred_verifier is not None:
                                p_alfred = float(self.alfred_verifier.predict_proba(vec)[0, 1])
                            if self.jarvis_verifier is not None:
                                p_jarvis = float(self.jarvis_verifier.predict_proba(vec)[0, 1])

                    # Combine with stock openWakeWord Jarvis score
                    oww_jarvis = float(prediction.get("hey_jarvis_v0.1", 0.0))
                    combined_jarvis = max(p_jarvis, oww_jarvis)

                    eval_max = max(p_alfred, combined_jarvis)
                    if eval_max > curr_score:
                        curr_score = eval_max

                    # Check detection with cooldown
                    now = time.time()
                    if (now - self._last_wake_time) > 1.8:
                        alfred_thresh = min(self.threshold, 0.32)
                        jarvis_thresh = min(self.threshold, 0.32)
                        best_score = max(p_alfred, combined_jarvis)

                        if best_score >= alfred_thresh:
                            if p_alfred >= combined_jarvis and p_alfred >= alfred_thresh:
                                detected = True
                                triggered_word = "alfred"
                                self._last_wake_time = now
                                logger.info(f"[WakeWordDetector] 'Alfred' detected (confidence={p_alfred:.2f})")
                                break
                            elif combined_jarvis >= jarvis_thresh:
                                detected = True
                                triggered_word = "jarvis"
                                self._last_wake_time = now
                                logger.info(f"[WakeWordDetector] 'Jarvis' detected (confidence={combined_jarvis:.2f})")
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
        """Clears internal audio and prediction buffers."""
        self._audio_buffer.clear()
        self._oww_accumulator.clear()
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

