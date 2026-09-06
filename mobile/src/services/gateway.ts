/**
 * VESPER Gateway WebSocket Client for Mobile Companion (Expo).
 *
 * Handles:
 * 1. Persistent connection to FastAPI Gateway (/ws).
 * 2. Automatic exponential backoff reconnection.
 * 3. Handshake (CLIENT_HELLO) & Device Registration with phone name & battery telemetry.
 * 4. PING/PONG heartbeat responses.
 * 5. Channel message demultiplexing and state synchronization.
 */

import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Battery from "expo-battery";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  Channel,
  ClientEnvelope,
  ClientType,
  DeviceRegistration,
  EventType,
  MobileNotificationPayload,
  ServerEnvelope,
  SynchronizedState,
} from "../types/events";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "reconnecting";

type EnvelopeListener = (envelope: ServerEnvelope) => void;
type StateListener = (state: SynchronizedState) => void;
type StatusListener = (status: ConnectionStatus) => void;

class GatewayClient {
  private ws: WebSocket | null = null;
  private gatewayUrl: string = "ws://127.0.0.1:8000/ws";
  private status: ConnectionStatus = "disconnected";
  private clientId: string = `mobile_${Platform.OS}_${Math.random().toString(36).substring(2, 9)}`;
  private deviceName: string = "Mobile Companion";

  private reconnectAttempts = 0;
  private reconnectTimer: any = null;
  private maxReconnectDelay = 16000;

  private envelopeListeners: Set<EnvelopeListener> = new Set();
  private stateListeners: Set<StateListener> = new Set();
  private statusListeners: Set<StatusListener> = new Set();

  private currentState: SynchronizedState | null = null;

  constructor() {
    this.initDeviceInfo();
  }

  private async initDeviceInfo() {
    try {
      const model = Device.modelName || Device.productName || (Platform.OS === "android" ? "Android Device" : "iOS Device");
      const name = Device.deviceName ? `${Device.deviceName} (${model})` : model;
      this.deviceName = name;

      const savedUrl = await AsyncStorage.getItem("vesper_gateway_url");
      if (savedUrl) {
        this.gatewayUrl = savedUrl;
      }
    } catch (e) {
      console.warn("[GatewayClient] Error reading device info:", e);
    }
  }

  public getStatus(): ConnectionStatus {
    return this.status;
  }

  public getGatewayUrl(): string {
    return this.gatewayUrl;
  }

  public getDeviceName(): string {
    return this.deviceName;
  }

  public getState(): SynchronizedState | null {
    return this.currentState;
  }

  public async setGatewayUrl(url: string) {
    this.gatewayUrl = url;
    await AsyncStorage.setItem("vesper_gateway_url", url);
    this.disconnect();
    this.connect();
  }

  public connect(customUrl?: string) {
    if (customUrl) {
      this.gatewayUrl = customUrl;
    }
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.updateStatus(this.reconnectAttempts > 0 ? "reconnecting" : "connecting");

    try {
      console.log(`[GatewayClient] Connecting to ${this.gatewayUrl}...`);
      this.ws = new WebSocket(this.gatewayUrl);

      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
    } catch (err) {
      console.error("[GatewayClient] WebSocket instantiation error:", err);
      this.scheduleReconnect();
    }
  }

