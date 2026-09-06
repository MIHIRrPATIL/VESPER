/**
 * VESPER Mobile Notification Dispatcher & Simulation Service.
 *
 * Provides:
 * 1. Preset notification payloads (WhatsApp, Slack, Telegram, Gmail, Critical Server Alert, OTP).
 * 2. Custom notification transmission over Gateway WebSocket Channel.NOTIFY.
 * 3. Inbound notification digest listener for synchronization with Desktop HUD.
 */

import { gatewayClient } from "./gateway";
import { Channel, EventType, MobileNotificationPayload, ServerEnvelope } from "../types/events";

export interface PresetNotification {
  id: string;
  label: string;
  app_name: string;
  package_name: string;
  title: string;
  text: string;
  priority: "URGENT" | "HIGH" | "MEDIUM" | "LOW";
}

export const PRESET_NOTIFICATIONS: PresetNotification[] = [
  {
    id: "preset_whatsapp",
    label: "WhatsApp Message",
    app_name: "WhatsApp",
    package_name: "com.whatsapp",
    title: "Alex Chen",
    text: "Hey! Are you free for a quick 10-min design call today?",
    priority: "HIGH",
  },
  {
    id: "preset_slack",
    label: "Slack Alert",
    app_name: "Slack",
    package_name: "com.slack",
    title: "#devops-alerts",
    text: "Kubernetes pod 'vesper-api-gateway' restarted (OOMKilled, exit code 137).",
    priority: "HIGH",
  },
  {
    id: "preset_gmail",
    label: "Gmail Work Email",
    app_name: "Gmail",
    package_name: "com.google.android.gm",
    title: "Google Cloud Platform",
    text: "Monthly invoice #INV-2026-09 is now available for download.",
    priority: "MEDIUM",
  },
  {
    id: "preset_server_down",
    label: "Urgent Server Alert",
    app_name: "Datadog",
    package_name: "com.datadoghq.app",
    title: "CRITICAL: Server Down",
    text: "Database primary replica connection timeout in region eu-west-1.",
    priority: "URGENT",
  },
  {
    id: "preset_otp",
    label: "Two-Factor Auth OTP",
    app_name: "Messages",
    package_name: "com.google.android.apps.messaging",
    title: "Security Verification",
    text: "Your VESPER verification code is 849201. Valid for 5 minutes.",
    priority: "URGENT",
  },
];

export class MobileNotificationService {
  /**
   * Emits an alert over the active Gateway WebSocket connection.
   */
  public static sendNotification(notif: MobileNotificationPayload): boolean {
    return gatewayClient.sendNotificationRelay({
      package_name: notif.package_name,
      app_name: notif.app_name,
      title: notif.title,
      text: notif.text,
      subtext: notif.subtext,
      priority: notif.priority,
      post_time: Date.now() / 1000.0,
    });
  }

  /**
   * Sends a pre-configured template notification for immediate testing.
   */
  public static sendPreset(presetId: string): boolean {
    const preset = PRESET_NOTIFICATIONS.find((p) => p.id === presetId);
    if (!preset) {
      console.warn(`[NotificationService] Preset '${presetId}' not found.`);
      return false;
    }
    return this.sendNotification({
      package_name: preset.package_name,
      app_name: preset.app_name,
      title: preset.title,
      text: preset.text,
      priority: preset.priority,
    });
  }

  /**
   * Subscribes to inbound notification digests broadcast from the cluster.
   */
  public static onDigest(callback: (digest: any) => void): () => void {
    return gatewayClient.onEnvelope((env: ServerEnvelope) => {
      if (env.channel === Channel.NOTIFY && env.type === EventType.NOTIFICATION_DIGEST) {
        callback(env.payload);
      }
    });
  }
}
