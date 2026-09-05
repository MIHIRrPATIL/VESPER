export type Channel = 'CONTROL' | 'SYSTEM' | 'VOICE' | 'GESTURE' | 'NOTIFY' | 'SYNC' | 'AGENT';

export type EventType =
  | 'CLIENT_HELLO'
  | 'SERVER_HELLO'
  | 'HELLO_ACK'
  | 'PING'
  | 'PONG'
  | 'INTERRUPT'
  | 'INTERRUPT_ACK'
  | 'SET_VOLUME'
  | 'ZEN_MODE_STATE'
  | 'FOCUS_MODE_STATE'
  | 'MEDIA_CONTROL'
  | 'WAKE_WORD_DETECTED'
  | 'WAKE_WORD_TOGGLE'
  | 'WAKE_WORD_STATE'
  | 'VOICE_COMMAND'
  | 'AGENT_ACTIVATING'
  | 'AGENT_RESPONSE'
  | 'AGENT_SPEAKING'
  | 'AGENT_IDLE'
  | 'GESTURE_EVENT';

export type AgentState = 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING';

export interface VesperEnvelope {
  uuid: string;
  channel: Channel;
  type: EventType;
  timestamp?: number;
  status?: string;
  payload: Record<string, any>;
}

export interface ClientHelloPayload {
  client_id: string;
  client_type?: string;
  capabilities?: string[];
  roles?: string[];
  has_camera?: boolean;
  has_display?: boolean;
  has_speaker?: boolean;
  os?: string;
  version?: string;
}

export interface AgentCard {
  title?: string;
  type?: string;
  content?: string;
  data?: Record<string, any>;
}

export interface ConversationMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  markdown?: string;
  timestamp: number;
  cards?: AgentCard[];
  intent?: string;
  latencyMs?: number;
}
