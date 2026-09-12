import { gatewayService } from './gateway';
import { deviceService } from './device-service';
import {
  VesperEnvelope,
  MobileNotification,
  ProactiveAlert,
  HudOutput,
  HudCardType,
  NotificationUrgency,
} from '../types/vesper';

// ── Listener types ──────────────────────────────────────────────────────────

export type NotificationStoreListener = () => void;

// ── Intent -> HUD card type mapping ─────────────────────────────────────────

const INTENT_TO_HUD_TYPE: Record<string, HudCardType> = {
  WEATHER: 'weather',
  WEATHER_FORECAST: 'weather',
  YOUTUBE: 'youtube',
  PLAY_VIDEO: 'youtube',
  RECIPE: 'recipe',
  COOK: 'recipe',
  FINANCE: 'transaction',
  BANK: 'transaction',
  TRANSFER: 'transaction',
  SPOTIFY: 'spotify',
  PLAY_MUSIC: 'spotify',
  PLAY_SONG: 'spotify',
  PLAY_PLAYLIST: 'spotify',
  MUSIC: 'spotify',
  EMAIL: 'email',
  EMAILS: 'email',
  INBOX: 'email',
  GMAIL: 'email',
  READ_EMAIL: 'email',
  SEARCH_EMAIL: 'email',
  TASK: 'task',
  TASKS: 'task',
  TODO: 'task',
  AGENDA: 'task',
  CALENDAR: 'calendar',
  SCHEDULE: 'calendar',
  BRIEFING: 'briefing',
  MORNING_BRIEFING: 'briefing',
  DESK_RETURN: 'briefing',
  RESEARCH: 'research',
  SEARCH: 'research',
  WEB_SEARCH: 'research',
  GITHUB: 'github',
  SYSTEM: 'system_status',
  STATUS: 'system_status',
  DEVICES: 'system_status',
};

// ── Store ───────────────────────────────────────────────────────────────────

class NotificationStore {
  private _notifications: MobileNotification[] = [];
  private _alerts: ProactiveAlert[] = [];
  private _hudOutputs: HudOutput[] = [];
  private _listeners: Set<NotificationStoreListener> = new Set();
  private _unsubGateway: (() => void) | null = null;

  // Maximum visible toast stack
  public readonly MAX_VISIBLE_TOASTS = 5;

  // Zen Mode state and statistics
  private _zenMode: boolean = false;
  private _heldNotificationsCount: number = 0;

  constructor() {
    if (typeof window !== 'undefined') {
      try {
        const savedNotifs = sessionStorage.getItem('vesper_session_notifications');
        if (savedNotifs) this._notifications = JSON.parse(savedNotifs);
        const savedAlerts = sessionStorage.getItem('vesper_session_alerts');
        if (savedAlerts) this._alerts = JSON.parse(savedAlerts);
        const savedHud = sessionStorage.getItem('vesper_session_hud_outputs');
        if (savedHud) this._hudOutputs = JSON.parse(savedHud);
      } catch (e) {
        console.error('[NotificationStore] Failed to hydrate from sessionStorage:', e);
      }
    }
  }

  // ── Public getters ──────────────────────────────────────────────────────

  get zenMode(): boolean {
    return this._zenMode;
  }

  get heldNotificationsCount(): number {
    return this._heldNotificationsCount;
  }

  setZenMode(enabled: boolean): void {
    if (this._zenMode === enabled) return;
    this._zenMode = enabled;
    if (enabled) {
      this._heldNotificationsCount = 0;
      this.dismissAllToasts();
    }
    this._notify();
  }

  resetZenStats(): void {
    this._heldNotificationsCount = 0;
    this._notify();
  }

  get notifications(): readonly MobileNotification[] {
    return this._notifications;
  }

  get alerts(): readonly ProactiveAlert[] {
    return this._alerts;
  }

  get activeAlerts(): readonly ProactiveAlert[] {
    return this._alerts.filter((a) => !a.dismissed);
  }

  get activeToasts(): readonly ProactiveAlert[] {
    return this._alerts.filter((a) => !a.dismissed && !a.toastDismissed);
  }

  get activeProactiveAlerts(): readonly ProactiveAlert[] {
    return this._alerts.filter(
      (a) => !a.dismissed && (a.actionRequired || !!a.stagedActionId || !!a.stagedAction || a.appName?.toLowerCase().includes('alfred'))
    );
  }

  get pendingProactiveCount(): number {
    return this.activeProactiveAlerts.length;
  }

  get hudOutputs(): readonly HudOutput[] {
    return this._hudOutputs;
  }

  get activeHudOutputs(): readonly HudOutput[] {
    return this._hudOutputs.filter((h) => !h.dismissed);
  }

