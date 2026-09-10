import pytest
from backend.agent.fast_path import FastPathEngine


def test_media_playback_phrasing():
    fp = FastPathEngine()

    resume_phrases = [
        "continue playing the music",
        "continue playing music",
        "continue playing",
        "keep playing the music",
        "keep playing music",
        "keep playing",
        "unpause",
        "unpause music",
        "resume",
        "resume music",
        "resume playback",
        "play",
    ]

    for phrase in resume_phrases:
        res = fp.evaluate(phrase)
        assert res.matched is True, f"Failed to match resume phrase: '{phrase}'"
        assert res.intent == "media", f"Expected intent 'media' for '{phrase}', got '{res.intent}'"
        assert res.action == "resume", f"Expected action 'resume' for '{phrase}', got '{res.action}'"

    pause_phrases = [
        "pause",
        "pause music",
        "pause playback",
        "stop music",
        "stop playback",
        "hold the music",
        "halt music",
    ]

    for phrase in pause_phrases:
        res = fp.evaluate(phrase)
        assert res.matched is True, f"Failed to match pause phrase: '{phrase}'"
        assert res.intent == "media", f"Expected intent 'media' for '{phrase}', got '{res.intent}'"
        assert res.action == "pause", f"Expected action 'pause' for '{phrase}', got '{res.action}'"


def test_deterministic_page_navigation():
    fp = FastPathEngine()

    test_cases = [
        ("open workstation page", "center"),
        ("workstation page", "center"),
        ("go to workstation", "center"),
        ("open workstation", "center"),
        ("whats the agenda page", "agenda"),
        ("what is the agenda page", "agenda"),
        ("open agenda page", "agenda"),
        ("open agenda", "agenda"),
        ("show agenda", "agenda"),
        ("agenda page", "agenda"),
        ("open tasks page", "agenda"),
        ("tasks page", "agenda"),
        ("finances", "transactions"),
        ("open finances", "transactions"),
        ("whats the finances page", "transactions"),
        ("finances page", "transactions"),
        ("open ledger", "transactions"),
        ("open transactions", "transactions"),
        ("open services page", "services"),
        ("show services", "services"),
        ("telemetry page", "services"),
        ("open tools", "tools"),
        ("tools page", "tools"),
        ("open tools page", "tools"),
        ("open logs", "logs"),
        ("open logs page", "logs"),
        ("open event stream", "logs"),
        ("open directives", "voice"),
        ("open voice page", "voice"),
    ]

    for phrase, expected_view in test_cases:
        res = fp.evaluate(phrase)
        assert res.matched is True, f"Failed to match navigation query: '{phrase}'"
        assert res.intent == "navigation", f"Expected intent 'navigation' for '{phrase}', got '{res.intent}'"
        assert res.navigate_to == expected_view, f"Expected navigate_to '{expected_view}' for '{phrase}', got '{res.navigate_to}'"
        assert len(res.speech_text) > 0, f"Expected non-empty speech_text for '{phrase}'"
        assert res.card_payload is not None, f"Expected card_payload for '{phrase}'"

