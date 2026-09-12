import React, { useState, useEffect } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Modal,
  Animated,
  Dimensions,
  Platform,
  Linking,
  ActivityIndicator,
} from "react-native";
import { theme } from "../styles/theme";
import { gatewayClient, ConnectionStatus } from "../services/gateway";
import { AlfredService } from "../../modules/alfred-service";
import { AgentState } from "../types/vesper";
import { offlineStore } from "../services/offline-store";
import { SubnetDiscoveryService, DiscoveredGateway } from "../services/discovery";
import * as Battery from "expo-battery";
import * as Network from "expo-network";

const { height: SCREEN_HEIGHT } = Dimensions.get("window");

interface ClusterSettingsModalProps {
  visible: boolean;
  onClose: () => void;
  pendingSyncCount?: number;
  onSyncNow?: () => void;
  agentState?: AgentState;
  onToggleVoice?: () => void;
}

export const ClusterSettingsModal: React.FC<ClusterSettingsModalProps> = ({
  visible,
  onClose,
  pendingSyncCount = 0,
  onSyncNow,
  agentState = "IDLE",
  onToggleVoice,
}) => {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [gatewayUrl, setGatewayUrl] = useState(gatewayClient.getGatewayUrl());
  const [isServiceRunning, setIsServiceRunning] = useState(false);
  const [hasPermission, setHasPermission] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [sweepStatus, setSweepStatus] = useState<string | null>(null);

  // Telemetry
  const [batteryLevel, setBatteryLevel] = useState<number | null>(null);
  const [isCharging, setIsCharging] = useState(false);
  const [localIp, setLocalIp] = useState<string>("Detecting...");

  const slideAnim = React.useRef(new Animated.Value(SCREEN_HEIGHT)).current;

  useEffect(() => {
    if (visible) {
      Animated.spring(slideAnim, {
        toValue: 0,
        tension: 65,
        friction: 11,
        useNativeDriver: true,
      }).start();
      refreshVitals();
    } else {
      Animated.timing(slideAnim, {
        toValue: SCREEN_HEIGHT,
        duration: 180,
        useNativeDriver: true,
      }).start();
    }
  }, [visible]);

  useEffect(() => {
    const unsub = gatewayClient.subscribeStatus((newStatus) => {
      setStatus(newStatus);
      setGatewayUrl(gatewayClient.getGatewayUrl());
    });
    return () => unsub();
  }, []);

  const refreshVitals = async () => {
    try {
      const running = await AlfredService.isServiceRunning();
      setIsServiceRunning(running);
    } catch {}

    try {
      const level = await Battery.getBatteryLevelAsync();
      setBatteryLevel(level >= 0 ? Math.round(level * 100) : null);
      const state = await Battery.getBatteryStateAsync();
      setIsCharging(state === Battery.BatteryState.CHARGING || state === Battery.BatteryState.FULL);
    } catch {}

    try {
      const ip = await Network.getIpAddressAsync();
      if (ip) setLocalIp(ip);
    } catch {}

    checkNotificationPermission();
  };

  const checkNotificationPermission = async () => {
    if (Platform.OS === "android") {
      try {
        const listener = require("react-native-android-notification-listener");
        if (listener?.default?.getPermissionStatus) {
          const perm = await listener.default.getPermissionStatus();
          setHasPermission(perm === "authorized");
        }
      } catch {
        setHasPermission(false);
      }
    }
  };

  const handleConnect = () => {
    if (!gatewayUrl.trim()) return;
    gatewayClient.setGatewayUrl(gatewayUrl.trim());
    gatewayClient.disconnect();
    gatewayClient.connect();
  };

  const handleQuickScan = async () => {
    setIsScanning(true);
    setSweepStatus("Scanning LAN...");
    try {
      const found = await SubnetDiscoveryService.quickScan(gatewayUrl);
      if (found) {
        setGatewayUrl(found.wsUrl);
        await gatewayClient.setGatewayUrl(found.wsUrl);
        setSweepStatus(`Connected: ${found.ip}`);
      } else {
        setSweepStatus("No cluster detected on default ports.");
      }
    } catch (e: any) {
      setSweepStatus(`Scan error: ${e?.message || "Failed"}`);
    } finally {
      setIsScanning(false);
    }
  };

  const handleSubnetSweep = async () => {
    setIsScanning(true);
    setSweepStatus("Sweeping subnet (1-254)...");
    try {
      const found = await SubnetDiscoveryService.corporateSubnetSweep(
        (tested: number, total: number, curIp: string) => {
          setSweepStatus(`Testing ${tested}/${total} (${curIp})...`);
        }
      );
      if (found) {
        setGatewayUrl(found.wsUrl);
        await gatewayClient.setGatewayUrl(found.wsUrl);
        setSweepStatus(`Discovered: ${found.ip}`);
      } else {
        setSweepStatus("Sweep complete: 0 gateways found.");
      }
    } catch (e: any) {
      setSweepStatus(`Sweep failed: ${e?.message || "Error"}`);
    } finally {
      setIsScanning(false);
    }
  };

  const handleToggleService = async () => {
    try {
      if (isServiceRunning) {
        await AlfredService.stopService();
        setIsServiceRunning(false);
      } else {
        await AlfredService.startService();
        setIsServiceRunning(true);
      }
    } catch (e) {
      console.warn("Toggle foreground service failed:", e);
    }
  };

  const openNotificationSettings = () => {
    try {
      if (Platform.OS === "android") {
        const RNAndroidNotificationListener = require("react-native-android-notification-listener");
        RNAndroidNotificationListener.openNotificationListenerSettings();
      } else {
        Linking.openSettings();
      }
    } catch {
      Linking.openSettings();
    }
  };

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <TouchableOpacity style={styles.backdropTouch} activeOpacity={1} onPress={onClose} />
        <Animated.View
          style={[
            styles.sheet,
            {
              transform: [{ translateY: slideAnim }],
            },
          ]}
        >
          {/* Header */}
          <View style={styles.sheetHeader}>
            <View>
              <Text style={styles.sheetTitle}>Cluster Settings</Text>
              <Text style={styles.sheetSubtitle}>Gateway & Device Topology</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeGlyph}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.scrollBody} showsVerticalScrollIndicator={false}>
            {/* Connection Section */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <Text style={styles.cardSectionTitle}>GATEWAY ENDPOINT</Text>
                <View style={styles.statusBadge}>
                  <View
                    style={[
                      styles.statusDot,
                      {
                        backgroundColor:
                          status === "connected"
                            ? theme.colors.emerald
                            : status === "connecting" || status === "reconnecting"
                            ? theme.colors.amber
                            : theme.colors.crimson,
                      },
                    ]}
                  />
                  <Text style={styles.statusBadgeText}>{status.toUpperCase()}</Text>
                </View>
              </View>

              <View style={styles.inputRow}>
                <TextInput
                  style={styles.textInput}
                  value={gatewayUrl}
                  onChangeText={setGatewayUrl}
                  placeholder="ws://192.168.0.x:8000/ws"
                  placeholderTextColor={theme.colors.textMuted}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <TouchableOpacity style={styles.connectBtn} onPress={handleConnect}>
                  <Text style={styles.connectBtnText}>CONNECT</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.discoveryRow}>
                <TouchableOpacity
                  style={[styles.discoveryBtn, isScanning && styles.btnDisabled]}
                  onPress={handleQuickScan}
                  disabled={isScanning}
                >
                  {isScanning ? (
                    <ActivityIndicator size="small" color={theme.colors.boneWhite} />
                  ) : (
                    <Text style={styles.discoveryBtnText}>AUTO-DETECT LAN</Text>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.discoveryBtn, isScanning && styles.btnDisabled]}
                  onPress={handleSubnetSweep}
                  disabled={isScanning}
                >
                  <Text style={styles.discoveryBtnText}>SUBNET SWEEP</Text>
                </TouchableOpacity>
              </View>

              {sweepStatus && <Text style={styles.sweepStatusText}>{sweepStatus}</Text>}
            </View>

            {/* Voice & Agent Mic Control */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <Text style={styles.cardSectionTitle}>ALFRED VOICE & MIC</Text>
                <View style={styles.statusBadge}>
                  <View
                    style={[
                      styles.statusDot,
                      {
                        backgroundColor:
                          agentState === "LISTENING"
                            ? theme.colors.emerald
                            : agentState === "THINKING"
                            ? theme.colors.amber
                            : theme.colors.textMuted,
                      },
                    ]}
                  />
                  <Text style={styles.statusBadgeText}>{agentState}</Text>
                </View>
              </View>
              <View style={styles.actionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.actionTitle}>Voice Interaction</Text>
                  <Text style={styles.actionSubtext}>
                    {agentState === "LISTENING"
                      ? "Alfred is actively listening to voice input"
                      : agentState === "THINKING"
                      ? "Synthesizing response and executing tool call"
                      : "Tap to initiate voice dialog or interrupt agent"}
                  </Text>
                </View>
                <TouchableOpacity
                  style={[
                    styles.pillBtn,
                    (agentState === "LISTENING" || agentState === "THINKING") && styles.pillBtnActive,
                  ]}
                  onPress={onToggleVoice}
                >
                  <Text style={[styles.pillBtnText, (agentState === "LISTENING" || agentState === "THINKING") && styles.pillBtnTextActive]}>
                    {agentState === "LISTENING" ? "INTERRUPT" : "TALK"}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* Offline Cache & Outbox Sync Queue */}
            <View style={styles.card}>
              <View style={styles.cardHeaderRow}>
                <Text style={styles.cardSectionTitle}>OFFLINE STORAGE & OUTBOX</Text>
                <View style={styles.statusBadge}>
                  <View
                    style={[
                      styles.statusDot,
                      {
                        backgroundColor:
                          pendingSyncCount > 0
                            ? theme.colors.amber
                            : theme.colors.emerald,
                      },
                    ]}
                  />
                  <Text style={styles.statusBadgeText}>
                    {pendingSyncCount > 0 ? `${pendingSyncCount} QUEUED` : "SYNCED"}
                  </Text>
                </View>
              </View>
              <View style={styles.actionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.actionTitle}>Outbox Sync Engine</Text>
                  <Text style={styles.actionSubtext}>
                    {pendingSyncCount > 0
                      ? `${pendingSyncCount} offline mutations pending dispatch to gateway`
                      : "Local storage synchronized with cluster gateway"}
                  </Text>
                </View>
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                  {pendingSyncCount > 0 && (
                    <TouchableOpacity
                      style={[styles.pillBtn, { borderColor: "rgba(244, 63, 94, 0.4)" }]}
                      onPress={async () => {
                        await offlineStore.clearPendingBacklog();
                      }}
                      activeOpacity={0.75}
                    >
                      <Text style={[styles.pillBtnText, { color: theme.colors.rose }]}>
                        CLEAR
                      </Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity
                    style={[styles.pillBtn, pendingSyncCount > 0 && styles.pillBtnActive]}
                    onPress={() => {
                      if (onSyncNow) {
                        onSyncNow();
                      } else {
                        offlineStore.syncPendingBacklog();
                      }
                    }}
                    activeOpacity={0.75}
                  >
                    <Text style={[styles.pillBtnText, pendingSyncCount > 0 && styles.pillBtnTextActive]}>
                      SYNC NOW
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>

            {/* Vigilance & Permissions */}
            <View style={styles.card}>
              <Text style={styles.cardSectionTitle}>BACKGROUND VIGILANCE</Text>

              {/* Notification Row */}
              <View style={styles.actionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.actionTitle}>Notification Forwarding</Text>
                  <Text style={styles.actionSubtext}>
                    Relay SMS, WhatsApp & OTP alerts to workstation
                  </Text>
                </View>
                <TouchableOpacity
                  style={[styles.pillBtn, hasPermission && styles.pillBtnActive]}
                  onPress={openNotificationSettings}
                >
                  <Text style={[styles.pillBtnText, hasPermission && styles.pillBtnTextActive]}>
                    {hasPermission ? "ACTIVE" : "CONFIGURE"}
                  </Text>
                </TouchableOpacity>
              </View>

              <View style={styles.divider} />

              {/* Foreground Service Row */}
              <View style={styles.actionRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.actionTitle}>Alfred Foreground Service</Text>
                  <Text style={styles.actionSubtext}>
                    Keep alert watcher active when phone is locked
                  </Text>
                </View>
                <TouchableOpacity
                  style={[styles.pillBtn, isServiceRunning && styles.pillBtnActive]}
                  onPress={handleToggleService}
                >
                  <Text style={[styles.pillBtnText, isServiceRunning && styles.pillBtnTextActive]}>
                    {isServiceRunning ? "RUNNING" : "START"}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* Device Telemetry */}
            <View style={styles.card}>
              <Text style={styles.cardSectionTitle}>DEVICE TELEMETRY</Text>
              <View style={styles.vitalsGrid}>
                <View style={styles.vitalItem}>
                  <Text style={styles.vitalLabel}>LOCAL IP</Text>
                  <Text style={styles.vitalValue}>{localIp}</Text>
                </View>
                <View style={styles.vitalItem}>
                  <Text style={styles.vitalLabel}>BATTERY</Text>
                  <Text style={styles.vitalValue}>
                    {batteryLevel !== null ? `${batteryLevel}% ${isCharging ? "(Charging)" : ""}` : "AC"}
                  </Text>
                </View>
                <View style={styles.vitalItem}>
                  <Text style={styles.vitalLabel}>PLATFORM</Text>
                  <Text style={styles.vitalValue}>
                    {Platform.OS.toUpperCase()} {Platform.Version}
                  </Text>
                </View>
                <View style={styles.vitalItem}>
                  <Text style={styles.vitalLabel}>CLIENT ID</Text>
                  <Text style={styles.vitalValue} numberOfLines={1}>
                    {gatewayClient.getClientId()}
                  </Text>
                </View>
              </View>
            </View>
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    justifyContent: "flex-end",
  },
  backdropTouch: {
    flex: 1,
  },
  sheet: {
    backgroundColor: "#121212",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderTopWidth: 1,
    borderColor: theme.colors.borderSubtle,
    maxHeight: SCREEN_HEIGHT * 0.82,
    paddingBottom: Platform.OS === "ios" ? 30 : 16,
  },
  sheetHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
  },
  sheetTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 17,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  sheetSubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 1,
  },
  closeBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    alignItems: "center",
    justifyContent: "center",
  },
  closeGlyph: {
    color: theme.colors.textMuted,
    fontSize: 12,
  },
  scrollBody: {
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  card: {
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
  },
  cardHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  cardSectionTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.textMuted,
    marginBottom: 8,
  },
  statusBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },
  inputRow: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
  },
  textInput: {
    flex: 1,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 8,
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  connectBtn: {
    backgroundColor: theme.colors.boneWhite,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  connectBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "700",
    color: theme.colors.background,
  },
  discoveryRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 10,
  },
  discoveryBtn: {
    flex: 1,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 8,
    paddingVertical: 8,
    alignItems: "center",
  },
  discoveryBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
  },
  btnDisabled: {
    opacity: 0.4,
  },
  sweepStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.amber,
    marginTop: 8,
  },
  actionRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 6,
  },
  actionTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    color: theme.colors.boneWhite,
  },
  actionSubtext: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  pillBtn: {
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 14,
    minWidth: 80,
    alignItems: "center",
  },
  pillBtnActive: {
    backgroundColor: "rgba(16, 185, 129, 0.1)",
    borderColor: theme.colors.emerald,
  },
  pillBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "700",
    color: theme.colors.textMuted,
  },
  pillBtnTextActive: {
    color: theme.colors.emerald,
  },
  divider: {
    height: 1,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    marginVertical: 8,
  },
  vitalsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 4,
  },
  vitalItem: {
    width: "48%",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderRadius: 6,
    padding: 8,
  },
  vitalLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  vitalValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.boneWhite,
    marginTop: 2,
  },
});
