import React, { useState, useEffect } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";
import { MobileNotificationService } from "../services/notifications";
import { gatewayClient } from "../services/gateway";
import { ConversationMessage } from "../types/vesper";

type LogTab = "all" | "queries" | "intercepted" | "wire";

export const LogsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<LogTab>("all");
  const [messages, setMessages] = useState<ConversationMessage[]>(workstationStore.messages);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [testStatus, setTestStatus] = useState("");

  useEffect(() => {
    const unsub = workstationStore.subscribe(() => {
      setMessages(workstationStore.messages);
    });
    loadNotifications();
    return () => unsub();
  }, []);

  const loadNotifications = async () => {
    const notifs = await gatewayClient.fetchClusterNotifications(20);
    if (notifs) setNotifications(notifs);
  };

  const handleSendTestRelay = (type: "whatsapp" | "urgent") => {
    if (type === "whatsapp") {
      MobileNotificationService.sendNotification({
        package_name: "com.whatsapp",
        app_name: "WhatsApp",
        title: "Alex Chen",
        text: "Design review scheduled for 4:00 PM today. See you on the call!",
        priority: "HIGH",
      });
      setTestStatus("Sent WhatsApp test alert to cluster.");
    } else {
      MobileNotificationService.sendNotification({
        package_name: "com.datadoghq.app",
        app_name: "Datadog",
        title: "CRITICAL: Replica Latency Spike",
        text: "Database secondary replica latency exceeded 450ms in eu-west-1.",
        priority: "URGENT",
      });
      setTestStatus("Sent Urgent Server alert to cluster.");
    }
    setTimeout(() => {
      setTestStatus("");
      loadNotifications();
    }, 2500);
  };

  const queryGroups = messages.filter((m) => m.sender === "user" || m.sender === "agent");

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerMono}>AUDIT TRAILS & EVENT WIRE</Text>
          <Text style={styles.headerTitle}>Logs & Telemetry</Text>
        </View>
        <TouchableOpacity
          style={styles.clearBtn}
          onPress={() => workstationStore.clearMessages()}
        >
          <Text style={styles.clearBtnText}>CLEAR</Text>
        </TouchableOpacity>
      </View>

      {/* Filter Tabs */}
      <View style={styles.tabRow}>
        {(["all", "queries", "intercepted", "wire"] as LogTab[]).map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.subTab, activeTab === tab && styles.subTabActive]}
            onPress={() => setActiveTab(tab)}
          >
            <Text style={[styles.subTabText, activeTab === tab && styles.subTabTextActive]}>
              {tab.toUpperCase()}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={styles.scrollBody} showsVerticalScrollIndicator={false}>
        {/* Test Alert Forwarders */}
        <View style={styles.card}>
          <Text style={styles.cardMono}>NOTIFICATION INTERCEPTOR FORWARDERS</Text>
          <Text style={styles.cardDesc}>
            Test phone-to-cluster notification forwarding and desktop HUD relay.
          </Text>
          <View style={styles.testBtnRow}>
            <TouchableOpacity style={styles.testBtn} onPress={() => handleSendTestRelay("whatsapp")}>
              <Text style={styles.testBtnText}>+ TEST WHATSAPP</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.testBtn, styles.testBtnUrgent]} onPress={() => handleSendTestRelay("urgent")}>
              <Text style={[styles.testBtnText, { color: theme.colors.coral }]}>+ TEST URGENT</Text>
            </TouchableOpacity>
          </View>
          {testStatus ? <Text style={styles.statusConfirmText}>{testStatus}</Text> : null}
        </View>

        {/* ── Queries Tab ── */}
        {(activeTab === "all" || activeTab === "queries") && (
          <View style={styles.sectionBlock}>
            <Text style={styles.sectionHeaderMono}>SYNCHRONIZED QUERY SESSIONS</Text>
            {queryGroups.length === 0 ? (
              <View style={styles.card}>
                <Text style={styles.emptyText}>No query sessions recorded.</Text>
              </View>
            ) : (
              queryGroups.map((msg) => (
                <View key={msg.id} style={styles.queryCard}>
                  <View style={styles.queryHeaderRow}>
                    <Text style={styles.querySenderMono}>
                      {msg.sender === "user" ? "USER UTTERANCE" : "ALFRED RESPONSE"}
                    </Text>
                    {msg.latencyMs && (
                      <Text style={styles.queryLatencyMono}>{msg.latencyMs}ms</Text>
                    )}
                  </View>
                  <Text style={styles.queryText}>{msg.text}</Text>
                  {msg.specialistActions && msg.specialistActions.length > 0 && (
                    <View style={styles.specialistActionsBox}>
                      <Text style={styles.specialistBoxHeader}>SPECIALISTS COORDINATED:</Text>
                      {msg.specialistActions.map((act, i) => (
                        <Text key={i} style={styles.specialistActionLine}>
                          • {act.specialist || "Agent"}: {act.action || act.tool_name || "Processed"}
                        </Text>
                      ))}
                    </View>
                  )}
                </View>
              ))
            )}
          </View>
        )}

        {/* ── Intercepted Notifications Tab ── */}
        {(activeTab === "all" || activeTab === "intercepted") && (
          <View style={styles.sectionBlock}>
            <View style={styles.sectionHeaderRow}>
              <Text style={styles.sectionHeaderMono}>INTERCEPTED PHONE NOTIFICATIONS</Text>
              <TouchableOpacity onPress={loadNotifications}>
                <Text style={styles.syncLink}>REFRESH</Text>
              </TouchableOpacity>
            </View>

            {notifications.length === 0 ? (
              <View style={styles.card}>
                <Text style={styles.emptyText}>No intercepted notifications logged.</Text>
              </View>
            ) : (
              notifications.map((notif, idx) => (
                <View key={idx} style={styles.notifCard}>
                  <View style={styles.notifHeader}>
                    <Text style={styles.notifApp}>{notif.app_name || notif.package_name}</Text>
                    <View
                      style={[
                        styles.priorityPill,
                        { borderColor: notif.priority === "URGENT" ? theme.colors.coral : theme.colors.borderSubtle },
                      ]}
                    >
                      <Text
                        style={[
                          styles.priorityText,
                          { color: notif.priority === "URGENT" ? theme.colors.coral : theme.colors.boneWhite },
                        ]}
                      >
                        {notif.priority || "NORMAL"}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.notifTitle}>{notif.title}</Text>
                  <Text style={styles.notifText}>{notif.text}</Text>
                </View>
              ))
            )}
          </View>
        )}

        {/* ── Event Wire Tab ── */}
        {(activeTab === "all" || activeTab === "wire") && (
          <View style={styles.sectionBlock}>
            <Text style={styles.sectionHeaderMono}>RAW EVENT LOGS</Text>
            {messages.map((m) => (
              <View key={m.id} style={styles.wireRow}>
                <Text style={styles.wireTime}>
                  {new Date(m.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </Text>
                <Text style={styles.wireChannel}>{m.channel || "EVENT"}</Text>
                <Text style={styles.wireText} numberOfLines={2}>
                  {m.eventType || m.intent || m.text}
                </Text>
              </View>
            ))}
          </View>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
    paddingBottom: theme.spacing.sm,
  },
  headerLeft: {
    flex: 1,
  },
  headerMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
  },
  headerTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 22,
    color: theme.colors.boneWhite,
    marginTop: 2,
  },
  clearBtn: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: theme.radii.xs,
  },
  clearBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  tabRow: {
    flexDirection: "row",
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    padding: 2,
    marginBottom: theme.spacing.md,
    gap: 4,
  },
  subTab: {
    flex: 1,
    paddingVertical: 6,
    alignItems: "center",
    borderRadius: theme.radii.xs,
  },
  subTabActive: {
    backgroundColor: theme.colors.cardSubdued,
    borderWidth: 1,
    borderColor: theme.colors.borderActive,
  },
  subTabText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  subTabTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "bold",
  },
  scrollBody: {
    flex: 1,
  },
  card: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
  },
  cardMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1.2,
    marginBottom: 4,
  },
  cardDesc: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginBottom: 8,
  },
  testBtnRow: {
    flexDirection: "row",
    gap: 8,
  },
  testBtn: {
    flex: 1,
    backgroundColor: theme.colors.cardSubdued,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingVertical: 7,
    alignItems: "center",
    borderRadius: theme.radii.xs,
  },
  testBtnUrgent: {
    borderColor: "rgba(242, 106, 75, 0.4)",
  },
  testBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  statusConfirmText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.emerald,
    marginTop: 6,
  },
  sectionBlock: {
    marginBottom: theme.spacing.lg,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  sectionHeaderMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1.2,
    marginBottom: 6,
  },
  syncLink: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  queryCard: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.sm,
    marginBottom: 6,
  },
  queryHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  querySenderMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  queryLatencyMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.amber,
  },
  queryText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  specialistActionsBox: {
    marginTop: 6,
    paddingTop: 4,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  specialistBoxHeader: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    marginBottom: 2,
  },
  specialistActionLine: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
  },
  notifCard: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.sm,
    marginBottom: 6,
  },
  notifHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 2,
  },
  notifApp: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  priorityPill: {
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 2,
    borderWidth: 1,
  },
  priorityText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    letterSpacing: 1,
  },
  notifTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "bold",
    color: theme.colors.boneWhite,
  },
  notifText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  wireRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 5,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.03)",
  },
  wireTime: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    width: 60,
  },
  wireChannel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.amber,
    width: 60,
  },
  wireText: {
    flex: 1,
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    textAlign: "center",
    paddingVertical: 8,
  },
});
