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

from backend.shared.config import GROQ_API_KEY

logger = logging.getLogger("vesper.vision.vllm")

# Primary Groq Multimodal Vision Model
DEFAULT_VISION_MODEL = "llama-3.2-11b-vision-preview"
FALLBACK_VISION_MODEL = "meta-llama/llama-3.2-11b-vision-instruct"


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
    """Dispatches multimodal image reasoning and OCR requests to Groq LPUs."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_VISION_MODEL) -> None:
        self.api_key = api_key or GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
        self.model = model

    async def analyze_image(
        self,
        image_base64: str,
        query: str = "Describe what you see in this image in detail.",
        source: str = "webcam",
        system_instruction: Optional[str] = None,
    ) -> VisionAnalysisResult:
        """Sends an image and visual inquiry to the Groq Multimodal LPU."""
        if not self.api_key:
            logger.warning("[GroqVisionClient] No GROQ_API_KEY found.")
            return VisionAnalysisResult(
                success=False,
                description="Vision perception requires a GROQ_API_KEY configured for free LPU multimodal inference, sir.",
                error="GROQ_API_KEY is not set.",
                source=source,
            )

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

        # Note: Groq Jinja template requirement: Must include a user message with the query & image!
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        image_data_url = f"data:image/jpeg;base64,{image_base64}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": sys_prompt,
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url},
                        },
                    ],
                },
            ],
            "temperature": 0.2,
            "max_tokens": 800,
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
                    err_text = res.text
                    logger.error(f"[GroqVisionClient] API error {res.status_code}: {err_text}")
                    return VisionAnalysisResult(
                        success=False,
                        description=f"Optical reasoning encountered an issue (HTTP {res.status_code}), sir.",
                        error=err_text,
                        source=source,
                    )
        except Exception as e:
            logger.error(f"[GroqVisionClient] Network request failed: {e}", exc_info=True)
            return VisionAnalysisResult(
                success=False,
                description=f"Failed to communicate with the optical vision reasoning cluster: {str(e)}",
                error=str(e),
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