  public disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus("disconnected");
  }

  private async handleOpen() {
    console.log("[GatewayClient] WebSocket connected. Sending CLIENT_HELLO...");
    this.reconnectAttempts = 0;
    this.updateStatus("connected");

    // 1. Send CLIENT_HELLO
    const clientType = Platform.OS === "android" ? ClientType.MOBILE_ANDROID : ClientType.MOBILE_IOS;
    const helloEnvelope: ClientEnvelope = {
      channel: Channel.CONTROL,
      type: EventType.CLIENT_HELLO,
      payload: {
        client_id: this.clientId,
        client_type: clientType,
        version: "2.0.0",
        capabilities: ["display", "notification_relay", "battery_telemetry"],
      },
    };
    this.send(helloEnvelope);

    // 2. Fetch battery telemetry
    let batteryLevel: number | null = null;
    let isCharging: boolean | null = null;
    try {
      const level = await Battery.getBatteryLevelAsync();
      batteryLevel = level >= 0 ? Math.round(level * 100) : null;
      const state = await Battery.getBatteryStateAsync();
      isCharging = state === Battery.BatteryState.CHARGING || state === Battery.BatteryState.FULL;
    } catch (e) {
      // Running in environment without battery API (e.g. simulator/web)
      batteryLevel = 85;
      isCharging = false;
    }

    // 3. Send DEVICE_REGISTER
    const regEnvelope: ClientEnvelope = {
      channel: Channel.SYNC,
      type: EventType.DEVICE_REGISTER,
      payload: {
        device_id: this.clientId,
        device_type: Platform.OS === "android" ? "mobile_android" : "mobile_ios",
        device_name: this.deviceName,
        hostname: Device.deviceName || "mobile",
        os_name: Platform.OS === "android" ? "Android" : "iOS",
        architecture: Platform.OS,
        has_display: true,
        has_camera: true,
        has_microphone: true,
        battery_level: batteryLevel,
        is_charging: isCharging,
        network_type: "wifi",
      },
    };
    this.send(regEnvelope);
  }

  private handleMessage(event: WebSocketMessageEvent) {
    try {
      const env: ServerEnvelope = JSON.parse(event.data);

      // Handle PING -> reply PONG
      if (env.channel === Channel.CONTROL && env.type === EventType.PING) {
        this.send({
          channel: Channel.CONTROL,
          type: EventType.PONG,
          payload: { client_id: this.clientId },
        });
        return;
      }

      // Handle State updates
      if (env.channel === Channel.SYNC) {
        if (env.type === EventType.STATE_SNAPSHOT || env.type === EventType.STATE_SYNC) {
          this.currentState = env.payload as SynchronizedState;
          this.notifyStateListeners(this.currentState);
        }
      }

      // Dispatch to all listeners
      this.envelopeListeners.forEach((listener) => {
        try {
          listener(env);
        } catch (e) {
          console.error("[GatewayClient] Error in envelope listener:", e);
        }
      });
    } catch (err) {
      console.warn("[GatewayClient] Malformed frame received:", event.data);
    }
  }

  private handleError(error: any) {
    console.warn("[GatewayClient] WebSocket error:", error?.message || error);
  }

  private handleClose(event: WebSocketCloseEvent) {
    console.log(`[GatewayClient] WebSocket closed (code=${event.code}).`);
    this.ws = null;
    this.scheduleReconnect();
  }

  private scheduleReconnect() {
    this.updateStatus("reconnecting");
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;
    console.log(`[GatewayClient] Reconnecting in ${Math.round(delay / 1000)}s (attempt ${this.reconnectAttempts})...`);

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private updateStatus(newStatus: ConnectionStatus) {
    this.status = newStatus;
    this.statusListeners.forEach((cb) => cb(newStatus));
  }

  public send(envelope: ClientEnvelope): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("[GatewayClient] Cannot send: WebSocket is not open.");
      return false;
    }
    const data = JSON.stringify({
      uuid: envelope.uuid || `mob_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      channel: envelope.channel,
      type: envelope.type,
      timestamp: envelope.timestamp || Date.now() / 1000.0,
      payload: envelope.payload || {},
    });
    this.ws.send(data);
    return true;
  }

  // ── High-Level Action Helpers ───────────────────────────────────────────

  public sendNotificationRelay(payload: MobileNotificationPayload): boolean {
    return this.send({
      channel: Channel.NOTIFY,
      type: EventType.NOTIFICATION_RELAY,
      payload: {
        ...payload,
        device_id: this.clientId,
        device_name: this.deviceName,
        post_time: payload.post_time || Date.now() / 1000.0,
      },
    });
  }

  public setMasterVolume(volume: number): boolean {
    return this.send({
      channel: Channel.SYSTEM,
      type: EventType.SET_VOLUME,
      payload: { volume: Math.max(0, Math.min(100, Math.round(volume))) },
    });
  }

  public toggleZenMode(target?: boolean): boolean {
    return this.send({
      channel: Channel.SYSTEM,
      type: EventType.ZEN_MODE_STATE,
      payload: {
        toggle: target === undefined,
        zen_mode: target !== undefined ? target : !this.currentState?.zen_mode,
      },
    });
  }

  // ── Listener Subscriptions ──────────────────────────────────────────────

  public onEnvelope(listener: EnvelopeListener): () => void {
    this.envelopeListeners.add(listener);
    return () => this.envelopeListeners.delete(listener);
  }

  public onState(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    if (this.currentState) {
      listener(this.currentState);
    }
    return () => this.stateListeners.delete(listener);
  }

  public onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  private notifyStateListeners(state: SynchronizedState) {
    this.stateListeners.forEach((cb) => {
      try {
        cb(state);
      } catch (e) {
        console.error("[GatewayClient] Error notifying state listener:", e);
      }
    });
  }
}

export const gatewayClient = new GatewayClient();
