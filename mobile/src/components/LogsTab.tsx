import React, { useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
} from "react-native";
import { theme } from "../styles/theme";
import { MobileNotificationService } from "../services/notifications";

interface LogEvent {
  id: string;
  time: string;
  text: string;
  channel: string;
}

interface LogsTabProps {
  eventLogs: LogEvent[];
  clusterNotifications: any[];
  onRefreshNotifications: () => void;
  isLoadingNotifs: boolean;
}

export const LogsTab: React.FC<LogsTabProps> = ({
  eventLogs,
  clusterNotifications,
  onRefreshNotifications,
  isLoadingNotifs,
}) => {
  const [testStatus, setTestStatus] = useState<string>("");

  const handleSendTestRelay = (type: "whatsapp" | "urgent") => {
    if (type === "whatsapp") {
      MobileNotificationService.sendNotification({
        package_name: "com.whatsapp",
        app_name: "WhatsApp",
        title: "Alex Chen",
        text: "Design review scheduled for 4:00 PM today. See you on the call!",
        priority: "HIGH",
      });
      setTestStatus("Sent WhatsApp test alert to desk companion.");
    } else {
      MobileNotificationService.sendNotification({
        package_name: "com.datadoghq.app",
        app_name: "Datadog",
        title: "CRITICAL: Replica Latency Spike",
        text: "Database secondary replica latency exceeded 450ms in eu-west-1.",
        priority: "URGENT",
      });
      setTestStatus("Sent Urgent Server alert to desk companion.");
    }
    setTimeout(() => setTestStatus(""), 3500);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "URGENT":
        return theme.colors.accent;
      case "HIGH":
        return theme.colors.warning;
      case "MEDIUM":
        return theme.colors.info;
      default:
        return theme.colors.textMuted;
    }
  };

  return (
    <View style={styles.container}>
      {/* ── 1. Intercepted Notifications Stream ── */}
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <Text style={styles.sectionHeader}>INTERCEPTED NOTIFICATIONS</Text>
          <TouchableOpacity onPress={onRefreshNotifications} disabled={isLoadingNotifs}>
            <Text style={styles.actionText}>
              {isLoadingNotifs ? "SYNCING..." : "SYNC"}
            </Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.helpText}>
          Real-time alerts intercepted on this phone and relayed to the VESPER desk companion.
        </Text>

        {/* Quick Test Transmitter */}
        <View style={styles.testActionsRow}>
          <TouchableOpacity
            style={styles.testButton}
            onPress={() => handleSendTestRelay("whatsapp")}
          >
            <Text style={styles.testButtonText}>+ TEST WHATSAPP</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.testButtonUrgent}
            onPress={() => handleSendTestRelay("urgent")}
          >
            <Text style={styles.testButtonUrgentText}>+ TEST URGENT</Text>
          </TouchableOpacity>
        </View>

        {testStatus !== "" && (
          <View style={styles.testStatusBox}>
            <Text style={styles.testStatusText}>{testStatus}</Text>
          </View>
        )}

        {clusterNotifications.length === 0 ? (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyText}>
              No notifications relayed yet. Incoming alerts from your phone will appear here.
            </Text>
          </View>
        ) : (
          <View style={styles.notifList}>
            {clusterNotifications.slice(0, 10).map((n, idx) => {
              const priorityColor = getPriorityColor(n.priority || "LOW");
              return (
                <View key={`notif_${idx}`} style={styles.notifPod}>
                  <View style={styles.notifTopRow}>
                    <Text style={styles.appName}>{n.app_name || "Notification"}</Text>
                    <View style={[styles.priorityBadge, { borderColor: priorityColor }]}>
                      <Text style={[styles.priorityBadgeText, { color: priorityColor }]}>
                        {n.priority || "LOW"}
                      </Text>
                    </View>
                  </View>

                  <Text style={styles.notifTitle}>{n.title}</Text>
                  {n.text ? <Text style={styles.notifBody}>{n.text}</Text> : null}
                </View>
              );
            })}
          </View>
        )}
      </View>

      {/* ── 2. Real-Time Cluster Wire ── */}
      <View style={styles.card}>
        <Text style={styles.sectionHeader}>CLUSTER EVENT WIRE</Text>
        <Text style={styles.helpText}>
          Inbound WebSocket telemetry and dispatch envelopes from the Gateway.
        </Text>

        {eventLogs.length === 0 ? (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyText}>
              Wire idle. Connect to Gateway to observe cluster state packets.
            </Text>
          </View>
        ) : (
          <View style={styles.wireList}>
            {eventLogs.slice(0, 15).map((log, idx) => (
              <View key={`log_${idx}`} style={styles.wireItem}>
                <Text style={styles.wireTime}>[{log.time}]</Text>
                <Text style={styles.wireChannel}>{log.channel}</Text>
                <Text style={styles.wireText} numberOfLines={2}>
                  {log.text}
                </Text>
              </View>
            ))}
          </View>
        )}
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
    marginBottom: theme.spacing.xs,
  },
  actionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.textSecondary,
    fontWeight: "600",
  },
  helpText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.md,
  },
  testActionsRow: {
    flexDirection: "row",
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  testButton: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xs,
    paddingVertical: theme.spacing.xs,
    paddingHorizontal: theme.spacing.md,
  },
  testButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.textSecondary,
    fontWeight: "600",
  },
  testButtonUrgent: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.accent,
    borderRadius: theme.radii.xs,
    paddingVertical: theme.spacing.xs,
    paddingHorizontal: theme.spacing.md,
  },
  testButtonUrgentText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.accent,
    fontWeight: "600",
  },
  testStatusBox: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  testStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
  emptyBox: {
    padding: theme.spacing.md,
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textGhost,
    textAlign: "center",
  },
  notifList: {
    gap: theme.spacing.sm,
  },
  notifPod: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.md,
  },
  notifTopRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: theme.spacing.xs,
  },
  appName: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "600",
    letterSpacing: 0.5,
  },
  priorityBadge: {
    borderWidth: 1,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.xs,
    paddingVertical: 1,
  },
  priorityBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 1,
  },
  notifTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.textPrimary,
  },
  notifBody: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: theme.colors.textSecondary,
    marginTop: 2,
  },
  wireList: {
    gap: theme.spacing.xs,
  },
  wireItem: {
    flexDirection: "row",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.borderSubtle,
    alignItems: "flex-start",
  },
  wireTime: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textGhost,
  },
  wireChannel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  wireText: {
    flex: 1,
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
});
