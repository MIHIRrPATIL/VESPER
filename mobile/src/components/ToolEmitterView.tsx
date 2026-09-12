import React, { useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";
import { HudCardType } from "../types/vesper";

type ToolCategory = "all" | "productivity" | "finance" | "intel" | "media" | "system";

interface ToolDefinition {
  id: string;
  name: string;
  specialist: string;
  category: ToolCategory;
  description: string;
  hudType: HudCardType;
  cardTitle: string;
  mockArgs: Record<string, any>;
  mockData: Record<string, any>;
}

const TOOLS_REGISTRY: ToolDefinition[] = [
  {
    id: "weather.get_radar",
    name: "weather.get_radar",
    specialist: "Atmospheric Intelligence Specialist",
    category: "intel",
    description: "Queries high-resolution rain radar, hourly temperature & weather alerts",
    hudType: "weather",
    cardTitle: "ATMOSPHERIC INTELLIGENCE",
    mockArgs: { location: "Mumbai, IN", include_radar: true },
    mockData: {
      location: "Mumbai, IN",
      temperature: "28°C",
      summary: "Humid & Partly Cloudy",
      humidity: "78%",
      wind: "14 km/h SW",
      forecast: [
        { day: "Today", temp: "30°C", condition: "Partly Cloudy" },
        { day: "Tomorrow", temp: "29°C", condition: "Light Showers" },
        { day: "Sunday", temp: "28°C", condition: "Overcast" },
      ],
    },
  },
  {
    id: "finance.get_ledger_snapshot",
    name: "finance.get_ledger_snapshot",
    specialist: "Double-Entry Finance Specialist",
    category: "finance",
    description: "Calculates net liquid capital, bank accounts and active peer debts in INR",
    hudType: "transaction",
    cardTitle: "FINANCIAL LEDGER & CAPITAL",
    mockArgs: { currency: "INR", include_peer_debts: true },
    mockData: {
      net_worth: 245000,
      monthly_burn: 42500,
      accounts: [
        { name: "Saraswat Bank", balance: 145000 },
        { name: "SBI Operating", balance: 65000 },
        { name: "HDFC Reserve", balance: 25000 },
        { name: "Petty Cash", balance: 10000 },
      ],
      debts_owed_to_user: 12400,
      debts_user_owes: 3200,
    },
  },
  {
    id: "task.list_priorities",
    name: "task.list_priorities",
    specialist: "Task & Google Calendar Manager",
    category: "productivity",
    description: "Retrieves active deliverables, overdue flags and calendar schedule",
    hudType: "task",
    cardTitle: "ACTIVE TASKS & EXECUTIVE AGENDA",
    mockArgs: { status: "pending", sort: "deadline" },
    mockData: {
      tasks: [
        { id: "t1", title: "Verify Jetson Orin zero-copy DMA", priority: "urgent", done: false },
        { id: "t2", title: "Review Supabase ledger balance triggers", priority: "high", done: true },
        { id: "t3", title: "Audit Google Calendar cron sync logs", priority: "normal", done: false },
      ],
    },
  },
  {
    id: "research.deep_search",
    name: "research.deep_search",
    specialist: "Deep Web & Research Specialist",
    category: "intel",
    description: "Performs real-time Tavily search and returns verified citations",
    hudType: "research",
    cardTitle: "DEEP RESEARCH & WEB CITATIONS",
    mockArgs: { query: "Latest breakthroughs in autonomous AI agent swarms" },
    mockData: {
      query: "Autonomous AI agent swarms",
      sources: [
        { title: "Distributed Swarm Orchestration", url: "https://arxiv.org/abs/2405.xxxxx" },
        { title: "Zero-Latency Sub-agent Scheduling", url: "https://research.vesper.ai/swarms" },
      ],
      synthesis: "Hierarchical agent routing reduces token consumption by 84% while maintaining sub-second barge-in reaction times.",
    },
  },
  {
    id: "spotify.mpris_controls",
    name: "spotify.mpris_controls",
    specialist: "Media & Spotify Specialist",
    category: "media",
    description: "Inspects live MPRIS track metadata and volume level",
    hudType: "spotify",
    cardTitle: "SPOTIFY & VINYL ENGINE",
    mockArgs: { device: "mihir-arch" },
    mockData: {
      track: "Starboy",
      artist: "The Weeknd, Daft Punk",
      album: "Starboy (Deluxe Edition)",
      album_art: "https://i.scdn.co/image/ab67616d0000b2734718e2b124f79258be7bc452",
      spotify_uri: "spotify:track:7MXVkk9YM5IZxh0wAEAGdo",
      url: "https://open.spotify.com/track/7MXVkk9YM5IZxh0wAEAGdo",
      is_playing: true,
      duration_ms: 230000,
      position_ms: 68000,
    },
  },
  {
    id: "youtube.search_video",
    name: "youtube.search_video",
    specialist: "Media & YouTube Specialist",
    category: "media",
    description: "Searches YouTube videos with direct app deep-linking and 16:9 thumbnail previews",
    hudType: "youtube",
    cardTitle: "YOUTUBE MEDIA RUNTIME",
    mockArgs: { query: "Hans Zimmer Live in Prague Time" },
    mockData: {
      title: "Hans Zimmer - Time (Live in Prague 4K)",
      channel: "Hans Zimmer Official",
      duration: "4:36",
      video_id: "RxabV9zPC8U",
      thumbnail: "https://img.youtube.com/vi/RxabV9zPC8U/hqdefault.jpg",
      views: "128M views",
      snippet: "Official live performance of Time from the movie Inception, performed by Hans Zimmer and the Czech National Symphony Orchestra.",
      url: "https://www.youtube.com/watch?v=RxabV9zPC8U",
    },
  },
];

export const ToolEmitterView: React.FC = () => {
  const [selectedCat, setSelectedCat] = useState<ToolCategory>("all");

  const filteredTools = TOOLS_REGISTRY.filter((t) =>
    selectedCat === "all" ? true : t.category === selectedCat
  );

  const handleEmitToHud = (tool: ToolDefinition) => {
    const card = {
      id: `emit_${Date.now()}_${tool.id}`,
      type: tool.hudType,
      title: tool.cardTitle,
      timestamp: Date.now(),
      data: tool.mockData,
    };
    workstationStore.openHudDrawer([card], tool.cardTitle, tool.description);
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerMono}>SPECIALIST TOOL EMITTER & INSPECTOR</Text>
        <Text style={styles.headerTitle}>Tool Emitter Deck</Text>
        <Text style={styles.headerSubtitle}>
          Test and preview structured execution cards and inject them directly into the HUD Intelligence Deck.
        </Text>
      </View>

      {/* Category Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.catScroll}>
        {(["all", "productivity", "finance", "intel", "media", "system"] as ToolCategory[]).map((cat) => (
          <TouchableOpacity
            key={cat}
            style={[styles.catPill, selectedCat === cat && styles.catPillActive]}
            onPress={() => setSelectedCat(cat)}
          >
            <Text style={[styles.catPillText, selectedCat === cat && styles.catPillTextActive]}>
              {cat.toUpperCase()}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Tool List */}
      <ScrollView style={styles.toolList} showsVerticalScrollIndicator={false}>
        {filteredTools.map((tool) => (
          <View key={tool.id} style={styles.toolCard}>
            <View style={styles.toolCardHeader}>
              <View style={{ flex: 1 }}>
                <Text style={styles.toolName}>{tool.name}</Text>
                <Text style={styles.toolSpecialist}>{tool.specialist}</Text>
              </View>
              <View style={styles.categoryBadge}>
                <Text style={styles.categoryBadgeText}>{tool.category.toUpperCase()}</Text>
              </View>
            </View>

            <Text style={styles.toolDesc}>{tool.description}</Text>

            {/* Parameter Preview */}
            <View style={styles.paramBox}>
              <Text style={styles.paramLabel}>INVOCATION PARAMETERS:</Text>
              <Text style={styles.paramCode}>{JSON.stringify(tool.mockArgs, null, 2)}</Text>
            </View>

            {/* Actions */}
            <View style={styles.cardActionsRow}>
              <Text style={styles.hudTargetMono}>EMITS: {tool.hudType.toUpperCase()}</Text>
              <TouchableOpacity
                style={styles.emitBtn}
                onPress={() => handleEmitToHud(tool)}
              >
                <Text style={styles.emitBtnText}>EMIT TO HUD DECK &gt;</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}

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
    marginBottom: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
    paddingBottom: theme.spacing.sm,
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
  headerSubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: 2,
    lineHeight: 16,
  },
  catScroll: {
    gap: 6,
    paddingVertical: 6,
    marginBottom: 6,
  },
  catPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: theme.radii.xs,
    backgroundColor: theme.colors.cardElevated,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  catPillActive: {
    borderColor: theme.colors.borderActive,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
  },
  catPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  catPillTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "bold",
  },
  toolList: {
    flex: 1,
  },
  toolCard: {
    backgroundColor: theme.colors.cardElevated,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  toolCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 4,
  },
  toolName: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.boneWhite,
    fontWeight: "bold",
  },
  toolSpecialist: {
    fontFamily: theme.fonts.sans,
    fontSize: 10,
    color: theme.colors.textMuted,
    marginTop: 1,
  },
  categoryBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 2,
    backgroundColor: theme.colors.cardSubdued,
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  categoryBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
  toolDesc: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginVertical: 6,
    lineHeight: 16,
  },
  paramBox: {
    backgroundColor: theme.colors.cardSubdued,
    borderRadius: theme.radii.xs,
    padding: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    marginVertical: 4,
  },
  paramLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    marginBottom: 2,
  },
  paramCode: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
    lineHeight: 14,
  },
  cardActionsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  hudTargetMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.amber,
    letterSpacing: 1,
  },
  emitBtn: {
    backgroundColor: theme.colors.cardSubdued,
    borderWidth: 1,
    borderColor: theme.colors.borderActive,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: theme.radii.xs,
  },
  emitBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
  },
});
