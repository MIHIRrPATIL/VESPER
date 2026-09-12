import React, { useState, useEffect, useRef } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Animated,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";
import { gatewayClient } from "../services/gateway";
import { offlineStore } from "../services/offline-store";
import { ApiTask, CalendarEvent } from "../types/vesper";

export const CockpitView: React.FC = () => {
  const [time, setTime] = useState(new Date());
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [financeOverview, setFinanceOverview] = useState<any | null>(null);
  const [financeDebts, setFinanceDebts] = useState<any[]>([]);
  const [commandInput, setCommandInput] = useState("");
  const [spokenText, setSpokenText] = useState<string | null>(null);
  const [isWakeWordArmed, setIsWakeWordArmed] = useState<boolean>(workstationStore.isWakeWordArmed);
  const [zenMode, setZenMode] = useState<boolean>(workstationStore.zenMode);

  const spokenFadeAnim = useRef(new Animated.Value(0)).current;
  const dismissTimerRef = useRef<any>(null);

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    fetchTasksAndCalendar();
    loadFinanceData();
  }, []);

  useEffect(() => {
    const unsub = workstationStore.subscribe(() => {
      setIsWakeWordArmed(workstationStore.isWakeWordArmed);
      setZenMode(workstationStore.zenMode);

      const messages = workstationStore.messages;
      const latestAgentMsg = [...messages].reverse().find((m) => m.sender === "agent");
      if (latestAgentMsg?.text && latestAgentMsg.text !== spokenText) {
        setSpokenText(latestAgentMsg.text);
        Animated.timing(spokenFadeAnim, {
          toValue: 1,
          duration: 250,
          useNativeDriver: true,
        }).start();

        if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
        dismissTimerRef.current = setTimeout(() => {
          Animated.timing(spokenFadeAnim, {
            toValue: 0,
            duration: 400,
            useNativeDriver: true,
          }).start(() => setSpokenText(null));
        }, 12000);
      }
    });

    return () => {
      unsub();
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    };
  }, [spokenText]);

  const fetchTasksAndCalendar = async () => {
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/tasks`);
      if (res.ok) {
        const data = await res.json();
        if (data.tasks) setTasks(data.tasks);
        if (data.calendar_events) setCalendarEvents(data.calendar_events);
      }
    } catch {}
  };

  const loadFinanceData = async () => {
    try {
      const cachedOv = await offlineStore.getCachedFinanceOverview();
      const cachedDebts = await offlineStore.getCachedDebts();
      if (cachedOv) setFinanceOverview(cachedOv);
      if (cachedDebts && Array.isArray(cachedDebts)) setFinanceDebts(cachedDebts);

      const [ovRes, debtRes] = await Promise.all([
        gatewayClient.fetchFinanceOverview(),
        gatewayClient.fetchFinanceDebts(),
      ]);

      if (ovRes) {
        setFinanceOverview(ovRes);
        offlineStore.saveCachedFinanceOverview(ovRes);
      }
      if (debtRes) {
        const debtsList = Array.isArray(debtRes) ? debtRes : (debtRes as any)?.debts || [];
        setFinanceDebts(debtsList);
        offlineStore.saveCachedDebts(debtsList);
      }
    } catch (e) {
      console.warn("[CockpitView] Finance load error:", e);
    }
  };

  const formatCurrency = (val: number | undefined | null) => {
    const num = Number(val || 0);
    return `₹${num.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };

  const handleToggleTask = async (task: ApiTask) => {
    setTasks((prev) =>
      prev.map((t) => (t.id === task.id ? { ...t, done: !t.done } : t))
    );
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      await fetch(`${baseUrl}/api/tasks/${task.id}/toggle`, { method: "PATCH" });
    } catch {
      fetchTasksAndCalendar();
    }
  };

  const handleDispatchCommand = () => {
    if (!commandInput.trim()) return;
    workstationStore.sendUserMessage(commandInput.trim());
    setCommandInput("");
  };

  // Chronometer formatters
  const rawHours = time.getHours();
  const displayHours = rawHours % 12 || 12;
  const hourStr = String(displayHours).padStart(2, "0");
  const minutes = String(time.getMinutes()).padStart(2, "0");
  const seconds = String(time.getSeconds()).padStart(2, "0");
  const period = rawHours >= 12 ? "PM" : "AM";
  const dayName = time.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase();
  const monthName = time.toLocaleDateString("en-US", { month: "short" }).toUpperCase();
  const dayNum = String(time.getDate()).padStart(2, "0");

  const getGreeting = () => {
    if (rawHours < 12) return "Good morning, sir.";
    if (rawHours < 17) return "Good afternoon, sir.";
    if (rawHours < 21) return "Good evening, sir.";
    return "Working late, sir.";
  };

  const pendingTasks = tasks.filter((t) => !t.done);
  const topTask = pendingTasks[0] || null;
  const nextEvent = calendarEvents[0] || null;

  const totalLiquidMoney = financeOverview?.total_net_worth ?? 245000;

  const debtsOwedToUser = (financeDebts || [])
    .filter((d: any) => !d.settled && d.direction === "owed")
    .reduce((acc: number, d: any) => acc + (d.amount || 0), 0);

  const debtsUserOwes = (financeDebts || [])
    .filter((d: any) => !d.settled && d.direction === "owe")
    .reduce((acc: number, d: any) => acc + (d.amount || 0), 0);

  const netPeerBalance = debtsOwedToUser - debtsUserOwes;

  let netOwedDescription = "All Debts Settled";
  if (netPeerBalance > 0) {
    netOwedDescription = `+${formatCurrency(netPeerBalance)} Net Owed to You`;
  } else if (netPeerBalance < 0) {
    netOwedDescription = `-${formatCurrency(Math.abs(netPeerBalance))} You Owe`;
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* ── Section 1: Aerospace Header & Live Telemetry Deck ── */}
      <View style={styles.headerOuterBezel}>
        <View style={styles.headerInnerCore}>
          <View style={styles.greetingBlock}>
            <View style={styles.systemTagRow}>
              <View style={styles.pulseDot} />
              <Text style={styles.systemTagText}>CLUSTER NOMINAL</Text>
              <Text style={styles.systemSeparator}>•</Text>
              <Text style={styles.systemNodeText}>EDGE-01</Text>
            </View>
            <Text style={styles.greetingTitle}>{getGreeting()}</Text>
            <Text style={styles.greetingSub}>Swarm standing watch over 10 active nodes.</Text>
          </View>

          {/* Precision Aerospace Chronometer Pill */}
          <View style={styles.chronoCapsule}>
            <View style={styles.chronoTopRow}>
              <Text style={styles.chronoDigits}>
                {hourStr}:{minutes}
              </Text>
              <Text style={styles.chronoSeconds}>:{seconds}</Text>
              <Text style={styles.chronoPeriod}>{period}</Text>
            </View>
            <Text style={styles.chronoDate}>
              {dayName} • {monthName} {dayNum}
            </Text>
          </View>
        </View>
      </View>

      {/* ── Section 2: Alfred Live Spoken Transcript (Dynamic Pulse) ── */}
      {spokenText ? (
        <Animated.View style={[styles.spokenOuterBezel, { opacity: spokenFadeAnim }]}>
          <View style={styles.spokenInnerCore}>
            <View style={styles.spokenHeaderRow}>
              <View style={styles.spokenTitleWrap}>
                <View style={styles.spokenDot} />
                <Text style={styles.spokenLabel}>ALFRED BUTLER</Text>
              </View>
              <Text style={styles.spokenStatusBadge}>VOICE SYNTHESIZED</Text>
            </View>
            <Text style={styles.spokenBodyText}>"{spokenText}"</Text>
          </View>
        </Animated.View>
      ) : null}

      {/* ── Section 3: High-Visibility Directives Capsule Bar ── */}
      <View style={styles.directiveOuterBezel}>
        <View style={styles.directiveInnerCore}>
          <View style={styles.directiveInputRow}>
            <Text style={styles.directivePrefix}>vesper &gt;</Text>
            <TextInput
              style={styles.directiveInput}
              value={commandInput}
              onChangeText={setCommandInput}
              placeholder="Instruct Alfred or query cluster..."
              placeholderTextColor="#A39E93"
              onSubmitEditing={handleDispatchCommand}
              returnKeyType="send"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TouchableOpacity
              style={[
                styles.directiveRunBtn,
                !commandInput.trim() && styles.directiveRunBtnDisabled,
              ]}
              onPress={handleDispatchCommand}
              disabled={!commandInput.trim()}
              activeOpacity={0.8}
            >
              <Text
                style={[
                  styles.directiveRunText,
                  !commandInput.trim() && styles.directiveRunTextDisabled,
                ]}
              >
                RUN
              </Text>
            </TouchableOpacity>
          </View>

          {/* Action Chips */}
          <View style={styles.chipsRow}>
            {[
              "Check balance",
              "Today's agenda",
              "Swarm status",
            ].map((chip) => (
              <TouchableOpacity
                key={chip}
                style={styles.chipPill}
                onPress={() => workstationStore.sendUserMessage(chip)}
                activeOpacity={0.7}
              >
                <Text style={styles.chipPillText}>{chip}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>

      {/* ── Section 4: Asymmetric Bento Architecture ── */}

      {/* Hero Card: Primary Mission / Focus (Full Width) */}
      <View style={styles.heroOuterBezel}>
        <TouchableOpacity
          style={styles.heroInnerCore}
          onPress={() => workstationStore.setActiveView("agenda")}
          activeOpacity={0.85}
        >
          <View style={styles.bentoHeaderRow}>
            <View style={styles.bentoTagWrap}>
              <View style={styles.bentoAmberDot} />
              <Text style={styles.bentoEyebrow}>PRIMARY MISSION FOCUS</Text>
            </View>
            <View style={styles.bentoLinkCapsule}>
              <Text style={styles.bentoLinkText}>AGENDA &gt;</Text>
            </View>
          </View>

          <View style={styles.heroContentRow}>
            {topTask ? (
              <View style={styles.heroTaskCol}>
                <TouchableOpacity
                  style={styles.taskToggleRow}
                  onPress={() => handleToggleTask(topTask)}
                  activeOpacity={0.7}
                >
                  <View
                    style={[
                      styles.heroCheckbox,
                      topTask.done && styles.heroCheckboxDone,
                    ]}
                  >
                    {topTask.done && <View style={styles.heroCheckboxCheck} />}
                  </View>
                  <Text
                    style={[
                      styles.heroTaskTitle,
                      topTask.done && styles.heroTaskTitleDone,
                    ]}
                    numberOfLines={2}
                  >
                    {topTask.title}
                  </Text>
                </TouchableOpacity>

                <View style={styles.heroMetaRow}>
                  <Text style={styles.heroMetaText}>
                    {pendingTasks.length} {pendingTasks.length === 1 ? "task" : "tasks"} remaining today
                  </Text>
                  {nextEvent ? (
                    <Text style={styles.heroMetaEvent} numberOfLines={1}>
                      • Next: {nextEvent.summary || nextEvent.title}
                    </Text>
                  ) : null}
                </View>
              </View>
            ) : (
              <View style={styles.allClearCol}>
                <Text style={styles.allClearTitle}>All Objectives Completed</Text>
                <Text style={styles.allClearSubtitle}>
                  No remaining tasks scheduled for today. Ready for directives.
                </Text>
              </View>
            )}
          </View>
        </TouchableOpacity>
      </View>

      {/* Dual Bento Row: Capital Ledger + Specialist Swarm */}
      <View style={styles.dualBentoRow}>
        {/* Card A: Financial Ledger */}
        <View style={styles.dualCardOuter}>
          <TouchableOpacity
            style={styles.dualCardInner}
            onPress={() => workstationStore.setActiveView("ledger")}
            activeOpacity={0.85}
          >
            <View style={styles.bentoHeaderRow}>
              <Text style={styles.bentoEyebrow}>CAPITAL LEDGER</Text>
              <Text style={styles.cardArrow}>&gt;</Text>
            </View>

            <View style={styles.dualValueCol}>
              <Text style={styles.dualMetricMain} numberOfLines={1} adjustsFontSizeToFit>
                {formatCurrency(totalLiquidMoney)}
              </Text>
              <Text style={styles.dualMetricSub} numberOfLines={1}>
                {netOwedDescription}
              </Text>
            </View>

            <View style={styles.dualFooterPill}>
              <View style={styles.syncPulseDot} />
              <Text style={styles.dualFooterText}>SUPABASE SYNCED</Text>
            </View>
          </TouchableOpacity>
        </View>

        {/* Card B: Swarm Topology */}
        <View style={styles.dualCardOuter}>
          <TouchableOpacity
            style={styles.dualCardInner}
            onPress={() => workstationStore.setActiveView("services")}
            activeOpacity={0.85}
          >
            <View style={styles.bentoHeaderRow}>
              <Text style={styles.bentoEyebrow}>SWARM TOPOLOGY</Text>
              <Text style={styles.cardArrow}>&gt;</Text>
            </View>

            <View style={styles.dualValueCol}>
              <Text style={styles.dualMetricMain}>10 Nodes</Text>
              <Text style={styles.dualMetricSub}>Alfred, Vision, Radar active</Text>
            </View>

            <View style={styles.dualFooterPill}>
              <View style={styles.nominalDot} />
              <Text style={styles.dualFooterText}>EDGE HEALTHY</Text>
            </View>
          </TouchableOpacity>
        </View>
      </View>

      {/* ── Section 5: Hardware & Focus Quick Deck ── */}
      <View style={styles.quickDeckRow}>
        {/* Zen Focus Launcher */}
        <TouchableOpacity
          style={[styles.quickDeckBtn, zenMode && styles.quickDeckBtnActive]}
          onPress={() => workstationStore.toggleZenMode()}
          activeOpacity={0.8}
        >
          <Text style={styles.quickDeckGlyph}>◬</Text>
          <View style={styles.quickDeckTextCol}>
            <Text style={styles.quickDeckLabel}>ZEN FOCUS</Text>
            <Text style={styles.quickDeckSub}>{zenMode ? "ACTIVE (25M)" : "START 25M SPRINT"}</Text>
          </View>
        </TouchableOpacity>

        {/* Wake Word Acoustic Toggle */}
        <TouchableOpacity
          style={[styles.quickDeckBtn, isWakeWordArmed && styles.quickDeckBtnActive]}
          onPress={() => workstationStore.toggleWakeWord()}
          activeOpacity={0.8}
        >
          <Text style={styles.quickDeckGlyph}>◉</Text>
          <View style={styles.quickDeckTextCol}>
            <Text style={styles.quickDeckLabel}>WAKE WORD</Text>
            <Text style={styles.quickDeckSub}>{isWakeWordArmed ? "ARMED (HEY ALFRED)" : "MUTED"}</Text>
          </View>
        </TouchableOpacity>
      </View>

      <View style={{ height: 28 }} />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  contentContainer: {
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 24,
  },

  // Double-Bezel Header
  headerOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    padding: 3,
    marginBottom: 12,
  },
  headerInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 17,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  greetingBlock: {
    marginBottom: 12,
  },
  systemTagRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
  },
  pulseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  systemTagText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  systemSeparator: {
    color: "rgba(255, 255, 255, 0.2)",
    fontSize: 10,
  },
  systemNodeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  greetingTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 24,
    fontStyle: "italic",
    color: theme.colors.boneWhite,
    letterSpacing: -0.3,
  },
  greetingSub: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: 2,
    lineHeight: 16,
  },

  // Chronometer Capsule
  chronoCapsule: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "#141414",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  chronoTopRow: {
    flexDirection: "row",
    alignItems: "baseline",
  },
  chronoDigits: {
    fontFamily: theme.fonts.mono,
    fontSize: 22,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },
  chronoSeconds: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.textMuted,
    marginLeft: 1,
  },
  chronoPeriod: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    marginLeft: 5,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
  },
  chronoDate: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },

  // Alfred Spoken Speech Bubble
  spokenOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    padding: 3,
    marginBottom: 12,
  },
  spokenInnerCore: {
    backgroundColor: "#18221D",
    borderRadius: 13,
    padding: 12,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.15)",
  },
  spokenHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  spokenTitleWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  spokenDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  spokenLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  spokenStatusBadge: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "rgba(255, 255, 255, 0.5)",
    letterSpacing: 0.8,
  },
  spokenBodyText: {
    fontFamily: theme.fonts.serif,
    fontSize: 13,
    fontStyle: "italic",
    color: theme.colors.boneWhite,
    lineHeight: 19,
  },

  // Directive Command Deck
  directiveOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    padding: 3,
    marginBottom: 12,
  },
  directiveInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 15,
    padding: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  directiveInputRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#131313",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  directivePrefix: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginRight: 6,
  },
  directiveInput: {
    flex: 1,
    color: theme.colors.boneWhite,
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    paddingVertical: 6,
  },
  directiveRunBtn: {
    backgroundColor: theme.colors.boneWhite,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  directiveRunBtnDisabled: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.16)",
  },
  directiveRunText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: "#121212",
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  directiveRunTextDisabled: {
    color: "#D1CCC2",
    fontWeight: "600",
  },
  chipsRow: {
    flexDirection: "row",
    gap: 6,
    marginTop: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  chipPill: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  chipPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#A39E93",
  },

  // Hero Bento Card
  heroOuterBezel: {
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    padding: 3,
    marginBottom: 12,
  },
  heroInnerCore: {
    backgroundColor: "#1C1C1C",
    borderRadius: 15,
    padding: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  bentoHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  bentoTagWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  bentoAmberDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.amber,
  },
  bentoEyebrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1.3,
    fontWeight: "700",
  },
  bentoLinkCapsule: {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 4,
  },
  bentoLinkText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
  },
  cardArrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
  },
  heroContentRow: {
    marginTop: 2,
  },
  heroTaskCol: {
    gap: 6,
  },
  taskToggleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  heroCheckbox: {
    width: 18,
    height: 18,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: "rgba(255, 255, 255, 0.3)",
    alignItems: "center",
    justifyContent: "center",
  },
  heroCheckboxDone: {
    backgroundColor: theme.colors.emerald,
    borderColor: theme.colors.emerald,
  },
  heroCheckboxCheck: {
    width: 6,
    height: 6,
    backgroundColor: "#121212",
    borderRadius: 1,
  },
  heroTaskTitle: {
    flex: 1,
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    lineHeight: 20,
  },
  heroTaskTitleDone: {
    textDecorationLine: "line-through",
    color: theme.colors.textMuted,
  },
  heroMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginLeft: 28,
  },
  heroMetaText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  heroMetaEvent: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.amber,
    flex: 1,
  },
  allClearCol: {
    paddingVertical: 6,
  },
  allClearTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 16,
    fontStyle: "italic",
    color: theme.colors.boneWhite,
  },
  allClearSubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: 2,
  },

  // Dual Bento Row
  dualBentoRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 12,
  },
  dualCardOuter: {
    flex: 1,
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.07)",
    padding: 3,
  },
  dualCardInner: {
    backgroundColor: "#1C1C1C",
    borderRadius: 15,
    padding: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    minHeight: 108,
    justifyContent: "space-between",
  },
  dualValueCol: {
    marginVertical: 4,
  },
  dualMetricMain: {
    fontFamily: theme.fonts.serif,
    fontSize: 16,
    color: theme.colors.boneWhite,
  },
  dualMetricSub: {
    fontFamily: theme.fonts.sans,
    fontSize: 10,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  dualFooterPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 6,
    alignSelf: "flex-start",
  },
  syncPulseDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: theme.colors.emerald,
  },
  nominalDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: theme.colors.info,
  },
  dualFooterText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
  },

  // Quick Deck Row
  quickDeckRow: {
    flexDirection: "row",
    gap: 10,
  },
  quickDeckBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#181818",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  quickDeckBtnActive: {
    borderColor: "rgba(255, 255, 255, 0.22)",
    backgroundColor: "#222222",
  },
  quickDeckGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.boneWhite,
  },
  quickDeckTextCol: {
    flex: 1,
  },
  quickDeckLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
    fontWeight: "700",
  },
  quickDeckSub: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
    marginTop: 1,
  },
});
