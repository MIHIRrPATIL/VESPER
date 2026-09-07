/**
 * VESPER Gateway WebSocket Client for Mobile Companion (Expo).
 *
 * Handles:
 * 1. Persistent connection to FastAPI Gateway (/ws).
 * 2. Automatic exponential backoff reconnection.
 * 3. Handshake (CLIENT_HELLO) & Device Registration with phone name & battery telemetry.
 * 4. PING/PONG heartbeat responses.
 * 5. Channel message demultiplexing and state synchronization.
 * 6. Offline notification queuing and automatic flush upon connection.
 * 7. REST helpers for notification queries and mutation.
 */

import { AppState, AppStateStatus, Platform } from "react-native";
import * as Device from "expo-device";
import * as Battery from "expo-battery";
import * as Network from "expo-network";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  Channel,
  ClientEnvelope,
  ClientType,
  EventType,
  MobileNotificationPayload,
  ServerEnvelope,
  SynchronizedState,
} from "../types/events";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "reconnecting";

type EnvelopeListener = (envelope: ServerEnvelope) => void;
type StateListener = (state: SynchronizedState) => void;
type StatusListener = (status: ConnectionStatus) => void;
type QueueListener = (count: number) => void;

class GatewayClient {
  private ws: WebSocket | null = null;
  private gatewayUrl: string = Platform.OS === "web" ? "ws://127.0.0.1:8000/ws" : "ws://192.168.0.202:8000/ws";
  private status: ConnectionStatus = "disconnected";
  private clientId: string = `mobile_${Platform.OS}_${Math.random().toString(36).substring(2, 9)}`;
  private deviceName: string = "Mobile Companion";

  private reconnectAttempts = 0;
  private reconnectTimer: any = null;
  private maxReconnectDelay = 16000;
  private lastMessageTimestamp = Date.now();
  private heartbeatSupervisorTimer: any = null;

  private envelopeListeners: Set<EnvelopeListener> = new Set();
  private stateListeners: Set<StateListener> = new Set();
  private statusListeners: Set<StatusListener> = new Set();
  private queueListeners: Set<QueueListener> = new Set();

  private currentState: SynchronizedState | null = null;
  private offlineQueue: MobileNotificationPayload[] = [];

  constructor() {
    this.initDeviceInfo();
    this.loadOfflineQueue();
    this.setupResilienceListeners();
  }

  private setupResilienceListeners() {
    // 1. AppState listener: reconnect immediately when user returns to app or switches back
    try {
      AppState.addEventListener("change", (nextState: AppStateStatus) => {
        console.log(`[GatewayClient] AppState changed to: ${nextState}`);
        if (nextState === "active") {
          if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.log("[GatewayClient] App became active. Initiating fast reconnect...");
            this.reconnectAttempts = 0;
            this.connect();
          }
        }
      });
    } catch (e) {
      console.warn("[GatewayClient] Could not attach AppState listener:", e);
    }

    // 2. Network state listener: reconnect immediately when device regains connectivity
    try {
      Network.addNetworkStateListener(async (event) => {
        console.log(`[GatewayClient] Network state: connected=${event.isConnected}, type=${event.type}`);
        if (event.isConnected) {
          try {
            const localIp = await Network.getIpAddressAsync();
            if (localIp && localIp.includes(".") && !localIp.startsWith("127.")) {
              const currentSubnet = localIp.split(".").slice(0, 3).join(".");
              const match = this.gatewayUrl.match(/\/\/([0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+/);
              if (match && match[1] !== currentSubnet) {
                console.log(`[GatewayClient] Subnet switched to ${currentSubnet}.x. Auto-adapting Gateway initial IP...`);
                this.autoDiscoverInitialGateway();
                return;
              }
            }
          } catch {}

          if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.log("[GatewayClient] Network reconnected. Connecting gateway...");
            this.reconnectAttempts = 0;
            this.connect();
          }
        }
      });
    } catch (e) {
      console.warn("[GatewayClient] Could not attach NetworkState listener:", e);
    }
  }

  private isAutoDiscovering = false;

  public async autoDiscoverInitialGateway(): Promise<string | null> {
    if (this.isAutoDiscovering) return null;
    this.isAutoDiscovering = true;
    try {
      const { SubnetDiscoveryService } = require("./discovery");
      console.log("[GatewayClient] Probing local network to adapt Gateway initial IP...");
      const found = await SubnetDiscoveryService.quickScan(this.gatewayUrl);
      if (found?.wsUrl) {
        console.log(`[GatewayClient] Auto-adapted Gateway URL to active device network: ${found.wsUrl}`);
        this.gatewayUrl = found.wsUrl;
        await AsyncStorage.setItem("vesper_gateway_url", found.wsUrl);
        if (!this.ws || (this.ws.readyState !== WebSocket.OPEN && this.ws.readyState !== WebSocket.CONNECTING)) {
          this.connect(found.wsUrl);
        }
        return found.wsUrl;
      }
    } catch (e) {
      console.warn("[GatewayClient] Dynamic IP auto-discovery notice:", e);
    } finally {
      this.isAutoDiscovering = false;
    }
    return null;
  }

