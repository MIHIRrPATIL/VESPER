import React, { useEffect, useRef, useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  Animated,
  Dimensions,
  Modal,
  TouchableWithoutFeedback,
  Linking,
  Image,
  Platform,
} from "react-native";
import { theme } from "../styles/theme";
import { workstationStore } from "../services/workstation-store";

const { height: SCREEN_HEIGHT } = Dimensions.get("window");

export interface HudCardData {
  id: string;
  type?: string;
  title?: string;
  subtitle?: string;
  timestamp?: number;
  data?: Record<string, any>;
  [key: string]: any;
}

interface HudDrawerModalProps {
  visible: boolean;
  cards: HudCardData[];
  onClose: () => void;
  onDismissCard: (id: string) => void;
  onDismissAll: () => void;
}

function timeAgo(ts?: number): string {
  if (!ts) return "JUST NOW";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return "JUST NOW";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}M AGO`;
  const diffHours = Math.floor(diffMin / 60);
  return `${diffHours}H AGO`;
}

// ── 1. Weather Card Renderer ────────────────────────────────────────────────
const WeatherRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const city = data.city || data.location || "Current Location";
  const temp = data.temperature !== undefined ? `${data.temperature}°` : "--";
  const condition = data.condition || data.summary || "Atmosphere Nominal";
  const humidity = data.humidity;
  const wind = data.wind_speed || data.wind;
  const feelsLike = data.feels_like;
  const forecast = Array.isArray(data.forecast) ? data.forecast : [];

  return (
    <View style={styles.cardDetailCol}>
      {/* Weather Header Bar */}
      <View style={styles.weatherHeroBlock}>
        <View style={styles.weatherLeftCol}>
          <Text style={styles.weatherLocationText}>{city.toUpperCase()}</Text>
          <Text style={styles.weatherConditionText}>{condition}</Text>
        </View>
        <Text style={styles.weatherGiantTemp}>{temp}</Text>
      </View>

      {/* Atmospheric Metrics Strip */}
      <View style={styles.metricsGrid}>
        {feelsLike !== undefined && (
          <View style={styles.metricWell}>
            <Text style={styles.metricWellLabel}>FEELS LIKE</Text>
            <Text style={styles.metricWellValue}>{feelsLike}°</Text>
          </View>
        )}
        {humidity !== undefined && (
          <View style={styles.metricWell}>
            <Text style={styles.metricWellLabel}>HUMIDITY</Text>
            <Text style={styles.metricWellValue}>{humidity}%</Text>
          </View>
        )}
        {wind !== undefined && (
          <View style={styles.metricWell}>
            <Text style={styles.metricWellLabel}>WIND SENTRY</Text>
            <Text style={styles.metricWellValue}>{String(wind)}</Text>
          </View>
        )}
      </View>

      {/* 4-Day Forecast Strip */}
      {forecast.length > 0 && (
        <View style={styles.forecastSection}>
          <Text style={styles.sectionHeaderLabel}>4-DAY ATMOSPHERIC OUTLOOK</Text>
          <View style={styles.forecastRow}>
            {forecast.slice(0, 4).map((f: any, idx: number) => (
              <View key={idx} style={styles.forecastWell}>
                <Text style={styles.forecastDayText}>
                  {String(f.day || f.date || `D+${idx + 1}`).substring(0, 3).toUpperCase()}
                </Text>
                <Text style={styles.forecastCondText} numberOfLines={1}>
                  {f.condition || f.weather || "—"}
                </Text>
                <Text style={styles.forecastTempText}>
                  {f.temp || f.max_temp || "--"}°
                </Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </View>
  );
};

// ── 2. Spotify / Media Card Renderer ─────────────────────────────────────────
const SpotifyRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(Boolean(data.is_playing ?? true));

  const track =
    data.track ||
    data.track_title ||
    data.title ||
    data.song ||
    workstationStore.nowPlayingTrack.title ||
    "Spotify Stream";

  const artist =
    data.artist ||
    (Array.isArray(data.artists) ? data.artists.join(", ") : data.artist_name) ||
    workstationStore.nowPlayingTrack.artist ||
    "Spotify Connect";

  const album =
    data.album ||
    data.album_name ||
    workstationStore.nowPlayingTrack.album ||
    "Studio Session";

  const artUrl =
    data.art_url ||
    data.album_art ||
    data.image_url ||
    data.cover_url ||
    workstationStore.nowPlayingTrack.art_url ||
    null;

  const playlist =
    data.playlist_name || data.playlist || (data.type === "spotify_playlist" ? data.name : null);

  const trackUri =
    data.uri ||
    data.spotify_uri ||
    (data.track_id ? `spotify:track:${data.track_id}` : null) ||
    (data.playlist_id ? `spotify:playlist:${data.playlist_id}` : null);

  const webUrl =
    data.url ||
    data.link ||
    (trackUri && trackUri.startsWith("spotify:track:")
      ? `https://open.spotify.com/track/${trackUri.replace("spotify:track:", "")}`
      : "https://open.spotify.com");

  const handleOpenInSpotify = async () => {
    if (trackUri) {
      try {
        const canOpen = await Linking.canOpenURL(trackUri);
        if (canOpen) {
          await Linking.openURL(trackUri);
          return;
        }
      } catch {}
    }
    Linking.openURL(webUrl).catch(() => {});
  };

  const handleTogglePlay = () => {
    setIsPlaying((prev) => !prev);
    workstationStore.sendZenTimerAction("soundscape", { soundscape: "spotify", music_source: "spotify" });
  };

  return (
    <View style={styles.cardDetailCol}>
      {playlist && (
        <View style={styles.tagPillRow}>
          <View style={styles.playlistPill}>
            <Text style={styles.playlistPillText}>PLAYLIST // {String(playlist).toUpperCase()}</Text>
          </View>
        </View>
      )}

      {/* Main Track Row with Album Art */}
      <View style={styles.spotifyTrackRow}>
        <TouchableOpacity
          style={styles.spotifyAlbumArtBox}
          onPress={handleOpenInSpotify}
          activeOpacity={0.8}
        >
          {artUrl ? (
            <Image
              source={{ uri: artUrl }}
              style={styles.spotifyAlbumCoverImage}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.spotifyVinylCircle}>
              <View style={styles.spotifyVinylHole} />
            </View>
          )}
          {isPlaying && (
            <View style={styles.pulseEqBars}>
              <View style={[styles.eqBar, styles.eqBar1]} />
              <View style={[styles.eqBar, styles.eqBar2]} />
              <View style={[styles.eqBar, styles.eqBar3]} />
            </View>
          )}
        </TouchableOpacity>

        <View style={styles.spotifyMetaCol}>
          <View style={styles.spotifyStatusBadge}>
            <Text style={styles.spotifyStatusText}>{isPlaying ? "NOW PLAYING" : "PAUSED"}</Text>
          </View>
          <TouchableOpacity onPress={handleOpenInSpotify} activeOpacity={0.7}>
            <Text style={styles.spotifyTrackTitle} numberOfLines={1}>{track}</Text>
          </TouchableOpacity>
          <Text style={styles.spotifyArtistText} numberOfLines={1}>{artist}</Text>
          {album && <Text style={styles.spotifyAlbumText} numberOfLines={1}>Disc // {album}</Text>}
        </View>
      </View>

      {/* Playback Controls & Open in Native Spotify App */}
      <View style={styles.spotifyControlsRow}>
        <View style={styles.spotifyControlGroup}>
          <TouchableOpacity
            style={styles.spotifyCtrlBtn}
            onPress={() => workstationStore.sendZenTimerAction("soundscape", { soundscape: "ocean" })}
          >
            <Text style={styles.spotifyCtrlGlyph}>|‹</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.spotifyCtrlBtn, styles.spotifyCtrlBtnActive]}
            onPress={handleTogglePlay}
          >
            <Text style={styles.spotifyCtrlGlyphActive}>{isPlaying ? "||" : ">"}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.spotifyCtrlBtn}
            onPress={() => workstationStore.sendZenTimerAction("soundscape", { soundscape: "ambient" })}
          >
            <Text style={styles.spotifyCtrlGlyph}>›|</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={styles.spotifyOpenBtn}
          onPress={handleOpenInSpotify}
          activeOpacity={0.8}
        >
          <Text style={styles.spotifyOpenText}>OPEN IN SPOTIFY APP ›</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

