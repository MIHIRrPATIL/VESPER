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
  | 'GESTURE_EVENT'
  | 'NOTIFICATION_RELAY'
  | 'NOTIFICATION_DIGEST'
  | 'CALL_STATE'
  | 'ZEN_TIMER_UPDATE'
  | 'STATE_SNAPSHOT'
  | 'STATE_SYNC'
  | 'DEVICE_REGISTER'
  | 'DEVICE_HEARTBEAT'
  | 'DEVICE_OFFLINE'
  | 'PROACTIVE_ALERT'
  | 'PROACTIVE_RESOLVE'
  | 'WORKSTATION_COMMAND_REQ'
  | 'WORKSTATION_COMMAND_RES';

export type AgentState = 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING';

export type NotificationUrgency = 'critical' | 'high' | 'normal' | 'low';

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

export interface SpecialistActionRecord {
  specialist?: string;
  action?: string;
  tool_name?: string;
  parameters?: Record<string, any>;
  status?: string;
  result?: any;
  latency_ms?: number;
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
  eventType?: EventType | string;
  channel?: Channel | string;
  queryId?: string;
  queryText?: string;
  isSingleton?: boolean;
  gesture?: string;
  action?: string;
  specialistActions?: SpecialistActionRecord[];
  navigateTo?: string;
}

// ── Notification Panel Types ────────────────────────────────────────────────

export interface MobileNotification {
  id: string;
  appName: string;
  title: string;
  body: string;
  timestamp: number;
  urgency: NotificationUrgency;
  deviceName?: string;
  isOngoing?: boolean;
  isUpdate?: boolean;
  read: boolean;
}

// ── Proactive Agent Toast Types ─────────────────────────────────────────────

export interface ProactiveAlert {
  id: string;
  title: string;
  body: string;
  appName: string;
  urgency: NotificationUrgency;
  timestamp: number;
  actionRequired?: boolean;
  stagedActionId?: string;
  stagedAction?: Record<string, any>;
  callState?: {
    caller: string;
    state: 'ringing' | 'active' | 'ended';
    phoneNumber?: string;
  };
  dismissed: boolean;
  toastDismissed?: boolean;
  domain?: string;
}

// ── HUD Output Types ────────────────────────────────────────────────────────

export type HudCardType =
  | 'weather'
  | 'youtube'
  | 'recipe'
  | 'transaction'
  | 'spotify'
  | 'briefing'
  | 'email'
  | 'task'
  | 'calendar'
  | 'research'
  | 'github'
  | 'system_status'
  | 'tool_call'
  | 'generic';

export interface HudOutput {
  id: string;
  type: HudCardType;
  title: string;
  timestamp: number;
  intent?: string;
  data: Record<string, any>;
  dismissed: boolean;
}

// ── Live Task Engine Types ──────────────────────────────────────────────────

export interface ApiTask {
  id: string;
  title: string;
  deadline?: string | null;
  done: boolean;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  category: 'today' | 'overdue' | 'upcoming' | 'completed';
  age_label: string;
  tag: string;
  created_at?: string;
  metadata?: Record<string, any>;
}

export interface TaskStats {
  total: number;
  today_count: number;
  overdue_count: number;
  upcoming_count: number;
  completed_count: number;
  pending_count: number;
}

// ── Dynamic Device & Cluster Hardware Types ─────────────────────────────────

export interface ConnectedDevice {
  device_id: string;
  device_type: string;
  device_name: string;
  hostname?: string;
  is_online: boolean;
  last_heartbeat?: number;
  battery_level?: number | null;
  is_charging?: boolean | null;
  network_type?: string;
  cpu_usage_pct?: number;
  has_camera?: boolean;
  has_display?: boolean;
  ip_address?: string;
}

// ── Staged Proactive Actions & Executive Queue ──────────────────────────────

export interface StagedAction {
  action_id: string;
  domain: string;
  title?: string;
  verbatim_text: string;
  status: string;
  urgency?: 'critical' | 'high' | 'normal' | 'low';
  timestamp?: number;
  parameters?: Record<string, any>;
}

export interface CalendarEvent {
  summary: string;
  time: string;
  start?: string;
  end?: string;
  location?: string;
}

export interface NowPlayingTrack {
  title: string;
  artist: string;
  album: string;
  art_url: string;
  is_playing: boolean;
  status: 'Playing' | 'Paused' | 'Stopped';
  duration_ms: number;
  position_ms: number;
}

// ── Personal Finance & Transactions Types ───────────────────────────────────

export interface FinanceAccount {
  id: string;
  user_id: string;
  name: string;
  type: 'bank' | 'cash' | 'credit' | 'wallet';
  balance: number;
  currency: string;
  is_default: boolean;
  metadata?: Record<string, any>;
  updated_at?: string;
}

export interface FinanceTransaction {
  id: string;
  user_id: string;
  type: 'income' | 'expense' | 'transfer';
  amount: number;
  category?: string | null;
  description?: string | null;
  account_id?: string | null;
  to_account_id?: string | null;
  date: string;
  created_at?: string;
  metadata?: Record<string, any>;
}

export interface FinanceDebt {
  id: string;
  user_id: string;
  person: string;
  amount: number;
  direction: 'owe' | 'owed';
  description?: string | null;
  settled: boolean;
  created_at?: string;
  settled_at?: string | null;
  metadata?: Record<string, any>;
}

export interface RecurringTransaction {
  id: string;
  user_id: string;
  name: string;
  amount: number;
  type: 'income' | 'expense' | 'transfer';
  category?: string | null;
  account_id?: string | null;
  to_account_id?: string | null;
  frequency: 'daily' | 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'yearly';
  day_of_month?: number | null;
  day_of_week?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  next_due_date?: string | null;
  last_executed_at?: string | null;
  active: boolean;
  auto_execute: boolean;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface PersonDebtGroup {
  person: string;
  owed_to_user: number;
  user_owes: number;
  net_amount: number;
  debts: FinanceDebt[];
}

export interface FinanceOverview {
  total_net_worth: number;
  bank_balance: number;
  cash_balance: number;
  default_account_id?: string | null;
  default_account_name: string;
  accounts: FinanceAccount[];
  debts: {
    total_owed_to_user: number;
    total_user_owes: number;
    net_debt_position: number;
    people: PersonDebtGroup[];
  };
  monthly_burn: number;
  monthly_income: number;
  monthly_net_savings: number;
  spending_by_category: Record<string, number>;
}