  private async initDeviceInfo() {
    try {
      const model = Device.modelName || Device.productName || (Platform.OS === "android" ? "Android Device" : "iOS Device");
      const name = Device.deviceName ? `${Device.deviceName} (${model})` : model;
      this.deviceName = name;

      const savedUrl = await AsyncStorage.getItem("vesper_gateway_url");
      let subnetMismatched = false;

      // Check current network subnet to ensure saved URL is still valid on this Wi-Fi network
      try {
        const localIp = await Network.getIpAddressAsync();
        if (localIp && localIp.includes(".") && !localIp.startsWith("127.")) {
          const parts = localIp.split(".");
          const currentSubnet = `${parts[0]}.${parts[1]}.${parts[2]}`;
          if (savedUrl) {
            const match = savedUrl.match(/\/\/([0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+/);
            if (match && match[1] !== currentSubnet) {
              console.log(`[GatewayClient] Network subnet changed: device is on ${currentSubnet}.x, savedUrl is ${savedUrl}. Auto-adapting initial IP...`);
              subnetMismatched = true;
            }
          }
        }
      } catch {
        // Network query fallback
      }

      if (savedUrl && !subnetMismatched) {
        this.gatewayUrl = savedUrl;
      } else {
        // Automatically adapt initial Gateway IP to whatever network the device is on
        this.autoDiscoverInitialGateway();
      }
    } catch (e) {
      console.warn("[GatewayClient] Error reading device info:", e);
    }
  }

  private async loadOfflineQueue() {
    try {
      const raw = await AsyncStorage.getItem("vesper_offline_notifications");
      if (raw) {
        this.offlineQueue = JSON.parse(raw);
        this.notifyQueueListeners();
      }
    } catch (e) {
      console.warn("[GatewayClient] Could not load offline queue:", e);
    }
  }

  private async saveOfflineQueue() {
    try {
      await AsyncStorage.setItem("vesper_offline_notifications", JSON.stringify(this.offlineQueue));
      this.notifyQueueListeners();
    } catch (e) {
      console.warn("[GatewayClient] Could not save offline queue:", e);
    }
  }

  public getStatus(): ConnectionStatus {
    return this.status;
  }

  public getGatewayUrl(): string {
    return this.gatewayUrl;
  }

  public getHttpUrl(): string {
    return this.gatewayUrl
      .replace(/^ws:\/\//i, "http://")
      .replace(/^wss:\/\//i, "https://")
      .replace(/\/ws\/?$/, "");
  }

  public getDeviceName(): string {
    return this.deviceName;
  }

  public getState(): SynchronizedState | null {
    return this.currentState;
  }

  public getOfflineQueueCount(): number {
    return this.offlineQueue.length;
  }

  public async setGatewayUrl(url: string) {
    if (this.gatewayUrl === url && this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }
    this.gatewayUrl = url;
    await AsyncStorage.setItem("vesper_gateway_url", url);
    this.reconnectAttempts = 0;
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

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.updateStatus(this.reconnectAttempts > 0 ? "reconnecting" : "connecting");

    try {
      console.log(`[GatewayClient] Connecting to ${this.gatewayUrl}...`);
      const socket = new WebSocket(this.gatewayUrl);
      this.ws = socket;

      socket.onopen = () => {
        if (this.ws === socket) {
          this.handleOpen();
        }
      };
      socket.onmessage = (evt) => {
        if (this.ws === socket) {
          this.handleMessage(evt);
        }
      };
      socket.onerror = (err) => {
        if (this.ws === socket) {
          this.handleError(err);
        }
      };
      socket.onclose = (evt) => {
        if (this.ws === socket) {
          this.handleClose(evt);
        }
      };
    } catch (err) {
      console.error("[GatewayClient] WebSocket instantiation error:", err);
      this.scheduleReconnect();
    }
  }

  public disconnect() {
    this.stopHeartbeatSupervisor();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      const oldWs = this.ws;
      this.ws = null;
      // Detach handlers so closing old socket doesn't fire handleClose -> scheduleReconnect
      oldWs.onopen = null;
      oldWs.onmessage = null;
      oldWs.onerror = null;
      oldWs.onclose = null;
      try {
        oldWs.close();
      } catch {}
    }
    this.updateStatus("disconnected");
  }

  private startHeartbeatSupervisor() {
    this.stopHeartbeatSupervisor();
    this.heartbeatSupervisorTimer = setInterval(() => {
      if (this.status !== "connected" || !this.ws) return;
      const elapsed = Date.now() - this.lastMessageTimestamp;
      if (elapsed > 35000) {
        console.warn(`[GatewayClient] Socket stalled (no traffic for ${Math.round(elapsed / 1000)}s). Forcing reconnect...`);
        this.disconnect();
        this.connect();
      } else if (elapsed > 15000) {
        // Proactive client ping to verify keepalive
        this.send({
          channel: Channel.CONTROL,
          type: EventType.PING,
          payload: { client_id: this.clientId },
        });
      }
    }, 12000);
  }

  private stopHeartbeatSupervisor() {
    if (this.heartbeatSupervisorTimer) {
      clearInterval(this.heartbeatSupervisorTimer);
      this.heartbeatSupervisorTimer = null;
    }
  }

  private async handleOpen() {
    console.log(`[GatewayClient] WebSocket connected. Sending CLIENT_HELLO...`);
    this.reconnectAttempts = 0;
    this.lastMessageTimestamp = Date.now();
    this.startHeartbeatSupervisor();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
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
    } catch {
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

    // 4. Flush offline notification backlog that occurred before connect
    await this.flushOfflineQueue();
  }

  private async flushOfflineQueue() {
    if (this.offlineQueue.length === 0) return;

    console.log(`[GatewayClient] Flushing ${this.offlineQueue.length} offline notifications to Gateway...`);
    const queueToFlush = [...this.offlineQueue];
    this.offlineQueue = [];
    await this.saveOfflineQueue();

    for (const notif of queueToFlush) {
      this.sendNotificationRelay(notif);
      await new Promise((r) => setTimeout(r, 40));
    }
  }

  private handleMessage(event: WebSocketMessageEvent) {
    try {
      this.lastMessageTimestamp = Date.now();
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
    this.stopHeartbeatSupervisor();
    this.ws = null;
    if (event.code !== 1000) {
      this.scheduleReconnect();
    } else {
      this.updateStatus("disconnected");
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.updateStatus("reconnecting");
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;
    console.log(`[GatewayClient] Reconnecting in ${Math.round(delay / 1000)}s (attempt ${this.reconnectAttempts})...`);

    this.reconnectTimer = setTimeout(() => {
      if (this.reconnectAttempts >= 2 && !this.isAutoDiscovering) {
        this.autoDiscoverInitialGateway().then((newUrl) => {
          if (!newUrl) {
            this.connect();
          }
        });
      } else {
        this.connect();
      }
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

  public async postNotificationDirectly(payload: MobileNotificationPayload): Promise<boolean> {
    const baseUrl = this.getHttpUrl();
    const url = `${baseUrl}/api/notifications/relay`;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4500);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          package_name: payload.package_name,
          app_name: payload.app_name,
          title: payload.title,
          text: payload.text,
          subtext: payload.subtext,
          post_time: payload.post_time || Date.now() / 1000.0,
          device_id: this.clientId,
          device_name: this.deviceName,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.ok) {
        console.log(`[GatewayClient] Direct HTTP notification relay successful: "${payload.title}"`);
        return true;
      }
    } catch (e) {
      console.warn("[GatewayClient] Direct HTTP relay failed:", e);
    }
    return false;
  }

  public sendNotificationRelay(payload: MobileNotificationPayload): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
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

    // Dual-path immediate fallback: Send over HTTP POST directly
    this.postNotificationDirectly(payload).then((delivered) => {
      if (!delivered) {
        this.enqueueOfflineNotification(payload);
      }
    });

    // Proactively initiate reconnect if disconnected
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
      this.connect();
    }

    return false;
  }

  private enqueueOfflineNotification(payload: MobileNotificationPayload) {
    const existingIdx = this.offlineQueue.findIndex(
      (item) => item.package_name === payload.package_name && item.title === payload.title
    );
    if (existingIdx >= 0) {
      this.offlineQueue[existingIdx].text = payload.text;
      this.offlineQueue[existingIdx].subtext = payload.subtext;
      this.offlineQueue[existingIdx].post_time = payload.post_time || Date.now() / 1000.0;
      this.saveOfflineQueue();
      return;
    }

    if (this.offlineQueue.length >= 25) {
      this.offlineQueue.shift();
    }

    console.log(`[GatewayClient] Offline: Enqueueing alert "${payload.title}" for auto-sync on reconnect.`);
    this.offlineQueue.push({
      ...payload,
      device_id: this.clientId,
      device_name: this.deviceName,
      post_time: payload.post_time || Date.now() / 1000.0,
    });
    this.saveOfflineQueue();
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

  // ── REST API Integration ────────────────────────────────────────────────

  public async fetchClusterNotifications(limit = 20, unreadOnly = false): Promise<any[]> {
    const baseUrl = this.getHttpUrl();
    const url = `${baseUrl}/api/notifications?limit=${limit}&unread_only=${unreadOnly}`;
    try {
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return data.notifications || [];
    } catch (e) {
      console.warn("[GatewayClient] fetchClusterNotifications failed:", e);
      return [];
    }
  }

  public async markNotificationAsRead(ids: string[]): Promise<boolean> {
    const baseUrl = this.getHttpUrl();
    const url = `${baseUrl}/api/notifications/read`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      return res.ok;
    } catch {
      return false;
    }
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

  public onOfflineQueue(listener: QueueListener): () => void {
    this.queueListeners.add(listener);
    listener(this.offlineQueue.length);
    return () => this.queueListeners.delete(listener);
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

  private notifyQueueListeners() {
    this.queueListeners.forEach((cb) => {
      try {
        cb(this.offlineQueue.length);
      } catch (e) {
        console.error("[GatewayClient] Error notifying queue listener:", e);
      }
    });
  }
}

export const gatewayClient = new GatewayClient();