// ── 3. YouTube Video & Media Runtime Renderer ────────────────────────────────
const YoutubeRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const title = data.title || "YouTube Video";
  const channel = data.channel || data.author || data.uploader || "YouTube Channel";
  const duration = data.duration || data.duration_string || data.length;
  const videoId =
    data.video_id ||
    data.youtube_id ||
    data.id ||
    (data.url ? (data.url.match(/[?&]v=([^&]+)/) || [])[1] : null);

  const link =
    data.url ||
    data.link ||
    (videoId ? `https://www.youtube.com/watch?v=${videoId}` : "https://www.youtube.com");

  const thumbnail =
    data.thumbnail ||
    data.thumbnail_url ||
    (videoId ? `https://img.youtube.com/vi/${videoId}/hqdefault.jpg` : null);

  const snippet = data.snippet || data.description || data.summary;
  const views = data.views || data.view_count;

  const handleOpenInYouTube = async () => {
    if (videoId) {
      const nativeUri =
        Platform.OS === "android"
          ? `vnd.youtube:${videoId}`
          : `youtube://watch?v=${videoId}`;
      try {
        const canOpen = await Linking.canOpenURL(nativeUri);
        if (canOpen) {
          await Linking.openURL(nativeUri);
          return;
        }
      } catch {}
    }
    Linking.openURL(link).catch(() => {});
  };

  return (
    <View style={styles.cardDetailCol}>
      {/* 16:9 Video Thumbnail Banner */}
      {thumbnail ? (
        <TouchableOpacity
          style={styles.ytThumbContainer}
          onPress={handleOpenInYouTube}
          activeOpacity={0.85}
        >
          <Image
            source={{ uri: thumbnail }}
            style={styles.ytThumbImage}
            resizeMode="cover"
          />
          {/* Play Button Overlay */}
          <View style={styles.ytPlayOverlay}>
            <View style={styles.ytPlayCircle}>
              <Text style={styles.ytPlayGlyph}>&gt;</Text>
            </View>
          </View>

          {/* Duration Badge */}
          {duration && (
            <View style={styles.ytDurationBadge}>
              <Text style={styles.ytDurationText}>{duration}</Text>
            </View>
          )}
        </TouchableOpacity>
      ) : null}

      {/* Video Details */}
      <View style={styles.ytMetaBlock}>
        <TouchableOpacity onPress={handleOpenInYouTube} activeOpacity={0.7}>
          <Text style={styles.ytTitleText} numberOfLines={2}>
            {title}
          </Text>
        </TouchableOpacity>

        <View style={styles.ytChannelRow}>
          <View style={styles.ytVerifiedDot} />
          <Text style={styles.ytChannelText}>{channel}</Text>
          {views && (
            <>
              <Text style={styles.ytDotSeparator}>•</Text>
              <Text style={styles.ytViewsText}>{views}</Text>
            </>
          )}
        </View>

        {snippet && (
          <Text style={styles.ytSnippetText} numberOfLines={3}>
            {snippet}
          </Text>
        )}
      </View>

      {/* Action Strip: Deep-link to YouTube App */}
      <View style={styles.ytActionRow}>
        <TouchableOpacity
          style={styles.ytAppLaunchBtn}
          onPress={handleOpenInYouTube}
          activeOpacity={0.8}
        >
          <View style={styles.ytRedBadge}>
            <Text style={styles.ytRedBadgeText}>&gt;</Text>
          </View>
          <Text style={styles.ytAppLaunchText}>OPEN IN YOUTUBE APP</Text>
        </TouchableOpacity>

        {videoId && (
          <TouchableOpacity
            style={styles.ytWebLinkBtn}
            onPress={() => Linking.openURL(link).catch(() => {})}
          >
            <Text style={styles.ytWebLinkText}>WEB ›</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
};

// ── 3. Transaction / Financial Ledger Renderer ──────────────────────────────
const TransactionRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const isSummaryCard =
    data.type === "finance_summary_card" ||
    (data.total_net_worth !== undefined && Array.isArray(data.accounts));

  if (isSummaryCard) {
    const netWorth = Number(data.total_net_worth || 0);
    const accounts: any[] = Array.isArray(data.accounts) ? data.accounts : [];
    const recentTxns: any[] = Array.isArray(data.recent_transactions) ? data.recent_transactions : [];

    return (
      <View style={styles.cardDetailCol}>
        {/* Total Net Worth Well */}
        <View style={styles.doubleBezelWell}>
          <View style={styles.wellTopRow}>
            <Text style={styles.wellLabel}>TOTAL LIQUID RESERVES</Text>
            <View style={styles.emeraldStatusPill}>
              <Text style={styles.emeraldStatusText}>LIVE LEDGER</Text>
            </View>
          </View>
          <Text style={styles.giantCurrencyText}>
            ₹ {netWorth.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </Text>
        </View>

        {/* Account Reserves Grid */}
        {accounts.length > 0 && (
          <View style={styles.accountsGrid}>
            {accounts.slice(0, 4).map((acc, idx) => (
              <View key={acc.id || idx} style={styles.accountCard}>
                <View style={styles.accountTopRow}>
                  <Text style={styles.accountName} numberOfLines={1}>{acc.name}</Text>
                  <Text style={styles.accountType}>{acc.type || "LIQUID"}</Text>
                </View>
                <Text style={styles.accountBalance}>
                  ₹ {Number(acc.balance || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* Recent Transactions Mini List */}
        {recentTxns.length > 0 && (
          <View style={styles.txnsListBlock}>
            <Text style={styles.sectionHeaderLabel}>RECENT MOVEMENTS</Text>
            {recentTxns.slice(0, 3).map((txn, idx) => {
              const isExpense = (txn.type || "").toLowerCase().includes("exp");
              return (
                <View key={txn.id || idx} style={styles.txnItemRow}>
                  <Text style={styles.txnDescText} numberOfLines={1}>
                    {txn.description || txn.category || "Transaction"}
                  </Text>
                  <Text style={[styles.txnAmountText, isExpense ? styles.amountExpense : styles.amountIncome]}>
                    {isExpense ? "-" : "+"} ₹ {Number(txn.amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </Text>
                </View>
              );
            })}
          </View>
        )}
      </View>
    );
  }

  // Single Transaction Card
  const amount = data.amount;
  const merchant = data.merchant || data.payee || data.description || "Operational Expense";
  const category = data.category || "General Ledger";
  const account = data.account || data.bank || "Primary Reserve";
  const balance = data.balance ?? data.new_balance;

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.doubleBezelWell}>
        <View style={styles.wellTopRow}>
          <Text style={styles.wellLabel}>AMOUNT PROCESSED</Text>
          <View style={styles.categoryPill}>
            <Text style={styles.categoryPillText}>{String(category).toUpperCase()}</Text>
          </View>
        </View>
        <Text style={styles.giantCurrencyText}>
          ₹ {Number(amount !== undefined ? amount : (data.total_balance ?? 0)).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
        </Text>
      </View>

      <View style={styles.keyValTable}>
        <View style={styles.tableRow}>
          <Text style={styles.tableKey}>RECIPIENT / NOTE</Text>
          <Text style={styles.tableVal} numberOfLines={1}>{merchant}</Text>
        </View>
        <View style={styles.tableRow}>
          <Text style={styles.tableKey}>SETTLEMENT ACCOUNT</Text>
          <Text style={styles.tableVal}>{account}</Text>
        </View>
        {balance !== undefined && (
          <View style={[styles.tableRow, styles.tableRowHighlight]}>
            <Text style={styles.tableKey}>BALANCE REMAINING</Text>
            <Text style={styles.tableValEmerald}>
              ₹ {Number(balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </Text>
          </View>
        )}
      </View>
    </View>
  );
};

// ── 4. Task & Agenda Card Renderer ──────────────────────────────────────────
const TaskRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const rawTasks = Array.isArray(data.tasks)
    ? data.tasks
    : data.task
    ? [data.task]
    : [data];

  const [completedMap, setCompletedMap] = useState<Record<string, boolean>>({});

  const toggleTask = (id: string) => {
    setCompletedMap((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tasksHeaderStrip}>
        <Text style={styles.sectionHeaderLabel}>OPERATIONAL DIRECTIVES</Text>
        <Text style={styles.metaCounterText}>{rawTasks.length} DIRECTIVES</Text>
      </View>

      <View style={styles.tasksList}>
        {rawTasks.map((t: any, idx: number) => {
          const id = t.id || `task_${idx}`;
          const isDone = Boolean(t.done || completedMap[id]);
          const priority = (t.priority || "normal").toLowerCase();
          const isUrgent = priority === "urgent";
          const isHigh = priority === "high";

          return (
            <TouchableOpacity
              key={id}
              style={[styles.taskItemCard, isDone && styles.taskItemDone]}
              onPress={() => toggleTask(id)}
              activeOpacity={0.7}
            >
              <View style={styles.taskCheckRow}>
                <View style={[styles.checkboxWell, isDone && styles.checkboxWellDone]}>
                  <Text style={styles.checkboxCheckGlyph}>{isDone ? "✓" : ""}</Text>
                </View>
                <Text style={[styles.taskTitleText, isDone && styles.taskTitleDone]} numberOfLines={2}>
                  {t.title || t.task || t.name || "Scheduled Operation"}
                </Text>
              </View>

              <View style={styles.taskMetaRow}>
                <View
                  style={[
                    styles.priorityPill,
                    isUrgent && styles.priorityUrgent,
                    isHigh && styles.priorityHigh,
                  ]}
                >
                  <Text
                    style={[
                      styles.priorityText,
                      isUrgent && styles.priorityTextUrgent,
                      isHigh && styles.priorityTextHigh,
                    ]}
                  >
                    {priority.toUpperCase()}
                  </Text>
                </View>

                {t.deadline && (
                  <Text style={styles.taskDeadlineText}>DUE: {t.deadline}</Text>
                )}
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};

// ── 5. Calendar Card Renderer ───────────────────────────────────────────────
const CalendarRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const events = Array.isArray(data.events)
    ? data.events
    : data.event
    ? [data.event]
    : [];

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tasksHeaderStrip}>
        <Text style={styles.sectionHeaderLabel}>SYNCHRONIZED APPOINTMENTS</Text>
        <Text style={styles.metaCounterText}>GOOGLE CALENDAR</Text>
      </View>

      <View style={styles.eventsList}>
        {events.length === 0 ? (
          <View style={styles.emptyCardWell}>
            <Text style={styles.emptyCardWellText}>No upcoming appointments logged.</Text>
          </View>
        ) : (
          events.map((ev: any, idx: number) => (
            <View key={idx} style={styles.eventItemCard}>
              <View style={styles.eventMainRow}>
                <Text style={styles.eventTitleText} numberOfLines={1}>
                  {ev.summary || ev.title || "Scheduled Engagement"}
                </Text>
                <View style={styles.eventTimePill}>
                  <Text style={styles.eventTimeText}>
                    {ev.time || (ev.start ? `${ev.start} - ${ev.end || ""}` : "SCHEDULED")}
                  </Text>
                </View>
              </View>
              {ev.location && (
                <Text style={styles.eventLocationText} numberOfLines={1}>
                  Location // {ev.location}
                </Text>
              )}
            </View>
          ))
        )}
      </View>
    </View>
  );
};

// ── 6. Research & Briefing Card Renderer ────────────────────────────────────
const BriefingRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const query = data.query;
  const answer = data.answer || data.summary || data.text || data.briefing || data.markdown || "";
  const sources: any[] = Array.isArray(data.sources) ? data.sources : [];
  const overdueTasks = Array.isArray(data.overdue_tasks) ? data.overdue_tasks : [];

  return (
    <View style={styles.cardDetailCol}>
      {query && (
        <View style={styles.tagPillRow}>
          <View style={styles.queryPill}>
            <Text style={styles.queryPillText}>QUERY // {String(query).toUpperCase()}</Text>
          </View>
        </View>
      )}

      {/* Synthesis / Summary Well */}
      {answer ? (
        <View style={styles.readingWell}>
          <Text style={styles.readingWellText}>{String(answer)}</Text>
        </View>
      ) : null}

      {/* Overdue Action Well */}
      {overdueTasks.length > 0 && (
        <View style={styles.overdueBlock}>
          <Text style={styles.overdueLabel}>OVERDUE MATTERS (ACTION REQUIRED)</Text>
          {overdueTasks.slice(0, 3).map((ot: any, idx: number) => (
            <View key={idx} style={styles.overdueItem}>
              <Text style={styles.overdueItemTitle} numberOfLines={1}>
                {ot.title || ot}
              </Text>
              <Text style={styles.overdueItemAge}>{ot.age || "Pending"}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Sources Chips */}
      {sources.length > 0 && (
        <View style={styles.sourcesBlock}>
          <Text style={styles.sectionHeaderLabel}>VERIFIED SOURCES ({sources.length})</Text>
          <View style={styles.sourcesChipRow}>
            {sources.map((src: any, idx: number) => {
              const link = typeof src === "string" ? src : src.url || src.link;
              const title = typeof src === "string" ? src : src.title || src.name || link;
              return (
                <TouchableOpacity
                  key={idx}
                  style={styles.sourceChip}
                  onPress={() => link && Linking.openURL(link).catch(() => {})}
                >
                  <Text style={styles.sourceChipText} numberOfLines={1}>{title}</Text>
                  <Text style={styles.sourceChipGlyph}>↗</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      )}
    </View>
  );
};


// ── 7. Email / Correspondence Card Renderer ────────────────────────────────
const EmailRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const email = data.email || data;
  const sender = email.sender || email.from || "Cluster Dispatch";
  const subject = email.subject || email.title || "Priority Correspondence";
  const body = email.body || email.snippet || email.text || "No preview content available.";
  const initial = (sender[0] || "V").toUpperCase();

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.emailHeaderRow}>
        <View style={styles.emailAvatarCircle}>
          <Text style={styles.emailAvatarText}>{initial}</Text>
        </View>
        <View style={styles.emailMetaCol}>
          <Text style={styles.emailSenderText} numberOfLines={1}>{sender}</Text>
          <Text style={styles.emailSubjectText} numberOfLines={1}>{subject}</Text>
        </View>
      </View>

      <View style={styles.readingWell}>
        <Text style={styles.readingWellText} numberOfLines={5}>{body}</Text>
      </View>
    </View>
  );
};

// ── 8. System Status / Telemetry Card Renderer ──────────────────────────────
const SystemStatusRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const cpu = Number(data.cpu_usage ?? data.cpu ?? 14);
  const ram = Number(data.ram_usage ?? data.memory ?? 48);
  const host = data.hostname || data.host || "VESPER-MASTER";

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.emeraldStatusPill}>
          <Text style={styles.emeraldStatusText}>NODE: {String(host).toUpperCase()}</Text>
        </View>
      </View>

      <View style={styles.telemetryBarsCol}>
        <View style={styles.telemetryBarItem}>
          <View style={styles.telemetryLabelRow}>
            <Text style={styles.metricWellLabel}>CPU COMPUTE LOAD</Text>
            <Text style={styles.metricWellValue}>{cpu}%</Text>
          </View>
          <View style={styles.barTrack}>
            <View style={[styles.barFill, { width: `${Math.min(100, Math.max(5, cpu))}%` }]} />
          </View>
        </View>

        <View style={styles.telemetryBarItem}>
          <View style={styles.telemetryLabelRow}>
            <Text style={styles.metricWellLabel}>RAM MEMORY RESERVES</Text>
            <Text style={styles.metricWellValue}>{ram}%</Text>
          </View>
          <View style={styles.barTrack}>
            <View style={[styles.barFill, { width: `${Math.min(100, Math.max(5, ram))}%` }]} />
          </View>
        </View>
      </View>
    </View>
  );
};

// ── 9. GitHub Suite Renderer ────────────────────────────────────────────────
const GithubRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const repo = data.repo || data.repository || data.repo_name || data.full_name || "";
  const stars = data.stars || data.stargazers_count;
  const forks = data.forks || data.forks_count;
  const openIssues = data.open_issues || data.open_issues_count;
  const language = data.primary_language || data.language;
  const description = data.description || "";
  const issues: any[] = Array.isArray(data.issues) ? data.issues : [];
  const prs: any[] = Array.isArray(data.pull_requests) ? data.pull_requests : (Array.isArray(data.prs) ? data.prs : []);
  const commits: any[] = Array.isArray(data.commits) ? data.commits : [];
  const matches: any[] = Array.isArray(data.matches) ? data.matches : [];
  const codeContent = data.content || data.code || data.snippet;
  const codePath = data.path || data.file || data.filename;

  const handleOpenUrl = (url?: string) => {
    const targetUrl = url || (repo ? `https://github.com/${repo}` : "https://github.com");
    Linking.openURL(targetUrl).catch(() => {});
  };

  return (
    <View style={styles.cardDetailCol}>
      {/* Repo Banner if repo name is provided */}
      {Boolean(repo) && (
        <View style={styles.githubHeroBlock}>
          <View style={styles.githubTitleRow}>
            <Text style={styles.githubRepoName} numberOfLines={1}>{repo}</Text>
            <TouchableOpacity
              style={styles.githubOpenBtn}
              onPress={() => handleOpenUrl(`https://github.com/${repo}`)}
              activeOpacity={0.7}
            >
              <Text style={styles.githubOpenBtnText}>VIEW REPO</Text>
            </TouchableOpacity>
          </View>
          {Boolean(description) && (
            <Text style={styles.githubDescText} numberOfLines={2}>{description}</Text>
          )}

          {/* Stats Bar */}
          <View style={styles.metricsGrid}>
            {stars !== undefined && (
              <View style={styles.metricWell}>
                <Text style={styles.metricWellLabel}>STARS</Text>
                <Text style={styles.metricWellValue}>{String(stars)}</Text>
              </View>
            )}
            {forks !== undefined && (
              <View style={styles.metricWell}>
                <Text style={styles.metricWellLabel}>FORKS</Text>
                <Text style={styles.metricWellValue}>{String(forks)}</Text>
              </View>
            )}
            {openIssues !== undefined && (
              <View style={styles.metricWell}>
                <Text style={styles.metricWellLabel}>ISSUES</Text>
                <Text style={styles.metricWellValue}>{String(openIssues)}</Text>
              </View>
            )}
            {Boolean(language) && (
              <View style={styles.metricWell}>
                <Text style={styles.metricWellLabel}>LANGUAGE</Text>
                <Text style={styles.metricWellValue} numberOfLines={1}>{String(language)}</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* Issues List */}
      {issues.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>ISSUES ({issues.length})</Text>
          {issues.slice(0, 5).map((iss: any, idx: number) => {
            const num = iss.number ? `#${iss.number}` : `#${idx + 1}`;
            const state = (iss.state || "open").toUpperCase();
            const isOpen = state === "OPEN";
            const issLink = iss.html_url || iss.url || (repo ? `https://github.com/${repo}/issues/${iss.number}` : undefined);
            return (
              <TouchableOpacity
                key={idx}
                style={styles.githubItemRow}
                onPress={() => handleOpenUrl(issLink)}
                activeOpacity={0.7}
              >
                <View style={styles.githubItemLeft}>
                  <Text style={styles.githubItemNum}>{num}</Text>
                  <Text style={styles.githubItemTitle} numberOfLines={1}>{iss.title || "Untitled Issue"}</Text>
                </View>
                <View style={[styles.githubStatePill, isOpen ? styles.statePillOpen : styles.statePillClosed]}>
                  <Text style={[styles.githubStateText, isOpen ? styles.stateTextOpen : styles.stateTextClosed]}>{state}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      )}

      {/* Pull Requests List */}
      {prs.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>PULL REQUESTS ({prs.length})</Text>
          {prs.slice(0, 5).map((pr: any, idx: number) => {
            const num = pr.number ? `#${pr.number}` : `#${idx + 1}`;
            const state = (pr.state || "open").toUpperCase();
            const isMerged = state === "MERGED";
            const isOpen = state === "OPEN";
            const prLink = pr.html_url || pr.url || (repo ? `https://github.com/${repo}/pull/${pr.number}` : undefined);
            return (
              <TouchableOpacity
                key={idx}
                style={styles.githubItemRow}
                onPress={() => handleOpenUrl(prLink)}
                activeOpacity={0.7}
              >
                <View style={styles.githubItemLeft}>
                  <Text style={styles.githubItemNum}>{num}</Text>
                  <Text style={styles.githubItemTitle} numberOfLines={1}>{pr.title || "Untitled PR"}</Text>
                </View>
                <View style={styles.githubPrRight}>
                  {(pr.additions !== undefined || pr.deletions !== undefined) && (
                    <Text style={styles.githubDiffText}>
                      +{pr.additions || 0} -{pr.deletions || 0}
                    </Text>
                  )}
                  <View style={[styles.githubStatePill, isMerged ? styles.statePillMerged : isOpen ? styles.statePillOpen : styles.statePillClosed]}>
                    <Text style={[styles.githubStateText, isMerged ? styles.stateTextMerged : isOpen ? styles.stateTextOpen : styles.stateTextClosed]}>{state}</Text>
                  </View>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      )}

      {/* Commits List */}
      {commits.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>RECENT COMMITS ({commits.length})</Text>
          {commits.slice(0, 4).map((c: any, idx: number) => {
            const sha = c.sha ? c.sha.substring(0, 7) : "HEAD";
            const msg = c.message || c.commit?.message || "Commit";
            const author = c.author?.name || c.author || "committer";
            const cLink = c.html_url || c.url || (repo && c.sha ? `https://github.com/${repo}/commit/${c.sha}` : undefined);
            return (
              <TouchableOpacity
                key={idx}
                style={styles.githubCommitRow}
                onPress={() => handleOpenUrl(cLink)}
                activeOpacity={0.7}
              >
                <View style={styles.commitShaPill}>
                  <Text style={styles.commitShaText}>{sha}</Text>
                </View>
                <View style={styles.commitMetaCol}>
                  <Text style={styles.commitMsgText} numberOfLines={1}>{msg}</Text>
                  <Text style={styles.commitAuthorText}>{author}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      )}

      {/* Code Snippet Box */}
      {(Boolean(codeContent) || Boolean(codePath)) && (
        <View style={styles.sectionCol}>
          {Boolean(codePath) && (
            <View style={styles.codeHeaderBar}>
              <Text style={styles.codePathText} numberOfLines={1}>{codePath}</Text>
            </View>
          )}
          <View style={styles.codeContainerWell}>
            <Text selectable={true} style={styles.codeText}>{codeContent || "// No source code body"}</Text>
          </View>
        </View>
      )}

      {/* Code Search Matches */}
      {matches.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>CODE SEARCH MATCHES ({matches.length})</Text>
          {matches.slice(0, 4).map((m: any, idx: number) => (
            <View key={idx} style={styles.codeMatchItem}>
              <Text style={styles.codePathText} numberOfLines={1}>{m.path || m.file}</Text>
              <Text selectable={true} style={styles.codeMatchSnippet} numberOfLines={3}>
                {m.fragment || m.snippet || m.match || ""}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
};

// ── 10. Email Inbox List Renderer ───────────────────────────────────────────
const EmailListRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const emails: any[] = Array.isArray(data.emails) ? data.emails : [];
  const title = data.title || "Unread Inbox";
  const unreadCount = data.unread_count ?? emails.filter((e) => e.unread !== false).length;

  const handleOpenEmail = (id?: string) => {
    const url = `https://mail.google.com/mail/u/0/#inbox/${id || ""}`;
    Linking.openURL(url).catch(() => {});
  };

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.inboxPill}>
          <Text style={styles.inboxPillText}>{title.toUpperCase()}</Text>
        </View>
        <View style={styles.unreadCountPill}>
          <Text style={styles.unreadCountText}>{unreadCount} UNREAD</Text>
        </View>
      </View>

      <View style={styles.emailListCol}>
        {emails.length === 0 ? (
          <View style={styles.readingWell}>
            <Text style={styles.readingWellText}>No emails matching search query.</Text>
          </View>
        ) : (
          emails.slice(0, 6).map((em: any, idx: number) => {
            const sender = em.from || em.sender || "Sender";
            const initial = (sender[0] || "M").toUpperCase();
            const subject = em.subject || "(No Subject)";
            const snippet = em.snippet || em.body || "";
            const isUnread = em.unread !== false;

            return (
              <TouchableOpacity
                key={em.id || idx}
                style={styles.emailItemBox}
                onPress={() => handleOpenEmail(em.id)}
                activeOpacity={0.7}
              >
                <View style={styles.emailAvatarCircleSmall}>
                  <Text style={styles.emailAvatarTextSmall}>{initial}</Text>
                </View>
                <View style={styles.emailItemMetaCol}>
                  <View style={styles.emailItemTopRow}>
                    <Text style={styles.emailSenderSmall} numberOfLines={1}>{sender}</Text>
                    {isUnread && <View style={styles.unreadAmberDot} />}
                    <Text style={styles.emailTimeSmall}>{em.date ? timeAgo(new Date(em.date).getTime()) : ""}</Text>
                  </View>
                  <Text style={styles.emailSubjectSmall} numberOfLines={1}>{subject}</Text>
                  {Boolean(snippet) && (
                    <Text style={styles.emailSnippetSmall} numberOfLines={2}>{snippet}</Text>
                  )}
                </View>
              </TouchableOpacity>
            );
          })
        )}
      </View>
    </View>
  );
};

// ── 11. Email Conversation Thread Renderer ──────────────────────────────────
const EmailThreadRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const subject = data.subject || "Email Thread";
  const messages: any[] = Array.isArray(data.messages) ? data.messages : [];
  const participants: string[] = Array.isArray(data.participants) ? data.participants : [];

  return (
    <View style={styles.cardDetailCol}>
      <Text style={styles.threadSubjectHeading}>{subject}</Text>

      {participants.length > 0 && (
        <View style={styles.sourcesChipRow}>
          {participants.map((p, idx) => (
            <View key={idx} style={styles.sourceChip}>
              <Text style={styles.sourceChipText} numberOfLines={1}>{p}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={styles.threadMessagesCol}>
        {messages.map((msg: any, idx: number) => {
          const from = msg.from || msg.sender || "User";
          const body = msg.body || msg.snippet || "";
          return (
            <View key={idx} style={styles.threadMsgCard}>
              <View style={styles.threadMsgHeader}>
                <Text style={styles.threadMsgSender}>{from}</Text>
                <Text style={styles.threadMsgTime}>{msg.date ? timeAgo(new Date(msg.date).getTime()) : ""}</Text>
              </View>
              <Text style={styles.threadMsgBody}>{body}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
};

// ── 12. Email Draft & Sent Card Renderer ────────────────────────────────────
const EmailDraftRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const draft = data.draft || data;
  const to = draft.to || "recipient@domain.com";
  const subject = draft.subject || "(No Subject)";
  const body = draft.body || draft.message || "";
  const isSent = data.type === "email_sent_card" || draft.status === "SENT";

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={isSent ? styles.emeraldStatusPill : styles.amberStatusPill}>
          <Text style={isSent ? styles.emeraldStatusText : styles.amberStatusText}>
            {isSent ? "DISPATCHED VIA SMTP" : "COMPOSED DRAFT"}
          </Text>
        </View>
      </View>

      <View style={styles.draftMetaBox}>
        <View style={styles.draftFieldRow}>
          <Text style={styles.draftFieldLabel}>TO</Text>
          <Text style={styles.draftFieldValue}>{to}</Text>
        </View>
        <View style={styles.draftFieldRow}>
          <Text style={styles.draftFieldLabel}>SUBJECT</Text>
          <Text style={styles.draftFieldValue}>{subject}</Text>
        </View>
      </View>

      <View style={styles.readingWell}>
        <Text style={styles.readingWellText}>{body || "(Empty message draft)"}</Text>
      </View>
    </View>
  );
};

// ── 13. Bill Split & Group Share Renderer ───────────────────────────────────
const BillSplitRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const total = Number(data.total_amount || data.total || data.amount || 0);
  const currency = data.currency || "₹";
  const payer = data.payer || data.paid_by || "Mihir";
  const desc = data.description || data.note || "Shared Expense";
  const participants: any[] = Array.isArray(data.participants) ? data.participants : [];
  const perPerson = data.per_person || (participants.length > 0 ? (total / participants.length).toFixed(2) : total.toFixed(2));

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.billHeroCard}>
        <View style={styles.billHeroTop}>
          <View>
            <Text style={styles.billHeroSub}>TOTAL BILL</Text>
            <Text style={styles.billHeroAmount}>{currency} {total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</Text>
          </View>
          <View style={styles.payerPill}>
            <Text style={styles.payerPillText}>PAID BY {String(payer).toUpperCase()}</Text>
          </View>
        </View>
        <Text style={styles.billHeroDesc}>{desc}</Text>
      </View>

      <View style={styles.perPersonBar}>
        <Text style={styles.perPersonLabel}>EQUAL SHARE</Text>
        <Text style={styles.perPersonValue}>{currency} {Number(perPerson).toLocaleString("en-IN", { minimumFractionDigits: 2 })} / person</Text>
      </View>

      {participants.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>PARTICIPANT BREAKDOWN</Text>
          <View style={styles.participantsGrid}>
            {participants.map((p: any, idx: number) => {
              const name = typeof p === "string" ? p : p.name;
              const share = typeof p === "object" && p.share ? p.share : perPerson;
              const isPayer = name.toLowerCase() === payer.toLowerCase();
              return (
                <View key={idx} style={styles.participantItem}>
                  <Text style={styles.participantName}>{name}</Text>
                  <Text style={isPayer ? styles.participantOwesEmerald : styles.participantOwesText}>
                    {isPayer ? "PAID ALL" : `${currency} ${Number(share).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}
                  </Text>
                </View>
              );
            })}
          </View>
        </View>
      )}
    </View>
  );
};

// ── 14. Peer Tab & Debt Summary Renderer ────────────────────────────────────
const DebtSummaryRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const currency = data.currency || "₹";
  const owedToYou = Number(data.total_owed_to_you || data.owed_to_me || data.owed || 0);
  const youOwe = Number(data.total_you_owe || data.you_owe || data.owe || 0);
  const peers: any[] = Array.isArray(data.peers) ? data.peers : (Array.isArray(data.debts) ? data.debts : []);

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.debtHeroGrid}>
        <View style={styles.debtHeroEmerald}>
          <Text style={styles.debtHeroLabelEmerald}>OWED TO YOU</Text>
          <Text style={styles.debtHeroValEmerald}>+ {currency} {owedToYou.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</Text>
        </View>
        <View style={styles.debtHeroRose}>
          <Text style={styles.debtHeroLabelRose}>YOU OWE</Text>
          <Text style={styles.debtHeroValRose}>- {currency} {youOwe.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</Text>
        </View>
      </View>

      {peers.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>PEER TAB BALANCES</Text>
          {peers.map((peer: any, idx: number) => {
            const name = peer.name || peer.person || `Peer ${idx + 1}`;
            const bal = Number(peer.balance || peer.amount || 0);
            const isOwed = bal >= 0;
            return (
              <View key={idx} style={styles.peerItemRow}>
                <Text style={styles.peerNameText}>{name}</Text>
                <Text style={isOwed ? styles.peerBalEmerald : styles.peerBalRose}>
                  {isOwed ? "+" : "-"} {currency} {Math.abs(bal).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </Text>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
};

// ── 15. Financial Goals Renderer ────────────────────────────────────────────
const FinancialGoalsRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const goals: any[] = Array.isArray(data.goals) ? data.goals : (data.goal ? [data.goal] : []);
  const currency = data.currency || "₹";

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.sectionCol}>
        {goals.map((g: any, idx: number) => {
          const name = g.name || g.title || `Goal ${idx + 1}`;
          const current = Number(g.current_amount || g.current || 0);
          const target = Number(g.target_amount || g.target || 1);
          const pct = Math.min(100, Math.round((current / target) * 100));
          const deficit = Math.max(0, target - current);

          return (
            <View key={idx} style={styles.goalCard}>
              <View style={styles.goalHeaderRow}>
                <Text style={styles.goalNameText}>{name}</Text>
                <View style={styles.goalPctPill}>
                  <Text style={styles.goalPctText}>{pct}%</Text>
                </View>
              </View>

              <View style={styles.goalBarTrack}>
                <View style={[styles.goalBarFill, { width: `${pct}%` }]} />
              </View>

              <View style={styles.goalBottomRow}>
                <Text style={styles.goalCurrentText}>{currency} {current.toLocaleString("en-IN")} / {currency} {target.toLocaleString("en-IN")}</Text>
                <Text style={styles.goalDeficitText}>{deficit > 0 ? `${currency} ${deficit.toLocaleString("en-IN")} to goal` : "TARGET ACHIEVED"}</Text>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
};

// ── 16. Optical Vision Analysis Renderer ────────────────────────────────────
const VisionAnalysisRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const source = (data.source || data.sensor || "LIVE WEBCAM SENSOR").toUpperCase();
  const analysis = data.analysis || data.description || data.text || "Visual cognitive scan complete.";
  const confidence = data.confidence ? `${Math.round(data.confidence * 100)}%` : "95%";
  const detected: any[] = Array.isArray(data.detected_objects) ? data.detected_objects : (Array.isArray(data.objects) ? data.objects : []);
  const imageUrl = data.image_url || data.preview_url || null;

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.visionSensorPill}>
          <Text style={styles.visionSensorText}>{source}</Text>
        </View>
        <View style={styles.visionConfidencePill}>
          <Text style={styles.visionConfidenceText}>{confidence} CONFIDENCE</Text>
        </View>
      </View>

      {Boolean(imageUrl) && (
        <View style={styles.visionImageWrapper}>
          <Image source={{ uri: imageUrl }} style={styles.visionImageThumb} resizeMode="cover" />
        </View>
      )}

      <View style={styles.readingWell}>
        <Text style={styles.readingWellText}>{analysis}</Text>
      </View>

      {detected.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>DETECTED ENTITIES ({detected.length})</Text>
          <View style={styles.sourcesChipRow}>
            {detected.map((obj: any, idx: number) => {
              const objName = typeof obj === "string" ? obj : obj.name || obj.label;
              return (
                <View key={idx} style={styles.sourceChip}>
                  <Text style={styles.sourceChipText}>{objName}</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}
    </View>
  );
};

// ── 17. OCR Optical Transcription Renderer ──────────────────────────────────
const OcrTranscriptionRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const text = data.extracted_text || data.text || data.transcription || "";
  const lineCount = data.line_count || (text ? text.split("\n").length : 0);
  const confidence = data.confidence ? `${Math.round(data.confidence * 100)}%` : null;

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.ocrLinesPill}>
          <Text style={styles.ocrLinesText}>{lineCount} LINES DETECTED</Text>
        </View>
        {Boolean(confidence) && (
          <View style={styles.visionConfidencePill}>
            <Text style={styles.visionConfidenceText}>{confidence} CONFIDENCE</Text>
          </View>
        )}
      </View>

      <View style={styles.ocrConsoleWell}>
        <Text selectable={true} style={styles.ocrConsoleText}>{text || "// No text detected in optical scan"}</Text>
      </View>
    </View>
  );
};

// ── 18. Cognitive Memory & Synapse Vault Renderer ───────────────────────────
const MemoryRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const action = (data.action || data.operation || "SYNAPSE STORED").toUpperCase();
  const category = (data.category || data.type || "EPISODIC KNOWLEDGE").toUpperCase();
  const fact = data.fact || data.distilled_knowledge || data.content || data.memory || "Synaptic association indexed.";
  const relevance = data.relevance_score ? `${Math.round(data.relevance_score * 100)}%` : null;

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.emeraldStatusPill}>
          <Text style={styles.emeraldStatusText}>{action}</Text>
        </View>
        <View style={styles.memoryCategoryPill}>
          <Text style={styles.memoryCategoryText}>{category}</Text>
        </View>
      </View>

      <View style={styles.memoryFactWell}>
        <Text style={styles.memoryFactText}>{fact}</Text>
      </View>

      {Boolean(relevance) && (
        <View style={styles.memoryMetaRow}>
          <Text style={styles.memoryMetaLabel}>RELEVANCE ACCURACY</Text>
          <Text style={styles.memoryMetaValue}>{relevance}</Text>
        </View>
      )}
    </View>
  );
};

// ── 19. Host Process Monitor Renderer ───────────────────────────────────────
const ProcessListRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const procs: any[] = Array.isArray(data.processes) ? data.processes : [];
  const sortBy = (data.sort_by || "CPU LOAD").toUpperCase();

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.processSortPill}>
          <Text style={styles.processSortText}>SORTED BY {sortBy}</Text>
        </View>
      </View>

      <View style={styles.processTableCol}>
        {procs.slice(0, 6).map((p: any, idx: number) => {
          const pid = p.pid || p.id || String(idx + 1);
          const name = p.name || p.process_name || "process";
          const cpu = Number(p.cpu_percent ?? p.cpu ?? 0);
          const mem = p.memory_mb !== undefined ? `${p.memory_mb}MB` : (p.mem ? `${p.mem}%` : "--");

          return (
            <View key={pid} style={styles.processItemRow}>
              <View style={styles.processLeftCol}>
                <Text style={styles.processPidText}>{pid}</Text>
                <Text style={styles.processNameText} numberOfLines={1}>{name}</Text>
              </View>
              <View style={styles.processRightCol}>
                <View style={styles.processBarTrack}>
                  <View style={[styles.processBarFill, { width: `${Math.min(100, Math.max(5, cpu))}%` }]} />
                </View>
                <Text style={styles.processCpuText}>{cpu}%</Text>
                <Text style={styles.processMemText}>{mem}</Text>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
};

// ── 20. Hardware Peripheral Control Renderer ────────────────────────────────
const HardwareControlRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const volume = data.volume;
  const isMuted = Boolean(data.muted);
  const displayPower = data.display_power || data.display || data.state;
  const devices: any[] = Array.isArray(data.devices) ? data.devices : [];

  return (
    <View style={styles.cardDetailCol}>
      {volume !== undefined && (
        <View style={styles.hardwareControlCard}>
          <View style={styles.hardwareHeaderRow}>
            <Text style={styles.metricWellLabel}>MASTER AUDIO GAIN</Text>
            <Text style={styles.metricWellValue}>{isMuted ? "MUTED" : `${volume}%`}</Text>
          </View>
          <View style={styles.barTrack}>
            <View style={[styles.barFill, { width: `${isMuted ? 0 : volume}%` }]} />
          </View>
        </View>
      )}

      {Boolean(displayPower) && (
        <View style={styles.hardwareControlCard}>
          <View style={styles.hardwareHeaderRow}>
            <Text style={styles.metricWellLabel}>PRIMARY DISPLAY POWER</Text>
            <Text style={styles.metricWellValue}>{String(displayPower).toUpperCase()}</Text>
          </View>
        </View>
      )}

      {devices.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>CONNECTED PERIPHERALS</Text>
          {devices.map((d: any, idx: number) => (
            <View key={idx} style={styles.hardwareDeviceRow}>
              <Text style={styles.hardwareDeviceName}>{d.name || d.device_name || "Peripheral"}</Text>
              <Text style={styles.hardwareDeviceStatus}>{d.status || (d.battery ? `${d.battery}% BATTERY` : "ONLINE")}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
};

// ── 21. Specialist Tool Call Execution Trace Renderer ───────────────────────
const ToolCallRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const toolName = data.tool_name || data.tool || data.name || "specialist_invocation";
  const specialist = (data.specialist || data.agent || "COGNITIVE SPECIALIST").toUpperCase();
  const duration = data.duration_ms !== undefined ? `${data.duration_ms}MS` : (data.duration ? `${data.duration}MS` : "<15MS");
  const status = (data.status || "SUCCESS").toUpperCase();
  const isSuccess = status === "SUCCESS";
  const args = data.args || data.arguments || data.params;
  const result = data.result_summary || data.result || data.output;

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.toolSpecialistPill}>
          <Text style={styles.toolSpecialistText}>{specialist}</Text>
        </View>
        <View style={styles.toolDurationPill}>
          <Text style={styles.toolDurationText}>{duration}</Text>
        </View>
        <View style={[styles.toolStatusPill, isSuccess ? styles.statePillOpen : styles.statePillClosed]}>
          <Text style={[styles.toolStatusText, isSuccess ? styles.stateTextOpen : styles.stateTextClosed]}>{status}</Text>
        </View>
      </View>

      <View style={styles.toolSignatureBox}>
        <Text style={styles.toolSignatureText}>{toolName}</Text>
      </View>

      {args && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>EXECUTION PARAMETERS</Text>
          <View style={styles.toolParamsWell}>
            <Text selectable={true} style={styles.codeText}>
              {typeof args === "object" ? JSON.stringify(args, null, 2) : String(args)}
            </Text>
          </View>
        </View>
      )}

      {Boolean(result) && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>RETURN TELEMETRY</Text>
          <View style={styles.readingWell}>
            <Text style={styles.readingWellText}>
              {typeof result === "object" ? JSON.stringify(result, null, 2) : String(result)}
            </Text>
          </View>
        </View>
      )}
    </View>
  );
};

// ── 22. Autonomous Web Crawler Dossier Renderer ─────────────────────────────
const CrawlSummaryRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const title = data.title || "Web Crawl Dossier";
  const url = data.url || data.link || "";
  const domain = url ? url.replace(/https?:\/\//, "").split("/")[0].toUpperCase() : "WEB SENTRY";
  const readTime = data.reading_time_min ? `${data.reading_time_min} MIN READ` : null;
  const bullets: string[] = Array.isArray(data.summary_bullets)
    ? data.summary_bullets
    : Array.isArray(data.bullets)
    ? data.bullets
    : (data.summary ? [data.summary] : []);

  const handleOpenUrl = () => {
    if (url) Linking.openURL(url).catch(() => {});
  };

  return (
    <View style={styles.cardDetailCol}>
      <View style={styles.tagPillRow}>
        <View style={styles.crawlDomainPill}>
          <Text style={styles.crawlDomainText}>{domain}</Text>
        </View>
        {Boolean(readTime) && (
          <View style={styles.unreadCountPill}>
            <Text style={styles.unreadCountText}>{readTime}</Text>
          </View>
        )}
      </View>

      <Text style={styles.crawlTitleText}>{title}</Text>

      {bullets.length > 0 && (
        <View style={styles.crawlBulletList}>
          {bullets.map((b, idx) => (
            <View key={idx} style={styles.crawlBulletItem}>
              <View style={styles.crawlBulletDot} />
              <Text style={styles.crawlBulletText}>{b}</Text>
            </View>
          ))}
        </View>
      )}

      {Boolean(url) && (
        <TouchableOpacity style={styles.crawlLinkBtn} onPress={handleOpenUrl} activeOpacity={0.7}>
          <Text style={styles.crawlLinkBtnText}>OPEN TARGET WEBPAGE</Text>
        </TouchableOpacity>
      )}
    </View>
  );
};

// ── 23. Interactive Recipe & Culinary Plan Renderer ─────────────────────────
const RecipeRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const recipeObj = data.recipe || data;
  const title = data.title || recipeObj.title || data.recipe_name || data.query || "Culinary Plan";
  const prepTime = data.prep_time || recipeObj.prep_time || data.time;
  const cookTime = data.cook_time || recipeObj.cook_time;
  const servings = data.servings || recipeObj.servings || data.portions;
  const rawIngredients: any[] = Array.isArray(data.ingredients)
    ? data.ingredients
    : (Array.isArray(recipeObj.ingredients) ? recipeObj.ingredients : []);
  const rawSteps: any[] = Array.isArray(data.steps)
    ? data.steps
    : (Array.isArray(recipeObj.steps) ? recipeObj.steps : (Array.isArray(data.instructions) ? data.instructions : []));
  const sourceUrl = data.source_url || recipeObj.source_url || data.top_url || "";
  const sourceTitle = data.source_title || recipeObj.source_title || "";
  const sources: any[] = Array.isArray(data.sources)
    ? data.sources
    : (Array.isArray(recipeObj.sources) ? recipeObj.sources : (sourceUrl ? [{ url: sourceUrl, title: sourceTitle || sourceUrl }] : []));
  const [checkedIngredients, setCheckedIngredients] = useState<Record<number, boolean>>({});

  const toggleIngredient = (idx: number) => {
    setCheckedIngredients((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <View style={styles.cardDetailCol}>
      <Text style={styles.recipeTitleHeading}>{title}</Text>

      <View style={styles.metricsGrid}>
        {Boolean(prepTime) && (
          <View style={styles.metricWell}>
            <Text style={styles.metricWellLabel}>PREP</Text>
            <Text style={styles.metricWellValue}>{String(prepTime)}</Text>
          </View>
        )}
        {Boolean(cookTime) && (
          <View style={styles.metricWell}>
            <Text style={styles.metricWellLabel}>COOK</Text>
            <Text style={styles.metricWellValue}>{String(cookTime)}</Text>
          </View>
        )}
        {Boolean(servings) && (
          <View style={styles.metricWell}>
            <Text style={styles.metricWellLabel}>PORTIONS</Text>
            <Text style={styles.metricWellValue}>{String(servings)}</Text>
          </View>
        )}
      </View>

      {/* Interactive Ingredients Checklist */}
      {rawIngredients.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>
            INGREDIENTS CHECKLIST ({Object.values(checkedIngredients).filter(Boolean).length}/{rawIngredients.length})
          </Text>
          <View style={styles.recipeChecklistCol}>
            {rawIngredients.map((item: any, idx: number) => {
              const isChecked = Boolean(checkedIngredients[idx]);
              const itemText = typeof item === "string" ? item : `${item.amount || ""} ${item.unit || ""} ${item.name || item.item || ""}`.trim();
              return (
                <TouchableOpacity
                  key={idx}
                  style={styles.recipeChecklistItem}
                  onPress={() => toggleIngredient(idx)}
                  activeOpacity={0.7}
                >
                  <View style={[styles.recipeCheckCircle, isChecked && styles.recipeCheckCircleActive]}>
                    {isChecked && <Text style={styles.recipeCheckGlyph}>✓</Text>}
                  </View>
                  <Text style={[styles.recipeItemText, isChecked && styles.recipeItemTextChecked]}>
                    {itemText}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      )}

      {/* Preparation Steps */}
      {rawSteps.length > 0 && (
        <View style={styles.sectionCol}>
          <Text style={styles.sectionHeaderLabel}>PREPARATION STEPS ({rawSteps.length})</Text>
          <View style={styles.recipeStepsCol}>
            {rawSteps.map((step: any, idx: number) => {
              const stepText = typeof step === "string" ? step : (step.step || step.instruction || JSON.stringify(step));
              const numStr = idx < 9 ? `0${idx + 1}` : `${idx + 1}`;
              return (
                <View key={idx} style={styles.recipeStepRow}>
                  <View style={styles.recipeStepNumBadge}>
                    <Text style={styles.recipeStepNumText}>{numStr}</Text>
                  </View>
                  <Text style={styles.recipeStepBodyText}>{stepText}</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Source Attribution */}
      {sources.length > 0 && (
        <View style={[styles.sourcesBlock, { marginTop: 14 }]}>
          <Text style={styles.sectionHeaderLabel}>SOURCE</Text>
          <View style={styles.sourcesChipRow}>
            {sources.slice(0, 3).map((src: any, idx: number) => {
              const link = typeof src === "string" ? src : src.url || src.link;
              const srcTitle = typeof src === "string" ? src : src.title || src.name || link;
              return (
                <TouchableOpacity
                  key={idx}
                  style={styles.sourceChip}
                  onPress={() => link && Linking.openURL(link).catch(() => {})}
                >
                  <Text style={styles.sourceChipText} numberOfLines={1}>{srcTitle}</Text>
                  <Text style={styles.sourceChipGlyph}>↗</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      )}
    </View>
  );
};

// ── 24. Aerospace Structured Telemetry Inspector (Universal Fallback) ───────
const TelemetryInspectorRenderer: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const metaKeys = ["id", "type", "title", "subtitle", "timestamp", "intent"];
  const rawKeys = Object.keys(data).filter((k) => !metaKeys.includes(k));

  return (
    <View style={styles.cardDetailCol}>
      {rawKeys.length > 0 ? (
        <View style={styles.inspectorGrid}>
          {rawKeys.map((key) => {
            const val = data[key];
            const isPrimitive = typeof val !== "object" || val === null;

            if (isPrimitive) {
              return (
                <View key={key} style={styles.inspectorSpecRow}>
                  <Text style={styles.inspectorSpecKey}>{key.replace(/_/g, " ").toUpperCase()}</Text>
                  <Text style={styles.inspectorSpecVal} numberOfLines={2}>{String(val)}</Text>
                </View>
              );
            }

            if (Array.isArray(val)) {
              return (
                <View key={key} style={styles.inspectorArrayBox}>
                  <Text style={styles.inspectorSpecKey}>{key.replace(/_/g, " ").toUpperCase()} ({val.length})</Text>
                  <View style={styles.sourcesChipRow}>
                    {val.slice(0, 8).map((item, idx) => (
                      <View key={idx} style={styles.sourceChip}>
                        <Text style={styles.sourceChipText} numberOfLines={1}>
                          {typeof item === "object" ? (item.name || item.title || item.id || `Item ${idx + 1}`) : String(item)}
                        </Text>
                      </View>
                    ))}
                  </View>
                </View>
              );
            }

            // Sub-object card
            return (
              <View key={key} style={styles.inspectorSubCard}>
                <Text style={styles.inspectorSpecKey}>{key.replace(/_/g, " ").toUpperCase()}</Text>
                <View style={styles.inspectorSubCardInner}>
                  {Object.keys(val).slice(0, 6).map((subKey) => (
                    <View key={subKey} style={styles.inspectorSubRow}>
                      <Text style={styles.inspectorSubKey}>{subKey}:</Text>
                      <Text style={styles.inspectorSubVal} numberOfLines={1}>
                        {typeof val[subKey] === "object" ? "[Object]" : String(val[subKey])}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            );
          })}
        </View>
      ) : (
        <View style={styles.readingWell}>
          <Text style={styles.readingWellText}>Operational specialist telemetry captured without parameters.</Text>
        </View>
      )}
    </View>
  );
};

// ── Main HudDrawerModal Component ───────────────────────────────────────────
export const HudDrawerModal: React.FC<HudDrawerModalProps> = ({
  visible,
  cards,
  onClose,
  onDismissCard,
  onDismissAll,
}) => {
  const slideAnim = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
  const backdropAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(slideAnim, {
          toValue: 0,
          tension: 65,
          friction: 11,
          useNativeDriver: true,
        }),
        Animated.timing(backdropAnim, {
          toValue: 1,
          duration: 220,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: SCREEN_HEIGHT,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(backdropAnim, {
          toValue: 0,
          duration: 180,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible]);

  if (!visible && cards.length === 0) {
    return null;
  }

  const primaryCard = cards[0];
  const primaryType = (primaryCard?.type || "").toLowerCase();

  let deckTitle = "HUD INTELLIGENCE DECK";
  let deckSubtitle = "Cognitive specialist output & structured execution parameters";

  if (primaryType === "weather") {
    deckTitle = "ATMOSPHERIC INTELLIGENCE";
    deckSubtitle = "Local weather sentry & forecast radar telemetry";
  } else if (primaryType.includes("bill") || primaryType.includes("debt") || primaryType.includes("goal") || primaryType === "transaction" || primaryType === "finance" || primaryType === "ledger") {
    deckTitle = "FINANCIAL LEDGER & ACCOUNTS";
    deckSubtitle = "Liquid accounts balance, bill splits & settlement parameters";
  } else if (primaryType === "task" || primaryType === "agenda" || primaryType === "todo" || primaryType.includes("task")) {
    deckTitle = "OPERATIONAL DIRECTIVES";
    deckSubtitle = "Active task queue & prioritized schedules";
  } else if (primaryType === "calendar" || primaryType === "event" || primaryType.includes("calendar")) {
    deckTitle = "SYNCHRONIZED CALENDAR";
    deckSubtitle = "Google Calendar appointments & agenda timeline";
  } else if (primaryType === "recipe_card" || primaryType === "recipe") {
    deckTitle = "CULINARY DIRECTIVE";
    deckSubtitle = "Recipe parameters, ingredients checklist & preparation steps";
  } else if (primaryType === "research" || primaryType === "briefing" || primaryType === "research_card") {
    deckTitle = "RESEARCH SYNTHESIS";
    deckSubtitle = "Aggregated intelligence & verified briefing notes";
  } else if (primaryType === "youtube" || primaryType === "video" || primaryType.includes("video")) {
    deckTitle = "YOUTUBE MEDIA RUNTIME";
    deckSubtitle = "Connected video streaming & media playback telemetry";
  } else if (primaryType === "spotify" || primaryType === "media" || primaryType === "spotify_playlist") {
    deckTitle = "MEDIA & SOUNDSCAPE";
    deckSubtitle = "Connected Spotify audio & acoustic backdrop";
  } else if (primaryType.startsWith("email") || primaryType === "inbox" || primaryType === "draft") {
    deckTitle = "COMMUNICATIONS & INBOX";
    deckSubtitle = "Synchronized email correspondence & draft parameters";
  } else if (primaryType.startsWith("github") || primaryType.includes("repo") || primaryType.includes("commit")) {
    deckTitle = "GITHUB DEV ENGINE";
    deckSubtitle = "Repositories, pull requests, issues & source telemetry";
  } else if (primaryType.startsWith("vision") || primaryType.startsWith("ocr")) {
    deckTitle = "OPTICAL SENSORY RUNTIME";
    deckSubtitle = "Camera feed analysis, OCR & spatial perception";
  } else if (primaryType.startsWith("memory") || primaryType.includes("recall")) {
    deckTitle = "NEURAL MEMORY VAULT";
    deckSubtitle = "Associative synaptic recall & persistent factual context";
  } else if (primaryType.startsWith("crawl") || primaryType.includes("scrape")) {
    deckTitle = "AUTONOMOUS WEB CRAWLER";
    deckSubtitle = "Target site synthesis & extracted article intelligence";
  } else if (primaryType === "recipe" || primaryType.includes("culinary")) {
    deckTitle = "CULINARY DIRECTIVE";
    deckSubtitle = "Recipe parameters, ingredients checklist & preparation steps";
  } else if (primaryType === "tool_call" || primaryType.includes("telemetry") || primaryType.includes("tool")) {
    deckTitle = "SPECIALIST DISPATCH TRACE";
    deckSubtitle = "Deterministic tool execution logs & parameter returns";
  } else if (primaryType === "system_status" || primaryType.includes("process") || primaryType.includes("hardware") || primaryType.includes("volume") || primaryType.includes("telemetry")) {
    deckTitle = "SYSTEM VITALS & CONTROL";
    deckSubtitle = "Host cluster telemetry, processes & runtime telemetry";
  } else if (primaryCard?.title) {
    deckTitle = primaryCard.title.toUpperCase();
  }

  const renderCardContent = (card: HudCardData) => {
    const type = (card.type || "").toLowerCase();
    const cData = card.data || card;

    // 1. Weather
    if (type === "weather") return <WeatherRenderer data={cData} />;

    // 2. YouTube & Video
    if (type === "youtube" || type === "video" || type.includes("video")) return <YoutubeRenderer data={cData} />;

    // 3. Spotify & Media
    if (type === "spotify" || type === "media" || type === "spotify_playlist") return <SpotifyRenderer data={cData} />;

    // 4. Finance Suite
    if (type === "bill_split" || type === "bill_split_card") return <BillSplitRenderer data={cData} />;
    if (type === "debt_summary" || type === "debt_list_card" || type === "debt_settled_card" || type === "person_tab_card" || type === "debt") return <DebtSummaryRenderer data={cData} />;
    if (type === "financial_goal_card" || type === "financial_goal_list_card" || type === "financial_goals" || type === "savings") return <FinancialGoalsRenderer data={cData} />;
    if (type === "transaction" || type === "finance" || type === "ledger" || type.includes("finance") || type.includes("transaction")) return <TransactionRenderer data={cData} />;

    // 5. Tasks & Agenda
    if (type === "task" || type === "agenda" || type === "todo" || type.includes("task")) return <TaskRenderer data={cData} />;

    // 6. Calendar
    if (type === "calendar" || type === "event" || type.includes("calendar")) return <CalendarRenderer data={cData} />;

    // 7. Recipe Card
    if (type === "recipe_card" || type === "recipe") return <RecipeRenderer data={cData} />;

    // 7b. Research & Briefing
    if (type === "research" || type === "briefing" || type === "research_card") return <BriefingRenderer data={cData} />;

    // 8. Email Suite
    if (type === "email_list_card" || type === "email_list" || type === "inbox") return <EmailListRenderer data={cData} />;
    if (type === "email_thread_card" || type === "email_thread") return <EmailThreadRenderer data={cData} />;
    if (type === "email_draft_card" || type === "email_draft" || type === "draft" || type === "email_sent_card") return <EmailDraftRenderer data={cData} />;
    if (type === "email" || type === "email_card") return <EmailRenderer data={cData} />;

    // 9. GitHub Suite
    if (type.startsWith("github") || type.includes("repo") || type.includes("commit") || type.includes("pull_request") || type.includes("issue")) {
      return <GithubRenderer data={cData} />;
    }

    // 10. Optical Sensory Suite (Vision & OCR)
    if (type === "vision_analysis" || type === "vision_analysis_card" || type === "vision_card" || type === "vision_perception" || type === "vision") {
      return <VisionAnalysisRenderer data={cData} />;
    }
    if (type === "ocr_transcription" || type === "ocr_transcription_card" || type === "ocr") {
      return <OcrTranscriptionRenderer data={cData} />;
    }

    // 11. Cognitive Memory Suite
    if (type.startsWith("memory") || type === "memory_fact_card" || type === "memory_card" || type === "memory_list_card" || type.includes("recall")) {
      return <MemoryRenderer data={cData} />;
    }

    // 12. Host Processes & Hardware Control
    if (type === "top_processes_card" || type === "process_list" || type === "process_query_card") {
      return <ProcessListRenderer data={cData} />;
    }
    if (type === "volume_card" || type === "mute_card" || type === "power_card" || type === "display_card" || type === "device_state_card" || type === "hardware_control") {
      return <HardwareControlRenderer data={cData} />;
    }
    if (type === "system_status" || type === "system_vitals" || type === "system_vitals_card" || type === "telemetry") {
      return <SystemStatusRenderer data={cData} />;
    }

    // 13. Autonomous Web Crawler & Culinary
    if (type.startsWith("crawl") || type === "quick_scrape_card" || type === "web_crawl") {
      return <CrawlSummaryRenderer data={cData} />;
    }
    if (type === "recipe" || type === "recipe_card" || type === "culinary_plan") {
      return <RecipeRenderer data={cData} />;
    }

    // 14. Specialist Tool Execution Trace
    if (type === "tool_call" || type === "tool_execution_card" || type === "execution_telemetry") {
      return <ToolCallRenderer data={cData} />;
    }

    // 15. Aerospace Structured Telemetry Inspector (Universal fallback)
    return <TelemetryInspectorRenderer data={cData} />;
  };

  return (
    <Modal
      transparent
      visible={visible}
      animationType="none"
      onRequestClose={onClose}
    >
      <TouchableWithoutFeedback onPress={onClose}>
        <Animated.View
          style={[styles.backdrop, { opacity: backdropAnim }]}
        />
      </TouchableWithoutFeedback>

      <Animated.View
        style={[
          styles.sheetContainer,
          { transform: [{ translateY: slideAnim }] },
        ]}
      >
        {/* Handle Bar */}
        <View style={styles.handleBarWrapper}>
          <View style={styles.handleBar} />
        </View>

        {/* Header Strip */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <View style={styles.titleRow}>
              <Text style={styles.headerTitle}>{deckTitle}</Text>
              {cards.length > 1 && (
                <View style={styles.countBadge}>
                  <Text style={styles.countBadgeText}>+{cards.length - 1} MORE</Text>
                </View>
              )}
            </View>
            <Text style={styles.headerSubtitle}>{deckSubtitle}</Text>
          </View>

          <View style={styles.headerActions}>
            {cards.length > 0 && (
              <TouchableOpacity
                style={styles.dismissAllButton}
                onPress={onDismissAll}
                activeOpacity={0.7}
              >
                <Text style={styles.dismissAllText}>CLEAR</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={styles.closeButton}
              onPress={onClose}
              activeOpacity={0.7}
            >
              <Text style={styles.closeGlyph}>✕</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Scrollable Cards Deck */}
        <ScrollView
          style={styles.cardList}
          contentContainerStyle={styles.cardListContent}
          showsVerticalScrollIndicator={false}
        >
          {cards.length === 0 ? (
            <View style={styles.emptyContainer}>
              <View style={styles.emptyRadarDot} />
              <Text style={styles.emptyLabel}>NO ACTIVE HUD CARDS</Text>
              <Text style={styles.emptySubtitle}>
                Directives with structured specialist returns will project here.
              </Text>
            </View>
          ) : (
            cards.map((card, idx) => {
              const cardType = (card.type || "SPECIALIST").toUpperCase();
              const cardTitle = card.title || cardType;

              return (
                <View key={card.id || `hud_${idx}`} style={styles.hudCard}>
                  {/* Card Header Strip */}
                  <View style={styles.hudCardHeader}>
                    <View style={styles.hudCardHeaderLeft}>
                      <View style={styles.typeTagPill}>
                        <Text style={styles.typeTagText}>{cardType}</Text>
                      </View>
                      <Text style={styles.hudCardHeading} numberOfLines={1}>
                        {cardTitle}
                      </Text>
                    </View>

                    <View style={styles.hudCardHeaderRight}>
                      <Text style={styles.cardTimeText}>{timeAgo(card.timestamp)}</Text>
                      <TouchableOpacity
                        style={styles.cardDismissBtn}
                        onPress={() => onDismissCard(card.id)}
                        activeOpacity={0.7}
                      >
                        <Text style={styles.cardDismissGlyph}>✕</Text>
                      </TouchableOpacity>
                    </View>
                  </View>

                  {/* Render High-Density Specialist Body */}
                  {renderCardContent(card)}
                </View>
              );
            })
          )}
        </ScrollView>
      </Animated.View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    ...(StyleSheet.absoluteFill as any),
    backgroundColor: "rgba(0, 0, 0, 0.72)",
  },
  sheetContainer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    maxHeight: SCREEN_HEIGHT * 0.88,
    backgroundColor: "#111111",
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.10)",
    paddingBottom: 28,
  },
  handleBarWrapper: {
    width: "100%",
    alignItems: "center",
    paddingTop: 10,
    paddingBottom: 6,
  },
  handleBar: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255, 255, 255, 0.22)",
  },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.06)",
  },
  headerLeft: {
    flex: 1,
    marginRight: 12,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  headerTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 1.1,
  },
  countBadge: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  countBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  headerSubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 3,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  dismissAllButton: {
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 6,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  dismissAllText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    fontWeight: "600",
    letterSpacing: 0.8,
  },
  closeButton: {
    width: 28,
    height: 28,
    borderRadius: 6,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  closeGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  cardList: {
    maxHeight: SCREEN_HEIGHT * 0.74,
  },
  cardListContent: {
    padding: 16,
    gap: 14,
  },
  emptyContainer: {
    paddingVertical: 52,
    paddingHorizontal: 24,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 18,
    backgroundColor: "#161616",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    marginVertical: 12,
  },
  emptyRadarDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: "rgba(255, 255, 255, 0.3)",
    marginBottom: 14,
  },
  emptyLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 1.2,
    marginBottom: 6,
  },
  emptySubtitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: "center",
    lineHeight: 18,
    maxWidth: 280,
  },

  // ── Double-Bezel Card Outer Shell ──
  hudCard: {
    backgroundColor: "#161616",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 16,
    gap: 12,
  },
  hudCardHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.05)",
    paddingBottom: 10,
  },
  hudCardHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flex: 1,
    marginRight: 10,
  },
  typeTagPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  typeTagText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
  },
  hudCardHeading: {
    fontFamily: theme.fonts.sans,
    fontSize: 13.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    flex: 1,
  },
  hudCardHeaderRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  cardTimeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  cardDismissBtn: {
    width: 22,
    height: 22,
    borderRadius: 5,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    alignItems: "center",
    justifyContent: "center",
  },
  cardDismissGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  cardDetailCol: {
    gap: 12,
  },

  // ── Weather Specific Styles ──
  weatherHeroBlock: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
  },
  weatherLeftCol: {
    gap: 2,
  },
  tempRow: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  weatherGiantTemp: {
    fontFamily: theme.fonts.mono,
    fontSize: 48,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: -1,
  },
  weatherDegreeSymbol: {
    fontFamily: theme.fonts.mono,
    fontSize: 26,
    color: theme.colors.textMuted,
    marginTop: 4,
    marginLeft: 2,
  },
  weatherConditionText: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.8,
  },
  weatherLocationText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  weatherRadarPill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    backgroundColor: "rgba(16, 185, 129, 0.10)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    gap: 5,
  },
  pulseEmeraldDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.emerald,
  },
  weatherRadarText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.6,
  },
  metricsGrid: {
    flexDirection: "row",
    gap: 8,
  },
  metricWell: {
    flex: 1,
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 3,
  },
  metricWellLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  metricWellValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  forecastSection: {
    gap: 6,
    paddingTop: 4,
  },
  sectionHeaderLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  forecastRow: {
    flexDirection: "row",
    gap: 6,
  },
  forecastWell: {
    flex: 1,
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingVertical: 8,
    paddingHorizontal: 4,
    alignItems: "center",
    gap: 3,
  },
  forecastDayText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    fontWeight: "700",
  },
  forecastCondText: {
    fontFamily: theme.fonts.sans,
    fontSize: 9,
    color: theme.colors.textSecondary,
  },
  forecastTempText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },

  // ── Spotify Specific Styles ──
  spotifyTrackRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  spotifyAlbumArtBox: {
    width: 60,
    height: 60,
    borderRadius: 12,
    backgroundColor: "#1C1C1C",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.10)",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  spotifyVinylCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 2,
    borderColor: "rgba(255, 255, 255, 0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  spotifyVinylHole: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: "#161616",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.3)",
  },
  pulseEqBars: {
    position: "absolute",
    bottom: 5,
    right: 5,
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 2,
    backgroundColor: "rgba(0,0,0,0.6)",
    paddingHorizontal: 3,
    paddingVertical: 2,
    borderRadius: 3,
  },
  eqBar: {
    width: 2,
    backgroundColor: theme.colors.emerald,
    borderRadius: 1,
  },
  eqBar1: { height: 8 },
  eqBar2: { height: 12 },
  eqBar3: { height: 6 },
  spotifyMetaCol: {
    flex: 1,
    gap: 2,
  },
  spotifyStatusBadge: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(16, 185, 129, 0.10)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.25)",
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
    marginBottom: 2,
  },
  spotifyStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  spotifyTrackTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  spotifyArtistText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  spotifyAlbumText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  spotifyControlsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  spotifyControlGroup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#1C1C1C",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  spotifyCtrlBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  spotifyCtrlBtnActive: {
    backgroundColor: "rgba(255, 255, 255, 0.12)",
  },
  spotifyCtrlGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
  },
  spotifyCtrlGlyphActive: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  spotifyOpenBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.28)",
  },
  spotifyOpenText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#A7F3D0",
    fontWeight: "700",
    letterSpacing: 0.6,
  },
  spotifyAlbumCoverImage: {
    width: "100%",
    height: "100%",
    borderRadius: 11,
  },

  // ── YouTube Video HUD Styles ──
  ytThumbContainer: {
    width: "100%",
    height: 180,
    borderRadius: 14,
    overflow: "hidden",
    backgroundColor: "#161616",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    position: "relative",
    justifyContent: "center",
    alignItems: "center",
  },
  ytThumbImage: {
    width: "100%",
    height: "100%",
  },
  ytPlayOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0, 0, 0, 0.35)",
    alignItems: "center",
    justifyContent: "center",
  },
  ytPlayCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "rgba(239, 68, 68, 0.90)",
    borderWidth: 1.5,
    borderColor: "rgba(255, 255, 255, 0.3)",
    alignItems: "center",
    justifyContent: "center",
  },
  ytPlayGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: "#FFFFFF",
    fontWeight: "700",
    marginLeft: 2,
  },
  ytDurationBadge: {
    position: "absolute",
    bottom: 8,
    right: 8,
    backgroundColor: "rgba(0, 0, 0, 0.85)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  ytDurationText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  ytMetaBlock: {
    gap: 6,
    paddingTop: 4,
  },
  ytTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 14.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    lineHeight: 20,
  },
  ytChannelRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  ytVerifiedDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: theme.colors.coral,
  },
  ytChannelText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    fontWeight: "600",
  },
  ytDotSeparator: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  ytViewsText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  ytSnippetText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11.5,
    color: theme.colors.textMuted,
    lineHeight: 16,
  },
  ytActionRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.05)",
    gap: 8,
  },
  ytAppLaunchBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(239, 68, 68, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(239, 68, 68, 0.35)",
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  ytRedBadge: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: "#EF4444",
    alignItems: "center",
    justifyContent: "center",
  },
  ytRedBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#FFFFFF",
    fontWeight: "700",
  },
  ytAppLaunchText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    fontWeight: "700",
    color: "#FCA5A5",
    letterSpacing: 0.5,
  },
  ytWebLinkBtn: {
    paddingVertical: 7,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: "#1C1C1C",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  ytWebLinkText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textSecondary,
    fontWeight: "600",
  },

  // ── Finance & Ledger Styles ──
  doubleBezelWell: {
    backgroundColor: "#1C1C1C",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 14,
    gap: 6,
  },
  wellTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  wellLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  giantCurrencyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 26,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.3,
  },
  emeraldStatusPill: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.28)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  emeraldStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  categoryPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 4,
  },
  categoryPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textSecondary,
    fontWeight: "600",
  },
  accountsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  accountCard: {
    width: "48%",
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 3,
  },
  accountTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  accountName: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    flex: 1,
  },
  accountType: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
  },
  accountBalance: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  txnsListBlock: {
    gap: 6,
    paddingTop: 4,
  },
  txnItemRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  txnDescText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11.5,
    color: theme.colors.textSecondary,
    flex: 1,
    marginRight: 8,
  },
  txnAmountText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11.5,
    fontWeight: "700",
  },
  amountExpense: {
    color: "#FCA5A5",
  },
  amountIncome: {
    color: "#A7F3D0",
  },
  keyValTable: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 8,
  },
  tableRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  tableRowHighlight: {
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.04)",
  },
  tableKey: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
  },
  tableVal: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    maxWidth: "65%",
    textAlign: "right",
  },
  tableValEmerald: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.emerald,
  },

  // ── Tasks & Agenda Styles ──
  tasksHeaderStrip: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  metaCounterText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  tasksList: {
    gap: 8,
  },
  taskItemCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 12,
    gap: 8,
  },
  taskItemDone: {
    opacity: 0.5,
  },
  taskCheckRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  checkboxWell: {
    width: 18,
    height: 18,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.25)",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255, 255, 255, 0.04)",
  },
  checkboxWellDone: {
    backgroundColor: "rgba(16, 185, 129, 0.2)",
    borderColor: theme.colors.emerald,
  },
  checkboxCheckGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.emerald,
    fontWeight: "700",
  },
  taskTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.boneWhite,
    flex: 1,
  },
  taskTitleDone: {
    textDecorationLine: "line-through",
    color: theme.colors.textMuted,
  },
  taskMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingLeft: 28,
  },
  priorityPill: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.10)",
  },
  priorityUrgent: {
    backgroundColor: "rgba(239, 68, 68, 0.15)",
    borderColor: "rgba(239, 68, 68, 0.35)",
  },
  priorityHigh: {
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    borderColor: "rgba(245, 158, 11, 0.35)",
  },
  priorityText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.textMuted,
  },
  priorityTextUrgent: {
    color: "#FCA5A5",
  },
  priorityTextHigh: {
    color: "#FCD34D",
  },
  taskDeadlineText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },

  // ── Calendar Styles ──
  eventsList: {
    gap: 8,
  },
  eventItemCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 12,
    gap: 4,
  },
  eventMainRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  eventTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    flex: 1,
  },
  eventTimePill: {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
  eventTimeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textSecondary,
  },
  eventLocationText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  emptyCardWell: {
    padding: 16,
    borderRadius: 10,
    backgroundColor: "#1C1C1C",
    alignItems: "center",
  },
  emptyCardWellText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },

  // ── Reading / Briefing / Email Styles ──
  tagPillRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  queryPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  queryPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  playlistPill: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.28)",
  },
  playlistPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: "#A7F3D0",
  },
  readingWell: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 12,
  },
  readingWellText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    color: theme.colors.textSecondary,
    lineHeight: 18,
  },
  overdueBlock: {
    backgroundColor: "rgba(239, 68, 68, 0.08)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(239, 68, 68, 0.22)",
    padding: 12,
    gap: 6,
  },
  overdueLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#FCA5A5",
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  overdueItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  overdueItemTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
    flex: 1,
    marginRight: 8,
  },
  overdueItemAge: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: "#FCA5A5",
  },
  sourcesBlock: {
    gap: 6,
    paddingTop: 4,
  },
  sourcesChipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  sourceChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "#1C1C1C",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 6,
  },
  sourceChipText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textSecondary,
    maxWidth: 160,
  },
  sourceChipGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },

  // ── Email Styles ──
  emailHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  emailAvatarCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
    alignItems: "center",
    justifyContent: "center",
  },
  emailAvatarText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  emailMetaCol: {
    flex: 1,
    gap: 1,
  },
  emailSenderText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  emailSubjectText: {
    fontFamily: theme.fonts.sans,
    fontSize: 11.5,
    color: theme.colors.textMuted,
  },

  // ── Telemetry Styles ──
  telemetryBarsCol: {
    gap: 10,
  },
  telemetryBarItem: {
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 6,
  },
  telemetryLabelRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  barTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    backgroundColor: theme.colors.emerald,
    borderRadius: 3,
  },

  // ── High-Taste Specialized Mobile HUD Styles (Stitch & LeonUIUX) ──
  sectionCol: {
    gap: 8,
    marginTop: 4,
  },


  // ── GitHub Styles ──
  githubHeroBlock: {
    gap: 8,
    backgroundColor: "#181818",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 12,
  },
  githubTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  githubRepoName: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    flex: 1,
  },
  githubOpenBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 5,
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  githubOpenBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.5,
  },
  githubDescText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textSecondary,
    lineHeight: 16,
  },
  githubItemRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 8,
  },
  githubItemLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
  },
  githubItemNum: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    fontWeight: "600",
  },
  githubItemTitle: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
    flex: 1,
  },
  githubStatePill: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
  },
  githubStateText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  statePillOpen: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    borderColor: "rgba(16, 185, 129, 0.3)",
  },
  stateTextOpen: {
    color: theme.colors.emerald,
  },
  statePillClosed: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  stateTextClosed: {
    color: theme.colors.textMuted,
  },
  statePillMerged: {
    backgroundColor: "rgba(168, 85, 247, 0.14)",
    borderColor: "rgba(168, 85, 247, 0.35)",
  },
  stateTextMerged: {
    color: "#C084FC",
  },
  githubPrRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  githubDiffText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  githubCommitRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 8,
  },
  commitShaPill: {
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderRadius: 4,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  commitShaText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  commitMetaCol: {
    flex: 1,
    gap: 2,
  },
  commitMsgText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  commitAuthorText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  codeHeaderBar: {
    backgroundColor: "#181818",
    borderTopLeftRadius: 8,
    borderTopRightRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  codePathText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textMuted,
  },
  codeContainerWell: {
    backgroundColor: "#0E0E0E",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 10,
  },
  codeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10.5,
    color: "#D1CFC0",
    lineHeight: 16,
  },
  codeMatchItem: {
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 8,
    gap: 4,
  },
  codeMatchSnippet: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
  },

  // ── Email Suite Styles ──
  inboxPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  inboxPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
  },
  unreadCountPill: {
    backgroundColor: "rgba(245, 158, 11, 0.12)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.28)",
  },
  unreadCountText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.amber,
    letterSpacing: 0.6,
  },
  emailListCol: {
    gap: 8,
  },
  emailItemBox: {
    flexDirection: "row",
    alignItems: "flex-start",
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 10,
  },
  emailAvatarCircleSmall: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    alignItems: "center",
    justifyContent: "center",
  },
  emailAvatarTextSmall: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  emailItemMetaCol: {
    flex: 1,
    gap: 2,
  },
  emailItemTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 6,
  },
  emailSenderSmall: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    flex: 1,
  },
  unreadAmberDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.amber,
  },
  emailTimeSmall: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  emailSubjectSmall: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.boneWhite,
  },
  emailSnippetSmall: {
    fontFamily: theme.fonts.sans,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 15,
  },

  // ── Thread Styles ──
  threadSubjectHeading: {
    fontFamily: theme.fonts.sans,
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  threadMessagesCol: {
    gap: 8,
    marginTop: 4,
  },
  threadMsgCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 12,
    gap: 6,
  },
  threadMsgHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  threadMsgSender: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  threadMsgTime: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  threadMsgBody: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    color: theme.colors.textSecondary,
    lineHeight: 18,
  },

  // ── Draft Styles ──
  amberStatusPill: {
    backgroundColor: "rgba(245, 158, 11, 0.12)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.28)",
  },
  amberStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.amber,
  },
  draftMetaBox: {
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 6,
  },
  draftFieldRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  draftFieldLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    width: 60,
    fontWeight: "700",
  },
  draftFieldValue: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
    flex: 1,
  },

  // ── Bill Split Styles ──
  billHeroCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 14,
    gap: 8,
  },
  billHeroTop: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
  },
  billHeroSub: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 0.8,
    fontWeight: "700",
  },
  billHeroAmount: {
    fontFamily: theme.fonts.mono,
    fontSize: 28,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: -0.5,
  },
  payerPill: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.28)",
  },
  payerPillText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.emerald,
  },
  billHeroDesc: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  perPersonBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#181818",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  perPersonLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    fontWeight: "700",
  },
  perPersonValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  participantsGrid: {
    gap: 6,
  },
  participantItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  participantName: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  participantOwesText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.amber,
    fontWeight: "700",
  },
  participantOwesEmerald: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.emerald,
    fontWeight: "700",
  },

  // ── Debt Styles ──
  debtHeroGrid: {
    flexDirection: "row",
    gap: 10,
  },
  debtHeroEmerald: {
    flex: 1,
    backgroundColor: "rgba(16, 185, 129, 0.08)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.22)",
    padding: 12,
    gap: 4,
  },
  debtHeroLabelEmerald: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.emerald,
    fontWeight: "700",
    letterSpacing: 0.6,
  },
  debtHeroValEmerald: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: "700",
    color: "#A7F3D0",
  },
  debtHeroRose: {
    flex: 1,
    backgroundColor: "rgba(244, 63, 94, 0.08)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(244, 63, 94, 0.22)",
    padding: 12,
    gap: 4,
  },
  debtHeroLabelRose: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.rose,
    fontWeight: "700",
    letterSpacing: 0.6,
  },
  debtHeroValRose: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: "700",
    color: "#FECDD3",
  },
  peerItemRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  peerNameText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    color: theme.colors.boneWhite,
  },
  peerBalEmerald: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.emerald,
  },
  peerBalRose: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.rose,
  },

  // ── Financial Goals Styles ──
  goalCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 12,
    gap: 8,
  },
  goalHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  goalNameText: {
    fontFamily: theme.fonts.sans,
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  goalPctPill: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  goalPctText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.emerald,
  },
  goalBarTrack: {
    height: 5,
    borderRadius: 2.5,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    overflow: "hidden",
  },
  goalBarFill: {
    height: "100%",
    borderRadius: 2.5,
    backgroundColor: theme.colors.emerald,
  },
  goalBottomRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  goalCurrentText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textSecondary,
  },
  goalDeficitText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },

  // ── Vision & Optical Styles ──
  visionSensorPill: {
    backgroundColor: "rgba(96, 165, 250, 0.12)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(96, 165, 250, 0.28)",
  },
  visionSensorText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.info,
    letterSpacing: 0.6,
  },
  visionConfidencePill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  visionConfidenceText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
  },
  visionImageWrapper: {
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    height: 160,
  },
  visionImageThumb: {
    width: "100%",
    height: "100%",
  },

  // ── OCR Styles ──
  ocrLinesPill: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  ocrLinesText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
  },
  ocrConsoleWell: {
    backgroundColor: "#0E0E0E",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    padding: 12,
  },
  ocrConsoleText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.boneWhite,
    lineHeight: 17,
  },

  // ── Memory & Synapse Styles ──
  memoryCategoryPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  memoryCategoryText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
  },
  memoryFactWell: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.emerald,
    padding: 12,
  },
  memoryFactText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12.5,
    color: theme.colors.boneWhite,
    lineHeight: 18,
  },
  memoryMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 2,
  },
  memoryMetaLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
    fontWeight: "700",
  },
  memoryMetaValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
    fontWeight: "700",
  },

  // ── Process Monitor Styles ──
  processSortPill: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  processSortText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 0.6,
  },
  processTableCol: {
    gap: 6,
  },
  processItemRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 10,
    paddingVertical: 7,
    gap: 10,
  },
  processLeftCol: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flex: 1,
  },
  processPidText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    color: theme.colors.textMuted,
    width: 44,
  },
  processNameText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.boneWhite,
    flex: 1,
  },
  processRightCol: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  processBarTrack: {
    width: 42,
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    overflow: "hidden",
  },
  processBarFill: {
    height: "100%",
    borderRadius: 2,
    backgroundColor: theme.colors.emerald,
  },
  processCpuText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
    width: 34,
    textAlign: "right",
  },
  processMemText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    width: 42,
    textAlign: "right",
  },

  // ── Hardware Control Styles ──
  hardwareControlCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 12,
    gap: 8,
  },
  hardwareHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  hardwareDeviceRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  hardwareDeviceName: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
  },
  hardwareDeviceStatus: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.emerald,
    fontWeight: "700",
  },

  // ── Tool Call Styles ──
  toolSpecialistPill: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  toolSpecialistText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  toolDurationPill: {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.10)",
  },
  toolDurationText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    color: theme.colors.textMuted,
  },
  toolStatusPill: {
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
  },
  toolStatusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
  },
  toolSignatureBox: {
    backgroundColor: "#181818",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  toolSignatureText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.boneWhite,
    fontWeight: "700",
  },
  toolParamsWell: {
    backgroundColor: "#0E0E0E",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
    padding: 10,
  },

  // ── Web Crawler Styles ──
  crawlDomainPill: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.15)",
  },
  crawlDomainText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  crawlTitleText: {
    fontFamily: theme.fonts.sans,
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    lineHeight: 20,
  },
  crawlBulletList: {
    gap: 6,
  },
  crawlBulletItem: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
  },
  crawlBulletDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: theme.colors.boneWhite,
    marginTop: 7,
  },
  crawlBulletText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textSecondary,
    flex: 1,
    lineHeight: 17,
  },
  crawlLinkBtn: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: "rgba(255, 255, 255, 0.06)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    alignItems: "center",
  },
  crawlLinkBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9.5,
    fontWeight: "700",
    color: theme.colors.boneWhite,
    letterSpacing: 0.6,
  },

  // ── Recipe Styles ──
  recipeTitleHeading: {
    fontFamily: theme.fonts.sans,
    fontSize: 16,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  recipeChecklistCol: {
    gap: 6,
  },
  recipeChecklistItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  recipeCheckCircle: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  recipeCheckCircleActive: {
    backgroundColor: "rgba(16, 185, 129, 0.25)",
    borderColor: theme.colors.emerald,
  },
  recipeCheckGlyph: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.emerald,
  },
  recipeItemText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.boneWhite,
    flex: 1,
  },
  recipeItemTextChecked: {
    textDecorationLine: "line-through",
    color: theme.colors.textMuted,
  },
  recipeStepsCol: {
    gap: 6,
  },
  recipeStepRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
  },
  recipeStepNumBadge: {
    width: 22,
    height: 22,
    borderRadius: 5,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  recipeStepNumText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    fontWeight: "700",
    color: theme.colors.boneWhite,
  },
  recipeStepBodyText: {
    fontFamily: theme.fonts.sans,
    fontSize: 12,
    color: theme.colors.textSecondary,
    flex: 1,
    lineHeight: 17,
  },

  // ── Telemetry Inspector Styles ──
  inspectorGrid: {
    gap: 8,
  },
  inspectorSpecRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#1C1C1C",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    paddingHorizontal: 10,
    paddingVertical: 7,
    gap: 10,
  },
  inspectorSpecKey: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    fontWeight: "700",
  },
  inspectorSpecVal: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.boneWhite,
    fontWeight: "600",
    flex: 1,
    textAlign: "right",
  },
  inspectorArrayBox: {
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 6,
  },
  inspectorSubCard: {
    backgroundColor: "#1C1C1C",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.05)",
    padding: 10,
    gap: 6,
  },
  inspectorSubCardInner: {
    backgroundColor: "#161616",
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
    padding: 8,
    gap: 4,
  },
  inspectorSubRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  inspectorSubKey: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  inspectorSubVal: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.boneWhite,
  },
});
