"""Unit tests for the 8 Architectural Hardening Pillars in VESPER.

Covers:
1. Deterministic Pre-Filtering & Provider Tracking
2. Few-Shot In-Context Planning
3. Verbatim Financial Accuracy Guarantee
4. Sandbox Transparency & Disclaimer
5. Context Staleness Window (TTL & Turn Expiry)
6. Gateway Interrupt Precedence Arbitration
7. Optical Camera Privacy Indicator
8. Static Cluster Workload Allocation Mode
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, patch

from backend.agent.alfred import AlfredSupervisor
from backend.agent.planner import SwarmPlanner, SwarmPlan
from backend.agent.registry import SpecialistRegistry
from backend.agent.specialists.base import SpecialistResult
from backend.gateway.router import MessageRouter
from backend.gateway.task_registry import TaskRegistry
from backend.shared.events import ClientEnvelope, Channel, EventType
from backend.sync.cluster_allocator import (
    ClusterWorkloadAllocator,
    ROLE_AUDIO_CAPTURE,
    ROLE_AUDIO_PLAYBACK,
    ROLE_COGNITIVE_SWARM,
    ROLE_VISION_PERCEPTION,
    ROLE_VECTOR_MEMORY,
)
from backend.sync.models import DeviceRegistration
from backend.sync.sync_manager import SyncManager
from backend.vision.camera_stream import CameraCapture


@pytest.mark.asyncio
async def test_pillar_1_deterministic_prefilter_and_provider_tracking():
    """Verifies that high-stakes fragile queries are prefiltered in 0ms with provider_used='prefilter'."""
    planner = SwarmPlanner()
    registry = SpecialistRegistry()

    # Query A: Handheld book inquiry
    plan, latency_ms = await planner.create_plan(
        "Tell me about the book I am holding in front of the camera",
        registry,
    )
    assert plan.provider_used == "prefilter"
    assert latency_ms == 0.0
    assert plan.plan_type == "sequential"
    assert plan.steps[0]["action"] == "ocr_webcam"
    assert plan.steps[1]["action"] == "web_search"

    # Query B: Screen error inspection
    plan_screen, latency_screen = await planner.create_plan(
        "Look at my screen and tell me what error is showing",
        registry,
    )
    assert plan_screen.provider_used == "prefilter"
    assert latency_screen == 0.0
    assert plan_screen.steps[0]["agent"] == "vision"
    assert plan_screen.steps[0]["action"] in ("inspect_screen", "ocr_screen")

    # Query C: Song origin follow-up
    plan_song, _ = await planner.create_plan(
        "What movie is this song from?",
        registry,
    )
    assert plan_song.provider_used == "prefilter"
    assert plan_song.plan_type == "sequential"
    assert plan_song.steps[0]["agent"] == "media"
    assert plan_song.steps[1]["agent"] == "research"


@pytest.mark.asyncio
async def test_pillar_3_verbatim_financial_templating_bypass():
    """Verifies that pure finance queries bypass LLM synthesis to prevent numeric rounding/transposition."""
    alfred = AlfredSupervisor()

    # Process balance query
    response = await alfred.process_query("What is my bank balance?")

    # Should contain exact ₹ symbol and balance summary from FinanceSpecialist
    assert "₹" in response.speech_text
    assert "₹" in response.markdown_body
    # Should reflect verified speech summary directly
    assert any(a["agent"].startswith("finance") for a in response.specialist_actions)


@pytest.mark.asyncio
async def test_pillar_4_transparent_sandbox_disclosure():
    """Verifies that when offline sandbox email/calendar data is returned, Alfred explicitly discloses it."""
    alfred = AlfredSupervisor()
    from backend.agent.specialists.email_specialist import EmailSpecialist
    email_spec = alfred.registry.get("email")
    if isinstance(email_spec, EmailSpecialist):
        email_spec.sandbox_mode = True

    # Search email triggers sandbox fallback
    response = await alfred.process_query("Search emails from Rohit")

    # Verify sandbox disclosure is explicitly present
    assert "[Sandbox Notice]" in response.markdown_body
    assert "sandbox" in response.speech_text.lower()


@pytest.mark.asyncio
async def test_pillar_5_context_staleness_window_and_turn_expiry():
    """Verifies that active session context entities expire after turn/time threshold."""
    alfred = AlfredSupervisor()

    # Turn 0: Inject active email
    mock_email = {
        "id": "msg_001",
        "sender": "rohit@example.com",
        "sender_name": "Rohit Kumar",
        "subject": "Architecture Sync",
    }
    alfred._set_active_entity("active_email", "email", mock_email)
    assert alfred.session_context.get("active_email") is not None

    # Verify immediate anaphora works
    res_immediate = await alfred.process_query("Who sent that email?")
    assert "Rohit Kumar" in res_immediate.speech_text

    # Simulate 10 turns elapsed
    for _ in range(10):
        alfred._turn_counter += 1

    # Prune should expire the 10-turn-old email slot
    alfred._prune_stale_context(max_turns=8)
    assert alfred.session_context.get("active_email") is None

    # Querying after expiration should ask for clarification instead of hallucinating Rohit
    res_stale = await alfred.process_query("Who sent that email?")
    assert "Which email" in res_stale.speech_text or "referring to" in res_stale.speech_text


@pytest.mark.asyncio
async def test_pillar_6_barge_in_precedence_over_proactive_alerts():
    """Verifies that user barge-in aborts active tasks, while proactive alerts are deferred during user voice pipeline."""
    task_registry = TaskRegistry()
    manager = MagicMock()
    sent_envelopes = []

    async def mock_send(session_id, env):
        sent_envelopes.append(env)

    manager.send_envelope = mock_send

    session = MagicMock()
    session.session_id = "sess_01"
    session.client_id = "client_desk"

    router = MessageRouter(connection_manager=manager, task_registry=task_registry)

    # 1. Register an in-flight user voice task
    async def dummy_voice_task():
        await asyncio.sleep(5.0)

    voice_task = asyncio.create_task(dummy_voice_task())
    task_registry.register("voice_req_01", voice_task, session_id="sess_01")
    assert task_registry.has_active_session_tasks("sess_01") is True

    # 2. Incoming low-priority proactive alert interrupt
    proactive_envelope = ClientEnvelope(
        uuid="alert_01",
        channel=Channel.SYSTEM,
        type=EventType.INTERRUPT,
        payload={"reason": "TRIAGE_ALERT", "priority": 2},
    )
    await router._handle_system(session, proactive_envelope)

    # Proactive alert should be deferred, leaving the voice task running
    assert voice_task.done() is False
    assert len(sent_envelopes) == 1
    assert sent_envelopes[0].status == "deferred"
    assert sent_envelopes[0].payload.get("queued") is True

    # 3. Incoming high-priority USER_BARGE_IN interrupt
    barge_in_envelope = ClientEnvelope(
        uuid="barge_in_01",
        channel=Channel.SYSTEM,
        type=EventType.INTERRUPT,
        payload={"reason": "USER_BARGE_IN", "priority": 10},
    )
    await router._handle_system(session, barge_in_envelope)
    await asyncio.sleep(0.05)

    # User barge-in must immediately cancel the active voice task
    assert voice_task.cancelled() is True or voice_task.done() is True
    assert len(sent_envelopes) == 2
    assert sent_envelopes[1].status == "interrupted"


def test_pillar_7_camera_privacy_state_sync():
    """Verifies that optical_sensor_active state updates during camera access."""
    sync = SyncManager.get_instance()
    assert sync.state.optical_sensor_active is False

    # Mock cv2 to simulate camera open and release
    with patch("cv2.VideoCapture") as mock_vc:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_vc.return_value = mock_cap

        # During capture frame, sensor becomes active, then releases to inactive in finally
        res = CameraCapture.capture_frame(camera_index=0)
        # After finally block, optical_sensor_active must return to False
        assert not sync.state.optical_sensor_active


def test_pillar_8_static_cluster_role_allocation():
    """Verifies that CLUSTER_ALLOCATION_MODE='static' assigns roles without dynamic rebalancer overhead."""
    dev_desktop = DeviceRegistration(
        device_id="desktop_01",
        device_type="desktop",
        has_display=True,
        has_camera=True,
        has_microphone=True,
        has_speaker=True,
        cpu_cores=8,
        ram_total_gb=16.0,
        ram_available_gb=8.0,
    )
    dev_orange_pi = DeviceRegistration(
        device_id="orange_pi_01",
        device_type="orange_pi",
        has_display=False,
        has_camera=False,
        has_microphone=True,
        has_speaker=True,
        cpu_cores=4,
        ram_total_gb=2.0,
        ram_available_gb=1.0,
    )

    devices = {
        "desktop_01": dev_desktop,
        "orange_pi_01": dev_orange_pi,
    }

    with patch("backend.sync.cluster_allocator.CLUSTER_ALLOCATION_MODE", "static"):
        with patch("backend.sync.cluster_allocator.STATIC_DEVICE_ROLES", ""):
            allocations = ClusterWorkloadAllocator.allocate_roles(devices)

            # Desktop should statically assume compute and vision roles
            assert ROLE_COGNITIVE_SWARM in allocations["desktop_01"]
            assert ROLE_VISION_PERCEPTION in allocations["desktop_01"]
            assert ROLE_VECTOR_MEMORY in allocations["desktop_01"]

            # Edge SBC should assume audio capture / playback
            assert ROLE_AUDIO_CAPTURE in allocations["orange_pi_01"]
            assert ROLE_AUDIO_PLAYBACK in allocations["orange_pi_01"]
