import React from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  Platform,
} from "react-native";
import { theme } from "../styles/theme";
import { WorkstationView } from "../services/workstation-store";
import { AgentState } from "../types/vesper";

interface MobileDockProps {
  activeView: WorkstationView;
  agentState: AgentState;
  zenMode: boolean;
  isWakeWordArmed: boolean;
  isCameraActive: boolean;
  onSelectView: (view: WorkstationView) => void;
  onToggleVoice: () => void;
  onToggleZenMode: (target?: boolean) => void;
  onToggleWakeWord: () => void;
  onToggleCamera: () => void;
}

interface MainTab {
  id: "cockpit" | "directives" | "agenda" | "ledger" | "system";
  view: WorkstationView;
  label: string;
  glyph: string;
}

const TABS: MainTab[] = [
  { id: "cockpit", view: "workstation", label: "Cockpit", glyph: "◈" },
  { id: "directives", view: "directives", label: "Directives", glyph: "◬" },
  { id: "agenda", view: "agenda", label: "Agenda", glyph: "▤" },
  { id: "ledger", view: "ledger", label: "Ledger", glyph: "₹" },
  { id: "system", view: "services", label: "System", glyph: "⌘" },
];

export const MobileDock: React.FC<MobileDockProps> = ({
  activeView,
  agentState,
  zenMode,
  onSelectView,
  onToggleZenMode,
}) => {
  // If Zen mode is engaged and view is zen, provide a minimal unobtrusive dock
  if (zenMode && activeView === "zen") {
    return (
      <View style={styles.zenMinimalDock}>
        <TouchableOpacity style={styles.zenExitBtn} onPress={() => onToggleZenMode(false)}>
          <Text style={styles.zenExitGlyph}>✕</Text>
          <Text style={styles.zenExitText}>EXIT ZEN FOCUS</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const isSystemActive =
    activeView === "services" ||
    activeView === "tools" ||
    activeView === "logs" ||
    activeView === "zen";

  return (
    <View style={styles.dockRoot}>
      <View style={styles.dockInner}>
        {TABS.map((tab) => {
          const isActive =
            tab.id === "system"
              ? isSystemActive
              : activeView === tab.view;

          const isDirectives = tab.id === "directives";
          const isAgentBusy = isDirectives && (agentState === "LISTENING" || agentState === "THINKING");

          return (
            <TouchableOpacity
              key={tab.id}
              style={[styles.tabItem, isActive && styles.tabItemActive]}
              onPress={() => onSelectView(tab.view)}
              activeOpacity={0.7}
            >
              <View style={styles.glyphWrapper}>
                <Text
                  style={[
                    styles.glyph,
                    isActive && styles.glyphActive,
                    isAgentBusy && {
                      color: agentState === "LISTENING" ? theme.colors.emerald : theme.colors.amber,
                    },
                  ]}
                >
                  {tab.glyph}
                </Text>
                {isAgentBusy && (
                  <View
                    style={[
                      styles.agentDot,
                      {
                        backgroundColor:
                          agentState === "LISTENING"
                            ? theme.colors.emerald
                            : theme.colors.amber,
                      },
                    ]}
                  />
                )}
              </View>
              <Text style={[styles.tabLabel, isActive && styles.tabLabelActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  dockRoot: {
    backgroundColor: "rgba(16, 16, 16, 0.96)",
    borderTopWidth: 1,
    borderTopColor: theme.colors.borderSubtle,
    paddingBottom: Platform.OS === "ios" ? 22 : 10,
    paddingTop: 8,
  },
  dockInner: {
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "center",
    paddingHorizontal: 8,
  },
  tabItem: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 4,
    borderRadius: 8,
  },
  tabItemActive: {
    backgroundColor: "rgba(255, 255, 255, 0.04)",
  },
  glyphWrapper: {
    position: "relative",
    width: 28,
    height: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  glyph: {
    fontSize: 16,
    color: theme.colors.textMuted,
  },
  glyphActive: {
    color: theme.colors.boneWhite,
  },
  tabLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 0.5,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  tabLabelActive: {
    color: theme.colors.boneWhite,
    fontWeight: "600",
  },
  agentDot: {
    position: "absolute",
    top: 0,
    right: 2,
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  zenMinimalDock: {
    position: "absolute",
    bottom: 24,
    alignSelf: "center",
    backgroundColor: "rgba(26, 26, 26, 0.9)",
    borderRadius: 24,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  zenExitBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  zenExitGlyph: {
    color: theme.colors.textMuted,
    fontSize: 12,
  },
  zenExitText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1.5,
    color: theme.colors.boneWhite,
  },
});
