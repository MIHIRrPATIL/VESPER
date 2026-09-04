"""VESPER Universal Event Schemas & Channel Envelopes.

Defines Pydantic v2 models for client-to-server and inter-service IPC.
All payloads use `extra="allow"` for forward compatibility as modules evolve.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ── Channels ─────────────────────────────────────────────────────────────
class Channel(str, Enum):
    CONTROL = "CONTROL"
    VOICE = "VOICE"
    GESTURE = "GESTURE"
    NOTIFY = "NOTIFY"
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"
    SYNC = "SYNC"


# ── Client Types ─────────────────────────────────────────────────────────
class ClientType(str, Enum):
    DESK_HUD = "DESK_HUD"
    MOBILE_ANDROID = "MOBILE_ANDROID"
    MOBILE_IOS = "MOBILE_IOS"
    EDGE_ORANGE_PI = "EDGE_ORANGE_PI"
    EDGE_NODE = "EDGE_NODE"
    DEV_TEST = "DEV_TEST"
    UNKNOWN = "UNKNOWN"


# ── Standard Event Types ─────────────────────────────────────────────────
class EventType(str, Enum):
    # Control & Handshake
    CLIENT_HELLO = "CLIENT_HELLO"
    SERVER_HELLO = "SERVER_HELLO"
    PING = "PING"
    PONG = "PONG"

    # Voice & Speech
    VOICE_COMMAND = "VOICE_COMMAND"
    VOICE_AUDIO_CHUNK = "VOICE_AUDIO_CHUNK"
    AGENT_RESPONSE = "AGENT_RESPONSE"

    # Gestures
    GESTURE_EVENT = "GESTURE_EVENT"

    # Mobile Notifications
    NOTIFICATION_RELAY = "NOTIFICATION_RELAY"
    NOTIFICATION_DIGEST = "NOTIFICATION_DIGEST"

    # System & Interruption
    SET_VOLUME = "SET_VOLUME"
    ZEN_MODE_STATE = "ZEN_MODE_STATE"
    FOCUS_MODE_STATE = "FOCUS_MODE_STATE"
    MEDIA_CONTROL = "MEDIA_CONTROL"
    INTERRUPT = "INTERRUPT"
    INTERRUPT_ACK = "INTERRUPT_ACK"

    # Cross-Device State Synchronization
    DEVICE_REGISTER = "DEVICE_REGISTER"
    DEVICE_HEARTBEAT = "DEVICE_HEARTBEAT"
    STATE_SYNC = "STATE_SYNC"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"

    # Status / Errors
    ERROR = "ERROR"
    STATUS_UPDATE = "STATUS_UPDATE"



# ── Base Extensible Payload ──────────────────────────────────────────────
class BasePayload(BaseModel):
    """Base model allowing arbitrary extra fields for evolutionary flexibility."""
    model_config = ConfigDict(extra="allow")


# ── Universal Envelopes ──────────────────────────────────────────────────
class ClientEnvelope(BaseModel):
    """Standard message received from a connected client (HUD / Mobile)."""
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: Channel
    type: EventType | str
    timestamp: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ServerEnvelope(BaseModel):
    """Standard message emitted by the Gateway to clients."""
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: Channel
    type: EventType | str
    timestamp: float = Field(default_factory=time.time)
    status: str = "ok"  # "ok" | "error" | "interrupted" | "pending"
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


# ── Typed Payload Models (Extensible Helpers) ────────────────────────────

class ClientHelloPayload(BasePayload):
    client_id: str
    client_type: ClientType = ClientType.UNKNOWN
    version: str = "2.0.0"
    capabilities: list[str] = Field(default_factory=list)


class ServerHelloPayload(BasePayload):
    status: str = "authenticated"
    session_id: str
    heartbeat_interval_ms: int = 15000
    server_version: str = "2.0.0"


class PingPayload(BasePayload):
    server_time: float = Field(default_factory=time.time)


class PongPayload(BasePayload):
    client_time: float = Field(default_factory=time.time)


class VoiceCommandPayload(BasePayload):
    command: str
    is_final: bool = True
    confidence: float = 1.0
    image: Optional[str] = None  # Base64 snapshot if vision context is attached


class AudioChunkPayload(BasePayload):
    chunk_index: int = 0
    is_final: bool = False
    format: str = "mp3"  # "mp3" | "pcm" | "wav"
    audio_data: str  # Base64-encoded audio slice


class GestureEventPayload(BasePayload):
    gesture: str  # e.g., "TOGGLE_ZEN", "MUTE", "VOLUME_DIAL:65"
    source: str = "WEBCAM_WORKER"
    confidence: float = 1.0


class NotificationRelayPayload(BasePayload):
    package_name: str
    sender: str
    title: str
    text: str
    is_priority_contact: bool = False


class InterruptPayload(BasePayload):
    target_uuid: Optional[str] = None  # UUID of the active task to cancel (or None for all)
    reason: str = "USER_BARGE_IN"


class SystemVolumePayload(BasePayload):
    volume: int = Field(ge=0, le=100)


class ToggleStatePayload(BasePayload):
    enabled: bool


class ErrorPayload(BasePayload):
    message: str
    code: str = "GENERAL_ERROR"
    details: Optional[dict[str, Any]] = None
