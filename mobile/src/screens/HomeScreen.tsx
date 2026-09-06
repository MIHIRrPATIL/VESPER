import React, { useEffect, useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  StatusBar,
  Switch,
} from "react-native";
import { gatewayClient, ConnectionStatus } from "../services/gateway";
import { MobileNotificationService, PRESET_NOTIFICATIONS } from "../services/notifications";
import { SynchronizedState } from "../types/events";

export default function HomeScreen() {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [gatewayUrl, setGatewayUrl] = useState<string>("ws://127.0.0.1:8000/ws");
  const [deviceName, setDeviceName] = useState<string>("Mobile Companion");
  const [state, setState] = useState<SynchronizedState | null>(null);

  // Custom alert form
  const [customTitle, setCustomTitle] = useState("");
  const [customText, setCustomText] = useState("");
  const [customApp, setCustomApp] = useState("WhatsApp");

  // Event feed log
  const [eventLogs, setEventLogs] = useState<Array<{ id: string; time: string; text: string; channel: string }>>([]);

  useEffect(() => {
    // 1. Initial info
    setGatewayUrl(gatewayClient.getGatewayUrl());
    setDeviceName(gatewayClient.getDeviceName());

    // 2. Status subscription
    const unsubStatus = gatewayClient.onStatus((newStatus) => {
      setStatus(newStatus);
    });

    // 3. State subscription
    const unsubState = gatewayClient.onState((newState) => {
      setState(newState);
    });

    // 4. Envelope log subscription
    const unsubEnvelope = gatewayClient.onEnvelope((env) => {
      const timeStr = new Date().toLocaleTimeString();
      let summary = `${env.channel} : ${env.type}`;
      if (env.channel === "NOTIFY" && env.payload?.notification) {
        summary += ` | [${env.payload.notification.priority}] ${env.payload.notification.app_name}: ${env.payload.notification.title}`;
      } else if (env.channel === "SYSTEM" && env.type === "SET_VOLUME") {
        summary += ` | Volume -> ${env.payload.volume}%`;
      }
      setEventLogs((prev) => [{ id: env.uuid || Math.random().toString(), time: timeStr, text: summary, channel: String(env.channel) }, ...prev.slice(0, 19)]);
    });

    // Connect automatically
    gatewayClient.connect();

    return () => {
      unsubStatus();
      unsubState();
      unsubEnvelope();
    };
  }, []);

  const handleConnect = () => {
    gatewayClient.setGatewayUrl(gatewayUrl.trim());
  };

  const handleSendPreset = (presetId: string) => {
    const success = MobileNotificationService.sendPreset(presetId);
    if (success) {
      console.log(`[HomeScreen] Sent preset: ${presetId}`);
    }
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
        return "#10B981"; // Emerald green
      case "connecting":
      case "reconnecting":
        return "#F59E0B"; // Amber
      default:
        return "#EF4444"; // Red
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
              placeholder="ws://192.168.1.xxx:8000/ws"
              placeholderTextColor="#64748B"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TouchableOpacity style={styles.primaryButton} onPress={handleConnect}>
              <Text style={styles.buttonText}>Connect</Text>
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

        {/* Quick Notification Transmitter */}
        <View style={styles.card}>
          <Text style={styles.cardHeader}>Notification Transmitter (Instant Relay)</Text>
          <Text style={styles.helpText}>
            Tap a preset to send an alert over WebSocket Channel.NOTIFY. The Desktop HUD will ingest, triage, and display it instantly.
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
            eventLogs.map((log) => (
              <View key={log.id} style={styles.logItem}>
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
    backgroundColor: "#0F172A", // Dark Slate
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
  buttonText: {
    color: "#FFFFFF",
    fontWeight: "600",
    fontSize: 14,
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
