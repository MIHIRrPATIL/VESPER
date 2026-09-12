"""VESPER Speech Normalization & Pronunciation Engine.

Re-exports SpeechNormalizer from backend.shared.normalizer for backward compatibility.
"""

from __future__ import annotations

from backend.shared.normalizer import SpeechNormalizer

__all__ = ["SpeechNormalizer"]
