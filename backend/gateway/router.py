"""VESPER Inbound Message Demultiplexer & Router.

Parses ClientEnvelope frames and routes them to their respective channel handlers:
CONTROL, SYSTEM (including out-of-band INTERRUPT), VOICE, GESTURE, and NOTIFY.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from backend.gateway.connection_manager import ClientSession, ConnectionManager
from backend.gateway.task_registry import TaskRegistry
from backend.shared.config import AGENT_SERVICE_URL
from backend.shared.events import (
    Channel,
    ClientEnvelope,
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
        else:
            logger.warning(f"[ROUTER] Unhandled control event '{event_type}'")

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
            # Broadcast UI state toggles
            is_enabled = payload.get("enabled", payload.get("toggle", True))
            key = "zen_mode" if event_type == EventType.ZEN_MODE_STATE else "focus_mode"
            await sync_manager.update_state({key: is_enabled}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=event_type,
                payload=payload,
            )
            await self.manager.broadcast(broadcast_envelope)

        elif event_type in [EventType.WAKE_WORD_TOGGLE, EventType.WAKE_WORD_STATE]:
            cur_state = sync_manager.get_snapshot().wakeword_active
            if "active" in payload:
                new_state = bool(payload["active"])
            elif "enabled" in payload:
                new_state = bool(payload["enabled"])
            elif "wakeword_active" in payload:
                new_state = bool(payload["wakeword_active"])
            else:
                new_state = not cur_state

            await sync_manager.update_state({"wakeword_active": new_state}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_STATE,
                payload={"wakeword_active": new_state, "source": session.client_id},
            )
            await self.manager.broadcast(broadcast_envelope)


    async def _handle_voice(self, session: ClientSession, envelope: ClientEnvelope) -> None:
        """Handles incoming voice transcripts, wake words, and commands."""
        event_type = envelope.type

        # 1. Wake Word Detected Broadcast
        if event_type == EventType.WAKE_WORD_DETECTED:
            wake_word = envelope.payload.get("wake_word", "hey alfred")
            conf = float(envelope.payload.get("confidence", 1.0))
            logger.info(f"[VOICE] Wake word detected: '{wake_word}' (conf={conf:.2f}) from '{session.client_id}'")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_DETECTED,
                payload={
                    "wake_word": wake_word,
                    "confidence": conf,
                    "state": "LISTENING",
                    "source": session.client_id,
                },
            )
            await self.manager.broadcast(broadcast_envelope)
            return

        command_text = envelope.payload.get("command", "")
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
                fast_path = False
                intent = "CONVERSE"
                latency_ms = 0.0

                try:
                    target_url = f"{AGENT_SERVICE_URL}/query"
                    timeout_config = httpx.Timeout(connect=5.0, read=35.0, write=5.0, pool=5.0)
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
                            fast_path = data.get("fast_path", False)
                            intent = data.get("plan_type", "CONVERSE")
                            latency_ms = data.get("latency_ms", 0.0)
                        else:
                            logger.error(f"[VOICE] Agent returned HTTP {agent_res.status_code}: {agent_res.text}")
                            response_text = "I apologize, sir, but an error occurred within the cognitive swarm."
                            markdown_body = f"**Cognitive Swarm Error**: HTTP {agent_res.status_code}\n\n```\n{agent_res.text[:400]}\n```"
                except Exception as agent_err:
                    err_desc = str(agent_err) or type(agent_err).__name__
                    logger.warning(f"[VOICE] Agent service call failed or unavailable ({err_desc}). Using fallback.")
                    response_text = "I apologize, sir, but the cognitive agent swarm is currently unreachable."
                    markdown_body = f"**Swarm Unreachable**: {err_desc}"

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
                        "fast_path": fast_path,
                        "intent": intent,
                        "status": "processed",
                        "latency_ms": latency_ms,
                    },
                )
                await self.manager.broadcast(response_envelope)

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

                # Maintain SPEAKING status briefly for UI visualizer animation
                await asyncio.sleep(1.5)

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

        if gesture in ("TOGGLE_ZEN", "PEACE_SIGN"):
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

        elif gesture in ("CLOSED_FIST", "MUTE", "PAUSE"):
            # Instant Mute / Pause playback and Mute Wake Word Listener
            _set_system_mute(True)
            _control_media_player("pause")
            cur_state = sync_manager.get_snapshot()
            media_copy = dict(cur_state.current_media)
            media_copy["is_playing"] = False
            await sync_manager.update_state(
                {"master_volume": 0, "current_media": media_copy, "wakeword_active": False},
                source_device_id=session.client_id,
            )
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": 0, "muted": True, "media_action": "pause", "wakeword_active": False},
            )
            await self.manager.broadcast(broadcast_envelope)

            ww_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.VOICE,
                type=EventType.WAKE_WORD_STATE,
                payload={"wakeword_active": False, "action": "pause", "source": "GESTURE:CLOSED_FIST"},
            )
            await self.manager.broadcast(ww_envelope)

        elif gesture in ("OPEN_PALM", "RESUME", "PLAY", "UNMUTE"):
            # Resume playback / Unmute to default level and Rearm Wake Word Listener
            current_vol = sync_manager.get_snapshot().master_volume
            restore_vol = current_vol if current_vol > 0 else 50
            _set_system_mute(False)
            _set_system_volume(restore_vol)
            _control_media_player("play")
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
                payload={"wakeword_active": new_ww, "toggle": True, "source": f"GESTURE:{gesture}"},
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

        elif gesture in ("NEXT_TRACK", "SWIPE_RIGHT"):
            # Next Track playback control
            logger.info(f"[GESTURE] Triggered NEXT_TRACK media control from '{session.client_id}'")
            _control_media_player("next")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload={"action": "next_track", "source": "GESTURE"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("PREV_TRACK", "PREVIOUS_TRACK", "SWIPE_LEFT"):
            # Previous Track playback control
            logger.info(f"[GESTURE] Triggered PREV_TRACK media control from '{session.client_id}'")
            _control_media_player("previous")
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload={"action": "previous_track", "source": "GESTURE"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("THUMB_UP", "VOLUME_UP"):
            # Step Volume Up (+10%)
            current_vol = sync_manager.get_snapshot().master_volume
            new_vol = min(100, current_vol + 10)
            _set_system_mute(False)
            _set_system_volume(new_vol)
            await sync_manager.update_state({"master_volume": new_vol}, source_device_id=session.client_id)
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.SYSTEM,
                type=EventType.SET_VOLUME,
                payload={"volume": new_vol, "direction": "up", "step": 10},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture in ("THUMB_DOWN", "VOLUME_DOWN"):
            # Step Volume Down (-10%)
            current_vol = sync_manager.get_snapshot().master_volume
            new_vol = max(0, current_vol - 10)
            _set_system_volume(new_vol)
            if new_vol == 0:
                _set_system_mute(True)
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

        elif gesture in ("AIR_TAP", "PINCH_TAP", "SELECT"):
            # Air tap / pinch click event
            broadcast_envelope = ServerEnvelope(
                uuid=envelope.uuid,
                channel=Channel.GESTURE,
                type=EventType.GESTURE_EVENT,
                payload={"gesture": "AIR_TAP", "action": "select"},
            )
            await self.manager.broadcast(broadcast_envelope)

        elif gesture.startswith("VOLUME_DIAL:") or gesture.startswith("PINCH_DIAL:"):
            try:
                level = int(gesture.split(":")[1])
                clamped = max(0, min(100, level))
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

        # Ingest and triage alert
        notif = notification_service.ingest_notification(
            payload=payload,
            source_device_id=session.client_id,
            source_device_name=dev_name,
        )

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
                "unread_count": notification_service.get_unread_count(),
            },
        )
        await self.manager.broadcast(hud_envelope)

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
            await sync_manager.record_heartbeat(dev_id)

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
