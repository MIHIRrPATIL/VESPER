"""VESPER Dual-Tier Async LLM Client.

Primary: Groq LPU (groq/compound-mini) for sub-500ms speed.
Fallback: OpenRouter (meta-llama/llama-3.3-70b-instruct) for deep reasoning.
Provides:
  - `generate_chat(...)` -> Conversational persona synthesis.
  - `generate_json(...)` -> Robust structured JSON output for planning.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from groq import AsyncGroq

from backend.shared.config import (
    AGENT_FAST_MODEL,
    AGENT_PRIMARY_MODEL,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
)

logger = logging.getLogger("vesper.agent.llm")


class LLMClient:
    """Async dual-model LLM interface with sub-second LPU primary and high-quality fallback."""

    def __init__(
        self,
        groq_key: Optional[str] = None,
        openrouter_key: Optional[str] = None,
        fast_model: str = AGENT_FAST_MODEL,
        primary_model: str = AGENT_PRIMARY_MODEL,
    ) -> None:
        self.groq_key = groq_key or GROQ_API_KEY
        self.openrouter_key = openrouter_key or OPENROUTER_API_KEY
        self.fast_model = fast_model
        self.primary_model = primary_model
        self._groq_client: Optional[AsyncGroq] = None

    @property
    def groq_client(self) -> AsyncGroq:
        if self._groq_client is None:
            if not self.groq_key:
                raise ValueError("GROQ_API_KEY is not configured.")
            self._groq_client = AsyncGroq(api_key=self.groq_key)
        return self._groq_client

    async def _call_groq(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, float]:
        """Queries Groq LPU."""
        t0 = time.perf_counter()
        kwargs: Dict[str, Any] = {
            "model": self.fast_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        res = await self.groq_client.chat.completions.create(**kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        content = ""
        if hasattr(res, "choices") and res.choices:  # pyright: ignore[reportAttributeAccessIssue]
            content = res.choices[0].message.content or ""  # pyright: ignore[reportAttributeAccessIssue]
        return content, elapsed_ms

    async def _call_openrouter(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 768,
    ) -> Tuple[str, float]:
        """Queries OpenRouter fallback."""
        t0 = time.perf_counter()
        if not self.openrouter_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.primary_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if res.status_code != 200:
                raise RuntimeError(f"OpenRouter error {res.status_code}: {res.text}")
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            return content, elapsed_ms

    async def generate_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 512,
        prefer_quality: bool = False,
    ) -> Tuple[str, float]:
        """Generates conversational text.

        If prefer_quality is True, queries OpenRouter directly. Otherwise tries Groq LPU first.
        """
        if not prefer_quality and self.groq_key:
            try:
                return await self._call_groq(messages, temperature=temperature, max_tokens=max_tokens)
            except Exception as e:
                logger.warning(f"[LLM] Groq call failed ({e}), falling back to OpenRouter...")

        return await self._call_openrouter(messages, temperature=temperature, max_tokens=max_tokens)

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> Tuple[Dict[str, Any], float]:
        """Generates structured JSON data with robust extraction and fallback."""
        raw_text = ""
        elapsed_ms = 0.0

        # Try Groq LPU first with JSON format
        if self.groq_key:
            try:
                raw_text, elapsed_ms = await self._call_groq(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                logger.warning(f"[LLM] Groq JSON generation failed ({e}), falling back to OpenRouter...")

        if not raw_text:
            raw_text, elapsed_ms = await self._call_openrouter(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Parse JSON and handle potential markdown fence formatting
        cleaned = raw_text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()

        try:
            parsed = json.loads(cleaned)
            return parsed, elapsed_ms
        except Exception as e:
            logger.error(f"[LLM] Failed to parse JSON from response: {cleaned[:200]}... Error: {e}")
            return {}, elapsed_ms
