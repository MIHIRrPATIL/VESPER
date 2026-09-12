import React, { useState, useEffect } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
} from "react-native";
import * as Battery from "expo-battery";
import * as Network from "expo-network";
import { theme } from "../styles/theme";
import { gatewayClient, ConnectionStatus } from "../services/gateway";
import { SubnetDiscoveryService, DiscoveredGateway } from "../services/discovery";
import { AlfredService } from "../../modules/alfred-service";

interface WorkstationTabProps {
  status: ConnectionStatus;
  gatewayUrl: string;
  setGatewayUrl: (url: string) => void;
  deviceName: string;
  offlineCount: number;
}

export const WorkstationTab: React.FC<WorkstationTabProps> = ({
  status,
  gatewayUrl,
  setGatewayUrl,
  deviceName,
  offlineCount,
}) => {
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanProgress, setScanProgress] = useState<string>("");
  const [hasNotificationAccess, setHasNotificationAccess] = useState<boolean>(false);
  const [isAlfredServiceRunning, setIsAlfredServiceRunning] = useState<boolean>(false);

  // Telemetry
  const [batteryLevel, setBatteryLevel] = useState<number | null>(null);
  const [batteryState, setBatteryState] = useState<string>("unknown");
  const [localIp, setLocalIp] = useState<string>("127.0.0.1");

  useEffect(() => {
    checkNotificationPermission();

    // Check Alfred Foreground Service
    if (Platform.OS === "android") {
      AlfredService.isServiceRunning()
        .then((running) => setIsAlfredServiceRunning(running))
        .catch(() => {});
    }

    // Battery & Network telemetry
    Battery.getBatteryLevelAsync()
      .then((lvl) => setBatteryLevel(Math.round(lvl * 100)))
      .catch(() => {});

    Battery.getBatteryStateAsync()
      .then((state) => {
        if (state === Battery.BatteryState.CHARGING) setBatteryState("charging");
        else if (state === Battery.BatteryState.FULL) setBatteryState("full");
        else if (state === Battery.BatteryState.UNPLUGGED) setBatteryState("battery");
      })
      .catch(() => {});

    Network.getIpAddressAsync()
      .then((ip) => {
        if (ip) setLocalIp(ip);
      })
      .catch(() => {});
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

  const handleAutoDiscover = async (mode: "quick" | "corporate" = "quick") => {
    if (isScanning) return;
    setIsScanning(true);
    setScanProgress(
      mode === "quick" ? "Probing fast-path LAN candidates..." : "Sweeping local /24 subnet..."
    );

    try {
      const discovered: DiscoveredGateway | null = await SubnetDiscoveryService.discoverHybrid(
        mode,
        (scanned, total, currentIp) => {
          setScanProgress(`Sweeping Subnet (${scanned}/${total}): ${currentIp}`);
        },
        undefined,
        gatewayUrl
      );

      if (discovered) {
        setGatewayUrl(discovered.wsUrl);
        setScanProgress(`Connected: Gateway found at ${discovered.ip}:${discovered.port}`);
        await gatewayClient.setGatewayUrl(discovered.wsUrl);
      } else {
        setScanProgress(
          mode === "quick"
            ? "Quick scan finished with no match. Try 'Subnet Sweep'."
            : "No gateway detected on subnet. Verify Wi-Fi or enter IP manually."
        );
      }
    } catch (err: any) {
      setScanProgress(`Scan error: ${err?.message || "Unknown error"}`);
    } finally {
      setIsScanning(false);
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case "connected":
        return theme.colors.success;
      case "connecting":
      case "reconnecting":
        return theme.colors.warning;
      default:
        return theme.colors.error;
    }
  };

  return (
    <View style={styles.container}>
      {/* ── 1. Gateway Connection Card ── */}
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <Text style={styles.sectionHeader}>CLUSTER GATEWAY</Text>
          <View style={styles.statusPill}>
            <View style={[styles.statusDot, { backgroundColor: getStatusColor() }]} />
            <Text style={[styles.statusText, { color: getStatusColor() }]}>
              {status.toUpperCase()}
            </Text>
          </View>
        </View>

        <Text style={styles.label}>MANUAL CONNECTION</Text>
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={gatewayUrl}
            onChangeText={setGatewayUrl}
            placeholder="ws://192.168.0.xxx:8000/ws"
            placeholderTextColor={theme.colors.textGhost}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity style={styles.primaryButton} onPress={handleConnect}>
            <Text style={styles.primaryButtonText}>CONNECT</Text>
          </TouchableOpacity>
        </View>

        <Text style={[styles.label, { marginTop: theme.spacing.md }]}>AUTO-DISCOVERY</Text>
        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.secondaryButton, isScanning && styles.buttonDisabled]}
            onPress={() => handleAutoDiscover("quick")}
            disabled={isScanning}
          >
            {isScanning ? (
              <ActivityIndicator size="small" color={theme.colors.warning} />
            ) : (
              <Text style={styles.secondaryButtonText}>QUICK SCAN (LAN)</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.secondaryButton, isScanning && styles.buttonDisabled]}
            onPress={() => handleAutoDiscover("corporate")}
            disabled={isScanning}
          >
            <Text style={styles.secondaryButtonText}>SUBNET SWEEP</Text>
          </TouchableOpacity>
        </View>

        {scanProgress !== "" && (
          <View style={styles.scanBox}>
            <Text style={styles.scanText}>{scanProgress}</Text>
          </View>
        )}

        {offlineCount > 0 && (
          <View style={styles.offlineBox}>
            <Text style={styles.offlineText}>
              {offlineCount} notification(s) queued offline. Will sync automatically upon connection.
            </Text>
          </View>
        )}
      </View>

      {/* ── 2. Permissions & Vigilance Card ── */}
      <View style={styles.card}>
        <Text style={styles.sectionHeader}>SYSTEM PERMISSIONS & VIGILANCE</Text>

        {/* Notification Listener Service */}
        <View style={styles.permissionBlock}>
          <View style={styles.rowBetween}>
            <Text style={styles.blockTitle}>NOTIFICATION INTERCEPTION</Text>
            <View
              style={[
                styles.miniBadge,
                {
                  borderColor: hasNotificationAccess ? theme.colors.success : theme.colors.warning,
                },
              ]}
            >
              <Text
                style={[
                  styles.miniBadgeText,
                  { color: hasNotificationAccess ? theme.colors.success : theme.colors.warning },
                ]}
              >
                {hasNotificationAccess ? "ACTIVE" : "PERMISSION REQUIRED"}
              </Text>
            </View>
          </View>
          <Text style={styles.descriptionText}>
            Enables forwarding incoming alerts from WhatsApp, Slack, SMS, and OTPs to the desk companion.
          </Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={handleRequestNotificationPermission}
            >
              <Text style={styles.secondaryButtonText}>OPEN ANDROID SETTINGS</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.ghostButton} onPress={checkNotificationPermission}>
              <Text style={styles.ghostButtonText}>REFRESH</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Alfred Persistent Foreground Service */}
        <View style={[styles.permissionBlock, { marginTop: theme.spacing.md }]}>
          <View style={styles.rowBetween}>
            <Text style={styles.blockTitle}>ALFRED VIGILANCE SERVICE</Text>
            <View
              style={[
                styles.miniBadge,
                {
                  borderColor: isAlfredServiceRunning ? theme.colors.success : theme.colors.textGhost,
                },
              ]}
            >
              <Text
                style={[
                  styles.miniBadgeText,
                  { color: isAlfredServiceRunning ? theme.colors.success : theme.colors.textMuted },
                ]}
              >
                {isAlfredServiceRunning ? "ACTIVE (VIGILANT)" : "STANDBY"}
              </Text>
            </View>
          </View>
          <Text style={styles.descriptionText}>
            Holds a persistent foreground notification to guarantee zero connection drops during Android Doze.
          </Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={handleToggleAlfredService}
            >
              <Text style={styles.secondaryButtonText}>
                {isAlfredServiceRunning ? "STOP SERVICE" : "START SERVICE"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.ghostButton}
              onPress={handleRequestBatteryExemption}
            >
              <Text style={styles.ghostButtonText}>BATTERY SHIELD</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* ── 3. Node Telemetry Card ── */}
      <View style={styles.card}>
        <Text style={styles.sectionHeader}>NODE TELEMETRY</Text>
        <View style={styles.telemetryGrid}>
          <View style={styles.telemetryPod}>
            <Text style={styles.telemetryLabel}>DEVICE</Text>
            <Text style={styles.telemetryValue} numberOfLines={1}>
              {deviceName}
            </Text>
          </View>

          <View style={styles.telemetryPod}>
            <Text style={styles.telemetryLabel}>LOCAL IP</Text>
            <Text style={styles.telemetryValue} numberOfLines={1}>
              {localIp}
            </Text>
          </View>

          <View style={styles.telemetryPod}>
            <Text style={styles.telemetryLabel}>BATTERY</Text>
            <Text style={styles.telemetryValue}>
              {batteryLevel !== null ? `${batteryLevel}%` : "--"} ({batteryState})
            </Text>
          </View>

          <View style={styles.telemetryPod}>
            <Text style={styles.telemetryLabel}>OFFLINE QUEUE</Text>
            <Text style={styles.telemetryValue}>
              {offlineCount} {offlineCount === 1 ? "alert" : "alerts"}
            </Text>
          </View>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    gap: theme.spacing.lg,
  },
  card: {
    backgroundColor: theme.colors.card,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing.lg,
  },
  sectionHeader: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    letterSpacing: 1.5,
    color: theme.colors.textMuted,
    fontWeight: "600",
  },
  rowBetween: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: theme.spacing.md,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.cardElevated,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "600",
    letterSpacing: 1,
  },
  label: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.xs,
  },
  inputRow: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  input: {
    flex: 1,
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  primaryButton: {
    backgroundColor: theme.colors.textPrimary,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.lg,
    justifyContent: "center",
    alignItems: "center",
  },
  primaryButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    color: theme.colors.bg,
  },
  buttonRow: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  secondaryButton: {
    flex: 1,
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xs,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    justifyContent: "center",
    alignItems: "center",
  },
  secondaryButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "600",
    letterSpacing: 1,
    color: theme.colors.textSecondary,
  },
  ghostButton: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xs,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    justifyContent: "center",
    alignItems: "center",
  },
  ghostButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.textMuted,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  scanBox: {
    marginTop: theme.spacing.md,
    padding: theme.spacing.sm,
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  scanText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
  offlineBox: {
    marginTop: theme.spacing.md,
    padding: theme.spacing.sm,
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.warning,
  },
  offlineText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.warning,
  },
  permissionBlock: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.md,
  },
  blockTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 1,
    color: theme.colors.textSecondary,
  },
  miniBadge: {
    borderWidth: 1,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.xs,
    paddingVertical: 2,
  },
  miniBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 1,
  },
  descriptionText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    lineHeight: 18,
    color: theme.colors.textMuted,
    marginVertical: theme.spacing.sm,
  },
  telemetryGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  telemetryPod: {
    flex: 1,
    minWidth: "45%",
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.md,
  },
  telemetryLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1.5,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.xxs,
  },
  telemetryValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.textPrimary,
  },
});
