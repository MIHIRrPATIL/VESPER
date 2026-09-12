import React, { useState, useEffect } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
} from "react-native";
import { theme } from "../styles/theme";
import { gatewayClient } from "../services/gateway";
import { EventType } from "../types/events";
import { CascadeView } from "./CascadeView";

export interface DirectiveMessage {
  id: string;
  sender: "user" | "alfred";
  text: string;
  time: string;
  latencyMs?: number;
  intent?: string;
  transcript?: string;
  hudCards?: any[];
  specialistOutcome?: any;
}

interface DirectivesTabProps {
  onOpenHudCards?: (cards: any[]) => void;
  onOpenHudDeck?: () => void;
}

export const DirectivesTab: React.FC<DirectivesTabProps> = ({
  onOpenHudCards,
  onOpenHudDeck,
}) => {
  const [inputText, setInputText] = useState("");
  const [executing, setExecuting] = useState(false);
  const [expandedTranscripts, setExpandedTranscripts] = useState<Set<string>>(
    new Set()
  );
  const [messages, setMessages] = useState<DirectiveMessage[]>([
    {
      id: "initial_greeting",
      sender: "alfred",
      text: "At your service, sir. Speak or transmit a directive to coordinate the cluster.",
      time: "Ready",
      latencyMs: 120,
      intent: "GREETING",
      transcript:
        "Cluster initialized. Sentry daemons armed. Ready for cognitive dispatch.",
    },
  ]);

  useEffect(() => {
    // Listen to real-time cluster AGENT_RESPONSE envelopes
    const unsub = gatewayClient.onEnvelope((env) => {
      if (env.type === EventType.AGENT_RESPONSE || env.type === "AGENT_RESPONSE") {
        const payload = env.payload || {};
        const alfredText =
          payload.response ||
          payload.speech_text ||
          payload.markdown_body ||
          "Directive executed across cluster.";
        const timeNow = new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });

        const newMsg: DirectiveMessage = {
          id: env.uuid || `alfred_${Date.now()}`,
          sender: "alfred",
          text: alfredText,
          time: timeNow,
          latencyMs: payload.latency_ms ? Math.round(payload.latency_ms) : undefined,
          intent: payload.intent || payload.plan_type || "DIRECTIVE",
          transcript:
            payload.markdown_body ||
            payload.reasoning ||
            payload.transcript ||
            undefined,
          hudCards: payload.hud_cards || [],
          specialistOutcome: (payload.hud_cards || [])[0],
        };

        setMessages((prev) => {
          // Prevent duplicates if already added by executeDirective
          if (prev.some((m) => m.id === newMsg.id)) return prev;
          return [newMsg, ...prev];
        });
      }
    });

    return () => unsub();
  }, []);

  const quickDirectives = [
    "What is my bank balance?",
    "How's the weather tomorrow in Mumbai?",
    "Check my unread emails",
    "What are my tasks today?",
    "Show system vitals",
  ];

  const toggleTranscript = (msgId: string) => {
    setExpandedTranscripts((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) {
        next.delete(msgId);
      } else {
        next.add(msgId);
      }
      return next;
    });
  };

  const handleRunDirective = async (queryToRun?: string) => {
    const query = (queryToRun || inputText).trim();
    if (!query || executing) return;

    setInputText("");
    const userMsgId = `user_${Date.now()}`;
    const timeNow = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    setMessages((prev) => [
      { id: userMsgId, sender: "user", text: query, time: timeNow },
      ...prev,
    ]);

    setExecuting(true);
    const startTime = Date.now();

    try {
      // 1. Send via WebSocket voice command broadcast if connected
      gatewayClient.sendVoiceCommand(query);

      // 2. Also invoke directive endpoint for direct response payload
      const res = await gatewayClient.executeDirective(query);
      const latency = Date.now() - startTime;

      const alfredText =
        res?.speech_text ||
        res?.response ||
        res?.raw_response ||
        "I have completed the requested directive, sir.";

      const cards = res?.hud_cards || [];
      const transcriptText =
        res?.markdown_body ||
        res?.reasoning ||
        res?.transcript ||
        (cards.length > 0
          ? `Executed specialist card output for ${cards[0]?.type || "directive"}.`
          : undefined);

      const alfredMsgId = `alfred_${Date.now()}`;
      setMessages((prev) => [
        {
          id: alfredMsgId,
          sender: "alfred",
          text: alfredText,
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          latencyMs: res?.latency_ms ? Math.round(res.latency_ms) : latency,
          intent: res?.plan_type || res?.intent || "DIRECTIVE",
          transcript: transcriptText,
          hudCards: cards,
          specialistOutcome: cards[0] || res?.data,
        },
        ...prev,
      ]);

      if (cards.length > 0 && onOpenHudCards) {
        onOpenHudCards(cards);
      }
    } catch (err: any) {
      setMessages((prev) => [
        {
          id: `err_${Date.now()}`,
          sender: "alfred",
          text: `I encountered an issue executing that command, sir. ${err?.message || ""}`,
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        },
        ...prev,
      ]);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* ── 1. Directive Input Card ── */}
      <CascadeView delay={0}>
        <View style={styles.card}>
          <Text style={styles.sectionHeader}>COMMAND & DIRECTIVES</Text>
          <Text style={styles.helpText}>
            Transmit instructions directly to the Alfred Cognitive Swarm over Gateway.
          </Text>

          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              value={inputText}
              onChangeText={setInputText}
              placeholder="Instruct Alfred..."
              placeholderTextColor={theme.colors.textGhost}
              onSubmitEditing={() => handleRunDirective()}
              returnKeyType="send"
              editable={!executing}
            />
            <TouchableOpacity
              style={[styles.primaryButton, executing && styles.buttonDisabled]}
              onPress={() => handleRunDirective()}
              disabled={executing}
            >
              {executing ? (
                <ActivityIndicator size="small" color={theme.colors.bg} />
              ) : (
                <Text style={styles.primaryButtonText}>DISPATCH</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Quick Chips */}
          <Text style={[styles.label, { marginTop: theme.spacing.md }]}>
            QUICK DIRECTIVES
          </Text>
          <View style={styles.chipsRow}>
            {quickDirectives.map((d, idx) => (
              <TouchableOpacity
                key={`chip_${idx}`}
                style={styles.chip}
                onPress={() => handleRunDirective(d)}
                disabled={executing}
              >
                <Text style={styles.chipText}>{d}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </CascadeView>

      {/* ── 2. Directive Execution Feed ── */}
      <CascadeView delay={60}>
        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.sectionHeader}>EXECUTION FEED</Text>
            {executing ? (
              <View style={styles.executingBadge}>
                <ActivityIndicator size="small" color={theme.colors.warning} />
                <Text style={styles.executingText}>PLANNING</Text>
              </View>
            ) : (
              <Text style={styles.feedStatusText}>SYNCED</Text>
            )}
          </View>

          <View style={styles.messageList}>
            {messages.map((msg) => {
              const isUser = msg.sender === "user";
              const isExpanded = expandedTranscripts.has(msg.id);
              const hasCards = (msg.hudCards && msg.hudCards.length > 0) || !!msg.specialistOutcome;

              return (
                <View
                  key={msg.id}
                  style={[
                    styles.messageBubble,
                    isUser ? styles.userBubble : styles.alfredBubble,
                  ]}
                >
                  <View style={styles.messageHeader}>
                    <View style={styles.senderBadgeRow}>
                      <View
                        style={[
                          styles.bubbleDot,
                          {
                            backgroundColor: isUser
                              ? theme.colors.textMuted
                              : theme.colors.accent,
                          },
                        ]}
                      />
                      <Text style={styles.senderLabel}>
                        {isUser ? "YOU // DIRECTIVE" : "ALFRED BUTLER RESPONSE"}
                      </Text>
                      {!isUser && msg.latencyMs !== undefined && (
                        <View style={styles.latencyBadge}>
                          <Text style={styles.latencyText}>
                            {msg.latencyMs}ms
                          </Text>
                        </View>
                      )}
                    </View>
                    <Text style={styles.messageTime}>{msg.time}</Text>
                  </View>

                  <Text style={isUser ? styles.userText : styles.alfredText}>
                    {msg.text}
                  </Text>

                  {/* Specialist HUD Outcome Button */}
                  {hasCards && (
                    <View style={styles.outcomeBar}>
                      <View style={styles.outcomeInfo}>
                        <Text style={styles.outcomeTag}>
                          SPECIALIST // {msg.hudCards?.[0]?.type?.toUpperCase() || "HUD CARD"}
                        </Text>
                      </View>
                      <TouchableOpacity
                        style={styles.hudDeckBtn}
                        onPress={() => {
                          if (msg.hudCards && msg.hudCards.length > 0 && onOpenHudCards) {
                            onOpenHudCards(msg.hudCards);
                          } else if (onOpenHudDeck) {
                            onOpenHudDeck();
                          }
                        }}
                      >
                        <Text style={styles.hudDeckBtnText}>VIEW IN HUD DECK</Text>
                      </TouchableOpacity>
                    </View>
                  )}

                  {/* Transcript & Reasoning Toggle */}
                  {msg.transcript && (
                    <View style={styles.transcriptContainer}>
                      <TouchableOpacity
                        style={styles.transcriptToggle}
                        onPress={() => toggleTranscript(msg.id)}
                      >
                        <Text style={styles.transcriptToggleText}>
                          {isExpanded
                            ? "[-] COLLAPSE REASONING TRANSCRIPT"
                            : "[+] VIEW REASONING TRANSCRIPT"}
                        </Text>
                      </TouchableOpacity>

                      {isExpanded && (
                        <View style={styles.transcriptBox}>
                          <Text style={styles.transcriptText}>
                            {msg.transcript}
                          </Text>
                        </View>
                      )}
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        </View>
      </CascadeView>
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
  helpText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.md,
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
    fontFamily: theme.fonts.sans,
    fontSize: 13,
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
  buttonDisabled: {
    opacity: 0.6,
  },
  chipsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.xs,
  },
  chip: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radii.xs,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  chipText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
  executingBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  executingText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
    color: theme.colors.warning,
  },
  feedStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1,
    color: theme.colors.textGhost,
  },
  messageList: {
    gap: theme.spacing.md,
  },
  messageBubble: {
    borderRadius: theme.radii.xs,
    padding: theme.spacing.md,
    borderWidth: 1,
  },
  userBubble: {
    backgroundColor: theme.colors.cardElevated,
    borderColor: theme.colors.borderSubtle,
  },
  alfredBubble: {
    backgroundColor: theme.colors.cardSubtle,
    borderColor: theme.colors.border,
  },
  messageHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: theme.spacing.xs,
  },
  senderBadgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  bubbleDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  senderLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1.5,
    color: theme.colors.textMuted,
    fontWeight: "600",
  },
  latencyBadge: {
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: theme.radii.xs,
    backgroundColor: theme.colors.card,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  latencyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textSecondary,
    letterSpacing: 0.5,
  },
  messageTime: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textGhost,
  },
  userText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    lineHeight: 19,
    color: theme.colors.textPrimary,
  },
  alfredText: {
    fontFamily: theme.fonts.serif,
    fontSize: 14,
    lineHeight: 22,
    color: theme.colors.textPrimary,
    fontStyle: "italic",
  },
  outcomeBar: {
    marginTop: theme.spacing.sm,
    paddingTop: theme.spacing.xs,
    borderTopWidth: 1,
    borderTopColor: theme.colors.borderSubtle,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  outcomeInfo: {
    flex: 1,
  },
  outcomeTag: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1,
    color: theme.colors.textMuted,
  },
  hudDeckBtn: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 3,
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  hudDeckBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "600",
    letterSpacing: 1,
    color: theme.colors.accent,
  },
  transcriptContainer: {
    marginTop: theme.spacing.xs,
  },
  transcriptToggle: {
    paddingVertical: 3,
  },
  transcriptToggleText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1,
    color: theme.colors.textMuted,
  },
  transcriptBox: {
    marginTop: 4,
    padding: theme.spacing.sm,
    backgroundColor: theme.colors.card,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  transcriptText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    lineHeight: 16,
    color: theme.colors.textSecondary,
  },
});
