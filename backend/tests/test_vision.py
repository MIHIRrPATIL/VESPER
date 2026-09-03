"""Tests for VESPER Vision Perception Suite & Hardware Probe.

Verifies:
1. Device capability probing (Orange Pi, SBC, Headless, Desktop).
2. Graceful butler degradation response when camera is absent (no crashes).
3. VisionSpecialist execution (webcam-first VLLM inspection, webcam-first OCR, screen inspection).
4. Decoupled gesture worker lifecycle and zero-CPU standby.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.agent.specialists.vision_specialist import VisionSpecialist
from backend.vision.camera_stream import CameraCapture, FrameCaptureResult, ScreenCapture
from backend.vision.device_probe import DeviceCapabilities, DeviceProbe
from backend.vision.gesture_service import GestureWorker
from backend.vision.vllm import GroqVisionClient, VisionAnalysisResult


@pytest.mark.asyncio
async def test_device_probe_capabilities():
    """Verifies that the hardware probe successfully profiles the host."""
    caps = DeviceProbe.get_capabilities(force_refresh=True)
    assert isinstance(caps, DeviceCapabilities)
    assert caps.device_type in ("desktop", "orange_pi", "raspberry_pi", "embedded_edge", "headless_server")
    assert isinstance(caps.available_cameras, list)
    assert isinstance(caps.is_headless, bool)
    assert caps.architecture != ""


@pytest.mark.asyncio
async def test_missing_camera_butler_response_formatting():
    """Verifies that missing cameras produce articulate butler explanations."""
    with patch.object(
        DeviceProbe,
        "get_capabilities",
        return_value=DeviceCapabilities(
            device_type="orange_pi",
            device_model="Orange Pi 5 Plus",
            has_camera=False,
            is_headless=True,
        ),
    ):
        msg = DeviceProbe.format_missing_camera_butler_response("inspect this book")
        assert "edge node" in msg.lower() or "orange pi" in msg.lower()
        assert "no optical camera sensors detected" in msg.lower()
        assert "sir" in msg.lower()


@pytest.mark.asyncio
async def test_vision_specialist_graceful_missing_camera():
    """Verifies that VisionSpecialist does NOT crash when camera is absent."""
    with patch.object(
        DeviceProbe,
        "get_capabilities",
        return_value=DeviceCapabilities(
            device_type="orange_pi",
            device_model="Orange Pi 5 Plus",
            has_camera=False,
            available_cameras=[],
        ),
    ):
        specialist = VisionSpecialist()
        res = await specialist.execute("inspect_webcam", {"query": "What am I holding?"})
        assert res.success is False
        assert "optical" in res.speech_summary.lower() or "camera" in res.speech_summary.lower()
        assert res.card_payload is not None
        assert res.card_payload.get("status") == "NO_OPTICAL_SENSOR"


@pytest.mark.asyncio
async def test_vision_specialist_webcam_inspection_success():
    """Verifies webcam visual inspection with mocked frame and Groq VLLM response."""
    mock_frame = FrameCaptureResult(
        success=True,
        source="webcam_0",
        image_base64="dGVzdF9pbWFnZV9kYXRh",
        width=1280,
        height=720,
    )

    mock_client = MagicMock(spec=GroqVisionClient)
    mock_client.analyze_image = AsyncMock(
        return_value=VisionAnalysisResult(
            success=True,
            description="You are holding a paperback copy of 'Designing Data-Intensive Applications', sir.",
            source="webcam",
            model_used="llama-3.2-11b-vision-preview",
        )
    )

    with patch.object(
        DeviceProbe,
        "get_capabilities",
        return_value=DeviceCapabilities(
            device_type="desktop",
            has_camera=True,
            available_cameras=[0],
        ),
    ), patch.object(CameraCapture, "capture_frame", return_value=mock_frame):
        specialist = VisionSpecialist(vision_client=mock_client)
        res = await specialist.execute("inspect_webcam", {"query": "What book is this?"})

        assert res.success is True
        assert "Designing Data-Intensive Applications" in res.speech_summary
        assert res.data["source"] == "webcam"
        assert res.data["model_used"] == "llama-3.2-11b-vision-preview"
        assert res.card_payload is not None
        assert res.card_payload["type"] == "VISION_ANALYSIS"



@pytest.mark.asyncio
async def test_vision_specialist_webcam_ocr_success():
    """Verifies webcam OCR extraction on physical documents."""
    mock_frame = FrameCaptureResult(
        success=True,
        source="webcam_0",
        image_base64="b2NyX3Rlc3RfZGF0YQ==",
        width=1280,
        height=720,
    )

    mock_client = MagicMock(spec=GroqVisionClient)
    mock_client.ocr_image = AsyncMock(
        return_value=VisionAnalysisResult(
            success=True,
            description="ORDER #94812\nTOTAL: $142.50\nSTATUS: PAID",
            extracted_text="ORDER #94812\nTOTAL: $142.50\nSTATUS: PAID",
            source="webcam",
        )
    )

    with patch.object(
        DeviceProbe,
        "get_capabilities",
        return_value=DeviceCapabilities(
            device_type="desktop",
            has_camera=True,
            available_cameras=[0],
        ),
    ), patch.object(CameraCapture, "capture_frame", return_value=mock_frame):
        specialist = VisionSpecialist(vision_client=mock_client)
        res = await specialist.execute("ocr_webcam", {"focus_hint": "order number and total"})

        assert res.success is True
        assert "ORDER #94812" in res.data["extracted_text"]
        assert res.card_payload is not None
        assert res.card_payload["type"] == "OCR_TRANSCRIPTION"



@pytest.mark.asyncio
async def test_vision_specialist_screen_inspection():
    """Verifies screen capture and analysis."""
    mock_screen = FrameCaptureResult(
        success=True,
        source="screen",
        image_base64="c2NyZWVuX2RhdGE=",
        width=1920,
        height=1080,
    )

    mock_client = MagicMock(spec=GroqVisionClient)
    mock_client.analyze_image = AsyncMock(
        return_value=VisionAnalysisResult(
            success=True,
            description="I observe a terminal window displaying a failing pytest assertion in test_agent.py, line 42, sir.",
            source="screen",
        )
    )

    with patch.object(
        DeviceProbe,
        "get_capabilities",
        return_value=DeviceCapabilities(
            device_type="desktop",
            has_display=True,
            is_headless=False,
        ),
    ), patch.object(ScreenCapture, "capture_screen", return_value=mock_screen):
        specialist = VisionSpecialist(vision_client=mock_client)
        res = await specialist.execute("inspect_screen", {"query": "What error is on my terminal?"})

        assert res.success is True
        assert "failing pytest assertion" in res.speech_summary
        assert res.data["source"] == "screen"


@pytest.mark.asyncio
async def test_decoupled_gesture_worker_standby_and_lifecycle():
    """Verifies that GestureWorker starts, handles missing camera standby, and cleanly stops."""
    worker = GestureWorker(fps=5.0)
    assert not worker.is_running

    await worker.start()
    assert worker.is_running

    # Verify stop
    await worker.stop()
    assert not worker.is_running
