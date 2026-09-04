"""VESPER Dual-Tier Async LLM Client.

Primary: Groq LPU (groq/compound-mini) for sub-500ms speed.
Fallback: OpenRouter (meta-llama/llama-3.3-70b-instruct) for deep reasoning.
Provides:
  - `generate_chat(...)` -> Conversational persona synthesis.
  - `generate_json(...)` -> Robust structured JSON output for planning.
"""

from __future__ import annotations

import asyncio
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
    GROQ_API_KEYS,
    OPENROUTER_API_KEY,
)

logger = logging.getLogger("vesper.agent.llm")


class LLMClient:
    """Async dual-model LLM interface with sub-second LPU primary and high-quality fallback.

    Supports a pool of Groq API keys (GROQ_API_KEY, GROQ_API_KEY2, …) that are
    rotated automatically on 429 / rate-limit errors before falling back to OpenRouter.
    """

    def __init__(
        self,
        groq_key: Optional[str] = None,
        openrouter_key: Optional[str] = None,
        fast_model: str = AGENT_FAST_MODEL,
        primary_model: str = AGENT_PRIMARY_MODEL,
    ) -> None:
        # Build key pool: explicit key takes priority, then the full env-defined pool.
        if groq_key:
            self._groq_keys: List[str] = [groq_key]
        else:
            self._groq_keys = list(GROQ_API_KEYS)  # copy so mutations are local
        self._key_index: int = 0  # current active key pointer

        self.openrouter_key = openrouter_key or OPENROUTER_API_KEY
        self.fast_model = fast_model
        self.primary_model = primary_model
        self._groq_client: Optional[AsyncGroq] = None
        self.last_provider_used: str = "none"

    # ------------------------------------------------------------------
    # Backwards-compat shim (used in a few places that read .groq_key)
    # ------------------------------------------------------------------
    @property
    def groq_key(self) -> str:
        return self._groq_keys[self._key_index] if self._groq_keys else ""

    @property
    def groq_client(self) -> AsyncGroq:
        """Returns an AsyncGroq client for the *current* active key."""
        if self._groq_client is None:
            if not self._groq_keys:
                raise ValueError("No GROQ_API_KEY configured.")
            self._groq_client = AsyncGroq(api_key=self._groq_keys[self._key_index])
        return self._groq_client

    def _rotate_groq_key(self) -> bool:
        """Advances to the next Groq key. Returns True if a new key is available."""
        next_index = self._key_index + 1
        if next_index < len(self._groq_keys):
            logger.warning(
                f"[LLM] Groq key #{self._key_index + 1} exhausted. "
                f"Rotating to key #{next_index + 1} of {len(self._groq_keys)}."
            )
            self._key_index = next_index
            self._groq_client = None  # Force rebuild with new key
            return True
        return False

    async def _call_groq(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, float]:
        """Queries Groq LPU with automatic key rotation on 429."""
        t0 = time.perf_counter()
        kwargs: Dict[str, Any] = {
            "model": self.fast_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        last_exc: Optional[Exception] = None

        # Try every available key before giving up
        for attempt in range(len(self._groq_keys) + 1):
            try:
                res = await self.groq_client.chat.completions.create(**kwargs)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                content = ""
                if hasattr(res, "choices") and res.choices:  # pyright: ignore[reportAttributeAccessIssue]
                    content = res.choices[0].message.content or ""  # pyright: ignore[reportAttributeAccessIssue]
                self.last_provider_used = "groq"
                return content, elapsed_ms
            except Exception as e:
                last_exc = e
                err_msg = str(e).lower()
                is_rate_limit = "429" in err_msg or "rate limit" in err_msg

                if is_rate_limit:
                    # Short sleep for per-minute (TPM) limits — then rotate key
                    if "minute" in err_msg or "tpm" in err_msg:
                        await asyncio.sleep(1.5)

                    if self._rotate_groq_key():
                        continue  # Try the next key immediately

                    # All keys exhausted — try model-level fallbacks on current client
                    fallback_models = ["groq/compound", "groq/compound-mini", "openai/gpt-oss-20b"]
                    for fb_m in fallback_models:
                        if fb_m != kwargs["model"]:
                            try:
                                logger.info(
                                    f"[LLM] All Groq keys exhausted for '{kwargs['model']}'. "
                                    f"Trying model-level fallback '{fb_m}'…"
                                )
                                kwargs["model"] = fb_m
                                res = await self.groq_client.chat.completions.create(**kwargs)
                                elapsed_ms = (time.perf_counter() - t0) * 1000
                                content = ""
                                if hasattr(res, "choices") and res.choices:  # pyright: ignore[reportAttributeAccessIssue]
                                    content = res.choices[0].message.content or ""  # pyright: ignore[reportAttributeAccessIssue]
                                self.last_provider_used = "groq"
                                return content, elapsed_ms
                            except Exception:
                                continue
                    # Nothing worked — propagate so callers fall back to OpenRouter
                    raise last_exc  # type: ignore[misc]
                else:
                    raise e

        raise last_exc or RuntimeError("Groq call failed with no exception detail")

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
            if res.status_code == 404:
                logger.warning(
                    f"[LLM] Model '{self.primary_model}' unavailable on OpenRouter (HTTP 404). "
                    "Auto-recovering via 'openrouter/free' fallback..."
                )
                payload["model"] = "openrouter/free"
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"OpenRouter error {res.status_code}: {res.text}")
            data = res.json()
            choices = data.get("choices", [])
            content = ""
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning") or ""
            self.last_provider_used = "openrouter"
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

        # Parse JSON and handle potential markdown fence formatting or text preambles
        cleaned = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            # Match outermost JSON object { ... } or array [ ... ]
            brace_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
            if brace_match:
                cleaned = brace_match.group(1).strip()

        try:
            parsed = json.loads(cleaned)
            return parsed, elapsed_ms
        except Exception as e:
            # --- Recovery path 1: Bracket/dot pseudo-tool syntax ---
            # e.g. [email(search_emails(query='...'))] or email.search_emails(query='...')
            m_pseudo = re.findall(r"(\w+)\s*[:\.\(]\s*(\w+)\s*\((.*?)\)", cleaned)
            if m_pseudo:
                steps = []
                for agent_n, act_n, param_str in m_pseudo:
                    p_dict = {}
                    param_pairs = re.findall(r"(\w+)\s*=\s*['\"]([^'\"]*)['\"]", param_str)
                    for pk, pv in param_pairs:
                        p_dict[pk] = pv
                    int_pairs = re.findall(r"(\w+)\s*=\s*(\d+)", param_str)
                    for ik, iv in int_pairs:
                        if ik not in p_dict:
                            p_dict[ik] = int(iv)
                    steps.append({"agent": agent_n, "action": act_n, "params": p_dict})
                if steps:
                    logger.info(f"[LLM] Recovered {len(steps)} plan steps from pseudo-tool bracket syntax.")
                    return {"plan_type": "parallel" if len(steps) == 1 else "sequential", "steps": steps}, elapsed_ms

            # --- Recovery path 2: OpenRouter XML-style <tool_call> syntax ---
            # e.g. <tool_call>web_search\n<arg_key>query</arg_key><arg_value>...</arg_value>...</tool_call>
            xml_calls = re.findall(r"<tool_call>(.*?)</tool_call>", cleaned, re.DOTALL)
            if not xml_calls:
                # Also handle unclosed tags (model truncated output)
                xml_calls = re.findall(r"<tool_call>(.*)", cleaned, re.DOTALL)
            if xml_calls:
                steps = []
                for call_body in xml_calls:
                    # First non-tag token is the tool/agent name
                    name_m = re.match(r"\s*([\w_]+)", call_body)
                    if not name_m:
                        continue
                    tool_name = name_m.group(1).strip()
                    # Extract key→value pairs from <arg_key>k</arg_key><arg_value>v</arg_value>
                    pairs = re.findall(r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", call_body, re.DOTALL)
                    params = {k.strip(): v.strip() for k, v in pairs}
                    # Map common OpenRouter tool names to agent:action pairs
                    tool_map = {
                        "web_search":   ("research", "web_search"),
                        "search_web":   ("research", "web_search"),
                        "quick_lookup": ("research", "quick_lookup"),
                        "search_emails":("email",    "search_emails"),
                        "play_music":   ("media",    "play_music"),
                        "get_weather":  ("research", "web_search"),
                    }
                    agent_n, action_n = tool_map.get(tool_name, ("research", tool_name))
                    steps.append({"agent": agent_n, "action": action_n, "params": params})
                if steps:
                    logger.info(f"[LLM] Recovered {len(steps)} plan steps from OpenRouter XML tool-call syntax.")
                    return {"plan_type": "parallel", "steps": steps}, elapsed_ms

            logger.error(f"[LLM] Failed to parse JSON from response: {cleaned[:200]}... Error: {e}")
            return {}, elapsed_ms
