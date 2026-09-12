import React, { useEffect, useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  StatusBar,
  TouchableOpacity,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { theme } from "../styles/theme";
import { gatewayClient, ConnectionStatus } from "../services/gateway";
import { workstationStore, WorkstationView } from "../services/workstation-store";
import { AgentState } from "../types/vesper";

// ── Views ──
import { CockpitView } from "../components/CockpitView";
import { DirectivesView } from "../components/DirectivesView";
import { AgendaView } from "../components/AgendaView";
import { LedgerView } from "../components/LedgerView";
import { ServicesView } from "../components/ServicesView";
import { ToolEmitterView } from "../components/ToolEmitterView";
import { LogsView } from "../components/LogsView";
import { ZenView } from "../components/ZenView";

// ── Modals & Dock ──
import { MobileDock } from "../components/MobileDock";
import { ClusterSettingsModal } from "../components/ClusterSettingsModal";
import { HudDrawerModal } from "../components/HudDrawerModal";
import { AdvisoryDrawerModal } from "../components/AdvisoryDrawerModal";
import {
  ProactiveAdvisoryModal,
  ProactiveAdvisory,
} from "../components/ProactiveAdvisoryModal";
import { CascadeView } from "../components/CascadeView";
import { ProactiveAlert } from "../types/vesper";
import { VesperLogo } from "../components/VesperLogo";
import { offlineStore } from "../services/offline-store";

export default function HomeScreen() {
  const [activeView, setActiveView] = useState<WorkstationView>(workstationStore.activeView);
  const [agentState, setAgentState] = useState<AgentState>(workstationStore.agentState);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [zenMode, setZenMode] = useState<boolean>(workstationStore.zenMode);
  const [isWakeWordArmed, setIsWakeWordArmed] = useState<boolean>(workstationStore.isWakeWordArmed);
  const [isCameraActive, setIsCameraActive] = useState<boolean>(workstationStore.isCameraActive);
  const [pendingSyncCount, setPendingSyncCount] = useState<number>(0);

  // Overlays
  const [isClusterModalOpen, setIsClusterModalOpen] = useState(false);
  const [isHudOpen, setIsHudOpen] = useState(false);
  const [hudCards, setHudCards] = useState<any[]>([]);
  const [isAdvisoryDrawerOpen, setIsAdvisoryDrawerOpen] = useState(false);
  const [advisories, setAdvisories] = useState<ProactiveAlert[]>([]);
  const [activeAdvisory, setActiveAdvisory] = useState<ProactiveAdvisory | null>(null);

  useEffect(() => {
    const unsubStore = workstationStore.subscribe(() => {
      setActiveView(workstationStore.activeView);
      setAgentState(workstationStore.agentState);
      setZenMode(workstationStore.zenMode);
      setIsWakeWordArmed(workstationStore.isWakeWordArmed);
      setIsCameraActive(workstationStore.isCameraActive);
      setIsHudOpen(workstationStore.isHudDrawerOpen);
      setHudCards(workstationStore.hudCards);
      setIsClusterModalOpen(workstationStore.isClusterModalOpen);
      setIsAdvisoryDrawerOpen(workstationStore.isAdvisoryDrawerOpen);
      setAdvisories(workstationStore.proactiveAdvisories);

      if (workstationStore.proactiveAdvisories.length > 0) {
        const top = workstationStore.proactiveAdvisories[0];
        setActiveAdvisory({
          id: top.id,
          title: top.title,
          message: top.body,
          severity: top.urgency === "critical" ? "CRITICAL" : "HIGH",
          timestamp: top.timestamp,
        });
      } else {
        setActiveAdvisory(null);
      }
    });

    const unsubStatus = gatewayClient.subscribeStatus((newStatus) => {
      setStatus(newStatus);
    });

    const unsubSync = offlineStore.subscribeSync((_syncing, count) => {
      setPendingSyncCount(count);
    });

    gatewayClient.connect();

    return () => {
      unsubStore();
      unsubStatus();
      unsubSync();
    };
  }, []);

  const handleSelectView = (view: WorkstationView) => {
    workstationStore.setActiveView(view);
  };

  const handleToggleVoice = () => {
    if (agentState === "LISTENING") {
      workstationStore.sendInterrupt();
    } else {
      workstationStore.simulateWakeWord();
    }
  };

  const handleToggleZenMode = (target?: boolean | any) => {
    workstationStore.toggleZenMode(typeof target === "boolean" ? target : undefined);
  };

  const handleToggleWakeWord = (target?: boolean | any) => {
    workstationStore.toggleWakeWord(typeof target === "boolean" ? target : undefined);
  };

  const handleToggleCamera = () => {
    workstationStore.toggleCamera();
  };

  const isSystemActive =
    activeView === "services" ||
    activeView === "tools" ||
    activeView === "logs" ||
    activeView === "zen";

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor={theme.colors.background} />

      {/* ── Top Header ── */}
      {!zenMode && (
        <View style={styles.headerBar}>
          <View style={styles.headerBrandCol}>
            <VesperLogo size={22} showWordmark={true} />
          </View>

          <View style={styles.headerRightRow}>
            {/* ── 1. Cluster Advisory (ADV) Button (Kept Separate) ── */}
            <TouchableOpacity
              style={[
                styles.headerPill,
                advisories.length > 0 && styles.headerPillAdvActive,
              ]}
              onPress={() => workstationStore.openAdvisoryDrawer()}
              activeOpacity={0.7}
            >
              <View
                style={[
                  styles.statusDot,
                  {
                    backgroundColor:
                      advisories.length > 0
                        ? advisories.some((a) => (a.urgency || "").toLowerCase() === "critical" || (a.urgency || "").toLowerCase() === "urgent")
                          ? theme.colors.crimson
                          : theme.colors.amber
                        : theme.colors.textGhost,
                  },
                ]}
              />
              <Text style={styles.headerPillText}>ADV</Text>
              {advisories.length > 0 && (
                <View
                  style={[
                    styles.advCountBadge,
                    advisories.some((a) => (a.urgency || "").toLowerCase() === "critical" || (a.urgency || "").toLowerCase() === "urgent")
                      ? styles.advCountBadgeCritical
                      : styles.advCountBadgeNormal,
                  ]}
                >
                  <Text style={styles.advCountText}>{advisories.length}</Text>
                </View>
              )}
            </TouchableOpacity>

            {/* ── 2. Unified System Status & Control Hamburger Capsule (Combines Cluster, Voice, and Sync) ── */}
            <TouchableOpacity
              style={[
                styles.unifiedSysPill,
                (agentState === "LISTENING" || agentState === "THINKING") && styles.unifiedSysPillVoiceActive,
                pendingSyncCount > 0 && styles.unifiedSysPillSyncPending,
              ]}
              onPress={() => setIsClusterModalOpen(true)}
              activeOpacity={0.75}
            >
              <View
                style={[
                  styles.statusDot,
                  {
                    backgroundColor:
                      agentState === "LISTENING"
                        ? theme.colors.emerald
                        : agentState === "THINKING"
                        ? theme.colors.amber
                        : status === "connected"
                        ? (pendingSyncCount > 0 ? theme.colors.amber : theme.colors.emerald)
                        : status === "connecting" || status === "reconnecting"
                        ? theme.colors.amber
                        : theme.colors.crimson,
                  },
                ]}
              />
              <Text style={styles.unifiedSysText}>
                {agentState === "LISTENING"
                  ? "LISTENING"
                  : agentState === "THINKING"
                  ? "THINKING"
                  : pendingSyncCount > 0
                  ? `SYNC (${pendingSyncCount})`
                  : status === "connected"
                  ? "ONLINE"
                  : status.toUpperCase()}
              </Text>
              {/* Sleek Aerospace Hamburger 3-line Glyph */}
              <View style={styles.hamburgerGlyph}>
                <View style={styles.hamburgerBar} />
                <View style={styles.hamburgerBar} />
                <View style={styles.hamburgerBar} />
              </View>
            </TouchableOpacity>

            {/* ── 3. Emergency Query Interrupt Stop Button ── */}
            {agentState !== "IDLE" && (
              <TouchableOpacity
                style={styles.interruptHeaderBtn}
                onPress={() => workstationStore.sendInterrupt()}
                activeOpacity={0.75}
              >
                <View style={styles.interruptSquareGlyph} />
                <Text style={styles.interruptHeaderBtnText}>STOP</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      )}

      {/* ── System Sub-Nav (Only visible when viewing System views) ── */}
      {isSystemActive && !zenMode && (
        <View style={styles.systemSubNavContainer}>
          {/* Quick Hardware / Sentry Actions */}
          <View style={styles.quickActionRow}>
            <TouchableOpacity
              style={[styles.quickActionBtn, zenMode && styles.quickActionBtnActive]}
              onPress={() => handleToggleZenMode()}
            >
              <Text style={[styles.quickActionText, zenMode && styles.quickActionTextActive]}>
                {zenMode ? "ZEN: ON" : "ZEN: OFF"}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.quickActionBtn, isWakeWordArmed && styles.quickActionBtnActive]}
              onPress={() => handleToggleWakeWord()}
            >
              <Text style={[styles.quickActionText, isWakeWordArmed && styles.quickActionTextActive]}>
                {isWakeWordArmed ? "WAKE: ON" : "WAKE: OFF"}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.quickActionBtn, isCameraActive && styles.quickActionBtnActive]}
              onPress={handleToggleCamera}
            >
              <Text style={[styles.quickActionText, isCameraActive && styles.quickActionTextActive]}>
                {isCameraActive ? "VISION: ON" : "VISION: OFF"}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Sub-view Segmented Tabs */}
          <View style={styles.subViewTabsRow}>
            {(["services", "tools", "logs", "zen"] as const).map((v) => (
              <TouchableOpacity
                key={v}
                style={[styles.subViewTab, activeView === v && styles.subViewTabActive]}
                onPress={() => handleSelectView(v)}
              >
                <Text style={[styles.subViewTabText, activeView === v && styles.subViewTabTextActive]}>
                  {v.toUpperCase()}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {/* ── Center Stage Viewport ── */}
      <View style={styles.viewViewport}>
        <CascadeView key={activeView} style={styles.cascadeContainer}>
          {activeView === "workstation" && <CockpitView />}
          {activeView === "directives" && <DirectivesView />}
          {activeView === "agenda" && <AgendaView />}
          {activeView === "ledger" && <LedgerView />}
          {activeView === "services" && <ServicesView />}
          {activeView === "tools" && <ToolEmitterView />}
          {activeView === "logs" && <LogsView />}
          {activeView === "zen" && <ZenView />}
        </CascadeView>
      </View>

      {/* ── Floating Single-Tier Mobile Dock ── */}
      <MobileDock
        activeView={activeView}
        agentState={agentState}
        zenMode={zenMode}
        isWakeWordArmed={isWakeWordArmed}
        isCameraActive={isCameraActive}
        onSelectView={handleSelectView}
        onToggleVoice={handleToggleVoice}
        onToggleZenMode={handleToggleZenMode}
        onToggleWakeWord={handleToggleWakeWord}
        onToggleCamera={handleToggleCamera}
      />

      {/* ── Modals ── */}
      <ClusterSettingsModal
        visible={isClusterModalOpen}
        onClose={() => {
          setIsClusterModalOpen(false);
          workstationStore.closeClusterModal();
        }}
        pendingSyncCount={pendingSyncCount}
        onSyncNow={() => offlineStore.syncPendingBacklog()}
        agentState={agentState}
        onToggleVoice={handleToggleVoice}
      />

      <HudDrawerModal
        visible={isHudOpen}
        cards={hudCards}
        onClose={() => {
          setIsHudOpen(false);
          workstationStore.closeHudDrawer();
        }}
        onDismissCard={(id) => workstationStore.dismissHudCard(id)}
        onDismissAll={() => workstationStore.dismissAllHudCards()}
      />

      <AdvisoryDrawerModal
        visible={isAdvisoryDrawerOpen}
        advisories={advisories}
        onClose={() => workstationStore.closeAdvisoryDrawer()}
        onDismiss={(id) => workstationStore.dismissProactiveAlert(id)}
        onConfirm={(id) => workstationStore.confirmProactiveAlert(id)}
        onDismissAll={() => workstationStore.clearAllProactiveAlerts()}
      />

      <ProactiveAdvisoryModal
        advisory={activeAdvisory}
        onAcknowledge={() => setActiveAdvisory(null)}
        onDismiss={() => setActiveAdvisory(null)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  headerBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.borderSubtle,
    backgroundColor: "rgba(16, 16, 16, 0.98)",
  },
  headerBrandCol: {
    flexDirection: "row",
    alignItems: "center",
  },
  brandTitle: {
    fontFamily: theme.fonts.serif,
    fontSize: 22,
    fontStyle: "italic",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },
  headerRightRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  headerPill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  headerPillActive: {
    borderColor: theme.colors.borderActive,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
  },
  headerPillAdvActive: {
    borderColor: "rgba(245, 158, 11, 0.4)",
    backgroundColor: "rgba(245, 158, 11, 0.08)",
  },
  unifiedSysPill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 7,
    gap: 6,
  },
  unifiedSysPillVoiceActive: {
    borderColor: "rgba(16, 185, 129, 0.4)",
    backgroundColor: "rgba(16, 185, 129, 0.08)",
  },
  unifiedSysPillSyncPending: {
    borderColor: "rgba(245, 158, 11, 0.35)",
    backgroundColor: "rgba(245, 158, 11, 0.06)",
  },
  unifiedSysText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
    fontWeight: "600",
  },
  hamburgerGlyph: {
    width: 11,
    height: 8,
    justifyContent: "space-between",
    alignItems: "center",
    marginLeft: 3,
  },
  hamburgerBar: {
    width: 11,
    height: 1.5,
    backgroundColor: theme.colors.textMuted,
    borderRadius: 1,
  },
  interruptHeaderBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    height: 28,
    paddingHorizontal: 8,
    borderRadius: 6,
    backgroundColor: "rgba(244, 63, 94, 0.15)",
    borderWidth: 1,
    borderColor: "rgba(244, 63, 94, 0.45)",
  },
  interruptSquareGlyph: {
    width: 7,
    height: 7,
    backgroundColor: theme.colors.rose,
    borderRadius: 1.5,
  },
  interruptHeaderBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.rose,
    letterSpacing: 0.8,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 5,
  },
  headerPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
    fontWeight: "600",
  },
  advCountBadge: {
    marginLeft: 5,
    borderRadius: 6,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  advCountBadgeNormal: {
    backgroundColor: theme.colors.amber,
  },
  advCountBadgeCritical: {
    backgroundColor: theme.colors.crimson,
  },
  advCountText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: "#111111",
    fontWeight: "bold",
  },
  hudCountBadge: {
    marginLeft: 4,
    backgroundColor: theme.colors.amber,
    borderRadius: 6,
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  hudCountText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: theme.colors.background,
    fontWeight: "bold",
  },
  systemSubNavContainer: {
    backgroundColor: "rgba(20, 20, 20, 0.98)",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.borderSubtle,
    paddingHorizontal: 14,
    paddingVertical: 8,
    gap: 6,
  },
  quickActionRow: {
    flexDirection: "row",
    gap: 6,
  },
  quickActionBtn: {
    flex: 1,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingVertical: 4,
    alignItems: "center",
    borderRadius: 4,
  },
  quickActionBtnActive: {
    borderColor: theme.colors.emerald,
    backgroundColor: "rgba(16, 185, 129, 0.08)",
  },
  quickActionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  quickActionTextActive: {
    color: theme.colors.emerald,
    fontWeight: "700",
  },
  subViewTabsRow: {
    flexDirection: "row",
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderRadius: 6,
    padding: 2,
  },
  subViewTab: {
    flex: 1,
    paddingVertical: 6,
    alignItems: "center",
    borderRadius: 4,
  },
  subViewTabActive: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
  },
  subViewTabText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  subViewTabTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  viewViewport: {
    flex: 1,
  },
  cascadeContainer: {
    flex: 1,
  },
});
