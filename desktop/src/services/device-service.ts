import { ConnectedDevice, StagedAction, CalendarEvent } from '../types/vesper';

export type DeviceListener = () => void;

const INITIAL_FALLBACK_DEVICES: ConnectedDevice[] = [
  {
    device_id: 'vesper-host-workstation',
    device_type: 'desktop',
    device_name: 'VESPER Host (mihir-arch)',
    hostname: 'mihir-arch',
    is_online: true,
    last_heartbeat: Date.now(),
    battery_level: 69,
    is_charging: true,
    cpu_usage_pct: 5,
    has_display: true,
    has_camera: true,
  },
];

import { gatewayService } from './gateway';

class DeviceService {
  private devices: ConnectedDevice[] = INITIAL_FALLBACK_DEVICES;
  private actions: StagedAction[] = [];
  private events: CalendarEvent[] = [];
  private recentActivities: string[] = [];
  private listeners: Set<DeviceListener> = new Set();
  private baseUrl = 'http://127.0.0.1:8000';
  private pollInterval: number | null = null;

  constructor() {
    this.refreshAll();
    if (typeof window !== 'undefined') {
      this.pollInterval = window.setInterval(() => {
        this.refreshAll();
      }, 15000);

      // Real-time synchronization: subscribe to Gateway WebSocket envelopes on Channel.SYNC
      gatewayService.subscribe((env: any) => {
        if (env.channel === 'SYNC') {
          if (env.type === 'DEVICE_HEARTBEAT' || env.type === 'DEVICE_REGISTER') {
            const payload = env.payload || {};
            const devId = payload.device_id;
            if (devId && devId !== 'mobile_companion_provisioned') {
              const idx = this.devices.findIndex((d) => d.device_id === devId);
              if (idx >= 0) {
                this.devices[idx] = {
                  ...this.devices[idx],
                  is_online: true,
                  last_heartbeat: Date.now(),
                  ...(payload.battery_level !== undefined ? { battery_level: payload.battery_level } : {}),
                  ...(payload.is_charging !== undefined ? { is_charging: payload.is_charging } : {}),
                  ...(payload.ip_address ? { ip_address: payload.ip_address } : {}),
                  ...(payload.device_name ? { device_name: payload.device_name } : {}),
                };
              } else {
                this.devices.push({
                  device_id: devId,
                  device_type: payload.device_type || 'mobile',
                  device_name: payload.device_name || 'VESPER Mobile',
                  hostname: payload.hostname || 'mobile',
                  is_online: true,
                  last_heartbeat: Date.now(),
                  battery_level: payload.battery_level,
                  is_charging: payload.is_charging,
                  ip_address: payload.ip_address,
                  network_type: payload.network_type || 'wifi',
                });
              }

              this.notify();
            }
          } else if (env.type === 'DEVICE_OFFLINE') {
            const devId = env.payload?.device_id;
            if (devId) {
              this.devices = this.devices.filter((d) => d.device_id !== devId);
              this.notify();
            }
          }
        }
      });
    }
  }

  public subscribe(listener: DeviceListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((cb) => {
      try {
        cb();
      } catch (err) {
        console.error('[DEVICE SERVICE] Listener error:', err);
      }
    });
  }

  public getDevices(): ConnectedDevice[] {
    return this.devices;
  }

  public getOnlineCount(): number {
    return this.devices.filter((d) => d.is_online).length;
  }

  public getStagedActions(): StagedAction[] {
    return this.actions;
  }

  public getEvents(): CalendarEvent[] {
    return this.events;
  }

  public getRecentActivities(): string[] {
    return this.recentActivities;
  }

  public async refreshAll(): Promise<void> {
    await Promise.allSettled([
      this.fetchDevices(),
      this.fetchStagedActions(),
      this.fetchBriefingEvents(),
    ]);
  }

  public async fetchDevices(): Promise<void> {
    try {
      const res = await fetch(`${this.baseUrl}/sync/devices`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        const seen = new Set<string>();
        const parsed: ConnectedDevice[] = [];
        for (const d of data) {
          const id = d.device_id || 'unknown_device';
          if (seen.has(id)) continue;
          if (id === 'mobile_companion_provisioned') continue;
          if (d.is_online === false) continue;
          seen.add(id);
          parsed.push({
            device_id: id,
            device_type: d.device_type || 'edge',
            device_name: d.device_name || d.hostname || 'VESPER Node',
            hostname: d.hostname,
            is_online: true,
            last_heartbeat: d.last_heartbeat ? d.last_heartbeat * 1000 : Date.now(),
            battery_level: d.battery_level,
            is_charging: d.is_charging,
            network_type: d.network_type,
            cpu_usage_pct: d.cpu_usage_pct,
            has_camera: d.has_camera,
            has_display: d.has_display,
            ip_address: d.ip_address,
          });
        }
        const hasHost = parsed.some(
          (d) => d.device_type === 'desktop' || d.device_id === 'vesper-host-workstation'
        );
        if (!hasHost) {
          parsed.unshift(INITIAL_FALLBACK_DEVICES[0]);
        }
        this.devices = parsed;
        this.notify();
      }
    } catch (_) {
      // Keep resilient fallback
    }
  }

  public async fetchStagedActions(): Promise<void> {
    try {
      const res = await fetch(`${this.baseUrl}/sync/proactive/actions/active`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        this.actions = data.map((a: any) => ({
          action_id: a.action_id,
          domain: a.domain || 'general',
          title: a.title,
          verbatim_text: a.verbatim_text || a.prompt || '',
          status: a.status || 'pending',
          urgency: a.urgency || 'normal',
          timestamp: a.timestamp ? a.timestamp * 1000 : Date.now(),
          parameters: a.parameters,
        }));
        this.notify();
      }
    } catch (_) {
      // Keep resilient fallback
    }
  }

  public async fetchBriefingEvents(): Promise<void> {
    try {
      const res = await fetch(`${this.baseUrl}/briefing`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (Array.isArray(data.hud_cards) && data.hud_cards.length > 0) {
        const card = data.hud_cards[0];
        if (Array.isArray(card.events) && card.events.length > 0) {
          this.events = card.events.map((e: any) => ({
            summary: e.summary || 'Scheduled Event',
            time: e.time || 'Today',
            start: e.start,
            end: e.end,
            location: e.location,
          }));
        } else {
          this.events = [];
        }
        if (Array.isArray(card.recent_activities)) {
          this.recentActivities = card.recent_activities;
        }
        this.notify();
      }
    } catch (_) {
      // Keep resilient fallback
    }
  }

  public async resolveAction(actionId: string, resolution: 'confirmed' | 'dismissed'): Promise<void> {
    // 1. Optimistically remove from state
    this.actions = this.actions.filter((a) => a.action_id !== actionId);
    this.notify();

    // 2. Transmit to Gateway
    try {
      await fetch(`${this.baseUrl}/sync/proactive/actions/${actionId}/resolve?new_status=${resolution}&confirmed_by=desktop_cockpit`, {
        method: 'POST',
      });
    } catch (err) {
      console.warn('[DEVICE SERVICE] Resolve action failed:', err);
    }
  }

  public destroy(): void {
    if (this.pollInterval !== null) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.listeners.clear();
  }
}

export const deviceService = new DeviceService();
