import { VesperEnvelope, Channel, EventType, ClientHelloPayload } from '../types/vesper';

export type EnvelopeListener = (envelope: VesperEnvelope) => void;
export type ConnectionStateListener = (connected: boolean, connecting: boolean) => void;

class GatewayClient {
  private ws: WebSocket | null = null;
  private url: string;
  private clientId: string;
  private listeners: Set<EnvelopeListener> = new Set();
  private connectionListeners: Set<ConnectionStateListener> = new Set();
  private isConnecting: boolean = false;
  private shouldReconnect: boolean = true;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 20;
  private reconnectTimeout: number | null = null;

  constructor(url = 'ws://127.0.0.1:8000/ws', clientId = 'vesper-desktop-hud') {
    this.url = url;
    this.clientId = clientId;
  }

  public connect(): void {
    this.shouldReconnect = true;

    if (this.ws) {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.notifyConnectionState(true, false);
        return;
      }
      if (this.ws.readyState === WebSocket.CONNECTING) {
        return;
      }
      try {
        this.ws.onopen = null;
        this.ws.onclose = null;
        this.ws.onerror = null;
        this.ws.onmessage = null;
        this.ws.close();
      } catch (_) {}
      this.ws = null;
    }

    this.isConnecting = true;
    this.notifyConnectionState(false, true);

    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
      this.ws = socket;
    } catch (err) {
      console.error('[GATEWAY] WebSocket initialization error:', err);
      this.isConnecting = false;
      this.notifyConnectionState(false, false);
      this.scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      if (this.ws !== socket) return;
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      console.log('[GATEWAY] Connected to:', this.url);
      this.notifyConnectionState(true, false);
      this.sendHello();
    };

    socket.onmessage = (event: MessageEvent) => {
      if (this.ws !== socket) return;
      try {
        const envelope: VesperEnvelope = JSON.parse(event.data);
        this.handleInboundEnvelope(envelope);
      } catch (err) {
        console.error('[GATEWAY] Failed to parse message frame:', err, event.data);
      }
    };

    socket.onclose = () => {
      if (this.ws !== socket) return;
      this.ws = null;
      this.isConnecting = false;
      this.notifyConnectionState(false, false);
      console.warn('[GATEWAY] Connection closed');
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    socket.onerror = (err) => {
      if (this.ws !== socket) return;
      console.error('[GATEWAY] WebSocket error encountered:', err);
    };
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.notifyConnectionState(false, false);
  }

  public setUrl(newUrl: string): void {
    if (this.url === newUrl) return;
    this.url = newUrl;
    if (this.ws) {
      this.disconnect();
      this.shouldReconnect = true;
      this.connect();
    }
  }

  public getUrl(): string {
    return this.url;
  }

  public subscribe(listener: EnvelopeListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public subscribeConnection(listener: ConnectionStateListener): () => void {
    this.connectionListeners.add(listener);
    const isConnected = this.ws ? this.ws.readyState === WebSocket.OPEN : false;
    listener(isConnected, this.isConnecting);
    return () => {
      this.connectionListeners.delete(listener);
    };
  }

  public send(channel: Channel, type: EventType, payload: Record<string, any> = {}): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[GATEWAY] Cannot send envelope, socket not open:', type);
      return false;
    }

    const envelope: VesperEnvelope = {
      uuid: crypto.randomUUID(),
      channel,
      type,
      timestamp: Date.now() / 1000,
      payload,
    };

    try {
      this.ws.send(JSON.stringify(envelope));
      return true;
    } catch (err) {
      console.error('[GATEWAY] Error sending envelope:', err);
      return false;
    }
  }

  public sendVoiceCommand(command: string): boolean {
    return this.send('VOICE', 'VOICE_COMMAND', {
      command: command.trim(),
      confidence: 1.0,
      is_final: true,
    });
  }

  public sendWakeWord(wakeWord = 'hey alfred', confidence = 0.95): boolean {
    return this.send('VOICE', 'WAKE_WORD_DETECTED', {
      wake_word: wakeWord,
      confidence,
      source: this.clientId,
    });
  }

  public sendGesture(gesture: string, confidence = 0.95, handedness = 'Right'): boolean {
    return this.send('GESTURE', 'GESTURE_EVENT', {
      gesture: gesture.toUpperCase(),
      confidence,
      handedness,
    });
  }

  public sendInterrupt(reason = 'USER_BARGE_IN', targetUuid?: string): boolean {
    return this.send('SYSTEM', 'INTERRUPT', {
      reason,
      priority: 10,
      target_uuid: targetUuid || null,
    });
  }

  public sendSetVolume(volume: number): boolean {
    const clamped = Math.max(0, Math.min(100, Math.round(volume)));
    return this.send('SYSTEM', 'SET_VOLUME', {
      volume: clamped,
    });
  }

  public sendZenModeToggle(): boolean {
    return this.send('SYSTEM', 'ZEN_MODE_STATE', {
      toggle: true,
    });
  }

  public sendWakeWordToggle(active?: boolean): boolean {
    return this.send('VOICE', 'WAKE_WORD_TOGGLE', {
      ...(active !== undefined ? { wakeword_active: active } : { toggle: true }),
    });
  }

  public sendCameraToggle(active?: boolean): boolean {
    return this.send('GESTURE', 'GESTURE_EVENT', {
      gesture: active !== undefined ? (active ? 'GESTURE_RESUME' : 'GESTURE_PAUSE') : 'GESTURE_TOGGLE',
      action: 'toggle_camera_sentry',
    });
  }

  private handleInboundEnvelope(envelope: VesperEnvelope): void {
    // Keepalive ping responder
    if (envelope.channel === 'CONTROL' && envelope.type === 'PING') {
      this.send('CONTROL', 'PONG', {
        reply_to: envelope.uuid,
      });
    }

    // Notify all registered envelope listeners
    for (const listener of this.listeners) {
      try {
        listener(envelope);
      } catch (err) {
        console.error('[GATEWAY] Error in envelope listener:', err);
      }
    }
  }

  private sendHello(): void {
    const helloPayload: ClientHelloPayload = {
      client_id: this.clientId,
      client_type: 'DESK_HUD',
      roles: ['ROLE_HUD_DISPLAY', 'ROLE_VISION_PERCEPTION'],
      capabilities: ['control', 'system', 'voice', 'gesture', 'notify', 'sync'],
      has_camera: true,
      has_display: true,
      has_speaker: true,
      os: 'linux',
      version: '2.0.0',
    };

    this.send('CONTROL', 'CLIENT_HELLO', helloPayload);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[GATEWAY] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts += 1;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 10000);
    console.log(`[GATEWAY] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = window.setTimeout(() => {
      this.connect();
    }, delay);
  }

  private notifyConnectionState(connected: boolean, connecting: boolean): void {
    for (const listener of this.connectionListeners) {
      try {
        listener(connected, connecting);
      } catch (err) {
        console.error('[GATEWAY] Error in connection listener:', err);
      }
    }
  }
}

export const gatewayService = new GatewayClient();
