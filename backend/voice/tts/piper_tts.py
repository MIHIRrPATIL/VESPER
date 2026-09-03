"""VESPER Offline / Embedded Local Fallback TTS Provider (Piper TTS).

Designed specifically for ARM SBCs (Orange Pi PC Plus / Raspberry Pi).
Runs entirely offline with ~30MB RAM footprint and zero external network calls.
Default voice: en_GB-semaine-medium (Speaker: Spike)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.piper")

# Standard local model search paths
DEFAULT_PIPER_DIR = Path(__file__).resolve().parent.parent / "models" / "piper"
DEFAULT_MODEL_PATH = DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx"


class PiperTTSProvider(BaseTTSProvider):
    """Local Piper ONNX TTS provider with native Python SDK streaming."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        speaker_id: int = 1,  # 1 = 'spike' in en_GB-semaine-medium
        piper_binary: Optional[str] = None,
    ) -> None:
        self.model_path = model_path or os.getenv("PIPER_MODEL_PATH", str(DEFAULT_MODEL_PATH))
        self.speaker_id = int(os.getenv("PIPER_SPEAKER_ID", str(speaker_id)))
        self.piper_binary = piper_binary or shutil.which("piper") or "piper"
        self._voice_instance: Any = None

    @property
    def name(self) -> str:
        return "piper_local_tts"

    def is_available(self) -> bool:
        """Available if the model ONNX file exists on disk, or piper binary exists."""
        return os.path.exists(self.model_path) or bool(shutil.which(self.piper_binary))

    def _get_voice(self) -> Any:
        """Loads and caches the PiperVoice ONNX instance."""
        if self._voice_instance is None:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Piper ONNX model not found at: {self.model_path}")

            from piper import PiperVoice

            config_path = f"{self.model_path}.json"
            if not os.path.exists(config_path):
                config_path = None

            self._voice_instance = PiperVoice.load(
                self.model_path,
                config_path=config_path,
            )
            logger.info(f"[TTS.Piper] Loaded Piper voice model: {self.model_path} (Speaker: {self.speaker_id})")
        return self._voice_instance

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        if not self.is_available():
            raise RuntimeError(
                "Piper TTS is not available on this host. "
                "Ensure Piper model is downloaded or `piper` executable is in PATH."
            )

        # 1. Prefer Native Python SDK
        try:
            from piper.config import SynthesisConfig

            voice = self._get_voice()
            cfg = SynthesisConfig(speaker_id=self.speaker_id)

            # synthesize is a generator running inference on chunks
            for chunk in voice.synthesize(text, syn_config=cfg):
                if chunk and chunk.audio_int16_bytes:
                    yield chunk.audio_int16_bytes
                    await asyncio.sleep(0)  # Yield execution back to event loop
            return
        except ImportError:
            logger.debug("[TTS.Piper] Native piper package not installed, falling back to CLI subprocess.")
        except Exception as e:
            logger.warning(f"[TTS.Piper] Native SDK synthesis failed ({e}), falling back to CLI subprocess.")

        # 2. CLI Subprocess Fallback
        cmd = [self.piper_binary, "--output-raw"]
        if self.model_path:
            cmd.extend(["--model", self.model_path, "--speaker", str(self.speaker_id)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate(input=text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"Piper execution failed: {stderr.decode('utf-8', errors='ignore')}")

        chunk_size = 4096
        for i in range(0, len(stdout), chunk_size):
            yield stdout[i : i + chunk_size]
            await asyncio.sleep(0)
