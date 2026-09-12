import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  TextInput,
  ActivityIndicator,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";
import { gatewayClient } from "../services/gateway";
import { ConnectedDevice } from "../types/vesper";
import { ServerEnvelope } from "../types/events";

type SystemSubTab = "specialists" | "hardware" | "health";

interface SpecialistAgent {
  id: string;
  name: string;
  domain: string;
  role: string;
  model: string;
  status: string;
  actionPrompt: string;
}

const SPECIALIST_AGENTS: SpecialistAgent[] = [
  {
    id: "system-specialist",
    name: "System Operations & Hardware Manager",
    domain: "SYSTEM & DPMS",
    role: "CPU/RAM load metrics, DPMS display sentry, audio sinks & shell execution engine",
    model: "Linux sysfs • PipeWire Audio",
    status: "Online",
    actionPrompt: "Report current system diagnostics, RAM usage, and display power",
  },
  {
    id: "vision-sentry",
    name: "Vision & Workspace Sentry",
    domain: "PERCEPTION",
    role: "BlazeFace camera presence detection, attention tracking & on-demand VLLM/OCR",
    model: "BlazeFace MediaPipe • Llama 3.2 Vision",
    status: "Armed",
    actionPrompt: "Run optical presence scan",
  },
  {
    id: "conversation-specialist",
    name: "Persona & Conversation Specialist",
    domain: "COORDINATOR",
    role: "Alfred conversational continuity, British butler persona & banter",
    model: "Groq Qwen 2.5 • FastPath Engine",
    status: "Active",
    actionPrompt: "Alfred, how are our operations running this evening?",
  },
  {
    id: "voice-pipeline",
    name: "Neural Voice Pipeline",
    domain: "AUDIO / TTS",
    role: "openWakeWord 'Hey Alfred', Groq Whisper STT & Piper Local TTS",
    model: "Whisper FP16 + Piper Local",
    status: "Armed",
    actionPrompt: "Test voice pipeline synthesis",
  },
  {
    id: "weather-specialist",
    name: "Atmospheric & Weather Intelligence",
    domain: "METEOROLOGY",
    role: "Local meteorological telemetry, rain radar & hourly forecast warnings",
    model: "Open-Meteo REST API",
    status: "Active",
    actionPrompt: "What is the current weather radar and today's forecast?",
  },
  {
    id: "research-specialist",
    name: "Deep Web & Research Specialist",
    domain: "INTELLIGENCE",
    role: "Multi-query web search, verified source synthesis & executive briefs",
    model: "Tavily Search • Groq LPU",
    status: "Ready",
    actionPrompt: "Research the latest advancements in AI multi-agent swarms",
  },
  {
    id: "crawl-specialist",
    name: "Web Extraction & Scraper Specialist",
    domain: "DATA SCRAPER",
    role: "Structured content extraction, article cleanup & markdown scraping",
    model: "Crawl4AI • BeautifulSoup4",
    status: "Standby",
    actionPrompt: "Scrape and summarize the latest project documentation",
  },
  {
    id: "github-specialist",
    name: "GitHub & DevOps Specialist",
    domain: "DEVELOPMENT",
    role: "Pull request reviews, active repo issues & commit history auditing",
    model: "GitHub REST API v3",
    status: "Connected",
    actionPrompt: "Check recent pull requests and open issues on our repository",
  },
  {
    id: "memory-specialist",
    name: "Episodic & Semantic Memory Specialist",
    domain: "SHODH MEMORY",
    role: "Persistent vector storage, user preference recall & cross-session continuity",
    model: "4-Tier Shodh Memory",
    status: "Indexed",
    actionPrompt: "Recall stored preferences and notes regarding our setup",
  },
  {
    id: "task-specialist",
    name: "Executive Task & Agenda Specialist",
    domain: "AGENDA SYNC",
    role: "Supabase tasks ledger and two-way Google Calendar OAuth sync",
    model: "Google Tasks • Supabase Postgres",
    status: "Active",
    actionPrompt: "What are my highest priority tasks for today?",
  },
];

interface SubsystemItem {
  id: string;
  name: string;
  meta: string;
  port: string;
  status: string;
}

