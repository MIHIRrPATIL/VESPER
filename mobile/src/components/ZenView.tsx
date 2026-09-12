import React, { useState, useEffect } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  Image,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";
import { gatewayClient } from "../services/gateway";
import { NowPlayingTrack, ApiTask } from "../types/vesper";

export type SoundscapeType = "off" | "ocean" | "rain" | "fireplace" | "spotify";

interface SoundscapeOption {
  id: SoundscapeType;
  label: string;
  glyph: string;
  description: string;
}

const SOUNDSCAPES: SoundscapeOption[] = [
  { id: "off", label: "Mute", glyph: "X", description: "Audio Muted • Silence" },
  { id: "ocean", label: "Ocean Waves", glyph: "~", description: "Pacific Ocean Waves (HD Stereo)" },
  { id: "rain", label: "Rainstorm", glyph: ":", description: "Gentle Rain on Glass (HD Stereo)" },
  { id: "fireplace", label: "Fireplace", glyph: "^", description: "Crackling Wood Hearth (HD Stereo)" },
  { id: "spotify", label: "Spotify", glyph: ">", description: "Spotify Audio Stream" },
];

export const ZenView: React.FC = () => {
  // Synchronized state from workstationStore
  const [secondsRemaining, setSecondsRemaining] = useState<number>(workstationStore.zenTimer.secondsRemaining);
  const [isRunning, setIsRunning] = useState<boolean>(workstationStore.zenTimer.isRunning);
  const [completedSprints, setCompletedSprints] = useState<number>(workstationStore.zenTimer.completedSprints);
  const [soundscape, setSoundscape] = useState<string>(workstationStore.zenTimer.soundscape);
  const [track, setTrack] = useState<NowPlayingTrack>(workstationStore.nowPlayingTrack);
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [activeTask, setActiveTask] = useState<string>("Executive Focus Sprint");

  // Sync with workstationStore
  useEffect(() => {
    workstationStore.fetchNowPlaying();
    const unsub = workstationStore.subscribe(() => {
      setSecondsRemaining(workstationStore.zenTimer.secondsRemaining);
      setIsRunning(workstationStore.zenTimer.isRunning);
      setCompletedSprints(workstationStore.zenTimer.completedSprints);
      setSoundscape(workstationStore.zenTimer.soundscape);
      setTrack(workstationStore.nowPlayingTrack);
    });
    fetchTasks();
    return () => unsub();
  }, []);

  // Poll Spotify track when in spotify mode
  useEffect(() => {
    if (soundscape === "spotify") {
      workstationStore.fetchNowPlaying();
      const interval = setInterval(() => {
        workstationStore.fetchNowPlaying();
      }, 2500);
      return () => clearInterval(interval);
    }
  }, [soundscape]);

  // Local tick while isRunning is true
  useEffect(() => {
    let interval: any = null;
    if (isRunning && secondsRemaining > 0) {
      interval = setInterval(() => {
        setSecondsRemaining((prev) => {
          if (prev <= 1) {
            workstationStore.sendZenTimerAction("tick", { seconds_remaining: 0 });
            return 25 * 60;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isRunning, secondsRemaining]);

  const fetchTasks = async () => {
    try {
      const baseUrl = gatewayClient.getHttpUrl();
      const res = await fetch(`${baseUrl}/api/tasks`);
      if (res.ok) {
        const data = await res.json();
        if (data.tasks) setTasks(data.tasks);
      }
    } catch {}
  };

  const handleToggleTimer = () => {
    const nextRunning = !isRunning;
    setIsRunning(nextRunning);
    workstationStore.sendZenTimerAction(nextRunning ? "start" : "pause", {
      seconds_remaining: secondsRemaining,
    });
  };

  const handleResetTimer = () => {
    setIsRunning(false);
    setSecondsRemaining(workstationStore.zenTimer.sprintMinutes * 60);
    workstationStore.sendZenTimerAction("reset");
  };

  const handleSelectSoundscape = (id: SoundscapeType) => {
    setSoundscape(id);
    workstationStore.sendZenTimerAction("soundscape", {
      soundscape: id,
      music_source: id === "spotify" ? "spotify" : "ambient",
      is_running: isRunning,
      seconds_remaining: secondsRemaining,
    });
    if (id === "spotify") {
      workstationStore.fetchNowPlaying();
    }
  };

  const handleMediaAction = (action: "play" | "pause" | "play-pause" | "next" | "previous") => {
    const nextPlaying = action === "play" ? true : action === "pause" ? false : !track.is_playing;
    setTrack((prev) => ({
      ...prev,
      is_playing: nextPlaying,
      status: nextPlaying ? "Playing" : "Paused",
    }));
    gatewayClient.sendMediaControl(action);
    setTimeout(() => {
      workstationStore.fetchNowPlaying();
    }, 400);
  };

  const handleExitZen = () => {
    workstationStore.toggleZenMode(false);
  };

  const minutes = Math.floor(secondsRemaining / 60);
  const seconds = secondsRemaining % 60;
  const timeStr = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;

  const currentSoundscapeDetails =
    SOUNDSCAPES.find((s) => s.id === soundscape) || SOUNDSCAPES[1];

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* Zen Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Zen Focus</Text>
          <Text style={styles.headerSubtitle}>Synced across all displays</Text>
        </View>
        <TouchableOpacity style={styles.exitPill} onPress={handleExitZen}>
          <Text style={styles.exitPillText}>EXIT ZEN</Text>
        </TouchableOpacity>
      </View>

      {/* ── 1. Minimalist Pomodoro Sprint Timer ── */}
      <View style={styles.timerCard}>
        <Text style={styles.cardMono}>POMODORO SPRINT RUNTIME</Text>
        <Text style={styles.bigDigits}>{timeStr}</Text>

        <View style={styles.timerControlsRow}>
          <TouchableOpacity
            style={[styles.timerMainBtn, isRunning && styles.timerMainBtnActive]}
            onPress={handleToggleTimer}
          >
            <Text style={styles.timerMainBtnText}>
              {isRunning ? "PAUSE FOCUS" : "COMMENCE SPRINT"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.timerResetBtn} onPress={handleResetTimer}>
            <Text style={styles.timerResetBtnText}>RESET</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.sprintStatsRow}>
          <Text style={styles.statLabel}>COMPLETED SPRINTS: {completedSprints}</Text>
          <Text style={styles.statLabel}>CYCLE: 25M WORK • 5M REST</Text>
        </View>
      </View>

      {/* ── 2. Soundscape & Audio Switcher ── */}
      <View style={styles.soundscapeCard}>
        <Text style={styles.cardMono}>AUDIO FOCUS ENGINE</Text>
        <Text style={styles.soundscapeSubtext}>
          Plays directly on host workstation speakers
        </Text>

        <View style={styles.soundscapePillsRow}>
          {SOUNDSCAPES.map((item) => {
            const isSelected = soundscape === item.id;
            return (
              <TouchableOpacity
                key={item.id}
                style={[styles.soundscapePill, isSelected && styles.soundscapePillActive]}
                onPress={() => handleSelectSoundscape(item.id)}
              >
                <Text
                  style={[
                    styles.soundscapePillText,
                    isSelected && styles.soundscapePillTextActive,
                  ]}
                >
                  {item.label.toUpperCase()}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Clear Now Playing Identification */}
        <View style={styles.nowPlayingDeck}>
          {soundscape === "spotify" && track.art_url ? (
            <Image source={{ uri: track.art_url }} style={styles.albumArt} />
          ) : (
            <View style={styles.nowPlayingDot} />
          )}
          <View style={{ flex: 1 }}>
            <Text style={styles.nowPlayingTitle} numberOfLines={1}>
              {soundscape === "spotify"
                ? track.title || "Spotify Audio Sink"
                : currentSoundscapeDetails.description}
            </Text>
            <Text style={styles.nowPlayingArtist} numberOfLines={1}>
              {soundscape === "spotify"
                ? `${track.artist || "Spotify"}${track.album ? ` • ${track.album}` : ""} • ${track.status || (track.is_playing ? "Playing" : "Paused")}`
                : soundscape === "off"
                ? "Audio Muted • Silence"
                : "High-Definition Stereo Field Recording • Host Speakers"}
            </Text>
          </View>
        </View>

        {/* Spotify Media Controls if in Spotify mode */}
        {soundscape === "spotify" && (
          <View style={styles.spotifyControlsRow}>
            <TouchableOpacity
              style={styles.mediaCtrlBtn}
              onPress={() => handleMediaAction("previous")}
            >
              <Text style={styles.mediaCtrlText}>PREV</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.mediaCtrlBtn, styles.mediaCtrlBtnPrimary]}
              onPress={() => handleMediaAction(track.is_playing ? "pause" : "play")}
            >
              <Text style={styles.mediaCtrlTextPrimary}>
                {track.is_playing ? "PAUSE" : "PLAY"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.mediaCtrlBtn}
              onPress={() => handleMediaAction("next")}
            >
              <Text style={styles.mediaCtrlText}>NEXT</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* ── 3. Focus Objective ── */}
      <View style={styles.taskCard}>
        <Text style={styles.cardMono}>ACTIVE FOCUS OBJECTIVE</Text>
        <Text style={styles.taskTitle}>{activeTask}</Text>
        <Text style={styles.taskSubtext}>
          Sensory suppression engaged. Notifications buffered until debrief.
        </Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0B0B0B",
  },
  contentContainer: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 40,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
  },
  headerTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 20,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  headerSubtitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    marginTop: 2,
    letterSpacing: 0.5,
  },
  exitPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 8,
  },
  exitPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
    letterSpacing: 1,
    fontWeight: "700",
  },
  timerCard: {
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 16,
    padding: 20,
    alignItems: "center",
    marginBottom: 16,
  },
  cardMono: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
    marginBottom: 10,
  },
  bigDigits: {
    fontFamily: theme.fonts.mono,
    fontSize: 64,
    fontWeight: "800",
    color: theme.colors.boneWhite,
    letterSpacing: -2,
    marginVertical: 6,
  },
  timerControlsRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 14,
    width: "100%",
  },
  timerMainBtn: {
    flex: 2,
    backgroundColor: theme.colors.boneWhite,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: "center",
  },
  timerMainBtnActive: {
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.2)",
  },
  timerMainBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.background,
    letterSpacing: 1,
  },
  timerResetBtn: {
    flex: 1,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: "center",
  },
  timerResetBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  sprintStatsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    width: "100%",
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  statLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  soundscapeCard: {
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  soundscapeSubtext: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginBottom: 12,
  },
  soundscapePillsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 14,
  },
  soundscapePill: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
  },
  soundscapePillActive: {
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    borderColor: "rgba(255, 255, 255, 0.3)",
  },
  soundscapePillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
  },
  soundscapePillTextActive: {
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  nowPlayingDeck: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: "rgba(16, 185, 129, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.18)",
    padding: 12,
    borderRadius: 10,
  },
  nowPlayingDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: theme.colors.emerald,
  },
  albumArt: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
  },
  nowPlayingTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  nowPlayingArtist: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.emerald,
    marginTop: 2,
  },
  spotifyControlsRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 12,
  },
  mediaCtrlBtn: {
    flex: 1,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: "center",
  },
  mediaCtrlBtnPrimary: {
    backgroundColor: theme.colors.boneWhite,
  },
  mediaCtrlText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  mediaCtrlTextPrimary: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: "700",
    color: theme.colors.background,
  },
  taskCard: {
    backgroundColor: "rgba(255, 255, 255, 0.02)",
    borderWidth: 1,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 16,
    padding: 16,
  },
  taskTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    marginVertical: 4,
  },
  taskSubtext: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    lineHeight: 16,
  },
});
