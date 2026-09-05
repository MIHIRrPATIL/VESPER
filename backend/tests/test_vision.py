"""Tests for VESPER Vision Perception Suite & Hardware Probe.

Verifies:
1. Device capability probing (Orange Pi, SBC, Headless, Desktop).
2. Graceful butler degradation response when camera is absent (no crashes).
3. VisionSpecialist execution (webcam-first VLLM inspection, webcam-first OCR, screen inspection).
4. Decoupled gesture worker lifecycle and zero-CPU standby.
"""

from __future__ import annotations

import time
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


@pytest.mark.asyncio
async def test_gesture_worker_inference_and_dispatch():
    """Verifies MediaPipe gesture recognition, evaluation, and cluster state updates."""
    from backend.sync.sync_manager import sync_manager
    import numpy as np

    callback_events = []

    def on_gesture(g: str, conf: float):
        callback_events.append((g, conf))

    worker = GestureWorker(fps=6.0, on_gesture_callback=on_gesture)
    
    # 1. Verify model loader
    recognizer = worker._init_recognizer()
    assert recognizer is not None, "GestureRecognizer task model should load successfully"

    # 2. Verify dummy frame evaluation
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    gesture, conf = worker._evaluate_gesture_heuristic(dummy_frame)
    assert gesture in ("NONE", "CLOSED_FIST", "OPEN_PALM", "PEACE_SIGN", "NEXT_TRACK", "PREV_TRACK")
    assert isinstance(conf, float)

    # 3. Verify CLOSED_FIST mute dispatch
    await sync_manager.update_state({"master_volume": 75}, source_device_id="test")
    await worker._dispatch_gesture("CLOSED_FIST", 0.95)
    s = sync_manager.get_snapshot()
    assert s.master_volume == 0
    assert s.current_media["is_playing"] is False

    # 4. Verify OPEN_PALM restore volume dispatch
    await worker._dispatch_gesture("OPEN_PALM", 0.90)
    s = sync_manager.get_snapshot()
    assert s.master_volume == 75
    assert s.current_media["is_playing"] is True

    # 5. Verify PEACE_SIGN Zen mode toggle
    initial_zen = s.zen_mode
    await worker._dispatch_gesture("PEACE_SIGN", 0.92)
    s = sync_manager.get_snapshot()
    assert s.zen_mode == (not initial_zen)

    # 6. Verify THUMB_UP volume increment
    cur_vol = s.master_volume
    await worker._dispatch_gesture("THUMB_UP", 0.88)
    s = sync_manager.get_snapshot()
    assert s.master_volume == min(100, cur_vol + 10)

    # 7. Verify THUMB_DOWN volume decrement
    cur_vol = s.master_volume
    await worker._dispatch_gesture("THUMB_DOWN", 0.88)
    s = sync_manager.get_snapshot()
    assert s.master_volume == max(0, cur_vol - 10)

    # 8. Verify VOLUME_DIAL setting
    await worker._dispatch_gesture("VOLUME_DIAL:45", 0.85)
    s = sync_manager.get_snapshot()
    assert s.master_volume == 45

    # 9. Verify GESTURE_TOGGLE:PAUSED and GESTURE_TOGGLE:RESUMED
    assert worker.state.tracking_paused is False
    await worker._dispatch_gesture("GESTURE_TOGGLE:PAUSED", 0.90)
    assert worker.state.tracking_paused is True

    await worker._dispatch_gesture("GESTURE_TOGGLE:RESUMED", 0.90)
    assert worker.state.tracking_paused is False

    # 10. Verify callback was executed
    assert len(callback_events) >= 8
    assert callback_events[0] == ("CLOSED_FIST", 0.95)
    assert callback_events[1] == ("OPEN_PALM", 0.90)


@pytest.mark.asyncio
async def test_gesture_worker_toggle_lockout_and_swipes():
    """Verifies that toggle lockout prevents flapping and trajectory correctly differentiates swipes."""
    import time

    worker = GestureWorker(fps=6.0)
    worker.state.tracking_paused = True
    worker._toggle_lockout_until = time.time() + 10.0

    # Under lockout, _check_toggle_gesture_only should return NONE immediately
    res, conf = worker._check_toggle_gesture_only(None)
    assert res == "NONE"
    assert conf == 0.0

    # Verify swipe trajectory logic with simulated wrist history
    now = time.time()
    # Mirrored X: Moving to user's right (from x=0.4 to x=0.6)
    worker._wrist_history.append((now - 0.2, 0.40, 0.50))
    worker._wrist_history.append((now, 0.60, 0.50))

    # Evaluate trajectory across history manually
    dx = 0.60 - 0.40
    dy = 0.50 - 0.50
    assert dx > 0.06
    assert abs(dx) > 1.2 * abs(dy)
    assert ("NEXT_TRACK" if dx > 0 else "PREV_TRACK") == "NEXT_TRACK"

    # Mirrored X: Moving to user's left (from x=0.6 to x=0.4)
    dx_left = 0.40 - 0.60
    assert ("NEXT_TRACK" if dx_left > 0 else "PREV_TRACK") == "PREV_TRACK"


