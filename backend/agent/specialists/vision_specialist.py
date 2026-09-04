"""VESPER Vision & Optical Perception Specialist.

Provides multimodal perception:
- Webcam-first OCR: Transcribes books, documents, notes, or IDs held up to the webcam.
- Webcam-first Visual Reasoning (VLLM): Inspects objects, hand-held items, or surroundings.
- Screen Perception & OCR: Inspects active desktop monitors or IDE code/errors upon explicit request.
- Hardware & Edge Awareness: Probes host capabilities (Orange Pi / SBC / Headless / Desktop).
  Gracefully informs user if optical sensors or displays are missing without crashing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.vision.camera_stream import CameraCapture, ScreenCapture
from backend.vision.device_probe import DeviceProbe
from backend.vision.vllm import GroqVisionClient

logger = logging.getLogger("vesper.agent.specialists.vision")


class VisionSpecialist(BaseSpecialist):
    """Specialist agent responsible for optical camera vision, screen perception, and OCR."""

    def __init__(self, vision_client: Optional[GroqVisionClient] = None) -> None:
        self.vision_client = vision_client or GroqVisionClient()

    @property
    def name(self) -> str:
        return "vision"

    @property
    def description(self) -> str:
        return (
            "Specialist for visual perception, webcam inspection, webcam OCR, "
            "screen analysis, and optical environmental reasoning."
        )

    def get_capabilities(self) -> str:
        return (
            "Analyzes physical surroundings, hand-held objects, or documents via webcam (primary), "
            "performs OCR on held-up papers or screens, and inspects desktop monitors upon request."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "inspect_webcam",
                "description": (
                    "Captures an optical frame from the user's primary webcam to analyze what they are holding, "
                    "wearing, pointing at, or showing to Alfred (e.g. 'what am I holding?', 'inspect this book', 'look at my room')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Specific visual question or instruction for Alfred (e.g. 'What book is this?', 'Describe what I am holding').",
                        },
                        "camera_index": {
                            "type": "integer",
                            "description": "Camera device index (default 0 for primary webcam).",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "ocr_webcam",
                "description": (
                    "Extracts text, code, serial numbers, labels, or handwriting from a document, paper, card, "
                    "or book held up directly in front of the webcam."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "focus_hint": {
                            "type": "string",
                            "description": "Optional clue or specific section to focus OCR transcription on.",
                        },
                        "camera_index": {
                            "type": "integer",
                            "description": "Camera device index (default 0 for primary webcam).",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "inspect_screen",
                "description": (
                    "Captures the desktop screen or active monitor to inspect code, errors, layouts, or open browser windows "
                    "when the user explicitly asks about their screen or display."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Specific question about what is displayed on the screen (e.g. 'What error is in the terminal?').",
                        },
                        "monitor_index": {
                            "type": "integer",
                            "description": "Display monitor index (default 1 for primary monitor).",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "ocr_screen",
                "description": (
                    "Performs optical character recognition (OCR) directly on the desktop screen to extract code or text from windows."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "focus_hint": {
                            "type": "string",
                            "description": "Optional hint on which window, code snippet, or error message to focus on.",
                        },
                        "monitor_index": {
                            "type": "integer",
                            "description": "Display monitor index (default 1).",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_device_vision_status",
                "description": (
                    "Checks the host hardware profile, detecting if optical cameras, displays, or headless edge constraints exist."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        """Executes optical perception and OCR tools."""
        try:
            if action == "inspect_webcam":
                return await self._inspect_webcam(params)
            elif action == "ocr_webcam":
                return await self._ocr_webcam(params)
            elif action == "inspect_screen":
                return await self._inspect_screen(params)
            elif action == "ocr_screen":
                return await self._ocr_screen(params)
            elif action == "get_device_vision_status":
                return await self._get_device_vision_status()
            else:
                return SpecialistResult(
                    success=False,
                    action=action,
                    error=f"Unknown vision action: '{action}'",
                    speech_summary=f"Unknown optical action '{action}', sir.",
                )
        except Exception as e:
            logger.error(f"[VisionSpecialist] Execution failed for action '{action}': {e}", exc_info=True)
            return SpecialistResult(
                success=False,
                action=action,
                error=str(e),
                speech_summary=f"An optical perception error occurred: {str(e)}",
            )

    # ── Tool Implementations ──────────────────────────────────────────────

    async def _inspect_webcam(self, params: Dict[str, Any]) -> SpecialistResult:
        """Captures a frame from webcam and conducts multimodal VLLM reasoning."""
        query = params.get("query") or "Describe what the user is holding up or showing in the webcam."
        cam_idx = params.get("camera_index", 0)

        # 1. Device Hardware Probe Check
        caps = DeviceProbe.get_capabilities()
        if not caps.has_camera:
            butler_msg = DeviceProbe.format_missing_camera_butler_response(query)
            return SpecialistResult(
                success=False,
                action="inspect_webcam",
                speech_summary=butler_msg,
                card_payload={
                    "type": "HARDWARE_STATUS",
                    "device": caps.device_model,
                    "status": "NO_OPTICAL_SENSOR",
                    "details": "Optical camera not detected.",
                },
                data={"has_camera": False, "device_type": caps.device_type},
            )

        # 2. Acquire optical frame
        frame = CameraCapture.capture_frame(camera_index=cam_idx)
        if not frame.success:
            return SpecialistResult(
                success=False,
                action="inspect_webcam",
                speech_summary=f"I was unable to capture a frame from the optical sensor, sir: {frame.error}",
                error=frame.error,
                data={"source": "webcam"},
            )

        # 3. Multimodal VLLM analysis via Groq LPU
        analysis = await self.vision_client.analyze_image(
            image_base64=frame.image_base64,
            query=query,
            source="webcam",
        )

        if not analysis.success:
            return SpecialistResult(
                success=False,
                action="inspect_webcam",
                speech_summary=analysis.description,
                error=analysis.error,
                data={"source": "webcam"},
            )

        desc = analysis.description or ""
        desc_lower = desc.lower()

        # Confidence scoring for scene analysis:
        # Check if model expresses uncertainty, occlusion, or lack of visual clarity
        uncertain_patterns = [
            "unclear", "cannot clearly", "hard to see", "hard to tell", "blurry",
            "difficult to read", "difficult to identify", "unable to identify",
            "partially obscured", "cannot make out", "not clearly visible",
            "not enough detail", "could not determine", "low lighting", "too dark"
        ]
        hedged_patterns = [
            "appears to be", "might be", "possibly", "looks somewhat like",
            "seems to be", "could be", "resembles"
        ]

        if len(desc.strip()) < 15 or any(p in desc_lower for p in uncertain_patterns):
            confidence = "uncertain"
        elif any(p in desc_lower for p in hedged_patterns):
            confidence = "medium"
        else:
            confidence = "high"

        return SpecialistResult(
            success=True,
            action="inspect_webcam",
            speech_summary=analysis.description,
            data={
                "description": analysis.description,
                "confidence": confidence,
                "raw_ocr": "",
                "source": "webcam",
                "width": frame.width,
                "height": frame.height,
                "model_used": analysis.model_used,
            },
            card_payload={
                "type": "VISION_ANALYSIS",
                "title": "Webcam Visual Inspection",
                "description": analysis.description,
                "source": "webcam",
                "confidence": confidence,
            },
        )

    async def _ocr_webcam(self, params: Dict[str, Any]) -> SpecialistResult:
        """Captures frame from webcam and transcribes text/code/labels via OCR."""
        focus_hint = params.get("focus_hint", "")
        cam_idx = params.get("camera_index", 0)

        caps = DeviceProbe.get_capabilities()
        if not caps.has_camera:
            butler_msg = DeviceProbe.format_missing_camera_butler_response()
            return SpecialistResult(
                success=False,
                action="ocr_webcam",
                speech_summary=butler_msg,
                card_payload={
                    "type": "HARDWARE_STATUS",
                    "device": caps.device_model,
                    "status": "NO_OPTICAL_SENSOR",
                },
                data={"has_camera": False},
            )

        frame = CameraCapture.capture_frame(camera_index=cam_idx)
        if not frame.success:
            return SpecialistResult(
                success=False,
                action="ocr_webcam",
                speech_summary=f"I could not capture a frame from the webcam for OCR, sir: {frame.error}",
                error=frame.error,
                data={"source": "webcam"},
            )

        ocr_result = await self.vision_client.ocr_image(
            image_base64=frame.image_base64,
            focus_hint=focus_hint,
            source="webcam",
        )

        if not ocr_result.success:
            return SpecialistResult(
                success=False,
                action="ocr_webcam",
                speech_summary=ocr_result.description,
                error=ocr_result.error,
                data={"source": "webcam"},
            )

        text = ocr_result.extracted_text or ocr_result.description
        speech = "Here is the transcription of what you are holding, sir." if len(text) > 40 else text

        # Confidence scoring: based on how much legible text was extracted.
        # "high"     → ≥15 chars of text (enough for a title/label search)
        # "medium"   → 5-14 chars (partial read, may still be useful)
        # "uncertain" → <5 chars or empty (cover not readable, ask user to reposition)
        stripped = text.strip()
        if len(stripped) >= 15:
            confidence = "high"
        elif len(stripped) >= 5:
            confidence = "medium"
        else:
            confidence = "uncertain"

        return SpecialistResult(
            success=True,
            action="ocr_webcam",
            speech_summary=speech,
            data={
                "extracted_text": text,
                "raw_ocr": text,           # direct OCR output, unmodified
                "confidence": confidence,  # high / medium / uncertain
                "source": "webcam",
                "width": frame.width,
                "height": frame.height,
            },
            card_payload={
                "type": "OCR_TRANSCRIPTION",
                "title": "Webcam Optical OCR",
                "text": text,
                "confidence": confidence,
                "source": "webcam",
            },
        )


    async def _inspect_screen(self, params: Dict[str, Any]) -> SpecialistResult:
        """Captures desktop monitor frame and conducts multimodal visual reasoning."""
        query = params.get("query") or "Describe the contents and windows currently visible on this desktop screen."
        mon_idx = params.get("monitor_index", 1)

        caps = DeviceProbe.get_capabilities()
        if caps.is_headless or not caps.has_display:
            return SpecialistResult(
                success=False,
                action="inspect_screen",
                speech_summary=f"This unit ({caps.device_model}) is running in headless mode without an active desktop display server, sir.",
                data={"is_headless": True},
            )

        frame = ScreenCapture.capture_screen(monitor_index=mon_idx)
        if not frame.success:
            return SpecialistResult(
                success=False,
                action="inspect_screen",
                speech_summary=f"I was unable to capture the desktop screen, sir: {frame.error}",
                error=frame.error,
                data={"source": "screen"},
            )

        analysis = await self.vision_client.analyze_image(
            image_base64=frame.image_base64,
            query=query,
            source="screen",
            system_instruction=(
                "You are Alfred, inspecting the user's desktop display. "
                "Analyze windows, code editors, terminals, browsers, errors, or system alerts with precision. "
                "Highlight relevant lines of code, buttons, or dialog boxes."
            ),
        )

        if not analysis.success:
            return SpecialistResult(
                success=False,
                action="inspect_screen",
                speech_summary=analysis.description,
                error=analysis.error,
                data={"source": "screen"},
            )

        desc = analysis.description or ""
        desc_lower = desc.lower()
        if len(desc.strip()) < 15 or any(p in desc_lower for p in ["unclear", "blurry", "cannot clearly", "hard to read", "unable to identify"]):
            confidence = "uncertain"
        elif any(p in desc_lower for p in ["appears to be", "might be", "possibly"]):
            confidence = "medium"
        else:
            confidence = "high"

        return SpecialistResult(
            success=True,
            action="inspect_screen",
            speech_summary=analysis.description,
            data={
                "description": analysis.description,
                "confidence": confidence,
                "raw_ocr": "",
                "source": "screen",
                "width": frame.width,
                "height": frame.height,
                "model_used": analysis.model_used,
            },
            card_payload={
                "type": "VISION_ANALYSIS",
                "title": "Desktop Screen Inspection",
                "description": analysis.description,
                "source": "screen",
                "confidence": confidence,
            },
        )

    async def _ocr_screen(self, params: Dict[str, Any]) -> SpecialistResult:
        """Captures desktop screen and performs OCR."""
        focus_hint = params.get("focus_hint", "")
        mon_idx = params.get("monitor_index", 1)

        caps = DeviceProbe.get_capabilities()
        if caps.is_headless or not caps.has_display:
            return SpecialistResult(
                success=False,
                action="ocr_screen",
                speech_summary=f"This unit ({caps.device_model}) is running in headless mode with no display to transcribe, sir.",
                data={"is_headless": True},
            )

        frame = ScreenCapture.capture_screen(monitor_index=mon_idx)
        if not frame.success:
            return SpecialistResult(
                success=False,
                action="ocr_screen",
                speech_summary=f"I could not capture the desktop screen for OCR, sir: {frame.error}",
                error=frame.error,
                data={"source": "screen"},
            )

        ocr_result = await self.vision_client.ocr_image(
            image_base64=frame.image_base64,
            focus_hint=focus_hint,
            source="screen",
        )

        if not ocr_result.success:
            return SpecialistResult(
                success=False,
                action="ocr_screen",
                speech_summary=ocr_result.description,
                error=ocr_result.error,
                data={"source": "screen"},
            )

        text = ocr_result.extracted_text or ocr_result.description
        speech = "I have transcribed the text visible on your display, sir." if len(text) > 40 else text

        stripped = text.strip()
        if len(stripped) >= 15:
            confidence = "high"
        elif len(stripped) >= 5:
            confidence = "medium"
        else:
            confidence = "uncertain"

        return SpecialistResult(
            success=True,
            action="ocr_screen",
            speech_summary=speech,
            data={
                "extracted_text": text,
                "raw_ocr": text,
                "confidence": confidence,
                "source": "screen",
                "width": frame.width,
                "height": frame.height,
            },
            card_payload={
                "type": "OCR_TRANSCRIPTION",
                "title": "Desktop Screen OCR",
                "text": text,
                "source": "screen",
            },
        )

    async def _get_device_vision_status(self) -> SpecialistResult:
        """Reports sensory hardware status."""
        caps = DeviceProbe.get_capabilities(force_refresh=True)
        summary = (
            f"Host device: {caps.device_model} ({caps.device_type}). "
            f"Optical cameras: {'Available (' + str(caps.available_cameras) + ')' if caps.has_camera else 'Not detected'}. "
            f"Display server: {'Active' if caps.has_display else 'Headless'}."
        )
        return SpecialistResult(
            success=True,
            action="get_device_vision_status",
            speech_summary=summary,
            data=caps.model_dump(),
            card_payload={
                "type": "DEVICE_CAPABILITIES",
                "device_type": caps.device_type,
                "device_model": caps.device_model,
                "has_camera": caps.has_camera,
                "has_display": caps.has_display,
                "is_headless": caps.is_headless,
            },
        )