  get unreadCount(): number {
    return this._notifications.filter((n) => !n.read).length;
  }

  // ── Subscription ────────────────────────────────────────────────────────

  subscribe(listener: NotificationStoreListener): () => void {
    this._listeners.add(listener);
    return () => {
      this._listeners.delete(listener);
    };
  }

  private _notify(): void {
    if (typeof window !== 'undefined') {
      try {
        sessionStorage.setItem('vesper_session_notifications', JSON.stringify(this._notifications));
        sessionStorage.setItem('vesper_session_alerts', JSON.stringify(this._alerts));
        sessionStorage.setItem('vesper_session_hud_outputs', JSON.stringify(this._hudOutputs));
      } catch (e) {
        // Ignore quota limits
      }
    }
    for (const listener of this._listeners) {
      try {
        listener();
      } catch (err) {
        console.error('[NotificationStore] Listener error:', err);
      }
    }
  }

  // ── Gateway integration ─────────────────────────────────────────────────

  connect(): void {
    if (this._unsubGateway) return;
    this._unsubGateway = gatewayService.subscribe((envelope) => {
      this._ingestEnvelope(envelope);
    });
  }

  disconnect(): void {
    if (this._unsubGateway) {
      this._unsubGateway();
      this._unsubGateway = null;
    }
  }

  // ── Envelope classification ─────────────────────────────────────────────

  private _ingestEnvelope(envelope: VesperEnvelope): void {
    const { type, payload } = envelope;

    // Call state -> proactive alert (always high priority)
    if (type === 'CALL_STATE') {
      this._addProactiveAlert({
        id: envelope.uuid || crypto.randomUUID(),
        title: payload.caller || 'Incoming Call',
        body: payload.state === 'ringing'
          ? `Incoming call from ${payload.caller || 'Unknown'}`
          : payload.state === 'ended'
          ? `Call ended`
          : `Call active`,
        appName: 'Phone',
        urgency: 'critical',
        timestamp: Date.now(),
        callState: {
          caller: payload.caller || 'Unknown',
          state: payload.state || 'ringing',
          phoneNumber: payload.phone_number,
        },
        dismissed: false,
      });
      return;
    }

    // Notification digest / relay
    if (type === 'NOTIFICATION_DIGEST' || type === 'NOTIFICATION_RELAY' || envelope.channel === 'NOTIFY') {
      const isProactive = payload.proactive === true;
      const notif = payload.notification || {};

      if (isProactive) {
        this._addProactiveAlert({
          id: envelope.uuid || crypto.randomUUID(),
          title: notif.title || payload.title || 'Alfred',
          body: payload.speech || notif.text || '',
          appName: notif.app_name || 'Alfred Sentry',
          urgency: this._mapUrgency(notif.priority),
          timestamp: Date.now(),
          actionRequired: payload.action_required || false,
          stagedActionId: notif.staged_action_id,
          stagedAction: payload.staged_action,
          dismissed: false,
        });
      } else {
        this._addMobileNotification({
          id: envelope.uuid || crypto.randomUUID(),
          appName: notif.app_name || payload.app_name || 'Unknown',
          title: notif.title || payload.title || '',
          body: notif.text || notif.body || payload.text || '',
          timestamp: Date.now(),
          urgency: this._mapUrgency(notif.priority),
          deviceName: payload.device_name,
          isOngoing: payload.is_ongoing || false,
          isUpdate: payload.is_update || false,
          read: false,
        });
      }
      return;
    }

    // Proactive Advisory Resolution (from voice or backend resolve)
    if (type === 'PROACTIVE_RESOLVE') {
      const actionIds: string[] = payload.action_ids || (payload.action_id ? [payload.action_id] : []);
      if (actionIds.length > 0) {
        let changed = false;
        for (const a of this._alerts) {
          const stagedId = a.stagedActionId || (a.stagedAction as any)?.id || (a.stagedAction as any)?.action_id || a.id;
          if (actionIds.includes(stagedId) || actionIds.includes(a.id)) {
            if (!a.dismissed || !a.toastDismissed) {
              a.dismissed = true;
              a.toastDismissed = true;
              changed = true;
            }
          }
        }
        if (changed) this._notify();
      }
      return;
    }

    // Agent response with HUD cards or intent-based content
    if (type === 'AGENT_RESPONSE') {
      const cards: any[] = payload.hud_cards || [];
      const intent = (payload.intent || '').toUpperCase();

      // Dismiss older active HUD outputs so they don't linger in the drawer
      // when a new response arrives
      if (cards.length > 0 || INTENT_TO_HUD_TYPE[intent]) {
        for (const h of this._hudOutputs) {
          h.dismissed = true;
        }
      }

      // Explicit HUD cards from the response
      if (cards.length > 0) {
        for (const card of cards) {
          const cardType = this._inferCardType(card.type, intent);
          const rawTitle = card.title && card.title !== 'PARALLEL' ? card.title : null;
          const displayTitle =
            rawTitle ||
            (card.name ? (card.type?.includes('playlist') ? `Playlist: ${card.name}` : card.name) : null) ||
            (card.station ? `Radio: ${card.station}` : null) ||
            card.track ||
            card.song ||
            (cardType === 'spotify' ? 'Spotify Playback' : (intent && intent !== 'PARALLEL' ? intent : 'HUD Output'));

          this._addHudOutput({
            id: crypto.randomUUID(),
            type: cardType,
            title: displayTitle,
            timestamp: Date.now(),
            intent,
            data: card.data || card,
            dismissed: false,
          });
        }
        return;
      }

      // Intent-based HUD output (even without explicit cards)
      const mappedType = INTENT_TO_HUD_TYPE[intent];
      if (mappedType) {
        const fallbackTitle = (intent && intent !== 'PARALLEL' ? intent : 'HUD Output');
        this._addHudOutput({
          id: crypto.randomUUID(),
          type: mappedType,
          title: payload.response?.substring(0, 80) || fallbackTitle,
          timestamp: Date.now(),
          intent,
          data: {
            response: payload.response,
            markdown_body: payload.markdown_body,
            ...payload,
          },
          dismissed: false,
        });
      }
    }
  }

