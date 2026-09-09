import { gatewayService } from './gateway';
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

  // ── Public getters ──────────────────────────────────────────────────────

  get notifications(): readonly MobileNotification[] {
    return this._notifications;
  }

  get alerts(): readonly ProactiveAlert[] {
    return this._alerts;
  }

  get activeAlerts(): readonly ProactiveAlert[] {
    return this._alerts.filter((a) => !a.dismissed);
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

    // Agent response with HUD cards or intent-based content
    if (type === 'AGENT_RESPONSE') {
      const cards: any[] = payload.hud_cards || [];
      const intent = (payload.intent || '').toUpperCase();

      // Explicit HUD cards from the response
      if (cards.length > 0) {
        for (const card of cards) {
          const cardType = this._inferCardType(card.type, intent);
          this._addHudOutput({
            id: crypto.randomUUID(),
            type: cardType,
            title: card.title || intent || 'HUD Output',
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
        this._addHudOutput({
          id: crypto.randomUUID(),
          type: mappedType,
          title: payload.response?.substring(0, 80) || intent,
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
    // Cap at 100 stored notifications
    if (this._notifications.length > 100) {
      this._notifications = this._notifications.slice(0, 100);
    }
    this._notify();
  }

  private _addProactiveAlert(alert: ProactiveAlert): void {
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

  dismissAlert(id: string): void {
    const alert = this._alerts.find((a) => a.id === id);
    if (alert) {
      alert.dismissed = true;
      this._notify();
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
      if (ct.includes('weather')) return 'weather';
      if (ct.includes('youtube') || ct.includes('video')) return 'youtube';
      if (ct.includes('recipe') || ct.includes('cook')) return 'recipe';
      if (ct.includes('transaction') || ct.includes('finance') || ct.includes('bank')) return 'transaction';
      if (ct.includes('spotify') || ct.includes('music') || ct.includes('playlist')) return 'spotify';
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
