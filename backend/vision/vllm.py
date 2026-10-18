"""VESPER Multimodal Vision & OCR Engine.

Leverages Groq's ultra-fast LPU Vision models (e.g., `llama-3.2-11b-vision-preview`)
to perform real-time visual reasoning, object detection, and high-accuracy OCR
on frames captured from the webcam or screen.

Maintains a 100% free operational cost.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel

from backend.shared.config import GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY

logger = logging.getLogger("vesper.vision.vllm")

# Primary Vision Models
DEFAULT_VISION_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK_VISION_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
OPENROUTER_VISION_MODEL = "google/gemini-2.5-flash"
GROQ_DECOMMISSIONED_VISION_MODELS = {"llama-3.2-11b-vision-preview", "llama-3.2-90b-vision-preview"}


class VisionAnalysisResult(BaseModel):
    """Structured response from the Multimodal Vision engine."""

    success: bool = True
    description: str = ""
    extracted_text: Optional[str] = None
    detected_objects: list[str] = []
    source: str = "webcam"
    model_used: str = DEFAULT_VISION_MODEL
    error: Optional[str] = None


class GroqVisionClient:
    """Dispatches multimodal image reasoning and OCR requests to Google Gemini, OpenRouter, or Groq."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        openrouter_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
        model: str = DEFAULT_VISION_MODEL,
    ) -> None:
        self.api_key = api_key or GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
        self.openrouter_key = openrouter_key or OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
        self.gemini_key = gemini_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.model = model

    async def analyze_image(
        self,
        image_base64: str,
        query: str = "Describe what you see in this image in detail.",
        source: str = "webcam",
        system_instruction: Optional[str] = None,
    ) -> VisionAnalysisResult:
        """Sends an image and visual inquiry to Google Gemini, OpenRouter, or Groq fallback."""
        if not image_base64:
            return VisionAnalysisResult(
                success=False,
                description="No optical frame data was provided for visual inspection, sir.",
                error="Empty image base64 provided.",
                source=source,
            )

        default_sys = (
            "You are Alfred, the sophisticated, perceptive butler and visual perception engine of VESPER. "
            "Analyze the provided image with high precision, observing objects, text, physical orientation, "
            "and environmental details. Be concise, articulate, and direct."
        )
        sys_prompt = system_instruction or default_sys
        image_data_url = f"data:image/jpeg;base64,{image_base64}"

        gemini_errors: list[str] = []
        openrouter_error: Optional[str] = None
        groq_error: Optional[str] = None

        # 1. Primary: Direct Google Gemini (Zero-Latency, 1M context, Native Multimodal)
        if self.gemini_key:
            candidate_models = [self.model] if self.model in GEMINI_FALLBACK_VISION_MODELS else []
            for m in GEMINI_FALLBACK_VISION_MODELS:
                if m not in candidate_models:
                    candidate_models.append(m)

            for gem_model in candidate_models:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                        res = await client.post(
                            gemini_url,
                            headers={
                                "Authorization": f"Bearer {self.gemini_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": gem_model,
                                "messages": [
                                    {"role": "system", "content": sys_prompt},
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": query},
                                            {"type": "image_url", "image_url": {"url": image_data_url}},
                                        ],
                                    },
                                ],
                                "max_tokens": 600,
                            },
                        )
                        if res.status_code == 200:
                            data = res.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            return VisionAnalysisResult(
                                success=True,
                                description=content,
                                source=source,
                                model_used=gem_model,
                            )
                        else:
                            gemini_errors.append(f"{gem_model} (status {res.status_code})")
                            logger.warning(
                                f"[GroqVisionClient] Gemini {gem_model} returned {res.status_code}: {res.text}. Trying fallback."
                            )
                except Exception as gem_err:
                    gemini_errors.append(f"{gem_model} error: {gem_err}")
                    logger.warning(f"[GroqVisionClient] Gemini {gem_model} call failed: {gem_err}. Trying fallback.")

        # 2. Secondary: OpenRouter Multimodal Vision (Google Gemini 2.5 Flash)
        if self.openrouter_key:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    or_res = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openrouter_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": OPENROUTER_VISION_MODEL,
                            "messages": [
                                {"role": "system", "content": sys_prompt},
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": query},
                                        {"type": "image_url", "image_url": {"url": image_data_url}},
                                    ],
                                },
                            ],
                            "max_tokens": 400,
                        },
                    )
                    if or_res.status_code == 200:
                        data = or_res.json()
                        content = data["choices"][0]["message"]["content"].strip()
                        return VisionAnalysisResult(
                            success=True,
                            description=content,
                            source=source,
                            model_used=OPENROUTER_VISION_MODEL,
                        )
                    else:
                        openrouter_error = f"OpenRouter returned status {or_res.status_code}"
                        logger.warning(f"[GroqVisionClient] OpenRouter returned {or_res.status_code}. Attempting Groq.")
            except Exception as or_err:
                openrouter_error = f"OpenRouter error: {or_err}"
                logger.warning(f"[GroqVisionClient] OpenRouter failed: {or_err}. Attempting Groq.")

        # 3. Tertiary: Groq LPU if active vision model is available
        if self.api_key and self.model not in GROQ_DECOMMISSIONED_VISION_MODELS:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": query},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    },
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            }

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                    if res.status_code == 200:
                        data = res.json()
                        content = data["choices"][0]["message"]["content"].strip()
                        return VisionAnalysisResult(
                            success=True,
                            description=content,
                            source=source,
                            model_used=self.model,
                        )
                    else:
                        groq_error = f"Groq returned status {res.status_code}"
            except Exception as e:
                groq_error = f"Groq request error: {e}"
                logger.warning(f"[GroqVisionClient] Groq vision request failed: {e}")

        # Assemble clear diagnostic message
        if not self.gemini_key and not self.openrouter_key and not self.api_key:
            err_msg = "No vision API keys configured."
            desc_msg = "No vision API keys (GEMINI_API_KEY, OPENROUTER_API_KEY, or GROQ_API_KEY) are configured, sir."
        else:
            failure_reasons = []
            if gemini_errors:
                failure_reasons.append(f"Gemini: {', '.join(gemini_errors)}")
            if openrouter_error:
                failure_reasons.append(openrouter_error)
            if groq_error:
                failure_reasons.append(groq_error)
            elif self.model in GROQ_DECOMMISSIONED_VISION_MODELS:
                failure_reasons.append(f"Groq vision model {self.model} was decommissioned")

            reasons_str = "; ".join(failure_reasons) if failure_reasons else "All vision endpoints failed to respond."
            err_msg = f"Vision provider failure: {reasons_str}"
            desc_msg = f"I was unable to complete the optical inspection: {reasons_str}, sir."

        return VisionAnalysisResult(
            success=False,
            description=desc_msg,
            error=err_msg,
            source=source,
        )

    async def ocr_image(
        self,
        image_base64: str,
        focus_hint: str = "",
        source: str = "webcam",
    ) -> VisionAnalysisResult:
        """Performs optical character recognition (OCR) on an image."""
        ocr_prompt = (
            "Perform rigorous Optical Character Recognition (OCR) on this image. "
            "Transcribe all visible text, headers, paragraphs, codes, labels, serial numbers, "
            "or handwritten notes verbatim. "
            "Preserve line breaks, indentations, and markdown formatting where appropriate. "
            "If code is present, enclose it in markdown code blocks. "
            "If no legible text is visible, respond with: 'No legible text detected in this frame.'"
        )
        if focus_hint:
            ocr_prompt += f" Please pay special attention to: {focus_hint}."

        result = await self.analyze_image(
            image_base64=image_base64,
            query=ocr_prompt,
            source=source,
            system_instruction=(
                "You are an ultra-precise OCR transcription specialist. "
                "Output the transcribed text faithfully without extraneous filler or meta-commentary."
            ),
        )

        if result.success:
            result.extracted_text = result.description
        return result
