/**
 * VESPER Universal Protocol Types for Mobile Companion (Expo).
 * Strictly mirrors backend schemas from `backend/shared/events.py` and `backend/sync/models.py`.
 */

export enum Channel {
  CONTROL = "CONTROL",
  VOICE = "VOICE",
  GESTURE = "GESTURE",
  NOTIFY = "NOTIFY",
  SYSTEM = "SYSTEM",
  AGENT = "AGENT",
  SYNC = "SYNC",
  VISION = "VISION",
}

export enum ClientType {
  DESK_HUD = "DESK_HUD",
  MOBILE_ANDROID = "MOBILE_ANDROID",
  MOBILE_IOS = "MOBILE_IOS",
  EDGE_ORANGE_PI = "EDGE_ORANGE_PI",
  EDGE_NODE = "EDGE_NODE",
  DEV_TEST = "DEV_TEST",
  UNKNOWN = "UNKNOWN",
}

export enum EventType {
  // Control & Handshake
  CLIENT_HELLO = "CLIENT_HELLO",
  SERVER_HELLO = "SERVER_HELLO",
  PING = "PING",
  PONG = "PONG",

  // Voice & Speech Lifecycle
  WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED",
  WAKE_WORD_TOGGLE = "WAKE_WORD_TOGGLE",
  WAKE_WORD_STATE = "WAKE_WORD_STATE",
  VOICE_COMMAND = "VOICE_COMMAND",
  AGENT_ACTIVATING = "AGENT_ACTIVATING",
  AGENT_RESPONSE = "AGENT_RESPONSE",
  AGENT_SPEAKING = "AGENT_SPEAKING",
  AGENT_IDLE = "AGENT_IDLE",

  // Gestures
  GESTURE_EVENT = "GESTURE_EVENT",
  GESTURE_TOGGLE = "GESTURE_TOGGLE",

  // Vision & Remote Display
  SCREEN_CAPTURE_REQUEST = "SCREEN_CAPTURE_REQUEST",
  SCREEN_CAPTURE_RESPONSE = "SCREEN_CAPTURE_RESPONSE",
  CAMERA_FRAME_STREAM = "CAMERA_FRAME_STREAM",

  // Mobile Notifications
  NOTIFICATION_RELAY = "NOTIFICATION_RELAY",
  NOTIFICATION_DIGEST = "NOTIFICATION_DIGEST",

  // System & Interruption
  SET_VOLUME = "SET_VOLUME",
  ZEN_MODE_STATE = "ZEN_MODE_STATE",
  FOCUS_MODE_STATE = "FOCUS_MODE_STATE",
  MEDIA_CONTROL = "MEDIA_CONTROL",
  INTERRUPT = "INTERRUPT",
  INTERRUPT_ACK = "INTERRUPT_ACK",

  // Cross-Device State Synchronization
  DEVICE_REGISTER = "DEVICE_REGISTER",
  DEVICE_HEARTBEAT = "DEVICE_HEARTBEAT",
  STATE_SYNC = "STATE_SYNC",
  STATE_SNAPSHOT = "STATE_SNAPSHOT",

  // Status / Errors
  ERROR = "ERROR",
  STATUS_UPDATE = "STATUS_UPDATE",
}

export interface ClientEnvelope {
  uuid?: string;
  channel: Channel | string;
  type: EventType | string;
  timestamp?: number;
  payload: Record<string, any>;
}

export interface ServerEnvelope {
  uuid: string;
  channel: Channel | string;
  type: EventType | string;
  timestamp: number;
  status: string; // "ok" | "error" | "interrupted" | "pending"
  payload: Record<string, any>;
}

export interface DeviceRegistration {
  device_id: string;
  device_type: string;
  device_name: string;
  hostname?: string;
  os_name?: string;
  architecture?: string;
  is_headless?: boolean;
  has_camera?: boolean;
  has_display?: boolean;
  has_microphone?: boolean;
  battery_level?: number | null;
  is_charging?: boolean | null;
  network_type?: string;
}

export interface SynchronizedState {
  master_volume: number;
  zen_mode: boolean;
  focus_mode: boolean;
  wakeword_active: boolean;
  optical_sensor_active: boolean;
  active_tasks_count: number;
  unread_notifications_count: number;
  recent_notifications: any[];
  current_media: {
    is_playing: boolean;
    track_title: string;
    artist: string;
    progress_ms: number;
  };
  last_speech_summary: string;
  active_devices: Record<string, DeviceRegistration>;
  version: number;
  updated_at: number;
}

export interface MobileNotificationPayload {
  package_name: string;
  app_name?: string;
  title: string;
  text: string;
  subtext?: string;
  priority?: "URGENT" | "HIGH" | "MEDIUM" | "LOW";
  post_time?: number;
}