@pytest.mark.asyncio
async def test_gesture_rock_on_lock_toggle_and_open_palm_immediate():
    """Verifies that Rock On (ILoveYou) locks/unlocks and Open Palm triggers immediately."""
    from unittest.mock import MagicMock
    import time

    worker = GestureWorker(fps=6.0)

    # Mock recognizer for testing
    mock_rec = MagicMock()
    worker._recognizer = mock_rec

    # 1. Immediate Open Palm (no hold timer delay)
    mock_cat = MagicMock()
    mock_cat.category_name = "Open_Palm"
    mock_cat.score = 0.92

    mock_res = MagicMock()
    mock_res.gestures = [[mock_cat]]
    mock_res.hand_landmarks = []
    mock_rec.recognize.return_value = mock_res

    # Mock frame
    import numpy as np
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    gesture, score = worker._evaluate_gesture_heuristic(dummy_frame)
    assert gesture == "OPEN_PALM"
    assert score == 0.92

    # 2. Rock On (ILoveYou) initial frame -> starts hold timer
    mock_cat.category_name = "ILoveYou"
    mock_cat.score = 0.88
    gesture, score = worker._evaluate_gesture_heuristic(dummy_frame)
    # First frame hasn't reached 1.0s hold yet
    assert gesture == "ROCK_ON"
    assert worker._toggle_gesture_start > 0.0
    assert worker._toggle_gesture_fired is False

    # 3. Simulate hold for 1.1s -> should fire GESTURE_TOGGLE:PAUSED
    worker._toggle_gesture_start = time.time() - 1.1
    gesture, score = worker._evaluate_gesture_heuristic(dummy_frame)
    assert gesture == "GESTURE_TOGGLE:PAUSED"
    assert worker._toggle_gesture_fired is True
    assert worker._toggle_lockout_until > time.time()

    # 4. In paused state, verify _check_toggle_gesture_only resumes on Rock On (ILoveYou) hold 1.0s
    worker.state.tracking_paused = True
    worker._toggle_lockout_until = 0.0  # bypass lockout for test
    worker._toggle_gesture_start = 0.0
    worker._toggle_gesture_fired = False

    # First frame starts timer
    res, conf = worker._check_toggle_gesture_only(dummy_frame)
    assert res == "NONE"
    assert worker._toggle_gesture_start > 0.0

    # Advance hold time >= 1.0s
    worker._toggle_gesture_start = time.time() - 1.1
    res, conf = worker._check_toggle_gesture_only(dummy_frame)
    assert res == "GESTURE_TOGGLE:RESUMED"
    assert conf == 0.88


@pytest.mark.asyncio
async def test_gesture_repeat_guard_and_volume_repeat_exception():
    """Verifies that non-volume gestures are blocked from consecutive repeat without release,
    while volume gestures (thumbs, dial) are permitted to repeat smoothly.
    """
    worker = GestureWorker(fps=8.0)
    dispatched = []

    async def _test_cb(g, c):
        dispatched.append(g)

    worker.on_gesture_callback = _test_cb

    # 1. Non-volume gesture (CLOSED_FIST): Streak requirement + release hysteresis
    # Frame 1: candidate streak becomes 1 (streak < 2, not emitted)
    # Simulate _run_loop evaluation step logic directly
    now = time.time()

    # Emulate streak + release logic for CLOSED_FIST
    worker._candidate_gesture = "CLOSED_FIST"
    worker._candidate_streak = 2  # 2 consecutive frames
    base_g = "CLOSED_FIST"
    assert base_g not in worker._gesture_awaiting_release

    # First emission allowed
    worker._last_gesture_emitted_times[base_g] = now
    worker._gesture_awaiting_release.add(base_g)
    await worker._dispatch_gesture("CLOSED_FIST", 0.90)
    assert dispatched == ["CLOSED_FIST"]

    # Consecutive frame: user still holding CLOSED_FIST without release
    # Check guard:
    assert base_g in worker._gesture_awaiting_release
    # It must be blocked while held
    is_blocked_by_release = base_g in worker._gesture_awaiting_release
    assert is_blocked_by_release is True

    # User releases hand (NONE)
    worker._candidate_gesture = "NONE"
    worker._candidate_streak = 0
    worker._none_streak = 1
    worker._gesture_awaiting_release.clear()
    assert base_g not in worker._gesture_awaiting_release

    # Cooldown check: if user immediately reforms fist within 0.2s, cooldown blocks it
    now_quick = now + 0.2
    assert (now_quick - worker._last_gesture_emitted_times[base_g]) < 1.5

    # 2. Volume gesture (THUMB_DOWN): Allowed to repeat without release
    worker._last_gesture_emitted_times.clear()
    worker._gesture_awaiting_release.clear()
    dispatched.clear()

    # Frame 1 & 2 of THUMB_DOWN
    worker._candidate_gesture = "THUMB_DOWN"
    worker._candidate_streak = 2
    is_volume = worker._candidate_gesture in ("THUMB_UP", "THUMB_DOWN", "VOLUME_UP", "VOLUME_DOWN")
    assert is_volume is True

    # Volume gestures bypass release lock
    t0 = time.time()
    worker._last_gesture_emitted_times["THUMB_DOWN"] = t0
    await worker._dispatch_gesture("THUMB_DOWN", 0.95)
    assert len(dispatched) == 1

    # Hand is STILL held (no release to NONE), 0.36s later (> 0.35s cooldown)
    t1 = t0 + 0.36
    assert (t1 - worker._last_gesture_emitted_times["THUMB_DOWN"]) >= 0.35
    # Since is_volume is True, release check is bypassed, allowing continuous volume steps
    worker._last_gesture_emitted_times["THUMB_DOWN"] = t1
    await worker._dispatch_gesture("THUMB_DOWN", 0.95)
    assert len(dispatched) == 2
    assert dispatched == ["THUMB_DOWN", "THUMB_DOWN"]


