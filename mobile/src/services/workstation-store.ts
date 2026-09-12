/**
 * VESPER Workstation Reactive State Store for Mobile Companion
 * Parity with Desktop App state management & WebSocket event demultiplexing.
 */

import {
  AgentState,
  ConversationMessage,
  VesperEnvelope,
  ProactiveAlert,
  NowPlayingTrack,
  ConnectedDevice,
  ApiTask,
} from '../types/vesper';
import { gatewayClient } from './gateway';
import { Channel, EventType, ServerEnvelope } from '../types/events';

export type WorkstationView =
  | 'workstation'
  | 'directives'
  | 'agenda'
  | 'ledger'
  | 'services'
  | 'tools'
  | 'logs'
  | 'zen';

export function resolveDeterministicView(
  query?: string,
  explicitTarget?: string,
  hudCards?: any[],
  intent?: string
): WorkstationView | null {
  if (explicitTarget) {
    const norm = explicitTarget.toLowerCase().trim();
    if (norm === 'agenda' || norm === 'tasks' || norm === 'calendar') return 'agenda';
    if (norm === 'finances' || norm === 'transactions' || norm === 'ledger' || norm === 'bank') return 'ledger';
    if (norm === 'workstation' || norm === 'center' || norm === 'overview' || norm === 'cockpit' || norm === 'dashboard') return 'workstation';
    if (norm === 'services' || norm === 'telemetry' || norm === 'swarm' || norm === 'devices') return 'services';
    if (norm === 'tools' || norm === 'emitter') return 'tools';
    if (norm === 'logs' || norm === 'stream' || norm === 'audit') return 'logs';
    if (norm === 'voice' || norm === 'directives' || norm === 'chat') return 'directives';
    if (norm === 'zen' || norm === 'focus' || norm === 'pomodoro') return 'zen';
  }

  const q = (query || '').toLowerCase().trim();
  if (!q) return null;

  if (
    /\b(zen(?:\s+mode)?|focus(?:\s+mode)?|pomodoro(?:\s+timer)?)\b/i.test(q) ||
    /^(open|start|go\s+to|switch\s+to)\s+(?:the\s+)?(zen|focus|pomodoro)/i.test(q)
  ) {
    return 'zen';
  }

  if (
    /\b(workstation(?:\s+page)?|overview(?:\s+page)?|cockpit|dashboard|home\s+page)\b/i.test(q) ||
    /^(open|show|go\s+to|switch\s+to)\s+(the\s+)?workstation/i.test(q)
  ) {
    return 'workstation';
  }

  if (
    /\b(agenda(?:\s+page)?|tasks?(?:\s+page)?|todo(?:\s+page)?|schedule(?:\s+page)?|calendar(?:\s+page)?)\b/i.test(q) ||
    /^(what(?:'s|\s+is)\s+the\s+agenda|open\s+(?:the\s+)?agenda|show\s+(?:the\s+)?agenda|what\s+are\s+my\s+tasks|show\s+(?:my\s+)?tasks|what's\s+on\s+my\s+schedule)/i.test(q)
  ) {
    return 'agenda';
  }

  if (
    /\b(finances?(?:\s+page)?|ledger(?:\s+page)?|transactions?(?:\s+page)?|bank(?:\s+page)?|accounts?(?:\s+page)?|expenses?|spending)\b/i.test(q) ||
    /^(what(?:'s|\s+is)\s+the\s+finances?|open\s+(?:the\s+)?finances?|show\s+(?:the\s+)?finances?|open\s+ledger|show\s+ledger|open\s+transactions)/i.test(q) ||
    q === 'finances' ||
    q === 'finance' ||
    q === 'ledger' ||
    q === 'transactions'
  ) {
    return 'ledger';
  }

  if (
    /\b(services?(?:\s+page)?|telemetry(?:\s+page)?|swarm(?:\s+mesh|\s+page|\s+status)?|hardware(?:\s+page)?|cluster(?:\s+nodes)?)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(services|telemetry|swarm)/i.test(q)
  ) {
    return 'services';
  }

  if (
    /\b(tools?(?:\s+page)?|tool\s+emitter|specialist\s+tools?|emitter\s+deck)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(tools|tool\s+emitter)/i.test(q)
  ) {
    return 'tools';
  }

  if (
    /\b(logs?(?:\s+page)?|audit\s+logs?|event\s+stream(?:\s+page)?|system\s+stream)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(logs|audit|event\s+stream)/i.test(q)
  ) {
    return 'logs';
  }

  if (
    /\b(directives?(?:\s+page)?|voice\s+agent(?:\s+page)?|voice\s+page|chat\s+page|conversation\s+page)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(directives|voice\s+agent|chat)/i.test(q)
  ) {
    return 'directives';
  }

  if (hudCards && hudCards.length > 0) {
    const cardTypes = hudCards.map((c) => (c.type || '').toLowerCase());
    if (cardTypes.some((t) => t.includes('calendar') || t.includes('task') || t.includes('agenda'))) {
      return 'agenda';
    }
    if (cardTypes.some((t) => t.includes('transaction') || t.includes('finance') || t.includes('debt') || t.includes('ledger'))) {
      return 'ledger';
    }
  }

  if (intent) {
    const intUpper = intent.toUpperCase();
    if (intUpper.includes('TASK') || intUpper.includes('AGENDA') || intUpper.includes('CALENDAR')) {
      return 'agenda';
    }
    if (intUpper.includes('FINANC') || intUpper.includes('LEDGER') || intUpper.includes('TRANSACTION')) {
      return 'ledger';
    }
  }

  return null;
}

export type StoreListener = () => void;

class WorkstationStore {
  // Navigation & Core Persona
  public activeView: WorkstationView = 'workstation';
  public agentState: AgentState = 'IDLE';
  public activeHeadline: string = 'What can I help you shape today?';
  public messages: ConversationMessage[] = [];

  // Toggles & System Flags
  public zenMode: boolean = false;
  public isWakeWordArmed: boolean = true;
  private wasWakeWordArmedBeforeTemporaryPTT: boolean | null = null;
  public isCameraActive: boolean = false;
  public masterVolume: number = 70;

  // Overlays & Telemetry
  public hudCards: any[] = [];
  public isHudDrawerOpen: boolean = false;
  public wasHudAutoOpenedByAgent: boolean = false;
  public hudDrawerTitle: string = 'HUD INTELLIGENCE DECK';
  public hudDrawerSubtitle: string = 'Cognitive specialist output & structured execution parameters';
  public proactiveAdvisories: ProactiveAlert[] = [];
  public isAdvisoryDrawerOpen: boolean = false;
  public isClusterModalOpen: boolean = false;

  // Media & Hardware
  public nowPlayingTrack: NowPlayingTrack = {
    title: 'GROOVY VIBES',
    artist: 'Spotify Connect',
    album: 'Ambient Desk Session',
    art_url: '',
    is_playing: false,
    status: 'Paused',
    duration_ms: 210000,
    position_ms: 45000,
  };
  public devices: ConnectedDevice[] = [];
  public tasks: ApiTask[] = [];
  public zenTimer = {
    isRunning: false,
    secondsRemaining: 25 * 60,
    sprintMinutes: 25,
    completedSprints: 0,
    soundscape: 'ocean',
    musicSource: 'ambient',
  };

  private listeners: Set<StoreListener> = new Set();
  private unsubGateway: (() => void) | null = null;

  constructor() {
    this.initDefaultMessages();
    this.bindGateway();
  }

  public subscribe(listener: StoreListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    this.listeners.forEach((l) => {
      try {
        l();
      } catch (e) {
        console.error('[WorkstationStore] Listener error:', e);
      }
    });
  }

  private initDefaultMessages() {
    this.messages = [
      {
        id: 'initial_sys_hello',
        sender: 'system',
        text: 'VESPER Cognitive Mobile Node synchronized. Cluster online.',
        timestamp: Date.now(),
        isSingleton: true,
      },
    ];
  }

  public bindGateway() {
    if (this.unsubGateway) return;

    this.fetchNowPlaying();

    this.unsubGateway = gatewayClient.subscribeEnvelope((envelope: ServerEnvelope) => {
      this.handleIncomingEnvelope(envelope);
    });
  }

  public async fetchNowPlaying(): Promise<NowPlayingTrack | null> {
    try {
      const data = await gatewayClient.fetchNowPlaying();
      if (data && (data.title || data.track_title)) {
        this.nowPlayingTrack = {
          title: data.title || data.track_title,
          artist: data.artist || 'Spotify',
          album: data.album || '',
          art_url: data.art_url || '',
          is_playing: Boolean(data.is_playing),
          status: data.status || (data.is_playing ? 'Playing' : 'Paused'),
          duration_ms: data.duration_ms || 0,
          position_ms: data.position_ms || 0,
        };
        this.notify();
        return this.nowPlayingTrack;
      }
    } catch {
      // Non-blocking
    }
    return null;
  }

  public handleIncomingEnvelope(envelope: ServerEnvelope) {
    const { type, payload } = envelope;

    if (type === 'WAKE_WORD_DETECTED') {
      this.agentState = 'LISTENING';
      this.messages = [
        ...this.messages,
        {
          id: envelope.uuid || Math.random().toString(36),
          sender: 'system',
          text: `Vocal Wake Word Perceived: "${payload?.wake_word || 'Hey Alfred'}"`,
          timestamp: Date.now(),
          intent: 'WAKE_WORD',
          isSingleton: true,
          eventType: 'WAKE_WORD_DETECTED',
          channel: 'VOICE',
        },
      ];
      this.notify();
    } else if (type === 'VOICE_COMMAND') {
      if (payload?.command) {
        this.activeHeadline = payload.command;
        const targetView = resolveDeterministicView(payload.command);
        if (targetView) {
          this.activeView = targetView;
        }
        const last = this.messages[this.messages.length - 1];
        if (!last || last.sender !== 'user' || last.text !== payload.command) {
          this.messages = [
            ...this.messages,
            {
              id: envelope.uuid || Math.random().toString(36),
              sender: 'user',
              text: payload.command,
              timestamp: Date.now(),
              eventType: 'VOICE_COMMAND',
              channel: 'VOICE',
            },
          ];
        }
        this.notify();
      }
    } else if (type === 'AGENT_ACTIVATING') {
      this.agentState = 'THINKING';
      if (payload?.command) {
        this.activeHeadline = payload.command;
        const targetView = resolveDeterministicView(payload.command);
        if (targetView) {
          this.activeView = targetView;
        }
      }
      this.notify();
    } else if (type === 'AGENT_RESPONSE') {
      this.agentState = 'SPEAKING';
      const cards = payload?.hud_cards || [];
      const specialistActions = payload?.specialist_actions || [];

      // Append agent message
      this.messages = [
        ...this.messages,
        {
          id: envelope.uuid || Math.random().toString(36),
          sender: 'agent',
          text: payload?.response || payload?.markdown_body || '',
          markdown: payload?.markdown_body,
          timestamp: Date.now(),
          cards,
          intent: payload?.intent,
          latencyMs: payload?.latency_ms,
          queryId: envelope.uuid,
          queryText: payload?.command,
          specialistActions,
          eventType: 'AGENT_RESPONSE',
          channel: 'AGENT',
          navigateTo: payload?.navigate_to,
        },
      ];

      // Deterministic automatic navigation on emitted response
      const targetView = resolveDeterministicView(
        payload?.command,
        payload?.navigate_to,
        cards,
        payload?.intent
      );
      if (targetView) {
        this.activeView = targetView;
      }

      // Title derivation for HUD drawer
      let derivedTitle = 'HUD INTELLIGENCE DECK';
      let derivedSubtitle = 'Cognitive specialist output & structured parameters';
      const firstCard = cards[0];
      if (firstCard) {
        const cType = (firstCard.type || '').toLowerCase();
        if (cType === 'youtube' || cType.includes('video')) {
          derivedTitle = 'YOUTUBE MEDIA RUNTIME';
          derivedSubtitle = 'Connected video streaming & media playback telemetry';
        } else if (cType === 'spotify') {
          derivedTitle = 'SPOTIFY & VINYL ENGINE';
          derivedSubtitle = 'Active MPRIS media controls & live audio telemetry';
        } else if (cType.includes('email')) {
          derivedTitle = 'UNREAD INBOX & CORRESPONDENCE';
          derivedSubtitle = 'IMAP & Gmail synchronized messages';
        } else if (cType === 'briefing') {
          derivedTitle = 'EXECUTIVE BRIEFING DOSSIER';
          derivedSubtitle = 'Synchronized agenda, correspondence & daily priorities';
        } else if (cType.includes('task') || cType.includes('todo')) {
          derivedTitle = 'ACTIVE TASKS & EXECUTIVE AGENDA';
          derivedSubtitle = 'Deterministic task priorities and daily agenda';
        } else if (cType.includes('calendar')) {
          derivedTitle = 'GOOGLE CALENDAR & APPOINTMENTS';
          derivedSubtitle = 'Two-way synchronized Google Calendar schedule';
        } else if (cType === 'transaction' || cType.includes('finance') || cType.includes('debt')) {
          derivedTitle = 'FINANCIAL LEDGER & ACCOUNTS';
          derivedSubtitle = 'Supabase ledger transactions & financial accounting';
        } else if (cType.includes('research')) {
          derivedTitle = 'DEEP RESEARCH & WEB INTELLIGENCE';
          derivedSubtitle = 'Real-time synthesis and verified citations';
        } else if (cType.includes('github')) {
          derivedTitle = 'GITHUB DEV ENGINE';
          derivedSubtitle = 'Repositories, pull requests & code search';
        } else if (cType === 'weather') {
          derivedTitle = 'ATMOSPHERIC INTELLIGENCE';
          derivedSubtitle = 'Local weather sentry & forecast radar telemetry';
        } else if (firstCard.title) {
          derivedTitle = firstCard.title.toUpperCase();
        }
      }

      this.hudDrawerTitle = derivedTitle;
      this.hudDrawerSubtitle = derivedSubtitle;

      if (cards.length > 0) {
        this.hudCards = cards;
        this.wasHudAutoOpenedByAgent = true;
        this.isHudDrawerOpen = true;
      }

      // HUD close is now driven by the backend AGENT_IDLE event (TTS duration + 5s linger)

      this.notify();
    } else if (type === 'AGENT_SPEAKING') {
      this.agentState = 'SPEAKING';
      this.notify();
    } else if (type === 'AGENT_IDLE') {
      this.agentState = 'IDLE';
      this.checkAndRevertTemporaryPTT();
      if (this.wasHudAutoOpenedByAgent) {
        this.isHudDrawerOpen = false;
        this.wasHudAutoOpenedByAgent = false;
      }
      this.notify();
    } else if (type === 'ZEN_MODE_STATE') {
      const isZen = payload?.zen_mode ?? payload?.enabled;
      if (typeof isZen === 'boolean') {
        this.zenMode = isZen;
        if (isZen) {
          this.activeView = 'zen';
          if (payload?.timer) {
            this.zenTimer = {
              isRunning: Boolean(payload.timer.is_running),
              secondsRemaining: typeof payload.timer.seconds_remaining === 'number' ? payload.timer.seconds_remaining : 25 * 60,
              sprintMinutes: typeof payload.timer.sprint_minutes === 'number' ? payload.timer.sprint_minutes : 25,
              completedSprints: typeof payload.timer.completed_sprints === 'number' ? payload.timer.completed_sprints : 0,
              soundscape: payload.timer.soundscape || 'ocean',
              musicSource: payload.timer.music_source || 'ambient',
            };
          } else {
            this.zenTimer.isRunning = true;
            this.zenTimer.secondsRemaining = this.zenTimer.sprintMinutes * 60;
          }
        } else {
          this.zenTimer.isRunning = false;
          if (this.activeView === 'zen') {
            this.activeView = 'workstation';
          }
        }
        this.messages = [
          ...this.messages,
          {
            id: envelope.uuid || Math.random().toString(36),
            sender: 'system',
            text: `Zen Mode: ${isZen ? 'Engaged (Monastic Focus & Sensory Suppression)' : 'Disengaged'}`,
            timestamp: Date.now(),
            intent: 'ZEN_MODE',
            isSingleton: true,
            eventType: 'ZEN_MODE_STATE',
            channel: 'CONTROL',
          },
        ];
        this.notify();
      }
    } else if (type === 'ZEN_TIMER_UPDATE') {
      const timer = payload?.timer || payload;
      const action = payload?.action;
      if (timer) {
        if (action === 'soundscape') {
          this.zenTimer = {
            ...this.zenTimer,
            soundscape: timer.soundscape || this.zenTimer.soundscape,
            musicSource: timer.music_source || this.zenTimer.musicSource,
          };
        } else {
          this.zenTimer = {
            isRunning: typeof timer.is_running === 'boolean' ? timer.is_running : this.zenTimer.isRunning,
            secondsRemaining: typeof timer.seconds_remaining === 'number' ? timer.seconds_remaining : this.zenTimer.secondsRemaining,
            sprintMinutes: typeof timer.sprint_minutes === 'number' ? timer.sprint_minutes : this.zenTimer.sprintMinutes,
            completedSprints: typeof timer.completed_sprints === 'number' ? timer.completed_sprints : this.zenTimer.completedSprints,
            soundscape: timer.soundscape || this.zenTimer.soundscape,
            musicSource: timer.music_source || this.zenTimer.musicSource,
          };
        }
        this.notify();
      }
    } else if (type === 'SET_VOLUME') {
      if (typeof payload?.volume === 'number') {
        this.masterVolume = payload.volume;
        this.notify();
      }
    } else if (type === 'WAKE_WORD_STATE') {
      const active = typeof payload?.wakeword_active === 'boolean'
        ? payload.wakeword_active
        : typeof payload?.active === 'boolean'
        ? payload.active
        : typeof payload?.enabled === 'boolean'
        ? payload.enabled
        : typeof payload?.is_armed === 'boolean'
        ? payload.is_armed
        : undefined;
      if (typeof active === 'boolean') {
        this.isWakeWordArmed = active;
        this.notify();
      }
    } else if (type === 'STATE_SNAPSHOT' || type === 'STATE_SYNC') {
      const state = payload?.state || payload;
      if (typeof state?.wakeword_active === 'boolean') {
        this.isWakeWordArmed = state.wakeword_active;
      }
      if (typeof state?.zen_mode === 'boolean') {
        this.zenMode = state.zen_mode;
      }
      if (typeof state?.master_volume === 'number') {
        this.masterVolume = state.master_volume;
      }
      this.notify();
    } else if (type === 'MEDIA_CONTROL') {
      const track = payload?.track || payload;
      const title = track?.title || track?.track_title || payload?.title || payload?.track_title;
      if (title) {
        const isPlaying = typeof track?.is_playing === 'boolean'
          ? track.is_playing
          : typeof payload?.is_playing === 'boolean'
          ? payload.is_playing
          : payload?.action !== 'pause';
        this.nowPlayingTrack = {
          title,
          artist: track?.artist || payload?.artist || 'Spotify',
          album: track?.album || payload?.album || 'Now Playing',
          art_url: track?.art_url || payload?.art_url || '',
          is_playing: isPlaying,
          status: track?.status || payload?.status || (isPlaying ? 'Playing' : 'Paused'),
          duration_ms: track?.duration_ms || payload?.duration_ms || 210000,
          position_ms: track?.position_ms || payload?.position_ms || 0,
        };
        this.notify();
      }
    } else if (type === 'PROACTIVE_ALERT' || type === 'NOTIFICATION_RELAY') {
      const alert: ProactiveAlert = {
        id: envelope.uuid || Math.random().toString(36),
        title: payload?.title || 'Cluster Advisory',
        body: payload?.text || payload?.body || 'High-urgency notice from cluster',
        appName: payload?.app_name || payload?.package_name || 'VESPER',
        urgency: payload?.priority?.toLowerCase() || 'normal',
        timestamp: Date.now(),
        actionRequired: Boolean(payload?.action_required),
        stagedActionId: payload?.staged_action_id,
        stagedAction: payload?.staged_action,
        dismissed: false,
      };
      this.proactiveAdvisories = [alert, ...this.proactiveAdvisories.slice(0, 9)];
      this.notify();
    } else if (type === 'PROACTIVE_RESOLVE') {
      const actionIds: string[] = payload?.action_ids || (payload?.action_id ? [payload.action_id] : []);
      if (actionIds.length > 0) {
        this.proactiveAdvisories = this.proactiveAdvisories.filter(
          (a) => !actionIds.includes(a.id) && !(a.stagedActionId && actionIds.includes(a.stagedActionId))
        );
        this.notify();
      }
    } else if (type === 'GESTURE_EVENT') {
      const gestureToken = payload?.gesture || 'GESTURE';
      this.messages = [
        ...this.messages,
        {
          id: envelope.uuid || Math.random().toString(36),
          sender: 'system',
          text: `Perceived Hand Gesture: ${gestureToken}`,
          timestamp: Date.now(),
          intent: 'GESTURE',
          isSingleton: true,
          eventType: 'GESTURE_EVENT',
          channel: 'GESTURE',
        },
      ];
      this.notify();
    }
  }

  // ── Manual View Navigation (Independent on mobile) ─────────────────────────
  public setActiveView(view: WorkstationView) {
    this.activeView = view;
    this.notify();
  }

  // ── User Directive Dispatch ────────────────────────────────────────────────
  public sendUserMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;

    this.activeHeadline = trimmed;
    this.agentState = 'THINKING';

    const target = resolveDeterministicView(trimmed);
    if (target) {
      this.activeView = target;
    } else if (this.activeView === 'workstation') {
      this.activeView = 'directives';
    }

    const userMsgId = Math.random().toString(36);
    this.messages = [
      ...this.messages,
      {
        id: userMsgId,
        sender: 'user',
        text: trimmed,
        timestamp: Date.now(),
        queryId: userMsgId,
        queryText: trimmed,
        eventType: 'VOICE_COMMAND',
        channel: 'VOICE',
      },
    ];
    this.notify();

    gatewayClient.sendVoiceCommand(trimmed);
  }

  // ── System Toggles ─────────────────────────────────────────────────────────
  public toggleWakeWord(explicitTarget?: boolean) {
    const next = explicitTarget !== undefined ? explicitTarget : !this.isWakeWordArmed;
    this.isWakeWordArmed = next;
    gatewayClient.sendWakeWordToggle(next);
    this.notify();
  }

  private checkAndRevertTemporaryPTT() {
    if (this.wasWakeWordArmedBeforeTemporaryPTT === false) {
      this.isWakeWordArmed = false;
      gatewayClient.sendWakeWordToggle(false);
      this.wasWakeWordArmedBeforeTemporaryPTT = null;
    }
  }

  public simulateWakeWord() {
    if (!this.isWakeWordArmed) {
      this.wasWakeWordArmedBeforeTemporaryPTT = false;
      this.isWakeWordArmed = true;
      gatewayClient.sendWakeWordToggle(true);
    }
    this.agentState = 'LISTENING';
    gatewayClient.sendWakeWord('hey alfred', 0.98, 'push_to_talk');
    this.notify();
  }

  public toggleZenMode(explicitTarget?: boolean) {
    const next = explicitTarget !== undefined ? explicitTarget : !this.zenMode;
    this.zenMode = next;
    if (next) {
      this.activeView = 'zen';
      this.zenTimer.isRunning = true;
    } else {
      this.zenTimer.isRunning = false;
      if (this.activeView === 'zen') {
        this.activeView = 'workstation';
      }
    }
    gatewayClient.sendZenModeToggle(next);
    this.notify();
  }

  public sendZenTimerAction(
    action: 'start' | 'pause' | 'reset' | 'preset' | 'soundscape' | 'tick',
    payload: any = {}
  ) {
    if (action === 'start') {
      this.zenTimer.isRunning = true;
    } else if (action === 'pause') {
      this.zenTimer.isRunning = false;
    } else if (action === 'reset') {
      this.zenTimer.isRunning = false;
      this.zenTimer.secondsRemaining = this.zenTimer.sprintMinutes * 60;
    } else if (action === 'preset') {
      this.zenTimer.sprintMinutes = payload.minutes || 25;
      this.zenTimer.secondsRemaining = this.zenTimer.sprintMinutes * 60;
      this.zenTimer.isRunning = true;
    } else if (action === 'soundscape') {
      this.zenTimer.soundscape = payload.soundscape || 'ocean';
      this.zenTimer.musicSource = payload.music_source || (payload.soundscape === 'spotify' ? 'spotify' : 'ambient');
      payload = {
        is_running: this.zenTimer.isRunning,
        seconds_remaining: this.zenTimer.secondsRemaining,
        ...payload,
      };
      if (this.zenTimer.soundscape === 'spotify') {
        this.fetchNowPlaying();
      }
    }
    gatewayClient.sendZenTimerAction(action, payload);
    this.notify();
  }

  public toggleCamera() {
    const next = !this.isCameraActive;
    this.isCameraActive = next;
    gatewayClient.sendCameraToggle(next);
    this.notify();
  }

  public sendInterrupt() {
    this.agentState = 'IDLE';
    this.checkAndRevertTemporaryPTT();
    if (this.wasHudAutoOpenedByAgent || this.isHudDrawerOpen) {
      this.isHudDrawerOpen = false;
      this.wasHudAutoOpenedByAgent = false;
    }
    gatewayClient.sendInterrupt('USER_BARGE_IN');
    this.notify();
  }

  // ── Overlays Control ───────────────────────────────────────────────────────
  public openHudDrawer(cards?: any[], title?: string, subtitle?: string) {
    if (cards) this.hudCards = cards;
    if (title) this.hudDrawerTitle = title;
    if (subtitle) this.hudDrawerSubtitle = subtitle;
    this.wasHudAutoOpenedByAgent = false;
    this.isHudDrawerOpen = true;
    this.notify();
  }

  public closeHudDrawer() {
    this.isHudDrawerOpen = false;
    this.wasHudAutoOpenedByAgent = false;
    this.notify();
  }

  public dismissHudCard(id: string) {
    this.hudCards = this.hudCards.filter((c) => c.id !== id);
    if (this.hudCards.length === 0) {
      this.isHudDrawerOpen = false;
    }
    this.notify();
  }

  public dismissAllHudCards() {
    this.hudCards = [];
    this.isHudDrawerOpen = false;
    this.notify();
  }

  public openClusterModal() {
    this.isClusterModalOpen = true;
    this.notify();
  }

  public closeClusterModal() {
    this.isClusterModalOpen = false;
    this.notify();
  }

  public openAdvisoryDrawer() {
    this.isAdvisoryDrawerOpen = true;
    this.notify();
  }

  public closeAdvisoryDrawer() {
    this.isAdvisoryDrawerOpen = false;
    this.notify();
  }

  public clearAllProactiveAlerts() {
    this.proactiveAdvisories.forEach((a) => {
      if (a.stagedActionId) {
        gatewayClient.resolveProactiveAction(a.stagedActionId, 'dismissed').catch(() => {});
      }
    });
    this.proactiveAdvisories = [];
    this.notify();
  }

  public async dismissProactiveAlert(id: string) {
    const alert = this.proactiveAdvisories.find((a) => a.id === id);
    if (alert?.stagedActionId) {
      gatewayClient.resolveProactiveAction(alert.stagedActionId, 'dismissed').catch(() => {});
    }
    this.proactiveAdvisories = this.proactiveAdvisories.filter((a) => a.id !== id);
    this.notify();
  }

  public async confirmProactiveAlert(id: string) {
    const alert = this.proactiveAdvisories.find((a) => a.id === id);
    if (alert?.stagedActionId) {
      await gatewayClient.resolveProactiveAction(alert.stagedActionId, 'confirmed').catch(() => {});
    }
    this.proactiveAdvisories = this.proactiveAdvisories.filter((a) => a.id !== id);
    this.notify();
  }

  public clearMessages() {
    this.messages = [];
    this.notify();
  }
}

export const workstationStore = new WorkstationStore();