  // ── Mutators ────────────────────────────────────────────────────────────

  private _addMobileNotification(notif: MobileNotification): void {
    // Update-in-place if isUpdate
    if (notif.isUpdate) {
      const idx = this._notifications.findIndex(
        (n) => n.appName === notif.appName && n.title === notif.title
      );
      if (idx >= 0) {
        this._notifications[idx] = { ...this._notifications[idx], ...notif, id: this._notifications[idx].id };
        this._notify();
        return;
      }
    }
    this._notifications.unshift(notif);
    // If in Zen mode, increment held notifications count for debriefing
    if (this._zenMode) {
      this._heldNotificationsCount++;
    }
    // Cap at 100 stored notifications
    if (this._notifications.length > 100) {
      this._notifications = this._notifications.slice(0, 100);
    }
    this._notify();
  }

  private _addProactiveAlert(alert: ProactiveAlert): void {
    // If in Zen mode, check for upcoming task / calendar deadline exemption
    if (this._zenMode) {
      const isTaskOrCalendar =
        alert.domain === 'tasks' ||
        alert.domain === 'calendar' ||
        alert.appName?.toLowerCase().includes('calendar') ||
        alert.appName?.toLowerCase().includes('task') ||
        (alert.title && /deadline|due|meeting|starts in|agenda/i.test(alert.title)) ||
        (alert.body && /deadline|due|meeting|starts in|agenda/i.test(alert.body));

      if (!isTaskOrCalendar) {
        // Suppress on-screen toast popup during focus session
        alert.toastDismissed = true;
        this._heldNotificationsCount++;
      }
    }

    this._alerts.unshift(alert);
    // Cap at 50
    if (this._alerts.length > 50) {
      this._alerts = this._alerts.slice(0, 50);
    }
    this._notify();
  }

  private _addHudOutput(output: HudOutput): void {
    this._hudOutputs.unshift(output);
    // Cap at 50
    if (this._hudOutputs.length > 50) {
      this._hudOutputs = this._hudOutputs.slice(0, 50);
    }
    this._notify();
  }

  // ── Public injection (for dev / testing) ──────────────────────────────────

  injectNotification(notif: Partial<MobileNotification>): void {
    this._addMobileNotification({
      id: notif.id || crypto.randomUUID(),
      appName: notif.appName || 'WhatsApp',
      title: notif.title || 'Test Notification',
      body: notif.body || 'This is a test notification message.',
      timestamp: notif.timestamp || Date.now(),
      urgency: notif.urgency || 'normal',
      read: notif.read ?? false,
      deviceName: notif.deviceName,
      isOngoing: notif.isOngoing,
      isUpdate: notif.isUpdate,
    });
  }

  injectAlert(alert: Partial<ProactiveAlert>): void {
    this._addProactiveAlert({
      id: alert.id || crypto.randomUUID(),
      title: alert.title || 'Agent Notice',
      body: alert.body || 'Weather alert: Rain expected in 30 minutes.',
      appName: alert.appName || 'Vesper',
      urgency: alert.urgency || 'normal',
      timestamp: alert.timestamp || Date.now(),
      dismissed: false,
      callState: alert.callState,
    });
  }

