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
  const [activeTab, setActiveTab] = useState<"all" | "direct" | "promo">("all");

  const handleSendTestRelay = (type: "whatsapp" | "urgent" | "otp" | "ledger") => {
    if (type === "whatsapp") {
      MobileNotificationService.sendNotification({
        package_name: "com.whatsapp",
        app_name: "WhatsApp",
        title: "Alex Chen",
        text: "Design review scheduled for 4:00 PM today. See you on the call!",
        priority: "HIGH",
      });
      setTestStatus("Sent WhatsApp test alert to desk companion.");
    } else if (type === "urgent") {
      MobileNotificationService.sendNotification({
        package_name: "com.datadoghq.app",
        app_name: "Datadog",
        title: "CRITICAL: Replica Latency Spike",
        text: "Database secondary replica latency exceeded 450ms in eu-west-1.",
        priority: "URGENT",
      });
      setTestStatus("Sent Urgent Server alert to desk companion.");
    } else if (type === "otp") {
      MobileNotificationService.sendNotification({
        package_name: "com.google.android.apps.messaging",
        app_name: "Messages",
        title: "HDFC Bank",
        text: "482910 is your secret OTP for transaction of Rs. 1,499.00 at Swiggy. Valid for 10 mins. Do NOT share OTP.",
        priority: "HIGH",
      });
      setTestStatus("Sent OTP security alert to desk companion.");
    } else if (type === "ledger") {
      MobileNotificationService.sendNotification({
        package_name: "com.phonepe.app",
        app_name: "PhonePe",
        title: "Payment Successful",
        text: "Paid Rs 250 to Blue Tokai Coffee Roasters via UPI. Ref 4819283910.",
        priority: "MEDIUM",
      });
      setTestStatus("Sent Financial transaction alert to desk companion.");
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

  const getAppTag = (n: any) => {
    const pkg = (n.package_name || "").toLowerCase();
    const app = (n.app_name || "").toLowerCase();
    const title = (n.title || "").toLowerCase();
    const cat = n.category || "";

    if (pkg.includes("whatsapp") || app.includes("whatsapp")) {
      return { name: "WHATSAPP", color: theme.colors.emerald };
    }
    if (pkg.includes("telegram") || app.includes("telegram")) {
      return { name: "TELEGRAM", color: theme.colors.info };
    }
    if (pkg.includes("slack") || app.includes("slack")) {
      return { name: "SLACK", color: "#A855F7" };
    }
    if (
      cat === "FINANCIAL" ||
      app.includes("bank") ||
      title.includes("bank") ||
      pkg.includes("phonepe") ||
      pkg.includes("paytm") ||
      pkg.includes("gpay")
    ) {
      return { name: (n.app_name || "BANK").toUpperCase(), color: theme.colors.warning };
    }
    if (cat === "SECURITY" || n.otp_code) {
      return { name: "SECURITY", color: theme.colors.accent };
    }
    return { name: (n.app_name || "APP").toUpperCase(), color: theme.colors.textMuted };
  };

  const formatRelativeTime = (timestamp?: number) => {
    if (!timestamp) return "";
    const date = new Date(timestamp > 1e11 ? timestamp : timestamp * 1000);
    const now = Date.now();
    const diffSec = Math.floor((now - date.getTime()) / 1000);
    if (diffSec < 60) return "JUST NOW";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}M AGO`;
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  };

  const directNotifs = clusterNotifications.filter(
    (n) => !n.is_promo && n.category !== "PROMOTION"
  );
  const promoNotifs = clusterNotifications.filter(
    (n) => n.is_promo || n.category === "PROMOTION"
  );

  const displayedNotifs =
    activeTab === "direct"
      ? directNotifs
      : activeTab === "promo"
      ? promoNotifs
      : clusterNotifications;

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

        {/* Quick Test Transmitters */}
        <View style={styles.testActionsRow}>
          <TouchableOpacity
            style={styles.testButton}
            onPress={() => handleSendTestRelay("whatsapp")}
          >
            <Text style={styles.testButtonText}>+ WHATSAPP</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.testButtonUrgent}
            onPress={() => handleSendTestRelay("urgent")}
          >
            <Text style={styles.testButtonUrgentText}>+ URGENT</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.testButton}
            onPress={() => handleSendTestRelay("otp")}
          >
            <Text style={styles.testButtonText}>+ OTP</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.testButton}
            onPress={() => handleSendTestRelay("ledger")}
          >
            <Text style={styles.testButtonText}>+ LEDGER</Text>
          </TouchableOpacity>
        </View>

        {testStatus !== "" && (
          <View style={styles.testStatusBox}>
            <Text style={styles.testStatusText}>{testStatus}</Text>
          </View>
        )}

        {/* Category Filter Tabs */}
        <View style={styles.tabRow}>
          <TouchableOpacity
            style={[styles.tabButton, activeTab === "all" && styles.tabButtonActive]}
            onPress={() => setActiveTab("all")}
          >
            <Text
              style={[
                styles.tabButtonText,
                activeTab === "all" && styles.tabButtonTextActive,
              ]}
            >
              ALL ({clusterNotifications.length})
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.tabButton, activeTab === "direct" && styles.tabButtonActive]}
            onPress={() => setActiveTab("direct")}
          >
            <Text
              style={[
                styles.tabButtonText,
                activeTab === "direct" && styles.tabButtonTextActive,
              ]}
            >
              DIRECT & URGENT ({directNotifs.length})
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.tabButton, activeTab === "promo" && styles.tabButtonActive]}
            onPress={() => setActiveTab("promo")}
          >
            <Text
              style={[
                styles.tabButtonText,
                activeTab === "promo" && styles.tabButtonTextActive,
              ]}
            >
              PROMOTIONS ({promoNotifs.length})
            </Text>
          </TouchableOpacity>
        </View>

        {displayedNotifs.length === 0 ? (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyText}>
              {activeTab === "promo"
                ? "No promotional alerts intercepted."
                : activeTab === "direct"
                ? "No direct alerts intercepted."
                : "No notifications relayed yet. Incoming alerts will appear here."}
            </Text>
          </View>
        ) : (
          <View style={styles.notifList}>
            {displayedNotifs.slice(0, 15).map((n, idx) => {
              const priorityColor = getPriorityColor(n.priority || "LOW");
              const appMeta = getAppTag(n);
              const isLatest = idx === 0;
              const timeLabel = formatRelativeTime(n.timestamp);

              return (
                <View key={`notif_${n.id || idx}`} style={styles.notifPod}>
                  {/* Top Meta Bar */}
                  <View style={styles.notifTopRow}>
                    <View style={styles.originContainer}>
                      <View
                        style={[styles.appBadge, { borderColor: appMeta.color }]}
                      >
                        <Text style={[styles.appBadgeText, { color: appMeta.color }]}>
                          {appMeta.name}
                        </Text>
                      </View>
                      {n.is_promo || n.category === "PROMOTION" ? (
                        <View style={styles.promoBadge}>
                          <Text style={styles.promoBadgeText}>PROMO</Text>
                        </View>
                      ) : null}
                    </View>

                    <View style={styles.rightMetaContainer}>
                      {timeLabel ? (
                        <Text style={styles.timeLabel}>{timeLabel}</Text>
                      ) : null}
                      {isLatest ? (
                        <View style={styles.latestBadge}>
                          <Text style={styles.latestBadgeText}>LATEST</Text>
                        </View>
                      ) : null}
                      <View style={[styles.priorityBadge, { borderColor: priorityColor }]}>
                        <Text style={[styles.priorityBadgeText, { color: priorityColor }]}>
                          {n.priority || "LOW"}
                        </Text>
                      </View>
                    </View>
                  </View>

                  <Text style={styles.notifTitle}>{n.title}</Text>
                  {n.text ? <Text style={styles.notifBody}>{n.text}</Text> : null}

                  {/* Inline OTP Security Box */}
                  {n.otp_code ? (
                    <View style={styles.otpBox}>
                      <View>
                        <Text style={styles.otpHeader}>SECURITY VERIFICATION CODE</Text>
                        <Text selectable={true} style={styles.otpCode}>
                          {n.otp_code}
                        </Text>
                      </View>
                      <View style={styles.otpTag}>
                        <Text style={styles.otpTagText}>AUTO-READ BY ALFRED</Text>
                      </View>
                    </View>
                  ) : null}
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
    flexWrap: "wrap",
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.md,
  },
  testButton: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.xs,
    paddingVertical: theme.spacing.xs,
    paddingHorizontal: theme.spacing.sm,
  },
  testButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 0.8,
    color: theme.colors.textSecondary,
    fontWeight: "600",
  },
  testButtonUrgent: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.accent,
    borderRadius: theme.radii.xs,
    paddingVertical: theme.spacing.xs,
    paddingHorizontal: theme.spacing.sm,
  },
  testButtonUrgentText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 0.8,
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
  tabRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginBottom: theme.spacing.md,
  },
  tabButton: {
    paddingVertical: 5,
    paddingHorizontal: 9,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    backgroundColor: theme.colors.cardSubtle,
  },
  tabButtonActive: {
    borderColor: theme.colors.borderActive,
    backgroundColor: theme.colors.cardElevated,
  },
  tabButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 0.8,
    color: theme.colors.textMuted,
    fontWeight: "600",
  },
  tabButtonTextActive: {
    color: theme.colors.boneWhite,
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
  originContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  appBadge: {
    borderWidth: 1,
    borderRadius: theme.radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 1,
    backgroundColor: "transparent",
  },
  appBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  promoBadge: {
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radii.xs,
    paddingHorizontal: 5,
    paddingVertical: 1,
    backgroundColor: "transparent",
  },
  promoBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "600",
    color: theme.colors.textGhost,
    letterSpacing: 0.5,
  },
  rightMetaContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  timeLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  latestBadge: {
    borderWidth: 1,
    borderColor: "#444440",
    borderRadius: theme.radii.xs,
    paddingHorizontal: 5,
    paddingVertical: 1,
    backgroundColor: "#222220",
  },
  latestBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
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
  otpBox: {
    marginTop: theme.spacing.sm,
    padding: theme.spacing.sm,
    backgroundColor: "#161616",
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.border,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  otpHeader: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    letterSpacing: 1,
    color: theme.colors.textMuted,
    marginBottom: 2,
  },
  otpCode: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: "700",
    letterSpacing: 3,
    color: theme.colors.boneWhite,
  },
  otpTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  otpTagText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    letterSpacing: 0.5,
    color: theme.colors.textMuted,
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
