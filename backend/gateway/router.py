"""VESPER Inbound Message Demultiplexer & Router.

Parses ClientEnvelope frames and routes them to their respective channel handlers:
CONTROL, SYSTEM (including out-of-band INTERRUPT), VOICE, GESTURE, and NOTIFY.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from backend.gateway.connection_manager import ClientSession, ConnectionManager
from backend.gateway.task_registry import TaskRegistry
from backend.shared.config import AGENT_SERVICE_URL
from backend.shared.events import (
    Channel,
    ClientEnvelope,
    ClientType,
    EventType,
    PongPayload,
    ServerEnvelope,
)
from backend.sync import DeviceRegistration, sync_manager
from backend.vision.gesture_service import (
    _control_media_player,
    _set_system_mute,
    _set_system_volume,
)

logger = logging.getLogger("vesper.gateway.router")


class MessageRouter:
    """Routes multiplexed client envelopes to specific asynchronous handlers."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        task_registry: TaskRegistry,
    ) -> None:
        self.manager = connection_manager
        self.tasks = task_registry
        self._pending_workstation_requests: dict[str, asyncio.Future] = {}

    async def route(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Main entry point for dispatching a validated ClientEnvelope."""
        channel = envelope.channel

        try:
            if channel == Channel.CONTROL:
                await self._handle_control(session, envelope)
            elif channel == Channel.SYSTEM:
                await self._handle_system(session, envelope)
            elif channel == Channel.VOICE:
                await self._handle_voice(session, envelope)
            elif channel == Channel.GESTURE:
                await self._handle_gesture(session, envelope)
            elif channel == Channel.NOTIFY:
                await self._handle_notify(session, envelope)
            elif channel == Channel.SYNC:
                await self._handle_sync(session, envelope)
            else:
                logger.warning(f"[ROUTER] Unknown channel '{channel}' from {session.session_id}")

                await self._send_error(
                    session,
                    envelope.uuid,
                    channel,
                    f"Unsupported channel: {channel}",
                )
        except Exception as e:
            logger.error(f"[ROUTER] Error handling {channel}:{envelope.type}: {e}", exc_info=True)
            await self._send_error(
                session,
                envelope.uuid,
                channel,
                f"Internal routing error: {str(e)}",
            )

    # ── Channel Handlers ──────────────────────────────────────────────────

    async def _handle_control(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles keep-alive and session control frames."""
        event_type = envelope.type

        if event_type == EventType.PONG:
            self.manager.record_pong(session.session_id)
            logger.debug(f"[ROUTER] Recorded PONG from '{session.session_id}'")
        elif event_type == EventType.PING:
            # Client pinged us; respond with pong
            pong = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.CONTROL,
                type=EventType.PONG,
                payload=PongPayload().model_dump(),
            )
            await self.manager.send_envelope(session.session_id, pong)
        elif event_type == EventType.MEDIA_CONTROL:
            await self._handle_media_control(session, envelope)
        elif event_type == EventType.WORKSTATION_COMMAND_REQ:
            await self._handle_workstation_command_req(session, envelope)
        elif event_type == EventType.WORKSTATION_COMMAND_RES:
            await self._handle_workstation_command_res(session, envelope)
        else:
            logger.warning(f"[ROUTER] Unhandled control event '{event_type}'")

    async def _handle_workstation_command_req(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Broadcasts or forwards a workstation command request to connected DESK_HUD / workstation clients."""
        fwd_env = ServerEnvelope(
            uuid=envelope.uuid,
            channel=Channel.CONTROL,
            type=EventType.WORKSTATION_COMMAND_REQ,
            payload=envelope.payload,
        )
        sent = await self.manager.broadcast(fwd_env, target_client_types=[ClientType.DESK_HUD])
        logger.info(f"[ROUTER] Forwarded WORKSTATION_COMMAND_REQ '{envelope.uuid}' to {sent} desktop client(s)")

    async def _handle_workstation_command_res(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles response envelope from workstation client and fulfills pending future."""
        req_uuid = envelope.uuid or envelope.payload.get("request_uuid")
        logger.info(f"[ROUTER] Received WORKSTATION_COMMAND_RES for request '{req_uuid}' from '{session.client_id}'")
        if req_uuid and req_uuid in self._pending_workstation_requests:
            fut = self._pending_workstation_requests[req_uuid]
            if not fut.done():
                fut.set_result(envelope.payload)

    async def execute_workstation_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 4.0,
    ) -> Dict[str, Any]:
        """Dispatches a workstation command down WebSocket to connected DESK_HUD and awaits result."""
        req_uuid = str(uuid.uuid4())
        req_env = ServerEnvelope(
            uuid=req_uuid,
            channel=Channel.CONTROL,
            type=EventType.WORKSTATION_COMMAND_REQ,
            payload={
                "request_uuid": req_uuid,
                "command": command,
                "params": params or {},
            },
        )
        # Check if any DESK_HUD client is connected
        desk_sessions = [s for s in self.manager._sessions.values() if s.client_type == ClientType.DESK_HUD]
        if not desk_sessions:
            return {"success": False, "error": "No workstation or desktop companion connected to Gateway"}

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_workstation_requests[req_uuid] = fut

        sent = await self.manager.broadcast(req_env, target_client_types=[ClientType.DESK_HUD])
        if sent == 0:
            self._pending_workstation_requests.pop(req_uuid, None)
            return {"success": False, "error": "Failed to dispatch command to desktop companion"}

        try:
            res_payload = await asyncio.wait_for(fut, timeout=timeout)
            return res_payload if isinstance(res_payload, dict) else {"success": True, "result": res_payload}
        except asyncio.TimeoutError:
            logger.warning(f"[ROUTER] Workstation command '{command}' (req={req_uuid}) timed out after {timeout}s")
            return {"success": False, "error": f"Workstation command '{command}' timed out after {timeout}s"}
        finally:
            self._pending_workstation_requests.pop(req_uuid, None)

    async def _handle_system(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles high-priority system events and out-of-band INTERRUPT signals."""
        event_type = envelope.type
        payload = envelope.payload

        if event_type == EventType.INTERRUPT:
            target_uuid = payload.get("target_uuid")
            reason = payload.get("reason", "USER_BARGE_IN")
            priority = int(payload.get("priority", 10 if "USER" in str(reason).upper() else 1))
            logger.info(
                f"[ROUTER] INTERRUPT received from '{session.client_id}' "
                f"(target={target_uuid}, reason={reason}, priority={priority})"
            )

            # Precedence Arbitration:
            # - User Barge-In (priority >= 10): ALWAYS wins and aborts ongoing pipelines immediately.
            # - Proactive / Triage Alerts (priority < 10): If user has active tasks/speech in session,
            #   do not cancel or disrupt active pipeline; queue alert silently.
            is_proactive = priority < 10 or "PROACTIVE" in str(reason).upper() or "TRIAGE" in str(reason).upper()
            if is_proactive and self.tasks.has_active_session_tasks(session.session_id):
                logger.info(
                    f"[ROUTER] Proactive alert interrupt (reason={reason}, priority={priority}) deferred: "
                    f"user voice pipeline is actively processing in session '{session.session_id}'."
                )
                ack = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.INTERRUPT_ACK,
                    status="deferred",
                    payload={
                        "target_uuid": target_uuid,
                        "cancelled": False,
                        "reason": reason,
                        "queued": True,
                    },
                )
                await self.manager.send_envelope(session.session_id, ack)
                return

            cancelled = False
            if target_uuid:
                cancelled = self.tasks.cancel(target_uuid)
            else:
                count = self.tasks.cancel_session(session.session_id)
                cancelled = count > 0

            # Immediate acknowledgment back to client
            ack = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.INTERRUPT_ACK,
                status="interrupted" if cancelled else "ok",
                payload={
                    "target_uuid": target_uuid,
                    "cancelled": cancelled,
                    "reason": reason,
                },
            )
            await self.manager.send_envelope(session.session_id, ack)

        elif event_type == EventType.SET_VOLUME:
            # Broadcast volume change to all connected clients and apply host OS volume
            vol = payload.get("volume", 50)
            logger.info(f"[ROUTER] Setting master volume to {vol}%")
            _set_system_volume(vol)
            await sync_manager.update_state({"master_volume": vol}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": vol},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif event_type in [EventType.ZEN_MODE_STATE, EventType.FOCUS_MODE_STATE]:
            key = "zen_mode" if event_type == EventType.ZEN_MODE_STATE else "focus_mode"
            current_val = getattr(sync_manager.get_snapshot(), key, False)

            if "zen_mode" in payload:
                new_state = bool(payload["zen_mode"])
            elif "enabled" in payload:
                new_state = bool(payload["enabled"])
            elif "active" in payload:
                new_state = bool(payload["active"])
            elif payload.get("toggle", False) or "toggle" in payload:
                new_state = not current_val
            else:
                new_state = True

            diff: Dict[str, Any] = {key: new_state}
            timer_state = dict(sync_manager.get_snapshot().zen_timer)

            if new_state:
                # Entering Zen Mode:
                # 1. Pause Spotify if currently playing
                try:
                    from backend.vision.gesture_service import _control_media_player
                    _control_media_player("pause")
                except Exception as media_err:
                    logger.debug(f"[Router] Zen pause Spotify error: {media_err}")

                # 2. Automatically start Pomodoro timer
                timer_state["is_running"] = True
                if "seconds_remaining" in payload and isinstance(payload["seconds_remaining"], int):
                    timer_state["seconds_remaining"] = payload["seconds_remaining"]
                else:
                    timer_state["seconds_remaining"] = timer_state.get("sprint_minutes", 25) * 60

                timer_state["soundscape"] = payload.get("soundscape", "ocean")
                timer_state["music_source"] = payload.get("music_source", "ambient")
                diff["zen_timer"] = timer_state
            else:
                # Exiting Zen Mode:
                timer_state["is_running"] = False
                timer_state["soundscape"] = "off"
                diff["zen_timer"] = timer_state

            await sync_manager.update_state(diff, source_device_id=session.client_id)

            broadcast_payload = {
                "toggle": False,
                key: new_state,
                "enabled": new_state,
                "zen_mode": new_state,
                "timer": timer_state,
                "soundscape": timer_state.get("soundscape", "off"),
                "music_source": timer_state.get("music_source", "ambient"),
            }

            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=event_type,
                payload=broadcast_payload,
            )
            await self.manager.broadcast(broadcast_envelope)

        elif event_type == EventType.ZEN_TIMER_UPDATE:
            # Handle timer actions (start, pause, reset, preset, soundscape)
            timer_state = dict(sync_manager.get_snapshot().zen_timer)
            action = payload.get("action", "")

            if action == "start":
                timer_state["is_running"] = True
                if "seconds_remaining" in payload:
                    timer_state["seconds_remaining"] = int(payload["seconds_remaining"])
            elif action == "pause":
                timer_state["is_running"] = False
                if "seconds_remaining" in payload:
                    timer_state["seconds_remaining"] = int(payload["seconds_remaining"])
            elif action == "reset":
                timer_state["is_running"] = False
                timer_state["seconds_remaining"] = timer_state.get("sprint_minutes", 25) * 60
            elif action == "preset":
                mins = int(payload.get("minutes", 25))
                timer_state["sprint_minutes"] = mins
                timer_state["seconds_remaining"] = mins * 60
                timer_state["is_running"] = True
            elif action == "tick":
                secs = int(payload.get("seconds_remaining", timer_state.get("seconds_remaining", 0)))
                timer_state["seconds_remaining"] = max(0, secs)
                if secs <= 0:
                    timer_state["is_running"] = False
                    timer_state["completed_sprints"] = timer_state.get("completed_sprints", 0) + 1
            elif action == "soundscape":
                soundscape = payload.get("soundscape", "ocean")
                music_source = payload.get("music_source", "ambient" if soundscape != "spotify" else "spotify")
                timer_state["soundscape"] = soundscape
                timer_state["music_source"] = music_source

                # Preserve current timer countdown and running state if provided
                if "is_running" in payload:
                    timer_state["is_running"] = bool(payload["is_running"])
                if "seconds_remaining" in payload and isinstance(payload["seconds_remaining"], int):
                    timer_state["seconds_remaining"] = payload["seconds_remaining"]

                # Media player switching
                try:
                    from backend.vision.gesture_service import _control_media_player
                    if music_source == "spotify" or soundscape == "spotify":
                        _control_media_player("play", is_gesture=False)
                    else:
                        _control_media_player("pause", is_gesture=False)
                except Exception as media_err:
                    logger.debug(f"[Router] Soundscape media control error: {media_err}")

            await sync_manager.update_state({"zen_timer": timer_state}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.ZEN_TIMER_UPDATE,
                payload={"action": action, "timer": timer_state},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif event_type == EventType.MEDIA_CONTROL:
            await self._handle_media_control(session, envelope)

        elif event_type in [EventType.WAKE_WORD_TOGGLE, EventType.WAKE_WORD_STATE]:
            await self._handle_wake_word_toggle(session, envelope)

    async def _handle_media_control(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Executes hardware media playback control actions (play, pause, next, prev, play-pause)."""
        payload = envelope.payload or {}
        action = payload.get("action", "play-pause")
        logger.info(f"[ROUTER] Handling MEDIA_CONTROL from '{session.client_id}': action={action}")

        try:
            from backend.vision.gesture_service import _control_media_player
            await asyncio.to_thread(_control_media_player, action, False)
            await asyncio.sleep(0.15)
        except Exception as err:
            logger.warning(f"[ROUTER] Error executing media control action: {err}")

        try:
            from backend.gateway.routes.media import _fetch_mpris_now_playing
            track_info = await asyncio.to_thread(_fetch_mpris_now_playing)
            await sync_manager.update_state({"current_media": track_info}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload=track_info,
            )
            await self.manager.broadcast(broadcast_envelope)
        except Exception as err:
            logger.warning(f"[ROUTER] Error broadcasting updated media state: {err}")

    async def _handle_wake_word_toggle(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles wake word enable/disable and broadcast to all cluster nodes."""
        payload = envelope.payload or {}
        cur_state = sync_manager.get_snapshot().wakeword_active
        if "wakeword_active" in payload and isinstance(payload["wakeword_active"], bool):
            new_state = payload["wakeword_active"]
        elif "active" in payload and isinstance(payload["active"], bool):
            new_state = payload["active"]
        elif "enabled" in payload and isinstance(payload["enabled"], bool):
            new_state = payload["enabled"]
        elif "is_armed" in payload and isinstance(payload["is_armed"], bool):
            new_state = payload["is_armed"]
        elif payload.get("action") == "pause":
            new_state = False
        elif payload.get("action") == "resume":
            new_state = True
        elif payload.get("toggle", False) or "toggle" in payload:
            new_state = not cur_state
        else:
            new_state = not cur_state

        logger.info(f"[ROUTER] Wake word toggle from '{session.client_id}': new_state={new_state}")
        await sync_manager.update_state({"wakeword_active": new_state}, source_device_id=session.client_id)

        broadcast_envelope = ServerEnvelope(
            uuid=envelope.uuid,
            channel=Channel.VOICE,
            type=EventType.WAKE_WORD_STATE,
            payload={
                "wakeword_active": new_state,
                "active": new_state,
                "enabled": new_state,
                "is_armed": new_state,
                "action": "resume" if new_state else "pause",
                "toggle": True,
                "source": session.client_id,
            },
        )
        await self.manager.broadcast(broadcast_envelope)

    async def _handle_voice(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles incoming voice transcripts, wake words, and commands."""
        event_type = envelope.type

        # 0. Wake Word Toggle / State
        if event_type in [EventType.WAKE_WORD_TOGGLE, EventType.WAKE_WORD_STATE]:
            await self._handle_wake_word_toggle(session, envelope)
            return

        # 1. Wake Word Detected Broadcast
        if event_type == EventType.WAKE_WORD_DETECTED:
            is_explicit_ptt = envelope.payload.get("trigger") == "push_to_talk" or envelope.payload.get("source") != "acoustic_listener"
            if not sync_manager.get_snapshot().wakeword_active and not is_explicit_ptt:
                logger.info(f"[VOICE] Wake word suppressed because acoustic listener is DISARMED/MUTED (from '{session.client_id}')")
                return

            wake_word = envelope.payload.get("wake_word", "hey alfred")
            conf = float(envelope.payload.get("confidence", 1.0))
            logger.info(f"[VOICE] Wake word detected: '{wake_word}' (conf={conf:.2f}, ptt={is_explicit_ptt}) from '{session.client_id}'")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_DETECTED,
                payload={
                    "wake_word": wake_word,
                    "confidence": conf,
                    "state": "LISTENING",
                    "source": session.client_id,
                    "trigger": envelope.payload.get("trigger", "push_to_talk" if is_explicit_ptt else "acoustic"),
                },
            )
            await self.manager.broadcast(broadcast_envelope)
            return

        command_text = (envelope.payload.get("command") or "").strip()
        if not command_text:
            logger.debug(f"[VOICE] Empty voice command from '{session.client_id}' ignored.")
            return

        logger.info(f"[VOICE] Command from '{session.client_id}': \"{command_text}\" (UUID: {envelope.uuid})")

        # 2. Agent Activating Broadcast -> Notify cluster that LangGraph has started reasoning (THINKING)
        activating_envelope = ServerEnvelope(
            uuid=envelope.uuid,
            channel=Channel.AGENT,
            type=EventType.AGENT_ACTIVATING,
            payload={
                "command": command_text,
                "state": "THINKING",
                "session_id": session.session_id,
            },
        )
        await self.manager.broadcast(activating_envelope)

        # Create background task for processing to never block the network loop
        async def _execute_voice_pipeline():
            try:
                response_text = f"Acknowledged: {command_text}"
                markdown_body = response_text
                hud_cards = []
                specialist_actions: list[Any] = []
                fast_path = False
                intent = "CONVERSE"
                latency_ms = 0.0
                navigate_to: Optional[str] = None
                resolved_advisory_ids: list[str] = []

                try:
                    target_url = f"{AGENT_SERVICE_URL}/query"
                    timeout_config = httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0)
                    async with httpx.AsyncClient(timeout=timeout_config) as http_client:
                        try:
                            agent_res = await http_client.post(
                                target_url,
                                json={
                                    "query": command_text,
                                    "session_id": session.session_id,
                                    "client_id": session.client_id,
                                },
                            )
                        except (httpx.ConnectTimeout, httpx.ConnectError) as conn_err:
                            fallback_url = "http://127.0.0.1:8001/query"
                            if target_url != fallback_url:
                                logger.warning(f"[VOICE] Agent connection to {target_url} failed ({conn_err}), retrying {fallback_url}")
                                agent_res = await http_client.post(
                                    fallback_url,
                                    json={
                                        "query": command_text,
                                        "session_id": session.session_id,
                                        "client_id": session.client_id,
                                    },
                                )
                            else:
                                raise conn_err

                        if agent_res.status_code == 200:
                            data = agent_res.json()
                            response_text = data.get("speech_text", response_text)
                            markdown_body = data.get("markdown_body", response_text)
                            hud_cards = data.get("hud_cards", [])
                            specialist_actions = data.get("specialist_actions", [])
                            fast_path = data.get("fast_path", False)
                            intent = data.get("plan_type", "CONVERSE")
                            latency_ms = data.get("latency_ms", 0.0)
                            navigate_to = data.get("navigate_to")
                            resolved_advisory_ids = data.get("resolved_advisory_ids", [])
                        else:
                            logger.error(f"[VOICE] Agent returned HTTP {agent_res.status_code}: {agent_res.text}")
                            response_text = "I apologize, sir, but an error occurred within the cognitive swarm."
                            markdown_body = f"**Cognitive Swarm Error**: HTTP {agent_res.status_code}\n\n```\n{agent_res.text[:400]}\n```"
                            navigate_to = None
                except Exception as agent_err:
                    err_desc = str(agent_err) or type(agent_err).__name__
                    logger.warning(f"[VOICE] Agent service call failed or unavailable ({err_desc}). Using fallback.")
                    response_text = "I apologize, sir, but the cognitive agent swarm is currently unreachable."
                    markdown_body = f"**Swarm Unreachable**: {err_desc}"
                    navigate_to = None

                # Fallback deterministic view resolution if agent did not provide one
                if not navigate_to and command_text:
                    cmd_lower = command_text.lower()
                    if any(w in cmd_lower for w in ["agenda", "task", "todo", "calendar", "schedule"]):
                        navigate_to = "agenda"
                    elif any(w in cmd_lower for w in ["finance", "ledger", "transaction", "bank", "account"]):
                        navigate_to = "transactions"
                    elif any(w in cmd_lower for w in ["workstation", "overview", "cockpit"]):
                        navigate_to = "center"
                    elif any(w in cmd_lower for w in ["service", "telemetry", "hardware", "swarm"]):
                        navigate_to = "services"
                    elif any(w in cmd_lower for w in ["tool", "emitter"]):
                        navigate_to = "tools"
                    elif any(w in cmd_lower for w in ["log", "event stream", "audit"]):
                        navigate_to = "logs"

                # 3. Agent Response Delivery -> Broadcast to all display interfaces (HUD, mobile)
                response_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.VOICE,
                    type=EventType.AGENT_RESPONSE,
                    payload={
                        "command": command_text,
                        "response": response_text,
                        "markdown_body": markdown_body,
                        "hud_cards": hud_cards,
                        "specialist_actions": specialist_actions,
                        "fast_path": fast_path,
                        "intent": intent,
                        "navigate_to": navigate_to,
                        "status": "processed",
                        "latency_ms": latency_ms,
                    },
                )
                await self.manager.broadcast(response_envelope)

                # 3b. Proactive Advisory Resolution Broadcast (if voice resolved any advisories)
                if resolved_advisory_ids:
                    resolve_envelope = ServerEnvelope(
                        uuid=envelope.uuid,
                        channel=Channel.SYSTEM,
                        type=EventType.PROACTIVE_RESOLVE,
                        payload={
                            "action_ids": resolved_advisory_ids,
                            "resolution": "resolved",
                            "source": "voice",
                        },
                    )
                    await self.manager.broadcast(resolve_envelope)
                    logger.info(f"[VOICE] Broadcast PROACTIVE_RESOLVE for advisory IDs: {resolved_advisory_ids}")

                # 4. Agent Speaking Broadcast
                speaking_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.VOICE,
                    type=EventType.AGENT_SPEAKING,
                    payload={
                        "command": command_text,
                        "response": response_text,
                        "state": "SPEAKING",
                    },
                )
                await self.manager.broadcast(speaking_envelope)

                # Estimate TTS speech duration (~150 WPM / 2.5 words per second)
                # plus a 5-second linger buffer so the user has time to read the HUD card
                word_count = len(response_text.split()) if response_text else 0
                speech_seconds = max(3.0, word_count / 2.5)
                hud_linger_wait = speech_seconds + 5.0
                logger.debug(f"[VOICE] Estimated speech: {speech_seconds:.1f}s ({word_count} words) + 5s linger = {hud_linger_wait:.1f}s total")
                await asyncio.sleep(hud_linger_wait)

                # 5. Agent Idle Broadcast -> State transitions back to IDLE
                idle_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.VOICE,
                    type=EventType.AGENT_IDLE,
                    payload={"state": "IDLE", "command": command_text},
                )
                await self.manager.broadcast(idle_envelope)

            except asyncio.CancelledError:
                logger.info(f"[VOICE] Pipeline task cancelled for UUID={envelope.uuid}")
                idle_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.VOICE,
                    type=EventType.AGENT_IDLE,
                    payload={"state": "IDLE", "reason": "INTERRUPTED"},
                )
                await self.manager.broadcast(idle_envelope)
                raise

        pipeline_task = asyncio.create_task(_execute_voice_pipeline())
        self.tasks.register(envelope.uuid, pipeline_task, session.session_id)

    async def _handle_gesture(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles discrete gesture shortcuts emitted by the client Web Worker or backend GestureWorker."""
        gesture = str(envelope.payload.get("gesture", "")).strip().upper()
        logger.info(f"[GESTURE] Received gesture '{gesture}' from '{session.client_id}'")

        if gesture in ("THREE_FINGERS", "PLAY_PAUSE", "MEDIA_PLAY_PAUSE"):
            # Pure media play/pause toggle without touching master volume or muting
            now = time.time()
            if getattr(self, "_last_media_toggle", 0.0) and (now - self._last_media_toggle < 1.0):
                logger.info("[GESTURE] Ignored rapid Play/Pause toggle (cluster debounce)")
                return
            self._last_media_toggle = now

            cur_state = sync_manager.get_snapshot()
            media_copy = dict(cur_state.current_media)
            is_currently_playing = media_copy.get("is_playing", True)
            new_playing = not is_currently_playing
            media_copy["is_playing"] = new_playing
            await sync_manager.update_state({"current_media": media_copy}, source_device_id=session.client_id)

            await asyncio.to_thread(_control_media_player, "play-pause")
            action_name = "play" if new_playing else "pause"
            logger.info(f"[GESTURE] THREE_FINGERS toggled media playback from '{session.client_id}' -> {action_name} (Volume untouched)")

            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload={"action": "play_pause", "media_state": action_name, "source": f"GESTURE:{gesture}"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("PEACE_SIGN", "VICTORY", "TOGGLE_ZEN", "ZEN_MODE"):
            now = time.time()
            if getattr(self, "_last_zen_toggle", 0.0) and (now - self._last_zen_toggle < 2.0):
                logger.info("[GESTURE] Ignored rapid Zen Mode toggle (cluster debounce)")
                return
            self._last_zen_toggle = now

            current_zen = sync_manager.get_snapshot().zen_mode
            new_zen = not current_zen
            await sync_manager.update_state({"zen_mode": new_zen}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.ZEN_MODE_STATE,
                payload={"toggle": True, "zen_mode": new_zen},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("CLOSED_FIST", "MUTE", "PAUSE", "STOP", "INTERRUPT"):
            # Out-of-band gesture interrupt: instantly stop assistant speech & active research pipelines
            cancelled_count = self.tasks.cancel_all()
            logger.info(f"[GESTURE] CLOSED_FIST interrupt aborted {cancelled_count} active task(s)")

            await asyncio.to_thread(_set_system_mute, True)
            await asyncio.to_thread(_set_system_volume, 0)
            await asyncio.to_thread(_control_media_player, "pause")
            cur_state = sync_manager.get_snapshot()
            media_copy = dict(cur_state.current_media)
            media_copy["is_playing"] = False
            await sync_manager.update_state(
                {"master_volume": 0, "current_media": media_copy, "wakeword_active": False},
                source_device_id=session.client_id,
            )

            # 1. SET_VOLUME broadcast
            vol_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": 0, "muted": True, "media_action": "pause", "wakeword_active": False},
            )
            await self.manager.broadcast(vol_envelope)

            # 2. WAKE_WORD_STATE broadcast
            ww_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_STATE,
                payload={"wakeword_active": False, "reason": "GESTURE_CLOSED_FIST"},
            )
            await self.manager.broadcast(ww_envelope)

            # 3. High-priority INTERRUPT signal across all connected sessions if tasks were cancelled
            if cancelled_count > 0:
                interrupt_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.INTERRUPT,
                    payload={"source": f"GESTURE:{gesture}", "reason": "USER_GESTURE_INTERRUPT", "cancelled_tasks": cancelled_count},
                )
                await self.manager.broadcast(interrupt_envelope)

        elif gesture in ("OPEN_PALM", "RESUME", "PLAY", "UNMUTE"):
            # Resume playback / Unmute to default level and Rearm Wake Word Listener
            current_vol = sync_manager.get_snapshot().master_volume
            restore_vol = current_vol if current_vol > 0 else 50
            await asyncio.to_thread(_set_system_mute, False)
            await asyncio.to_thread(_set_system_volume, restore_vol)
            await asyncio.to_thread(_control_media_player, "play")
            cur_state = sync_manager.get_snapshot()
            media_copy = dict(cur_state.current_media)
            media_copy["is_playing"] = True
            await sync_manager.update_state(
                {"master_volume": restore_vol, "current_media": media_copy, "wakeword_active": True},
                source_device_id=session.client_id,
            )
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": restore_vol, "muted": False, "media_action": "play", "wakeword_active": True},
            )
            await self.manager.broadcast(broadcast_envelope)

            # Rearm wake word listener
            ww_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_STATE,
                payload={"wakeword_active": True, "action": "resume", "source": "GESTURE:OPEN_PALM"},
            )
            await self.manager.broadcast(ww_envelope)

        elif gesture in ("POINTING_UP", "TOGGLE_WAKEWORD", "WAKEWORD_TOGGLE"):
            # Toggle active wake word listening state via Pointing Up gesture
            cur_ww = sync_manager.get_snapshot().wakeword_active
            new_ww = not cur_ww
            await sync_manager.update_state({"wakeword_active": new_ww}, source_device_id=session.client_id)
            ww_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_STATE,
                payload={
                    "wakeword_active": new_ww,
                    "active": new_ww,
                    "enabled": new_ww,
                    "is_armed": new_ww,
                    "action": "resume" if new_ww else "pause",
                    "toggle": True,
                    "source": f"GESTURE:{gesture}",
                },
            )
            await self.manager.broadcast(ww_envelope)

        elif gesture in ("ROCK_ON", "GESTURE_LOCK", "TOGGLE_GESTURES") or gesture.startswith("GESTURE_TOGGLE"):
            # Toggle gesture tracking pause/lock via Rock On deliberate hold or explicit toggle
            cur_paused = getattr(self, "_gestures_paused", False)
            if ":PAUSED" in gesture:
                new_paused = True
            elif ":RESUMED" in gesture:
                new_paused = False
            elif gesture.startswith("GESTURE_TOGGLE"):
                new_paused = not cur_paused
            else:
                return
            self._gestures_paused = new_paused
            status_str = "PAUSED" if new_paused else "RESUMED"
            logger.info(f"[GESTURE] Toggled gesture tracking via ROCK_ON -> {status_str}")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.GESTURE,
                type=EventType.GESTURE_TOGGLE,
                payload={"tracking_paused": new_paused, "status": status_str, "gesture": f"GESTURE_TOGGLE:{status_str}"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("NEXT_TRACK", "SWIPE_RIGHT", "GUN_RIGHT", "GUN_POINT_RIGHT"):
            # Next Track playback control
            logger.info(f"[GESTURE] Triggered NEXT_TRACK media control from '{session.client_id}' ({gesture})")
            await asyncio.to_thread(_control_media_player, "next")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload={"action": "next_track", "source": "GESTURE"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("PREV_TRACK", "PREVIOUS_TRACK", "SWIPE_LEFT", "GUN_LEFT", "GUN_POINT_LEFT"):
            # Previous Track playback control
            logger.info(f"[GESTURE] Triggered PREV_TRACK media control from '{session.client_id}' ({gesture})")
            await asyncio.to_thread(_control_media_player, "previous")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload={"action": "previous_track", "source": "GESTURE"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("THUMB_UP", "CONFIRM", "VOLUME_UP"):
            # Check if there is an active proactive staged recommendation awaiting confirmation
            from backend.agent.proactive.action_queue import action_queue
            recent_prompted = action_queue.get_recent_prompted_action(max_age_sec=15.0)
            if recent_prompted:
                action_queue.resolve_action(recent_prompted.id, "confirmed", confirmed_by="gesture_thumb_up")
                logger.info(f"[GESTURE] Confirmed staged action '{recent_prompted.id}' via THUMB_UP")
                confirm_env = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.NOTIFICATION_DIGEST,
                    payload={
                        "title": "Action Confirmed",
                        "speech": f"Confirmed via gesture, sir. Executing {recent_prompted.action}.",
                        "proactive": True,
                        "resolved_action": recent_prompted.model_dump(),
                    },
                )
                await self.manager.broadcast(confirm_env)
                return

            # Otherwise Step Volume Up (+10%)
            now = time.time()
            if getattr(self, "_last_vol_change", 0.0) and (now - self._last_vol_change < 0.15):
                return
            self._last_vol_change = now

            current_vol = sync_manager.get_snapshot().master_volume
            new_vol = min(100, current_vol + 10)
            await asyncio.to_thread(_set_system_mute, False)
            await asyncio.to_thread(_set_system_volume, new_vol)
            await sync_manager.update_state({"master_volume": new_vol}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": new_vol, "direction": "up", "step": 10},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("CANCEL", "DISMISS", "STAND_DOWN"):
            cancelled_count = self.tasks.cancel_all()
            logger.info(f"[GESTURE] {gesture} aborted {cancelled_count} active task(s)")
            if cancelled_count > 0:
                interrupt_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.INTERRUPT,
                    payload={"source": f"GESTURE:{gesture}", "reason": "USER_GESTURE_CANCEL", "cancelled_tasks": cancelled_count},
                )
                await self.manager.broadcast(interrupt_envelope)
            idle_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.AGENT_IDLE,
                payload={"state": "IDLE", "reason": "GESTURE_CANCEL"},
            )
            await self.manager.broadcast(idle_envelope)

        elif gesture in ("THUMB_DOWN", "REJECT", "VOLUME_DOWN"):
            # Check if there are active in-flight voice or reasoning tasks to cancel immediately
            if self.tasks.active_count > 0:
                cancelled_count = self.tasks.cancel_all()
                logger.info(f"[GESTURE] THUMB_DOWN aborted {cancelled_count} active task(s)")
                interrupt_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.INTERRUPT,
                    payload={"source": "GESTURE:THUMB_DOWN", "reason": "USER_GESTURE_CANCEL", "cancelled_tasks": cancelled_count},
                )
                await self.manager.broadcast(interrupt_envelope)
                idle_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.VOICE,
                    type=EventType.AGENT_IDLE,
                    payload={"state": "IDLE", "reason": "GESTURE_CANCEL"},
                )
                await self.manager.broadcast(idle_envelope)
                return

            # Check if there is an active proactive staged recommendation awaiting confirmation
            from backend.agent.proactive.action_queue import action_queue
            recent_prompted = action_queue.get_recent_prompted_action(max_age_sec=15.0)
            if recent_prompted:
                action_queue.resolve_action(recent_prompted.id, "rejected", confirmed_by="gesture_thumb_down")
                logger.info(f"[GESTURE] Rejected staged action '{recent_prompted.id}' via THUMB_DOWN")
                reject_env = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.NOTIFICATION_DIGEST,
                    payload={
                        "title": "Action Discarded",
                        "speech": "Understood, sir. I have discarded that proposal.",
                        "proactive": True,
                        "rejected_action": recent_prompted.model_dump(),
                    },
                )
                await self.manager.broadcast(reject_env)
                return

            # Otherwise Step Volume Down (-10%)
            now = time.time()
            if getattr(self, "_last_vol_change", 0.0) and (now - self._last_vol_change < 0.15):
                return
            self._last_vol_change = now

            current_vol = sync_manager.get_snapshot().master_volume
            new_vol = max(0, current_vol - 10)
            await asyncio.to_thread(_set_system_volume, new_vol)
            if new_vol == 0:
                await asyncio.to_thread(_set_system_mute, True)
            await sync_manager.update_state({"master_volume": new_vol}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": new_vol, "direction": "down", "step": 10},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("TOGGLE_FOCUS", "FOCUS_MODE"):
            # Toggle Focus Mode
            current_focus = sync_manager.get_snapshot().focus_mode
            new_focus = not current_focus
            await sync_manager.update_state({"focus_mode": new_focus}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.FOCUS_MODE_STATE,
                payload={"toggle": True, "focus_mode": new_focus},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("SHAKA", "HANG_LOOSE", "AIR_TAP", "PINCH_TAP", "SELECT"):
            # Touchless Shaka (Hang Loose) drawer toggle / select event
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.GESTURE,
                type=EventType.GESTURE_EVENT,
                payload={"gesture": "SHAKA", "action": "select"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture.startswith("VOLUME_DIAL:") or gesture.startswith("PINCH_DIAL:"):
            try:
                level = int(gesture.split(":")[1])
                clamped = max(0, min(100, level))
                await asyncio.to_thread(_set_system_volume, clamped)
                await sync_manager.update_state({"master_volume": clamped}, source_device_id=session.client_id)
                broadcast_envelope = ServerEnvelope(
                    uuid=envelope.uuid,
                    channel=Channel.SYSTEM,
                    type=EventType.SET_VOLUME,
                    payload={"volume": clamped},
                )
                await self.manager.broadcast(broadcast_envelope)
            except (ValueError, IndexError):
                pass

        elif gesture.startswith("GESTURE_TOGGLE"):
            is_paused = ":PAUSED" in gesture or gesture == "GESTURE_TOGGLE_PAUSED"
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.GESTURE,
                type=EventType.GESTURE_EVENT,
                payload={"gesture": gesture, "tracking_paused": is_paused},
            )
            await self.manager.broadcast(broadcast_envelope)

    async def _handle_notify(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles mobile companion notification ingestion."""
        from backend.sync.notification_service import notification_service
        payload = envelope.payload
        source_dev = sync_manager.state.active_devices.get(session.client_id)
        dev_name = payload.get("device_name") or (source_dev.device_name if source_dev else session.client_id)

        # Handle direct telephony CALL_STATE events
        if envelope.type == EventType.CALL_STATE:
            call_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.NOTIFY,
                type=EventType.CALL_STATE,
                payload={
                    "source_client": session.client_id,
                    "device_name": dev_name,
                    **payload,
                },
            )
            await self.manager.broadcast(call_envelope)
            return

        # Ingest and triage alert
        notif = notification_service.ingest_notification(
            payload=payload,
            source_device_id=session.client_id,
            source_device_name=dev_name,
        )
        if not notif:
            return

        # Synchronize notification state across cluster
        recent = [n.to_dict() for n in notification_service.get_recent_notifications(limit=5)]
        await sync_manager.sync_notifications(
            unread_count=notification_service.get_unread_count(),
            recent=recent,
        )

        # Broadcast ambient card update to Desk HUD
        hud_envelope = ServerEnvelope(
            uuid=envelope.uuid,
            channel=Channel.NOTIFY,
            type=EventType.NOTIFICATION_DIGEST,
            payload={
                "source_client": session.client_id,
                "device_name": dev_name,
                "notification": notif.to_dict(),
                "is_update": getattr(notif, "is_in_place_update", False),
                "is_ongoing": getattr(notif, "is_ongoing", False),
                "is_call": getattr(notif, "is_call", False),
                "call_phase": getattr(notif, "call_phase", None),
                "unread_count": notification_service.get_unread_count(),
            },
        )
        await self.manager.broadcast(hud_envelope)

        # Trigger Proactive Agent VIP triage for HIGH/URGENT notifications
        if notif.priority in ("URGENT", "HIGH"):
            try:
                from backend.agent.proactive_agent import proactive_agent
                asyncio.create_task(proactive_agent.evaluate_notification(notif))
            except Exception as e:
                logger.warning(f"[ROUTER] Proactive VIP triage trigger failed: {e}")

    async def _handle_sync(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles cross-device state synchronization and topology registration."""
        event_type = envelope.type
        payload = envelope.payload

        if event_type == EventType.DEVICE_REGISTER:
            reg_data = {
                "device_id": payload.get("device_id", session.client_id),
                "device_type": payload.get("device_type", "edge_node"),
                "device_name": payload.get("device_name", f"Node {session.client_id}"),
                "hostname": payload.get("hostname", ""),
                "os_name": payload.get("os_name", "Linux"),
                "architecture": payload.get("architecture", "unknown"),
                "is_headless": payload.get("is_headless", False),
                "has_camera": payload.get("has_camera", False),
                "has_display": payload.get("has_display", False),
                "has_microphone": payload.get("has_microphone", True),
                "battery_level": payload.get("battery_level"),
                "is_charging": payload.get("is_charging"),
                "network_type": payload.get("network_type", "wifi"),
            }
            reg = DeviceRegistration(**reg_data)
            current_state = await sync_manager.register_device(reg)

            # Reply with current state snapshot to newly joined device
            snapshot_env = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYNC,
                type=EventType.STATE_SNAPSHOT,
                payload=current_state.to_snapshot(),
            )
            await self.manager.send_envelope(session.session_id, snapshot_env)

            # Broadcast device registration announcement to all other nodes
            broadcast_env = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYNC,
                type=EventType.DEVICE_REGISTER,
                payload=reg.model_dump(),
            )
            await self.manager.broadcast(broadcast_env)

        elif event_type == EventType.DEVICE_HEARTBEAT:
            dev_id = payload.get("device_id", session.client_id)
            battery_level = payload.get("battery_level")
            is_charging = payload.get("is_charging")
            ip_address = payload.get("ip_address")
            device_name = payload.get("device_name")
            await sync_manager.record_heartbeat(
                dev_id,
                battery_level=battery_level,
                is_charging=is_charging,
                ip_address=ip_address,
                device_name=device_name,
            )
            # Re-broadcast device heartbeat across SYNC channel so desktop and mobile dashboards stay real-time
            heartbeat_env = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYNC,
                type=EventType.DEVICE_HEARTBEAT,
                payload={
                    "device_id": dev_id,
                    "device_name": device_name,
                    "battery_level": battery_level,
                    "is_charging": is_charging,
                    "ip_address": ip_address,
                    "last_heartbeat": time.time(),
                },
            )
            await self.manager.broadcast(heartbeat_env)

        elif event_type == EventType.STATE_SYNC:
            diff = payload.get("diff", payload)
            updated_state = await sync_manager.update_state(diff, source_device_id=session.client_id)

            # Broadcast state sync diff to all nodes
            sync_env = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYNC,
                type=EventType.STATE_SYNC,
                payload={"diff": diff, "version": updated_state.version},
            )
            await self.manager.broadcast(sync_env)

        elif event_type == EventType.STATE_SNAPSHOT:
            snapshot_env = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYNC,
                type=EventType.STATE_SNAPSHOT,
                payload=sync_manager.get_state_snapshot().to_snapshot(),
            )
            await self.manager.send_envelope(session.session_id, snapshot_env)

    async def _send_error(

        self,
        session: ClientSession,
        msg_uuid: str,
        channel: Channel,
        message: str,
    ) -> None:
        """Helper to return a standardized error envelope to a client."""
        err_envelope = ServerEnvelope(
            uuid=msg_uuid,
            channel=channel,
            type=EventType.ERROR,
            status="error",
            payload={"message": message},
        )
        await self.manager.send_envelope(session.session_id, err_envelope)