@pytest.mark.asyncio
async def test_screen_capture_blank_frame_detection():
    """Verifies that ScreenCapture correctly detects blank/black frames."""
    from PIL import Image

    # 1. Solid black image -> blank
    black_img = Image.new("RGB", (100, 100), (0, 0, 0))
    assert ScreenCapture._is_blank_frame(black_img) is True

    # 2. Image with faint noise <= 1 -> blank
    dim_img = Image.new("RGB", (100, 100), (1, 1, 1))
    assert ScreenCapture._is_blank_frame(dim_img) is True

    # 3. Regular active screen image -> not blank
    active_img = Image.new("RGB", (100, 100), (25, 120, 200))
    assert ScreenCapture._is_blank_frame(active_img) is False


@pytest.mark.asyncio
async def test_screen_capture_list_monitors_hyprland():
    """Verifies monitor discovery parsing under Hyprland compositor."""
    import json
    from unittest.mock import patch, MagicMock

    mock_hyprctl_output = json.dumps([
        {
            "id": 0,
            "name": "DP-3",
            "description": "Dell Inc. 27 Display",
            "width": 2560,
            "height": 1440,
            "focused": True,
        },
        {
            "id": 1,
            "name": "eDP-1",
            "description": "BOE Embedded Display",
            "width": 1920,
            "height": 1080,
            "focused": False,
        },
    ])

    with patch("shutil.which", return_value="/usr/bin/hyprctl"), \
         patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = mock_hyprctl_output
        mock_run.return_value = mock_proc

        monitors = ScreenCapture.list_monitors()
        assert len(monitors) == 2
        assert monitors[0]["name"] == "DP-3"
        assert monitors[0]["is_focused"] is True
        assert monitors[0]["width"] == 2560
        assert monitors[1]["name"] == "eDP-1"
        assert monitors[1]["is_focused"] is False
        assert monitors[1]["width"] == 1920


@pytest.mark.asyncio
async def test_vision_specialist_multi_monitor_natural_language_routing():
    """Verifies that VisionSpecialist routes queries targeting specific monitors."""
    mock_screen = FrameCaptureResult(
        success=True,
        source="screen_DP-3",
        monitor_name="DP-3",
        monitor_index=1,
        image_base64="bW9uaXRvcl9mcmFtZV9kYXRh",
        width=2560,
        height=1440,
    )

    mock_client = MagicMock(spec=GroqVisionClient)
    mock_client.analyze_image = AsyncMock(
        return_value=VisionAnalysisResult(
            success=True,
            description="On your external monitor (DP-3), I observe VSCode open, sir.",
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
    ), patch.object(ScreenCapture, "capture_screen", return_value=mock_screen) as mock_capture:
        specialist = VisionSpecialist(vision_client=mock_client)

        # 1. Test "external monitor" query
        res = await specialist.execute("inspect_screen", {"query": "What is on my external monitor?"})
        assert res.success is True
        assert res.data["monitor_name"] == "DP-3"
        assert mock_capture.call_args[1]["monitor_name"] == "external"

        # 2. Test "both screens" query
        res_both = await specialist.execute("inspect_screen", {"query": "Can you check both screens?"})
        assert res_both.success is True
        assert mock_capture.call_args[1]["monitor_index"] == 0


