import React, { useState, useEffect, useRef } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";
import { ConversationMessage } from "../types/vesper";

export const DirectivesView: React.FC = () => {
  const [inputText, setInputText] = useState("");
  const [expandedTranscripts, setExpandedTranscripts] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<ConversationMessage[]>(workstationStore.messages);
  const [agentState, setAgentState] = useState(workstationStore.agentState);
  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    const unsub = workstationStore.subscribe(() => {
      setMessages(workstationStore.messages);
      setAgentState(workstationStore.agentState);
    });
    return () => unsub();
  }, []);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    const timer = setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
    return () => clearTimeout(timer);
  }, [messages.length, agentState]);

  const handleSend = () => {
    const text = inputText.trim();
    if (!text) return;
    workstationStore.sendUserMessage(text);
    setInputText("");
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 150);
  };

  const handleToggleVoice = () => {
    if (agentState !== "IDLE") {
      workstationStore.sendInterrupt();
    } else {
      workstationStore.simulateWakeWord();
    }
  };

  const toggleTranscript = (id: string) => {
    setExpandedTranscripts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const quickDirectives = [
    "What is my bank balance?",
    "How is the weather tomorrow in Mumbai?",
    "Check my unread emails",
    "What are my agenda tasks today?",
    "Play my groovy vibes playlist",
    "Run optical presence scan",
  ];

  // Chronological top-to-bottom order (oldest to newest)
  const conversation = messages.filter(
    (m) => m.sender === "user" || m.sender === "agent"
  );

  const formatTime = (timestamp?: number) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    const h = String(date.getHours()).padStart(2, "0");
    const m = String(date.getMinutes()).padStart(2, "0");
    return `${h}:${m}`;
  };

  return (
    <KeyboardAvoidingView
      style={styles.keyboardContainer}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
    >
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.headerLabel}>ALFRED NEURAL DIRECTIVES</Text>
            <Text style={styles.headerTitle}>Directives</Text>
          </View>
          <View style={styles.agentStatePill}>
            <View
              style={[
                styles.stateDot,
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
            <Text style={styles.stateText}>{agentState}</Text>
          </View>
        </View>

        {/* Message Feed (Chronological Top-to-Bottom) */}
        <ScrollView
          ref={scrollViewRef}
          style={styles.feedScroll}
          contentContainerStyle={styles.feedContent}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: true })}
        >
          {conversation.length === 0 ? (
            <View style={styles.emptyFeed}>
              <View style={styles.emptyIconBox}>
                <Text style={styles.emptyGlyph}>[ALFRED STANDBY]</Text>
              </View>
              <Text style={styles.emptyTitle}>Ready for Directives</Text>
              <Text style={styles.emptyText}>
                Speak a command or type a directive below to instruct Alfred. Transcripts and reasoning will stream in real-time.
              </Text>
            </View>
          ) : (
            conversation.map((msg) => {
              const isUser = msg.sender === "user";
              const isExpanded = expandedTranscripts.has(msg.id);

              if (isUser) {
                return (
                  <View key={msg.id} style={styles.userBubbleWrapper}>
                    <View style={styles.userBubble}>
                      <View style={styles.userMetaRow}>
                        <Text style={styles.userLabel}>YOU</Text>
                        <Text style={styles.metaTime}>{formatTime(msg.timestamp)}</Text>
                      </View>
                      <Text style={styles.userText}>{msg.text}</Text>
                    </View>
                  </View>
                );
              }

              return (
                <View key={msg.id} style={styles.agentCardWrapper}>
                  <View style={styles.agentCard}>
                    {/* Agent Header */}
                    <View style={styles.agentCardHeader}>
                      <View style={styles.agentHeaderLeft}>
                        <View style={styles.agentDot} />
                        <Text style={styles.agentName}>ALFRED</Text>
                        {msg.latencyMs ? (
                          <Text style={styles.latencyText}>{msg.latencyMs}ms</Text>
                        ) : null}
                      </View>
                      <View style={styles.agentHeaderRight}>
                        {msg.intent && (
                          <View style={styles.intentBadge}>
                            <Text style={styles.intentBadgeText}>{msg.intent.toUpperCase()}</Text>
                          </View>
                        )}
                        <Text style={styles.metaTime}>{formatTime(msg.timestamp)}</Text>
                      </View>
                    </View>

                    {/* Spoken Response */}
                    <Text style={styles.spokenBodyText}>{msg.text}</Text>

                    {/* Collapsible Reasoning Transcript */}
                    {msg.markdown ? (
                      <View style={styles.transcriptSection}>
                        <TouchableOpacity
                          style={styles.transcriptToggle}
                          onPress={() => toggleTranscript(msg.id)}
                          activeOpacity={0.7}
                        >
                          <Text style={styles.transcriptToggleText}>
                            {isExpanded
                              ? "[-] HIDE REASONING TRANSCRIPT"
                              : "[+] VIEW REASONING TRANSCRIPT"}
                          </Text>
                        </TouchableOpacity>

                        {isExpanded && (
                          <View style={styles.transcriptBox}>
                            <Text style={styles.transcriptText}>{msg.markdown}</Text>
                          </View>
                        )}
                      </View>
                    ) : null}

                    {/* HUD Deck Link */}
                    {msg.cards && msg.cards.length > 0 && (
                      <View style={styles.hudDeckLinkRow}>
                        <TouchableOpacity
                          style={styles.hudDeckBtn}
                          onPress={() => workstationStore.openHudDrawer(msg.cards)}
                          activeOpacity={0.8}
                        >
                          <Text style={styles.hudDeckBtnText}>
                            INSPECT HUD INTELLIGENCE DECK ({msg.cards.length} CARDS) &gt;
                          </Text>
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                </View>
              );
            })
          )}

          {/* Agent Thinking Feedback Indicator */}
          {agentState === "THINKING" && (
            <View style={styles.thinkingIndicator}>
              <ActivityIndicator size="small" color={theme.colors.amber} />
              <Text style={styles.thinkingText}>Alfred is synthesizing response...</Text>
            </View>
          )}

          <View style={{ height: 16 }} />
        </ScrollView>

        {/* Suggestion Chips */}
        <View style={styles.chipsContainer}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipsScroll}
          >
            {quickDirectives.map((chip, idx) => (
              <TouchableOpacity
                key={idx}
                style={styles.chip}
                onPress={() => {
                  workstationStore.sendUserMessage(chip);
                  setTimeout(() => {
                    scrollViewRef.current?.scrollToEnd({ animated: true });
                  }, 150);
                }}
                activeOpacity={0.7}
              >
                <Text style={styles.chipText}>{chip}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>

        {/* Bottom Input Deck */}
        <View style={styles.inputContainer}>
          <View style={styles.inputBar}>
            <TouchableOpacity
              style={[
                styles.voiceMicBtn,
                agentState !== "IDLE" && styles.voiceMicBtnActive,
              ]}
              onPress={handleToggleVoice}
              activeOpacity={0.7}
            >
              <View
                style={[
                  styles.voiceMicDot,
                  agentState !== "IDLE" && {
                    backgroundColor:
                      agentState === "LISTENING"
                        ? theme.colors.emerald
                        : agentState === "THINKING"
                        ? theme.colors.amber
                        : theme.colors.rose,
                  },
                ]}
              />
              <Text
                style={[
                  styles.voiceMicText,
                  agentState !== "IDLE" && {
                    color:
                      agentState === "LISTENING"
                        ? theme.colors.emerald
                        : agentState === "THINKING"
                        ? theme.colors.amber
                        : theme.colors.rose,
                  },
                ]}
              >
                {agentState === "LISTENING" ? "MUTE" : agentState === "THINKING" || agentState === "SPEAKING" ? "STOP" : "VOICE"}
              </Text>
            </TouchableOpacity>

            <TextInput
              style={styles.textInput}
              value={inputText}
              onChangeText={setInputText}
              placeholder="Type directive for Alfred..."
              placeholderTextColor="#A39E93"
              onSubmitEditing={handleSend}
              returnKeyType="send"
              autoCapitalize="none"
              autoCorrect={false}
            />

            <TouchableOpacity
              style={[
                styles.sendBtn,
                (!inputText.trim() || agentState === "THINKING") && styles.sendBtnDisabled,
              ]}
              onPress={handleSend}
              disabled={!inputText.trim() || agentState === "THINKING"}
              activeOpacity={0.8}
            >
              <Text
                style={[
                  styles.sendBtnText,
                  (!inputText.trim() || agentState === "THINKING") && styles.sendBtnTextDisabled,
                ]}
              >
                DISPATCH
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  keyboardContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    paddingBottom: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
  },
  headerLeft: {
    flex: 1,
  },
  headerLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
  },
  headerTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 20,
    color: theme.colors.boneWhite,
    marginTop: 1,
  },
  agentStatePill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.cardElevated,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: theme.radii.xs,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  stateDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  stateText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  feedScroll: {
    flex: 1,
  },
  feedContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.sm,
  },
  emptyFeed: {
    padding: theme.spacing.xl,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 40,
  },
  emptyIconBox: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: theme.radii.xs,
    backgroundColor: theme.colors.cardSubdued,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    marginBottom: theme.spacing.sm,
  },
  emptyGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
  },
  emptyTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 18,
    color: theme.colors.boneWhite,
    marginBottom: 6,
  },
  emptyText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: "center",
    lineHeight: 18,
    maxWidth: 260,
  },
  userBubbleWrapper: {
    alignItems: "flex-end",
    marginBottom: theme.spacing.md,
  },
  userBubble: {
    maxWidth: "84%",
    backgroundColor: theme.colors.cardElevated,
    borderRadius: 14,
    borderBottomRightRadius: 2,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  userMetaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
    gap: 8,
  },
  userLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 1.2,
    fontWeight: "600",
  },
  metaTime: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textGhost,
  },
  userText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    color: theme.colors.boneWhite,
    lineHeight: 18,
  },
  agentCardWrapper: {
    alignItems: "flex-start",
    marginBottom: theme.spacing.md,
  },
  agentCard: {
    width: "100%",
    backgroundColor: theme.colors.cardSubdued,
    borderRadius: 14,
    borderTopLeftRadius: 2,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: theme.spacing.md,
  },
  agentCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.04)",
    paddingBottom: 6,
  },
  agentHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  agentDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  agentName: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  latencyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    marginLeft: 2,
  },
  agentHeaderRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  intentBadge: {
    backgroundColor: theme.colors.cardElevated,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  intentBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  spokenBodyText: {
    fontFamily: theme.fonts.serif,
    fontSize: 14,
    fontStyle: "italic",
    color: theme.colors.boneWhite,
    lineHeight: 21,
    marginVertical: 4,
  },
  transcriptSection: {
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
    paddingTop: 6,
  },
  transcriptToggle: {
    paddingVertical: 4,
  },
  transcriptToggleText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  transcriptBox: {
    backgroundColor: "#111111",
    borderRadius: theme.radii.xs,
    padding: theme.spacing.sm,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    marginTop: 4,
  },
  transcriptText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: "#B0AAA0",
    lineHeight: 15,
  },
  hudDeckLinkRow: {
    marginTop: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  hudDeckBtn: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.borderActive,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: theme.radii.xs,
    alignSelf: "flex-start",
  },
  hudDeckBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  thinkingIndicator: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  thinkingText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.amber,
    letterSpacing: 0.5,
  },
  chipsContainer: {
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
    paddingVertical: 6,
    backgroundColor: theme.colors.background,
  },
  chipsScroll: {
    paddingHorizontal: theme.spacing.md,
    gap: 6,
  },
  chip: {
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
  },
  chipText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  inputContainer: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: 4,
    paddingBottom: theme.spacing.sm,
    backgroundColor: theme.colors.background,
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.cardElevated,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  voiceMicBtn: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 14,
    backgroundColor: theme.colors.cardSubdued,
    marginRight: 6,
  },
  voiceMicBtnActive: {
    borderColor: theme.colors.emerald,
    borderWidth: 1,
  },
  voiceMicDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: theme.colors.textMuted,
    marginRight: 4,
  },
  voiceMicText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    fontWeight: "700",
  },
  textInput: {
    flex: 1,
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    paddingVertical: 6,
    paddingHorizontal: 6,
  },
  sendBtn: {
    backgroundColor: theme.colors.boneWhite,
    paddingHorizontal: 13,
    paddingVertical: 7,
    borderRadius: 14,
  },
  sendBtnDisabled: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.16)",
  },
  sendBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#121212",
    letterSpacing: 1,
    fontWeight: "700",
  },
  sendBtnTextDisabled: {
    color: "#D1CCC2",
    fontWeight: "600",
  },
});
