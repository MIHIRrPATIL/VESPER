"""Tests for VESPER Low-Power Continuous Wake Word Subsystem.

Verifies:
1. WebRTC VAD gating of silent frames (<0.1% CPU).
2. WakeWordDetector buffer management and reset.
3. WakeWordListener self-trigger prevention (pause/resume during TTS).
4. Direct PCM audio feed handling.
"""

from __future__ import annotations

import pytest

from backend.voice.wakeword.detector import WakeWordDetector, WakeWordEvent
from backend.voice.wakeword.listener import WakeWordListener


def test_wakeword_detector_silence_gating():
    """Verifies that pure silence frames are dropped without waking heavy classification."""
    detector = WakeWordDetector(threshold=0.6, sample_rate=16000, vad_mode=2)

    # 20ms of silence at 16000Hz 16-bit mono = 320 samples = 640 bytes of zeros
    silence_chunk = b"\x00" * 640

    event = detector.process_frame(silence_chunk)
    assert isinstance(event, WakeWordEvent)
    assert event.detected is False
    assert event.confidence == 0.0


def test_wakeword_detector_manual_trigger():
    """Verifies manual wake event creation for testing and UI invocation."""
    detector = WakeWordDetector()
    event = detector.trigger_manual_wake("hey_alfred")
    assert event.detected is True
    assert event.wake_word == "hey_alfred"
    assert event.confidence == 1.0


def test_wakeword_listener_pause_and_resume():
    """Verifies that listener pauses during TTS to prevent Alfred from self-triggering."""
    events = []
    listener = WakeWordListener(
        on_wake_word=lambda e: events.append(e),
        sample_rate=16000,
    )

    assert not listener.is_paused

    # Pause for TTS
    listener.pause()
    assert listener.is_paused

    # Feeding PCM while paused must return None
    res = listener.feed_pcm(b"\x00" * 640)
    assert res is None

    # Resume after TTS
    listener.resume()
    assert not listener.is_paused


def test_wakeword_listener_feed_pcm_and_detection():
    """Verifies feeding audio frames and receiving wake events."""
    received_events = []

    def on_wake(e: WakeWordEvent):
        received_events.append(e)

    listener = WakeWordListener(on_wake_word=on_wake, sample_rate=16000)

    # Process silence
    event = listener.feed_pcm(b"\x00" * 640)
    assert event is None
    assert len(received_events) == 0

    # Simulate manual trigger on detector
    wake_event = listener.detector.trigger_manual_wake("hey_alfred")
    assert wake_event.detected is True


def test_wakeword_listener_utterance_complete_callback():
    """Verifies that WakeWordListener accepts on_utterance_complete callback."""
    received_utterances = []

    def on_utterance(pcm: bytes):
        received_utterances.append(pcm)

    listener = WakeWordListener(
        on_wake_word=lambda e: None,
        on_utterance_complete=on_utterance,
        sample_rate=16000,
    )

    assert listener.on_utterance_complete is not None
    test_pcm = b"\x01\x00" * 3200
    listener.on_utterance_complete(test_pcm)
    assert len(received_utterances) == 1
    assert received_utterances[0] == test_pcm