  injectHudOutput(output: Partial<HudOutput>): void {
    this._addHudOutput({
      id: output.id || crypto.randomUUID(),
      type: output.type || 'generic',
      title: output.title || 'Output Card',
      intent: output.intent,
      data: output.data || {},
      timestamp: output.timestamp || Date.now(),
      dismissed: false,
    });
  }

  // ── Public actions ──────────────────────────────────────────────────────

  markNotificationRead(id: string): void {
    const notif = this._notifications.find((n) => n.id === id);
    if (notif) {
      notif.read = true;
      this._notify();
    }
  }

  markAllRead(): void {
    let changed = false;
    for (const n of this._notifications) {
      if (!n.read) {
        n.read = true;
        changed = true;
      }
    }
    if (changed) this._notify();
  }

  clearAllNotifications(): void {
    this._notifications = [];
    this._notify();
  }

  dismissToast(id: string): void {
    const alert = this._alerts.find((a) => a.id === id);
    if (alert && !alert.toastDismissed) {
      alert.toastDismissed = true;
      this._notify();
    }
  }

  dismissAllToasts(): void {
    let changed = false;
    for (const a of this._alerts) {
      if (!a.toastDismissed) {
        a.toastDismissed = true;
        changed = true;
      }
    }
    if (changed) this._notify();
  }

  dismissAlert(id: string): void {
    const alert = this._alerts.find((a) => a.id === id);
    if (alert) {
      alert.toastDismissed = true;
      alert.dismissed = true;
      this._notify();
    }
  }

  async resolveAlert(id: string, resolution: 'confirmed' | 'dismissed'): Promise<void> {
    const alert = this._alerts.find((a) => a.id === id);
    if (!alert) return;

    // Instantly dismiss toast and mark resolved in UI
    alert.toastDismissed = true;
    alert.dismissed = true;
    this._notify();

    const stagedId = alert.stagedActionId || (alert.stagedAction as any)?.id || (alert.stagedAction as any)?.action_id;
    if (stagedId) {
      try {
        await deviceService.resolveAction(stagedId, resolution);
      } catch (err) {
        console.warn('[NotificationStore] Failed to resolve staged action on backend:', err);
      }
    }
  }

  dismissAllAlerts(): void {
    let changed = false;
    for (const a of this._alerts) {
      if (!a.dismissed) {
        a.dismissed = true;
        changed = true;
      }
    }
    if (changed) this._notify();
  }

  dismissHudOutput(id: string): void {
    const output = this._hudOutputs.find((h) => h.id === id);
    if (output) {
      output.dismissed = true;
      this._notify();
    }
  }

  dismissAllHudOutputs(): void {
    let changed = false;
    for (const h of this._hudOutputs) {
      if (!h.dismissed) {
        h.dismissed = true;
        changed = true;
      }
    }
    if (changed) this._notify();
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  private _mapUrgency(priority?: string): NotificationUrgency {
    if (!priority) return 'normal';
    const p = priority.toLowerCase();
    if (p === 'critical' || p === 'urgent') return 'critical';
    if (p === 'high' || p === 'important') return 'high';
    if (p === 'low' || p === 'min') return 'low';
    return 'normal';
  }

  private _inferCardType(cardType?: string, intent?: string): HudCardType {
    if (cardType) {
      const ct = cardType.toLowerCase();
      if (ct.includes('email')) return 'email';
      if (ct.includes('task') || ct.includes('todo') || ct.includes('agenda')) return 'task';
      if (ct.includes('calendar') || ct.includes('event')) return 'calendar';
      if (ct.includes('weather')) return 'weather';
      if (ct.includes('youtube') || ct.includes('video')) return 'youtube';
      if (ct.includes('recipe') || ct.includes('cook')) return 'recipe';
      if (ct.includes('transaction') || ct.includes('finance') || ct.includes('bank') || ct.includes('debt') || ct.includes('balance') || ct.includes('goal')) return 'transaction';
      if (ct.includes('spotify') || ct.includes('music') || ct.includes('playlist') || ct.includes('track')) return 'spotify';
      if (ct.includes('briefing')) return 'briefing';
      if (ct.includes('research') || ct.includes('scrape') || ct.includes('crawl')) return 'research';
      if (ct.includes('github') || ct.includes('issue') || ct.includes('commit') || ct.includes('repo')) return 'github';
      if (ct.includes('system') || ct.includes('device') || ct.includes('process') || ct.includes('volume') || ct.includes('battery')) return 'system_status';
      if (ct.includes('tool')) return 'tool_call';
    }
    if (intent) {
      return INTENT_TO_HUD_TYPE[intent.toUpperCase()] || 'generic';
    }
    return 'generic';
  }
}

export const notificationStore = new NotificationStore();

if (typeof window !== 'undefined') {
  (window as any).__notificationStore = notificationStore;
}
