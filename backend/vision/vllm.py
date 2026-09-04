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

from backend.shared.config import GROQ_API_KEY, OPENROUTER_API_KEY

logger = logging.getLogger("vesper.vision.vllm")

# Primary Vision Models
DEFAULT_VISION_MODEL = "google/gemini-2.5-flash"
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
    """Dispatches multimodal image reasoning and OCR requests to Groq LPUs or OpenRouter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        openrouter_key: Optional[str] = None,
        model: str = DEFAULT_VISION_MODEL,
    ) -> None:
        self.api_key = api_key or GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
        self.openrouter_key = openrouter_key or OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model

    async def analyze_image(
        self,
        image_base64: str,
        query: str = "Describe what you see in this image in detail.",
        source: str = "webcam",
        system_instruction: Optional[str] = None,
    ) -> VisionAnalysisResult:
        """Sends an image and visual inquiry to OpenRouter multimodal vision or Groq fallback."""
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

        # 1. Primary: OpenRouter Multimodal Vision (Google Gemini 2.5 Flash)
        # Note: Groq decommissioned llama-3.2-11b/90b-vision-preview, so OpenRouter is primary.
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
                        logger.warning(f"[GroqVisionClient] OpenRouter returned {or_res.status_code}. Attempting Groq.")
            except Exception as or_err:
                logger.warning(f"[GroqVisionClient] OpenRouter failed: {or_err}. Attempting Groq.")

        # 2. Secondary: Groq LPU if active vision model is available
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
            except Exception as e:
                logger.warning(f"[GroqVisionClient] Groq vision request failed: {e}")

        return VisionAnalysisResult(
            success=False,
            description="Neither OPENROUTER_API_KEY nor an active GROQ vision model is available, sir.",
            error="No working vision API key found.",
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