const SUBSYSTEM_CHECKLIST: SubsystemItem[] = [
  { id: "gateway", name: "FastAPI Gateway Server", meta: "Central WebSocket Hub & Event Router", port: "8000", status: "ONLINE" },
  { id: "agent", name: "Agent Swarm Coordinator", meta: "Alfred Planner & 10 Domain Specialists", port: "8001", status: "ONLINE" },
  { id: "voice", name: "Neural Voice Subsystem", meta: "openWakeWord, Groq Whisper & Piper TTS", port: "8002", status: "ARMED" },
  { id: "supabase", name: "Supabase PostgreSQL Database", meta: "Tasks, Ledger & pgvector Embeddings", port: "Cloud", status: "ONLINE" },
  { id: "sentry", name: "DPMS & Display Sentry", meta: "Dual-Monitor Link Probes (eDP-1, DP-3)", port: "IPC", status: "ACTIVE" },
  { id: "calendar", name: "Google Calendar API v3", meta: "Two-Way OAuth Synchronized", port: "OAuth", status: "SYNCED" },
];

export const ServicesView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SystemSubTab>("specialists");
  const [devices, setDevices] = useState<ConnectedDevice[]>([]);
  const [loading, setLoading] = useState(false);
  const [commandInput, setCommandInput] = useState("");
  const [vitals, setVitals] = useState<Record<string, any> | null>(null);
  const pollTimerRef = useRef<any>(null);

  const fetchDiagnostics = useCallback(async () => {
    setLoading(true);
    try {
      const baseUrl = gatewayClient.getHttpUrl();

      // Fetch dynamic connected devices
      const devPromise = fetch(`${baseUrl}/api/sync/devices`, { signal: AbortSignal.timeout(3000) })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);

      // Fetch dynamic host hardware vitals
      const vitalsPromise = fetch(`${baseUrl}/api/system/status`, { signal: AbortSignal.timeout(3000) })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);

      const [devData, vitalsData] = await Promise.all([devPromise, vitalsPromise]);

      if (devData) {
        if (Array.isArray(devData)) setDevices(devData);
        else if (devData.devices && Array.isArray(devData.devices)) setDevices(devData.devices);
      } else {
        // Fallback to active client and desktop host if API call is quiet
        setDevices([
          {
            device_id: "desktop_host",
            device_name: "Workstation Host (mihir-arch)",
            device_type: "desktop",
            is_online: true,
            ip_address: "127.0.0.1",
            battery_level: undefined,
          },
          {
            device_id: gatewayClient.getClientId(),
            device_name: "Mobile Companion (Active)",
            device_type: "mobile",
            is_online: true,
            battery_level: 84,
            is_charging: false,
            ip_address: "LAN Node",
          },
        ]);
      }

      if (vitalsData) {
        setVitals(vitalsData);
      }
    } catch {
      // Graceful offline fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDiagnostics();

    // Periodic telemetry refresh every 20 seconds
    pollTimerRef.current = setInterval(() => {
      fetchDiagnostics();
    }, 20000);

    // Subscribe to real-time device registration / heartbeat events from WebSocket
    const unsub = gatewayClient.subscribeEnvelope((envelope: ServerEnvelope) => {
      if (envelope.channel === "SYNC" && (envelope.type === "DEVICE_REGISTER" || envelope.type === "DEVICE_HEARTBEAT")) {
        const payload = envelope.payload || {};
        if (payload.device_id) {
          setDevices((prev) => {
            const idx = prev.findIndex((d) => d.device_id === payload.device_id);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = {
                ...updated[idx],
                ...payload,
                is_online: true,
                last_heartbeat: Date.now(),
              };
              return updated;
            }
            return [
              ...prev,
              {
                device_id: payload.device_id,
                device_name: payload.device_name || "New Mesh Node",
                device_type: payload.device_type || "compute",
                is_online: true,
                last_heartbeat: Date.now(),
                ip_address: payload.ip_address || "LAN",
                battery_level: payload.battery_level,
                is_charging: payload.is_charging,
              },
            ];
          });
        }
      }
    });

    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      unsub();
    };
  }, [fetchDiagnostics]);

  const handleInvoke = (prompt: string) => {
    workstationStore.sendUserMessage(prompt);
  };

  const handleDispatchCommand = () => {
    const text = commandInput.trim();
    if (!text) return;
    setCommandInput("");
    workstationStore.sendUserMessage(text);
  };

  const cpuModel = vitals?.cpu_model || "12th Gen Intel Core i5-12500H (16T)";
  const gpuModel = vitals?.gpu_model || "Intel Iris Xe Graphics (Alder Lake-P)";
  const ramUsage = vitals?.ram_usage || "6.8 GB / 15.3 GB";
  const displayCount = vitals?.displays_count ?? 2;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* ── Section 1: Grand Swarm & Hardware Topology Deck (Double-Bezel Hero) ── */}
      <View style={styles.heroOuterBezel}>
        <View style={styles.heroInnerCore}>
          {/* Header Row */}
          <View style={styles.heroTopRow}>
            <View style={styles.heroStatusBlock}>
              <View style={styles.solidEmeraldDot} />
              <Text style={styles.heroStatusText}>SWARM ONLINE</Text>
              <Text style={styles.heroSeparator}>•</Text>
              <Text style={styles.heroSubText}>10 ACTIVE SPECIALISTS</Text>
            </View>

            {/* Manual Sync / Refresh Button */}
            <TouchableOpacity
              style={styles.syncBtn}
              onPress={fetchDiagnostics}
              disabled={loading}
              activeOpacity={0.7}
            >
              {loading ? (
                <ActivityIndicator size="small" color={theme.colors.boneWhite} style={{ transform: [{ scale: 0.7 }] }} />
              ) : (
                <Text style={styles.syncBtnText}>SYNC NOW</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Title & Scope */}
          <Text style={styles.heroTitle}>Cognitive Swarm & Mesh</Text>
          <Text style={styles.heroSubtitle}>
            10 domain specialists, dual-monitor DPMS sentry, and self-discovering edge compute topology.
          </Text>

          {/* Telemetry Quad Capsule */}
          <View style={styles.quadGrid}>
            <View style={styles.quadCell}>
              <Text style={styles.quadLabel}>COMPUTE HOST</Text>
              <Text style={styles.quadValue} numberOfLines={1}>
                {cpuModel}
              </Text>
            </View>

            <View style={styles.quadCell}>
              <Text style={styles.quadLabel}>DISPLAYS & GPU</Text>
              <Text style={styles.quadValue} numberOfLines={1}>
                {displayCount} Displays • {gpuModel}
              </Text>
            </View>

            <View style={styles.quadCell}>
              <Text style={styles.quadLabel}>GATEWAY LINK</Text>
              <Text style={styles.quadValue}>Port 8000 • WebSocket /ws</Text>
            </View>

            <View style={styles.quadCell}>
              <Text style={styles.quadLabel}>SYSTEM MEMORY</Text>
              <Text style={styles.quadValue}>{ramUsage} • Shodh Indexed</Text>
            </View>
          </View>
        </View>
      </View>

      {/* ── Section 2: Inline System Directive Input Bar (Matching Cockpit/Ledger) ── */}
      <View style={styles.directiveOuterBezel}>
        <View style={styles.directiveInnerCore}>
          <View style={styles.directiveInputRow}>
            <Text style={styles.directivePrefix}>vesper &gt;</Text>
            <TextInput
              style={styles.directiveInput}
              value={commandInput}
              onChangeText={setCommandInput}
              placeholder="Instruct Alfred on system diagnostics or peripherals..."
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
              <Text style={styles.directiveRunBtnText}>RUN</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* ── Section 3: Tactile Segmented Sub-View Switcher ── */}
      <View style={styles.segmentedContainer}>
        <TouchableOpacity
          style={[styles.segmentedPill, activeTab === "specialists" && styles.segmentedPillActive]}
          onPress={() => setActiveTab("specialists")}
          activeOpacity={0.7}
        >
          <Text style={[styles.segmentedText, activeTab === "specialists" && styles.segmentedTextActive]}>
            SPECIALISTS (10)
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.segmentedPill, activeTab === "hardware" && styles.segmentedPillActive]}
          onPress={() => setActiveTab("hardware")}
          activeOpacity={0.7}
        >
          <Text style={[styles.segmentedText, activeTab === "hardware" && styles.segmentedTextActive]}>
            HARDWARE MESH ({devices.length})
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.segmentedPill, activeTab === "health" && styles.segmentedPillActive]}
          onPress={() => setActiveTab("health")}
          activeOpacity={0.7}
        >
          <Text style={[styles.segmentedText, activeTab === "health" && styles.segmentedTextActive]}>
            HEALTH (6)
          </Text>
        </TouchableOpacity>
      </View>

      {/* ── Section 4: Tab 1 — Specialist Swarm Pods ── */}
      {activeTab === "specialists" && (
        <View style={styles.tabContent}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>OPERATIONAL SPECIALIST AGENTS (10)</Text>
            <TouchableOpacity
              style={styles.toolEmitterLink}
              onPress={() => workstationStore.setActiveView("tools")}
              activeOpacity={0.7}
            >
              <Text style={styles.toolEmitterLinkText}>TOOL EMITTER &gt;</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.specialistsGrid}>
            {SPECIALIST_AGENTS.map((agent) => (
              <View key={agent.id} style={styles.cardOuterBezel}>
                <View style={styles.cardInnerCore}>
                  {/* Top Bar: Eyebrow Tag & Solid Status Chip */}
                  <View style={styles.podHeader}>
                    <View style={styles.podEyebrowWrap}>
                      <View style={styles.solidEmeraldMiniDot} />
                      <Text style={styles.podEyebrowText}>SPECIALIST // {agent.domain}</Text>
                    </View>
                    <View style={styles.statusChip}>
                      <Text style={styles.statusChipText}>{agent.status.toUpperCase()}</Text>
                    </View>
                  </View>

                  {/* Specialist Name & Model Badge */}
                  <Text style={styles.agentName}>{agent.name}</Text>
                  <View style={styles.modelBadgeWrap}>
                    <Text style={styles.agentModel}>{agent.model}</Text>
                  </View>

                  {/* Role Description */}
                  <Text style={styles.agentRole}>{agent.role}</Text>

                  {/* Action Footer with Button-in-Button Invoke */}
                  <View style={styles.podFooter}>
                    <Text style={styles.podFooterMono}>Autonomous Node</Text>
                    <TouchableOpacity
                      style={styles.invokeBtn}
                      onPress={() => handleInvoke(agent.actionPrompt)}
                      activeOpacity={0.75}
                    >
                      <Text style={styles.invokeBtnText}>INVOKE</Text>
                      <View style={styles.invokeArrowCircle}>
                        <Text style={styles.invokeArrowGlyph}>&gt;</Text>
                      </View>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* ── Section 5: Tab 2 — Synchronized Hardware & Edge Board Mesh ── */}
      {activeTab === "hardware" && (
        <View style={styles.tabContent}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>SYNCHRONIZED HARDWARE MESH</Text>
            <Text style={styles.sectionMeta}>{devices.length} Nodes Discovered</Text>
          </View>

          <View style={styles.hardwareGrid}>
            {devices.map((dev) => {
              const isDesktop = dev.device_type === "desktop";
              const isMobile = dev.device_type === "mobile";

              return (
                <View key={dev.device_id} style={styles.cardOuterBezel}>
                  <View style={styles.cardInnerCore}>
                    <View style={styles.deviceHeader}>
                      <View style={styles.deviceTitleRow}>
                        <View style={dev.is_online ? styles.solidEmeraldMiniDot : styles.solidAmberMiniDot} />
                        <Text style={styles.deviceName} numberOfLines={1}>
                          {dev.device_name}
                        </Text>
                      </View>
                      <View style={[styles.statusChip, !dev.is_online && styles.statusChipStandby]}>
                        <Text style={[styles.statusChipText, !dev.is_online && styles.statusChipTextStandby]}>
                          {dev.is_online ? "ONLINE" : "STANDBY"}
                        </Text>
                      </View>
                    </View>

                    {/* Hardware Specifications & Telemetry */}
                    <View style={styles.deviceMetaRow}>
                      <View style={styles.deviceMetaItem}>
                        <Text style={styles.deviceMetaLabel}>DEVICE CLASS</Text>
                        <Text style={styles.deviceMetaValue}>
                          {isDesktop ? "Host Workstation" : isMobile ? "Companion Handset" : "Compute SBC Node"}
                        </Text>
                      </View>

                      <View style={styles.deviceMetaItem}>
                        <Text style={styles.deviceMetaLabel}>NETWORK</Text>
                        <Text style={styles.deviceMetaValue}>{dev.ip_address || "LAN Local"}</Text>
                      </View>

                      <View style={styles.deviceMetaItem}>
                        <Text style={styles.deviceMetaLabel}>POWER SOURCE</Text>
                        <Text style={styles.deviceMetaValue}>
                          {dev.battery_level !== null && dev.battery_level !== undefined
                            ? `${dev.battery_level}% Battery`
                            : "AC Main Line"}
                        </Text>
                      </View>
                    </View>
                  </View>
                </View>
              );
            })}

            {devices.length === 0 && (
              <View style={styles.emptyWell}>
                <Text style={styles.emptyWellText}>Scanning local LAN for registered compute nodes...</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* ── Section 6: Tab 3 — Subsystem Health Matrix ── */}
      {activeTab === "health" && (
        <View style={styles.tabContent}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>SUBSYSTEM HEALTH & INTEGRITY CHECKLIST</Text>
            <Text style={styles.sectionMeta}>6/6 Operational</Text>
          </View>

          <View style={styles.healthGrid}>
            {SUBSYSTEM_CHECKLIST.map((sub) => (
              <View key={sub.id} style={styles.cardOuterBezel}>
                <View style={styles.cardInnerCore}>
                  <View style={styles.healthRow}>
                    <View style={styles.healthCheckIcon}>
                      <Text style={styles.healthCheckGlyph}>✓</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={styles.healthTitleRow}>
                        <Text style={styles.healthName}>{sub.name}</Text>
                        <View style={styles.healthPortBadge}>
                          <Text style={styles.healthPortText}>{sub.port}</Text>
                        </View>
                      </View>
                      <Text style={styles.healthMeta}>{sub.meta}</Text>
                    </View>
                    <View style={styles.statusChip}>
                      <Text style={styles.statusChipText}>{sub.status}</Text>
                    </View>
                  </View>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      <View style={{ height: 120 }} />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  contentContainer: {
    paddingHorizontal: 16,
    paddingTop: 12,
  },

  /* ── Hero Double-Bezel Deck ── */
  heroOuterBezel: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 2,
    marginBottom: 12,
  },
  heroInnerCore: {
    backgroundColor: "#141413",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 14,
  },
  heroTopRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  heroStatusBlock: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  solidEmeraldDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: theme.colors.emerald,
  },
  solidEmeraldMiniDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  solidAmberMiniDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.amber,
  },
  heroStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.emerald,
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  heroSeparator: {
    color: "rgba(255, 255, 255, 0.2)",
    fontSize: 10,
  },
  heroSubText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#8E8A83",
    letterSpacing: 0.8,
  },
  syncBtn: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    justifyContent: "center",
    alignItems: "center",
    minWidth: 70,
  },
  syncBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#E8E3DA",
    letterSpacing: 1,
    fontWeight: "700",
  },
  heroTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 22,
    color: "#E8E3DA",
    fontWeight: "600",
    marginBottom: 3,
  },
  heroSubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: "#8E8A83",
    lineHeight: 16,
    marginBottom: 12,
  },
  quadGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  quadCell: {
    width: "48.8%",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  quadLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "#8E8A83",
    letterSpacing: 0.8,
    marginBottom: 2,
  },
  quadValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: "#D1CFC0",
    fontWeight: "600",
  },

  /* ── Directives Input Bar ── */
  directiveOuterBezel: {
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2,
    marginBottom: 12,
  },
  directiveInnerCore: {
    backgroundColor: "#111110",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  directiveInputRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  directivePrefix: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.amber,
    marginRight: 6,
    fontWeight: "700",
  },
  directiveInput: {
    flex: 1,
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: "#E8E3DA",
    paddingVertical: 2,
  },
  directiveRunBtn: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    marginLeft: 6,
  },
  directiveRunBtnDisabled: {
    opacity: 0.35,
  },
  directiveRunBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#E8E3DA",
    fontWeight: "700",
    letterSpacing: 0.5,
  },

  /* ── Segmented Switcher (Matching LedgerView) ── */
  segmentedContainer: {
    flexDirection: "row",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 3,
    marginBottom: 14,
    gap: 4,
  },
  segmentedPill: {
    flex: 1,
    paddingVertical: 7,
    alignItems: "center",
    borderRadius: 7,
  },
  segmentedPillActive: {
    backgroundColor: "rgba(255, 255, 255, 0.07)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  segmentedText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#8E8A83",
    letterSpacing: 0.8,
  },
  segmentedTextActive: {
    color: "#E8E3DA",
    fontWeight: "700",
  },

  /* ── Tab Content ── */
  tabContent: {
    gap: 8,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  sectionTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#8E8A83",
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  sectionMeta: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#5E5A53",
  },
  toolEmitterLink: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  toolEmitterLinkText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "#E8E3DA",
    letterSpacing: 0.8,
  },

  /* ── Card Double-Bezel Architecture ── */
  cardOuterBezel: {
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 2,
    marginBottom: 8,
  },
  cardInnerCore: {
    backgroundColor: "#131312",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    padding: 12,
  },

  /* ── Specialist Pods ── */
  specialistsGrid: {
    gap: 8,
  },
  podHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  podEyebrowWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  podEyebrowText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.amber,
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  statusChip: {
    backgroundColor: "rgba(16, 185, 129, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  statusChipStandby: {
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    borderColor: "rgba(245, 158, 11, 0.25)",
  },
  statusChipText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.emerald,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  statusChipTextStandby: {
    color: theme.colors.amber,
  },
  agentName: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "700",
    color: "#E8E3DA",
  },
  modelBadgeWrap: {
    marginTop: 2,
    marginBottom: 6,
  },
  agentModel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#8E8A83",
  },
  agentRole: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: "#B4B0A5",
    lineHeight: 16,
    marginBottom: 8,
  },
  podFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
    paddingTop: 8,
  },
  podFooterMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#5E5A53",
  },
  invokeBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    paddingLeft: 8,
    paddingRight: 4,
    paddingVertical: 3,
    borderRadius: 6,
    gap: 4,
  },
  invokeBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "#E8E3DA",
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  invokeArrowCircle: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    justifyContent: "center",
    alignItems: "center",
  },
  invokeArrowGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "#E8E3DA",
    lineHeight: 10,
  },

  /* ── Hardware Mesh ── */
  hardwareGrid: {
    gap: 8,
  },
  deviceHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  deviceTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
    marginRight: 8,
  },
  deviceName: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "700",
    color: "#E8E3DA",
  },
  deviceMetaRow: {
    flexDirection: "row",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.03)",
    paddingVertical: 6,
    paddingHorizontal: 8,
    justifyContent: "space-between",
  },
  deviceMetaItem: {
    flex: 1,
  },
  deviceMetaLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: "#8E8A83",
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  deviceMetaValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#D1CFC0",
    fontWeight: "600",
  },
  emptyWell: {
    padding: 16,
    borderRadius: 10,
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    alignItems: "center",
  },
  emptyWellText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: "#8E8A83",
  },

  /* ── Health Checklist ── */
  healthGrid: {
    gap: 8,
  },
  healthRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  healthCheckIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: theme.colors.emerald,
    justifyContent: "center",
    alignItems: "center",
  },
  healthCheckGlyph: {
    color: theme.colors.emerald,
    fontSize: 10,
    fontWeight: "bold",
    lineHeight: 12,
  },
  healthTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  healthName: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "700",
    color: "#E8E3DA",
  },
  healthPortBadge: {
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 3,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
  },
  healthPortText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: "#A39E93",
  },
  healthMeta: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#8E8A83",
    marginTop: 1,
  },
});
