import React, { useEffect, useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StatusBar,
  Switch,
  ActivityIndicator,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { gatewayClient, ConnectionStatus } from "../services/gateway";
import { MobileNotificationService, PRESET_NOTIFICATIONS } from "../services/notifications";
import { SubnetDiscoveryService, DiscoveredGateway } from "../services/discovery";
import { SynchronizedState, EventType } from "../types/events";
import { AlfredService } from "../../modules/alfred-service";

export default function HomeScreen() {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [gatewayUrl, setGatewayUrl] = useState<string>(gatewayClient.getGatewayUrl());
  const [deviceName, setDeviceName] = useState<string>("Mobile Companion");
  const [state, setState] = useState<SynchronizedState | null>(null);

  // Discovery state
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanProgress, setScanProgress] = useState<string>("");

  // Offline queue state
  const [offlineCount, setOfflineCount] = useState<number>(0);

  // Live OS notification permission state
  const [hasNotificationAccess, setHasNotificationAccess] = useState<boolean>(false);

  // Historical notifications
  const [clusterNotifications, setClusterNotifications] = useState<any[]>([]);
  const [isLoadingClusterNotifs, setIsLoadingClusterNotifs] = useState<boolean>(false);

  // Custom alert form
  const [customTitle, setCustomTitle] = useState("");
  const [customText, setCustomText] = useState("");
  const [customApp, setCustomApp] = useState("WhatsApp");

  // Alfred persistent foreground service state
  const [isAlfredServiceRunning, setIsAlfredServiceRunning] = useState<boolean>(false);

  // Event feed log
  const [eventLogs, setEventLogs] = useState<Array<{ id: string; time: string; text: string; channel: string }>>([]);

  useEffect(() => {
    // 1. Initial info
    setGatewayUrl(gatewayClient.getGatewayUrl());
    setDeviceName(gatewayClient.getDeviceName());
    setOfflineCount(gatewayClient.getOfflineQueueCount());
    checkNotificationPermission();

    // 2. Status subscription
    const unsubStatus = gatewayClient.onStatus((newStatus) => {
      setStatus(newStatus);
      if (newStatus === "connected") {
        fetchHistory();
      }
    });

    // 3. State subscription
    const unsubState = gatewayClient.onState((newState) => {
      setState(newState);
      if (newState?.recent_notifications && newState.recent_notifications.length > 0) {
        setClusterNotifications(newState.recent_notifications);
      }
    });

    // 4. Offline queue subscription
    const unsubQueue = gatewayClient.onOfflineQueue((count) => {
      setOfflineCount(count);
    });

    // 5. Envelope log subscription with unique key generator
    const unsubEnvelope = gatewayClient.onEnvelope((env) => {
      // Don't clutter the UI wire with routine heartbeat pings
      if (env.type === EventType.PING || env.type === EventType.PONG) {
        return;
      }

      const timeStr = new Date().toLocaleTimeString();
      let summary = `${env.channel} : ${env.type}`;
      if (env.channel === "NOTIFY" && env.payload?.notification) {
        summary += ` | [${env.payload.notification.priority}] ${env.payload.notification.app_name}: ${env.payload.notification.title}`;
      } else if (env.channel === "SYSTEM" && env.type === "SET_VOLUME") {
        summary += ` | Volume -> ${env.payload.volume}%`;
      }
      const uniqueId = `evt_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      setEventLogs((prev) => [{ id: uniqueId, time: timeStr, text: summary, channel: String(env.channel) }, ...prev.slice(0, 19)]);
    });

    // 6. Check and auto-start Alfred persistent foreground service on Android
    if (Platform.OS === "android") {
      AlfredService.isServiceRunning().then((running) => {
        setIsAlfredServiceRunning(running);
        if (!running) {
          AlfredService.startService(
            "Alfred (VESPER Nexus)",
            "Alfred is vigilantly standing watch, sir."
          ).then((started) => {
            if (started) setIsAlfredServiceRunning(true);
          }).catch(() => {});
        }
      }).catch(() => {});
    }

    // Connect automatically
    gatewayClient.connect();

    return () => {
      unsubStatus();
      unsubState();
      unsubQueue();
      unsubEnvelope();
    };
  }, []);

  const checkNotificationPermission = async () => {
    if (Platform.OS === "android") {
      try {
        const listener = require("react-native-android-notification-listener");
        if (listener?.default?.getPermissionStatus) {
          const perm = await listener.default.getPermissionStatus();
          setHasNotificationAccess(perm === "authorized");
        }
      } catch {
        setHasNotificationAccess(false);
      }
    }
  };

  const handleRequestNotificationPermission = () => {
    if (Platform.OS === "android") {
      try {
        const listener = require("react-native-android-notification-listener");
        if (listener?.default?.requestPermission) {
          listener.default.requestPermission();
        }
      } catch {
        alert("Native notification access requires an installed Android APK build.");
      }
    }
  };

  const handleToggleAlfredService = async () => {
    if (Platform.OS !== "android") {
      alert("Foreground service requires Android standalone build.");
      return;
    }
    if (isAlfredServiceRunning) {
      await AlfredService.stopService();
      setIsAlfredServiceRunning(false);
    } else {
      const ok = await AlfredService.startService(
        "Alfred (VESPER Nexus)",
        "Alfred is vigilantly standing watch, sir."
      );
      setIsAlfredServiceRunning(ok);
    }
  };

  const handleRequestBatteryExemption = async () => {
    if (Platform.OS !== "android") {
      alert("Battery optimization settings apply to Android devices.");
      return;
    }
    await AlfredService.requestIgnoreBatteryOptimizations();
  };

  const handleConnect = () => {
    gatewayClient.setGatewayUrl(gatewayUrl.trim());
  };

  const handleAutoDiscover = async (mode: "auto" | "quick" | "corporate" = "auto") => {
    if (isScanning) return;
    setIsScanning(true);
    const modeLabel =
      mode === "quick"
        ? "Running Quick Scan (<500ms)..."
        : mode === "corporate"
        ? "Running Corporate / Campus Subnet Sweep..."
        : "Running Hybrid Discovery...";
    setScanProgress(modeLabel);

    try {
      const discovered: DiscoveredGateway | null = await SubnetDiscoveryService.discoverHybrid(
        mode,
        (scanned, total, currentIp) => {
          setScanProgress(`Sweeping Subnet (${scanned}/${total}): ${currentIp}...`);
        },
        undefined,
        gatewayUrl
      );

      if (discovered) {
        setGatewayUrl(discovered.wsUrl);
        setScanProgress(`Found gateway at ${discovered.ip}:${discovered.port}! Connecting...`);
        await gatewayClient.setGatewayUrl(discovered.wsUrl);
      } else {
        setScanProgress(
          mode === "quick"
            ? "Quick scan finished with no match. Try 'Campus / Subnet Sweep'."
            : "No VESPER gateway detected on local subnet. Verify Wi-Fi or enter IP manually."
        );
      }
    } catch (err: any) {
      setScanProgress(`Scan error: ${err?.message || "Unknown error"}`);
    } finally {
      setIsScanning(false);
    }
  };

  const fetchHistory = async () => {
    setIsLoadingClusterNotifs(true);
    try {
      const notifs = await gatewayClient.fetchClusterNotifications(25, false);
      if (notifs && notifs.length > 0) {
        setClusterNotifications(notifs);
      }
    } finally {
      setIsLoadingClusterNotifs(false);
    }
  };

  const handleSendPreset = (presetId: string) => {
    MobileNotificationService.sendPreset(presetId);
  };

  const handleSendCustom = () => {
    if (!customTitle.trim() || !customText.trim()) {
      return;
    }
    MobileNotificationService.sendNotification({
      package_name: customApp === "WhatsApp" ? "com.whatsapp" : customApp === "Slack" ? "com.slack" : "com.app.custom",
      app_name: customApp,
      title: customTitle.trim(),
      text: customText.trim(),
    });
    setCustomTitle("");
    setCustomText("");
  };

  const handleVolumeChange = (delta: number) => {
    const cur = state?.master_volume ?? 50;
    gatewayClient.setMasterVolume(cur + delta);
  };

  const getStatusColor = () => {
    switch (status) {
      case "connected":
        return "#10B981"; // Emerald
      case "connecting":
      case "reconnecting":
        return "#F59E0B"; // Amber
      default:
        return "#EF4444"; // Red
    }
  };

  const getPriorityBadgeStyle = (priority: string) => {
    switch (priority) {
      case "URGENT":
        return { backgroundColor: "rgba(239, 68, 68, 0.2)", borderColor: "#EF4444", textColor: "#F87171" };
      case "HIGH":
        return { backgroundColor: "rgba(245, 158, 11, 0.2)", borderColor: "#F59E0B", textColor: "#FBBF24" };
      case "MEDIUM":
        return { backgroundColor: "rgba(59, 130, 246, 0.2)", borderColor: "#3B82F6", textColor: "#60A5FA" };
      default:
        return { backgroundColor: "rgba(100, 116, 139, 0.2)", borderColor: "#64748B", textColor: "#94A3B8" };
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor="#0F172A" />
      <ScrollView contentContainerStyle={styles.container}>
        {/* Title Header */}
        <View style={styles.header}>
          <Text style={styles.appTitle}>VESPER Mobile Companion</Text>
          <Text style={styles.deviceSubtitle}>{deviceName}</Text>
        </View>

        {/* Connection Box */}
        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardHeader}>Cluster Gateway</Text>
            <View style={[styles.statusBadge, { backgroundColor: getStatusColor() }]}>
              <Text style={styles.statusText}>{status.toUpperCase()}</Text>
            </View>
          </View>

          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              value={gatewayUrl}
              onChangeText={setGatewayUrl}
              placeholder="ws://192.168.0.xxx:8000/ws"
              placeholderTextColor="#64748B"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TouchableOpacity style={styles.primaryButton} onPress={handleConnect}>
              <Text style={styles.buttonText}>Connect</Text>
            </TouchableOpacity>
          </View>

          {/* Hybrid Auto-Discovery Buttons */}
          <View style={styles.discoveryButtonsRow}>
            <TouchableOpacity
              style={[styles.discoveryButtonHalf, isScanning && styles.buttonDisabled]}
              onPress={() => handleAutoDiscover("quick")}
              disabled={isScanning}
            >
              {isScanning ? (
                <ActivityIndicator size="small" color="#38BDF8" />
              ) : (
                <Text style={styles.buttonTextSecondary}>Quick Scan (Home)</Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.discoveryButtonHalf, isScanning && styles.buttonDisabled]}
              onPress={() => handleAutoDiscover("corporate")}
              disabled={isScanning}
            >
              {isScanning ? (
                <ActivityIndicator size="small" color="#38BDF8" />
              ) : (
                <Text style={styles.buttonTextSecondary}>Campus / Subnet Sweep</Text>
              )}
            </TouchableOpacity>
          </View>
          {scanProgress !== "" && <Text style={styles.scanFeedback}>{scanProgress}</Text>}

          {/* Offline Queue Notice */}
          {offlineCount > 0 && (
            <View style={styles.offlineBanner}>
              <Text style={styles.offlineBannerText}>
                {offlineCount} notification(s) stored in offline queue. Will sync automatically upon connection.
              </Text>
            </View>
          )}
        </View>

        {/* Live OS Notification Interception Service Card */}
        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardHeader}>Live OS Notification Interception</Text>
            <View
              style={[
                styles.statusBadge,
                { backgroundColor: hasNotificationAccess ? "#10B981" : "#F59E0B" },
              ]}
            >
              <Text style={styles.statusText}>
                {hasNotificationAccess ? "ACTIVE" : "PERMISSION REQUIRED"}
              </Text>
            </View>
          </View>
          <Text style={styles.helpText}>
            {hasNotificationAccess
              ? "NotificationListenerService is active. Incoming alerts from third-party apps (WhatsApp, SMS, Slack, etc.) are intercepted in real time and forwarded to VESPER."
              : "To capture real notifications arriving on this phone from other apps, grant Notification Access in Android Settings. (Requires installed APK)."}
          </Text>
          <View style={styles.rowBetween}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={handleRequestNotificationPermission}
            >
              <Text style={styles.buttonTextSecondary}>Open Notification Access Settings</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.smallButton} onPress={checkNotificationPermission}>
              <Text style={styles.buttonText}>Refresh Status</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Alfred Persistent Background Butler & Battery Shield */}
        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardHeader}>Alfred Persistent Vigilance</Text>
            <View
              style={[
                styles.statusBadge,
                { backgroundColor: isAlfredServiceRunning ? "#10B981" : "#64748B" },
              ]}
            >
              <Text style={styles.statusText}>
                {isAlfredServiceRunning ? "ACTIVE (VIGILANT)" : "STANDBY"}
              </Text>
            </View>
          </View>
          <Text style={styles.helpText}>
            Maintains a persistent Android foreground service with low-priority notification. Keeps Alfred capturing alerts and holding the relay connection even when the phone is locked or other apps are running.
          </Text>
          <View style={styles.rowBetween}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={handleToggleAlfredService}
            >
              <Text style={styles.buttonTextSecondary}>
                {isAlfredServiceRunning ? "Stop Service" : "Start Service"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.smallButton} onPress={handleRequestBatteryExemption}>
              <Text style={styles.buttonText}>Battery Exemption</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Synchronized Cluster State */}
        <View style={styles.card}>
          <Text style={styles.cardHeader}>Synchronized Cluster State</Text>

          <View style={styles.metricRow}>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Master Volume</Text>
              <Text style={styles.metricValue}>{state?.master_volume ?? "--"}%</Text>
              <View style={styles.volumeButtons}>
                <TouchableOpacity style={styles.smallButton} onPress={() => handleVolumeChange(-10)}>
                  <Text style={styles.buttonText}>-10%</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.smallButton} onPress={() => handleVolumeChange(10)}>
                  <Text style={styles.buttonText}>+10%</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Zen Mode</Text>
              <Switch
                value={state?.zen_mode ?? false}
                onValueChange={() => {
                  gatewayClient.toggleZenMode();
                }}
                trackColor={{ false: "#334155", true: "#3B82F6" }}
                thumbColor="#F8FAFC"
              />
              <Text style={styles.subtext}>{state?.zen_mode ? "Active" : "Disabled"}</Text>
            </View>

            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Unread Alerts</Text>
              <Text style={styles.metricValue}>{state?.unread_notifications_count ?? 0}</Text>
            </View>
          </View>
        </View>

        {/* Synchronized Notifications History */}
        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardHeader}>Recent Cluster Notifications</Text>
            <TouchableOpacity onPress={fetchHistory} disabled={isLoadingClusterNotifs}>
              <Text style={styles.actionLink}>
                {isLoadingClusterNotifs ? "Refreshing..." : "Refresh History"}
              </Text>
            </TouchableOpacity>
          </View>

          {clusterNotifications.length === 0 ? (
            <Text style={styles.emptyText}>No notifications stored in cluster yet.</Text>
          ) : (
            clusterNotifications.slice(0, 5).map((n: any, idx: number) => {
              const badge = getPriorityBadgeStyle(n.priority || "LOW");
              return (
                <View key={`notif_${n.id || idx}_${idx}`} style={styles.notifItem}>
                  <View style={styles.notifHeaderRow}>
                    <Text style={styles.notifAppName}>{n.app_name || "Unknown"}</Text>
                    <View style={[styles.priorityTag, { backgroundColor: badge.backgroundColor, borderColor: badge.borderColor }]}>
                      <Text style={[styles.priorityTagText, { color: badge.textColor }]}>{n.priority || "LOW"}</Text>
                    </View>
                  </View>
                  <Text style={styles.notifTitle}>{n.title}</Text>
                  <Text style={styles.notifBody}>{n.text}</Text>
                </View>
              );
            })
          )}
        </View>

        {/* Quick Notification Transmitter */}
        <View style={styles.card}>
          <Text style={styles.cardHeader}>Notification Transmitter (Simulation Engine)</Text>
          <Text style={styles.helpText}>
            Tap a preset to send an alert over WebSocket Channel.NOTIFY. If offline, the alert is cached and sent when reconnected.
          </Text>

          <View style={styles.presetGrid}>
            {PRESET_NOTIFICATIONS.map((preset) => (
              <TouchableOpacity
                key={preset.id}
                style={[
                  styles.presetButton,
                  preset.priority === "URGENT" && styles.urgentPreset,
                ]}
                onPress={() => handleSendPreset(preset.id)}
              >
                <Text style={styles.presetTitle}>{preset.label}</Text>
                <Text style={styles.presetApp}>[{preset.priority}] {preset.app_name}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Custom Notification Form */}
          <Text style={[styles.cardHeader, { marginTop: 16 }]}>Send Custom Alert</Text>
          <TextInput
            style={styles.inputFull}
            placeholder="Alert Title (e.g. Flight Booking Confirmed)"
            placeholderTextColor="#64748B"
            value={customTitle}
            onChangeText={setCustomTitle}
          />
          <TextInput
            style={[styles.inputFull, { height: 60 }]}
            placeholder="Alert Body / Details..."
            placeholderTextColor="#64748B"
            multiline
            value={customText}
            onChangeText={setCustomText}
          />
          <TouchableOpacity style={[styles.primaryButton, { alignSelf: "flex-end" }]} onPress={handleSendCustom}>
            <Text style={styles.buttonText}>Transmit to Cluster</Text>
          </TouchableOpacity>
        </View>

        {/* Live Inbound Event Feed */}
        <View style={styles.card}>
          <Text style={styles.cardHeader}>Cluster Event Wire (Live Inbound)</Text>
          {eventLogs.length === 0 ? (
            <Text style={styles.emptyText}>No cluster events received yet. Connect to Gateway to begin streaming.</Text>
          ) : (
            eventLogs.map((log, idx) => (
              <View key={`${log.id}_${idx}`} style={styles.logItem}>
                <Text style={styles.logTime}>[{log.time}]</Text>
                <Text style={styles.logContent}>{log.text}</Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#0F172A",
  },
  container: {
    padding: 16,
    paddingBottom: 32,
  },
  header: {
    marginBottom: 16,
  },
  appTitle: {
    fontSize: 22,
    fontWeight: "bold",
    color: "#F8FAFC",
  },
  deviceSubtitle: {
    fontSize: 14,
    color: "#94A3B8",
    marginTop: 2,
  },
  card: {
    backgroundColor: "#1E293B",
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#334155",
  },
  cardHeader: {
    fontSize: 16,
    fontWeight: "600",
    color: "#E2E8F0",
    marginBottom: 10,
  },
  rowBetween: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "bold",
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  input: {
    flex: 1,
    backgroundColor: "#0F172A",
    color: "#F8FAFC",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#334155",
    fontSize: 14,
  },
  inputFull: {
    backgroundColor: "#0F172A",
    color: "#F8FAFC",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#334155",
    fontSize: 14,
    marginBottom: 8,
  },
  primaryButton: {
    backgroundColor: "#2563EB",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: "center",
  },
  secondaryButton: {
    backgroundColor: "#1E293B",
    borderWidth: 1,
    borderColor: "#38BDF8",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: "center",
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: "#FFFFFF",
    fontWeight: "600",
    fontSize: 14,
  },
  buttonTextSecondary: {
    color: "#38BDF8",
    fontWeight: "600",
    fontSize: 13,
  },
  discoveryButtonsRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 8,
  },
  discoveryButtonHalf: {
    flex: 1,
    backgroundColor: "#1E293B",
    borderWidth: 1,
    borderColor: "#334155",
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  discoveryRow: {
    marginTop: 8,
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  scanFeedback: {
    fontSize: 12,
    color: "#94A3B8",
    marginTop: 6,
    fontStyle: "italic",
  },
  offlineBanner: {
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    borderWidth: 1,
    borderColor: "#F59E0B",
    borderRadius: 6,
    padding: 8,
    marginTop: 10,
  },
  offlineBannerText: {
    color: "#FBBF24",
    fontSize: 12,
  },
  metricRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  metricItem: {
    alignItems: "center",
    flex: 1,
  },
  metricLabel: {
    fontSize: 12,
    color: "#94A3B8",
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 20,
    fontWeight: "bold",
    color: "#38BDF8",
  },
  subtext: {
    fontSize: 11,
    color: "#64748B",
    marginTop: 2,
  },
  volumeButtons: {
    flexDirection: "row",
    gap: 4,
    marginTop: 6,
  },
  smallButton: {
    backgroundColor: "#334155",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  actionLink: {
    color: "#38BDF8",
    fontSize: 13,
    fontWeight: "500",
  },
  notifItem: {
    backgroundColor: "#0F172A",
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#334155",
  },
  notifHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  notifAppName: {
    fontSize: 12,
    fontWeight: "bold",
    color: "#94A3B8",
  },
  priorityTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
  },
  priorityTagText: {
    fontSize: 10,
    fontWeight: "bold",
  },
  notifTitle: {
    fontSize: 13,
    fontWeight: "600",
    color: "#F8FAFC",
    marginBottom: 2,
  },
  notifBody: {
    fontSize: 12,
    color: "#CBD5E1",
  },
  helpText: {
    fontSize: 12,
    color: "#94A3B8",
    marginBottom: 12,
    lineHeight: 18,
  },
  presetGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  presetButton: {
    backgroundColor: "#0F172A",
    borderWidth: 1,
    borderColor: "#334155",
    borderRadius: 8,
    padding: 10,
    width: "48%",
  },
  urgentPreset: {
    borderColor: "#EF4444",
    backgroundColor: "rgba(239, 68, 68, 0.1)",
  },
  presetTitle: {
    fontSize: 13,
    fontWeight: "600",
    color: "#F1F5F9",
  },
  presetApp: {
    fontSize: 11,
    color: "#94A3B8",
    marginTop: 2,
  },
  emptyText: {
    fontSize: 13,
    color: "#64748B",
    fontStyle: "italic",
  },
  logItem: {
    flexDirection: "row",
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: "#334155",
    gap: 6,
  },
  logTime: {
    fontSize: 11,
    color: "#64748B",
  },
  logContent: {
    fontSize: 12,
    color: "#CBD5E1",
    flex: 1,
  },
});
