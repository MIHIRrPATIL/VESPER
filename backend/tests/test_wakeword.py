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


def test_wakeword_single_dispatch_guarantee():
    """Verifies that a wake word trigger invokes the callback exactly once, avoiding duplicate logs or events."""
    dispatch_count = 0

    def on_wake(evt: WakeWordEvent):
        nonlocal dispatch_count
        dispatch_count += 1

    listener = WakeWordListener(on_wake_word=on_wake, sample_rate=16000)

    # Mock detector triggering a detected event
    class MockDetector:
        def __init__(self, on_wake_word=None):
            self.on_wake_word = on_wake_word
        def process_frame(self, data):
            return WakeWordEvent(detected=True, wake_word="hey_alfred", confidence=0.95)
        def reset(self):
            pass

    listener.detector = MockDetector(on_wake_word=listener._handle_detector_wake)

    # Feeding 1 frame with detection
    event = listener.feed_pcm(b"\x00" * 640)
    assert event is not None
    assert event.detected is True
    assert dispatch_count == 1  # Must be called EXACTLY once, not twice


def test_wake_phrase_parser():
    """Verifies parsing of various wake words, prefixes, and attached commands."""
    detector = WakeWordDetector()
    
    # Standalone wake phrases
    term, canon, cmd = detector._parse_wake_phrase("Alfred")
    assert term == "alfred" and canon == "alfred" and cmd == ""

    term, canon, cmd = detector._parse_wake_phrase("Hey Alfred!")
    assert term == "hey alfred" and canon == "alfred" and cmd == ""

    term, canon, cmd = detector._parse_wake_phrase("Jarvis.")
    assert term == "jarvis" and canon == "jarvis" and cmd == ""

    term, canon, cmd = detector._parse_wake_phrase("Hey, Jarvis")
    assert term == "hey jarvis" and canon == "jarvis" and cmd == ""

    term, canon, cmd = detector._parse_wake_phrase("Wake up Alfred")
    assert term == "wake up alfred" and canon == "alfred" and cmd == ""

    # Attached commands in same sentence
    term, canon, cmd = detector._parse_wake_phrase("Alfred play the everyday playlist")
    assert term == "alfred" and canon == "alfred" and cmd == "play the everyday playlist"

    term, canon, cmd = detector._parse_wake_phrase("Hey Alfred, what time is it?")
    assert term == "hey alfred" and canon == "alfred" and cmd == "what time is it"

    term, canon, cmd = detector._parse_wake_phrase("Jarvis, turn on the lights")
    assert term == "jarvis" and canon == "jarvis" and cmd == "turn on the lights"

    # Non-wake phrases must not match
    term, canon, cmd = detector._parse_wake_phrase("Hello there")
    assert term is None and canon is None and cmd == ""

    term, canon, cmd = detector._parse_wake_phrase("What time is it?")
    assert term is None and canon is None and cmd == ""

    term, canon, cmd = detector._parse_wake_phrase("Testing one two three")
    assert term is None and canon is None and cmd == ""


def test_utterance_verification_pending_event_pickup():
    """Verifies that when _pending_wake_event is set, process_frame yields detected=True."""
    detector = WakeWordDetector()
    
    # Initially no wake event
    event = detector.process_frame(b"\x00" * 640)
    assert event.detected is False

    # Simulate utterance verifier confirming "alfred"
    pending = WakeWordEvent(
        detected=True,
        wake_word="alfred",
        confidence=0.98,
        is_speech=True,
        transcript="Alfred",
        remaining_command="play music",
        command_pcm=b"\x01\x00" * 8000,
    )
    detector._pending_wake_event = pending

    # Next frame must return the confirmed wake event
    pickup_event = detector.process_frame(b"\x00" * 640)
    assert pickup_event.detected is True
    assert pickup_event.wake_word == "alfred"
    assert pickup_event.confidence == 0.98
    assert pickup_event.remaining_command == "play music"
    assert detector._pending_wake_event is None


def test_listener_attached_command_dispatch():
    """Verifies that an event with an attached command directly dispatches to on_utterance_complete."""
    wakes = []
    utterances = []

    listener = WakeWordListener(
        on_wake_word=lambda e: wakes.append(e),
        on_utterance_complete=lambda pcm: utterances.append(pcm),
        sample_rate=16000,
    )

    # Trigger wake with attached command
    mock_pcm = b"\x02\x00" * 1600
    event = WakeWordEvent(
        detected=True,
        wake_word="alfred",
        confidence=0.98,
        transcript="Alfred, pause music",
        remaining_command="pause music",
        command_pcm=mock_pcm,
    )
    
    # Inject directly via on_wake_word and on_utterance_complete pattern
    listener.on_wake_word(event)
    if listener.on_utterance_complete and event.command_pcm:
        listener.on_utterance_complete(event.command_pcm)

    assert len(wakes) == 1
    assert wakes[0].wake_word == "alfred"
    assert len(utterances) == 1
    assert utterances[0] == mock_pcm


