import React, { useState, useEffect, useCallback } from 'react';
import {
  Cloud,
  Play,
  ChefHat,
  CreditCard,
  Music,
  Wrench,
  FileText,
  X,
  Trash2,
  ExternalLink,
  Wind,
  Droplets,
  Clock,
  User,
  Sliders,
  Calendar,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { notificationStore } from '../services/notification-store';
import { HudOutput, HudCardType } from '../types/vesper';
import { cn } from '../lib/utils';
import {
  Drawer,
  DrawerContent,
  DrawerClose,
} from './ui/drawer';

// ── Card icon map ───────────────────────────────────────────────────────────

const CARD_ICONS: Record<HudCardType, React.FC<{ size?: number; strokeWidth?: number }>> = {
  weather: Cloud,
  youtube: Play,
  recipe: ChefHat,
  transaction: CreditCard,
  spotify: Music,
  briefing: Calendar,
  tool_call: Wrench,
  generic: FileText,
};

// ── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return 'now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function extractLink(data: Record<string, any>): string | null {
  return data.url || data.link || data.href || data.uri || null;
}

// ── Weather Card ────────────────────────────────────────────────────────────

const WeatherCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const temp = data.temperature ?? data.temp ?? '--';
  const condition = data.condition || data.description || 'Current Conditions';
  const humidity = data.humidity;
  const wind = data.wind_speed || data.wind;
  const location = data.location || data.city;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex items-baseline gap-1">
          <span className="font-mono text-5xl sm:text-6xl font-semibold text-[#E8E3DA] tabular-nums tracking-tighter">
            {temp}
          </span>
          <span className="font-mono text-3xl text-[#8E8A83]">°</span>
        </div>
        <div className="text-right">
          <span className="block font-sans text-base sm:text-lg font-semibold text-[#E8E3DA] uppercase tracking-wide">
            {condition}
          </span>
          {location && (
            <span className="block font-mono text-xs text-[#8E8A83] mt-0.5">
              {location}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 pt-1">
        {humidity !== undefined && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <Droplets size={13} strokeWidth={1.8} />
              <span>Humidity</span>
            </div>
            <span className="font-mono text-xl font-medium text-[#E8E3DA] tabular-nums">
              {humidity}%
            </span>
          </div>
        )}

        {wind !== undefined && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <Wind size={13} strokeWidth={1.8} />
              <span>Wind</span>
            </div>
            <span className="font-mono text-xl font-medium text-[#E8E3DA] tabular-nums">
              {wind}
            </span>
          </div>
        )}

        {(data.feels_like !== undefined || data.high !== undefined || data.uv_index !== undefined) && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <Sliders size={13} strokeWidth={1.8} />
              <span>{data.feels_like !== undefined ? 'Feels Like' : data.high !== undefined ? 'High / Low' : 'UV Index'}</span>
            </div>
            <span className="font-mono text-xl font-medium text-[#E8E3DA] tabular-nums">
              {data.feels_like !== undefined ? `${data.feels_like}°` : data.high !== undefined ? `${data.high}° / ${data.low ?? '--'}°` : data.uv_index}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

// ── YouTube Card ────────────────────────────────────────────────────────────

const YoutubeCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const title = data.title || 'YouTube Video';
  const channel = data.channel || data.author;
  const duration = data.duration;
  const link = extractLink(data);

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3">
      <div>
        <h4 className="font-sans text-lg sm:text-xl font-bold text-[#E8E3DA] tracking-tight leading-snug">
          {title}
        </h4>
        <div className="flex items-center gap-3 mt-1.5 font-sans text-sm text-[#8E8A83]">
          {channel && <span className="text-[#D1CFC0] font-medium">{channel}</span>}
          {channel && duration && <span>•</span>}
          {duration && <span className="font-mono text-xs">{duration}</span>}
        </div>
      </div>

      {link && (
        <div className="flex items-center justify-end pt-1">
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.12] text-sm font-sans font-medium text-[#E8E3DA] transition-all no-underline cursor-pointer"
          >
            <Play size={14} fill="currentColor" />
            <span>Watch on YouTube</span>
          </a>
        </div>
      )}
    </div>
  );
};

// ── Spotify Card ────────────────────────────────────────────────────────────

const SpotifyCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const track = data.track || data.title || data.song || 'Unknown Track';
  const artist = data.artist || 'Unknown Artist';
  const album = data.album;
  const playlist = data.playlist_name || data.playlist;
  const link = extractLink(data);

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <div className="relative w-16 h-16 sm:w-20 sm:h-20 rounded-xl bg-white/[0.04] border border-white/[0.1] flex items-center justify-center shrink-0">
          <Music size={28} strokeWidth={1.5} className="text-[#D1CFC0]" />
          <div className="absolute bottom-1.5 right-1.5 flex items-end gap-0.5 h-3">
            <span className="w-0.5 h-3 bg-[#E8E3DA] rounded-full animate-pulse" />
            <span className="w-0.5 h-2 bg-[#E8E3DA] rounded-full animate-pulse delay-75" />
            <span className="w-0.5 h-2.5 bg-[#E8E3DA] rounded-full animate-pulse delay-150" />
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <span className="inline-block px-2 py-0.5 mb-1 text-[10px] font-mono uppercase tracking-widest text-[#8E8A83] bg-white/[0.04] border border-white/[0.06] rounded">
            Now Playing
          </span>
          <h4 className="font-sans text-lg sm:text-xl font-bold text-[#E8E3DA] tracking-tight truncate leading-snug">
            {track}
          </h4>
          <p className="font-sans text-sm sm:text-base font-medium text-[#D1CFC0] truncate mt-0.5">
            {artist}
          </p>
          {(album || playlist) && (
            <p className="font-sans text-xs text-[#8E8A83] truncate mt-0.5">
              {playlist ? `Playlist: ${playlist}` : album}
            </p>
          )}
        </div>
      </div>

      {link && (
        <div className="flex items-center justify-end pt-1">
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.12] text-sm font-sans font-medium text-[#E8E3DA] transition-all no-underline cursor-pointer"
          >
            <span>Open in Spotify</span>
            <ExternalLink size={14} />
          </a>
        </div>
      )}
    </div>
  );
};

// ── Recipe Card ─────────────────────────────────────────────────────────────

const RecipeCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const prepTime = data.prep_time || data.cook_time;
  const servings = data.servings;
  const count = data.ingredients_count || (Array.isArray(data.ingredients) ? data.ingredients.length : null);
  const link = extractLink(data);
  const instructions = data.instructions || data.summary || data.description;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        {prepTime && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <Clock size={13} strokeWidth={1.8} />
              <span>Time</span>
            </div>
            <span className="font-mono text-base sm:text-lg font-medium text-[#E8E3DA]">
              {prepTime}
            </span>
          </div>
        )}

        {servings && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <User size={13} strokeWidth={1.8} />
              <span>Servings</span>
            </div>
            <span className="font-mono text-base sm:text-lg font-medium text-[#E8E3DA]">
              {servings}
            </span>
          </div>
        )}

        {count && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <ChefHat size={13} strokeWidth={1.8} />
              <span>Items</span>
            </div>
            <span className="font-mono text-base sm:text-lg font-medium text-[#E8E3DA]">
              {count} ingredients
            </span>
          </div>
        )}
      </div>

      {instructions && (
        <p className="font-sans text-sm text-[#D1CFC0] leading-relaxed line-clamp-3 bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
          {instructions}
        </p>
      )}

      {link && (
        <div className="flex items-center justify-end pt-1">
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.12] text-sm font-sans font-medium text-[#E8E3DA] transition-all no-underline cursor-pointer"
          >
            <span>Full Recipe</span>
            <ExternalLink size={14} />
          </a>
        </div>
      )}
    </div>
  );
};

// ── Transaction Card ────────────────────────────────────────────────────────

const TransactionCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const currency = data.currency || 'INR';
  const amount = data.amount;
  const merchant = data.merchant || data.payee;
  const category = data.category;
  const account = data.account || data.bank;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-widest block mb-1">
            Amount Processed
          </span>
          <span className="font-mono text-4xl sm:text-5xl font-bold text-[#E8E3DA] tabular-nums tracking-tight">
            {currency} {amount}
          </span>
        </div>

        {category && (
          <span className="font-mono text-xs text-[#D1CFC0] px-3 py-1 rounded-md bg-white/[0.06] border border-white/[0.1] uppercase tracking-wider self-start">
            {category}
          </span>
        )}
      </div>

      {merchant && (
        <div className="flex items-center justify-between text-sm pt-2 border-t border-white/[0.04]">
          <span className="font-sans text-[#8E8A83]">Recipient / Merchant</span>
          <span className="font-sans font-medium text-[#E8E3DA]">{merchant}</span>
        </div>
      )}

      {account && (
        <div className="flex items-center justify-between text-xs">
          <span className="font-sans text-[#8E8A83]">Account</span>
          <span className="font-mono text-[#D1CFC0]">{account}</span>
        </div>
      )}
    </div>
  );
};

// ── Briefing Card ───────────────────────────────────────────────────────────

const BriefingCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const overdueTasks = Array.isArray(data.overdue_tasks) ? data.overdue_tasks : [];
  const events = Array.isArray(data.events) ? data.events : [];
  const todayTasksCount = data.today_tasks_count ?? 0;
  const overdueCount = data.overdue_tasks_count ?? overdueTasks.length;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4">
      {/* Metrics Row */}
      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col p-2.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
          <span className="font-sans text-[10px] text-[#8E8A83] uppercase tracking-wider">Today's Agenda</span>
          <span className="font-mono text-xl font-semibold text-[#E8E3DA] mt-0.5">{todayTasksCount} Tasks</span>
        </div>
        <div className="flex flex-col p-2.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
          <span className="font-sans text-[10px] text-[#8E8A83] uppercase tracking-wider">Overdue Matters</span>
          <span className={cn("font-mono text-xl font-semibold mt-0.5", overdueCount > 0 ? "text-[#E8E3DA]" : "text-[#8E8A83]")}>
            {overdueCount} Items
          </span>
        </div>
        <div className="flex flex-col p-2.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
          <span className="font-sans text-[10px] text-[#8E8A83] uppercase tracking-wider">Calendar Sync</span>
          <span className="font-mono text-xl font-semibold text-[#E8E3DA] mt-0.5">{events.length} Events</span>
        </div>
      </div>

      {/* Overdue Matters Section */}
      {overdueTasks.length > 0 && (
        <div className="flex flex-col gap-2 p-3 rounded-xl bg-white/[0.02] border border-white/[0.08]">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs uppercase tracking-wider text-[#E8E3DA] font-semibold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA] animate-pulse" />
              Overdue Matters (Action Required)
            </span>
            <span className="font-mono text-[10px] text-[#8E8A83]">{overdueTasks.length} Pending</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {overdueTasks.map((ot: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                <div className="flex items-center gap-2 min-w-0 pr-2">
                  <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-white/[0.08] text-[#E8E3DA] border border-white/20 font-bold shrink-0">
                    OVERDUE
                  </span>
                  <span className="font-sans text-xs font-medium text-[#E8E3DA] truncate">
                    {ot.title || ot}
                  </span>
                </div>
                <span className="font-mono text-[10px] text-[#8E8A83] shrink-0">
                  {ot.age || 'Overdue'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Calendar Events Section */}
      {events.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Upcoming Calendar Appointments</span>
          {events.map((ev: any, idx: number) => (
            <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
              <span className="font-sans text-xs text-[#E8E3DA] truncate">{ev.summary}</span>
              <span className="font-mono text-[10px] text-[#D1CFC0]">{ev.time}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Generic Card ────────────────────────────────────────────────────────────

const GenericCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const body = data.response || data.markdown_body || data.text || data.message;
  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-2">
      {body && (
        <p className="font-sans text-base text-[#D1CFC0] leading-relaxed whitespace-pre-wrap">
          {String(body)}
        </p>
      )}
    </div>
  );
};

// ── HUD Card Renderer ───────────────────────────────────────────────────────

const HudCard: React.FC<{ output: HudOutput; onDismiss: (id: string) => void }> = ({
  output,
  onDismiss,
}) => {
  const Icon = CARD_ICONS[output.type] || FileText;

  const renderDetail = () => {
    switch (output.type) {
      case 'weather':
        return <WeatherCard data={output.data} />;
      case 'youtube':
        return <YoutubeCard data={output.data} />;
      case 'spotify':
        return <SpotifyCard data={output.data} />;
      case 'recipe':
        return <RecipeCard data={output.data} />;
      case 'transaction':
        return <TransactionCard data={output.data} />;
      case 'briefing':
        return <BriefingCard data={output.data} />;
      default:
        return <GenericCard data={output.data} />;
    }
  };

  return (
    <motion.div
      className="p-5 sm:p-6 rounded-2xl border border-white/[0.09] bg-[#191919] hover:border-white/[0.18] transition-all shadow-md"
      initial={{ y: 18, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: -12, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 280, damping: 28 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-white/[0.05] border border-white/[0.08] text-[#E8E3DA] shrink-0">
            <Icon size={18} strokeWidth={1.8} />
          </div>
          <div className="flex flex-col min-w-0">
            <h3 className="font-sans text-base sm:text-lg font-bold text-[#E8E3DA] truncate tracking-tight">
              {output.title}
            </h3>
            <div className="flex items-center gap-2 font-mono text-xs text-[#8E8A83] mt-0.5">
              <span className="uppercase tracking-wider">{output.type}</span>
              <span>•</span>
              <span>{timeAgo(output.timestamp)}</span>
            </div>
          </div>
        </div>

        <button
          className="flex items-center justify-center w-8 h-8 rounded-lg border border-transparent hover:border-white/[0.1] bg-transparent text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.06] transition-colors cursor-pointer shrink-0"
          onClick={() => onDismiss(output.id)}
          aria-label="Dismiss card"
        >
          <X size={15} />
        </button>
      </div>

      {renderDetail()}
    </motion.div>
  );
};

// ── Main Drawer ─────────────────────────────────────────────────────────────

interface HudDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customTitle?: string;
  customSubtitle?: string;
}

export const HudDrawer: React.FC<HudDrawerProps> = ({ 
  open, 
  onOpenChange,
  customTitle,
  customSubtitle,
}) => {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const unsub = notificationStore.subscribe(() => {
      forceUpdate((n) => n + 1);
    });
    return unsub;
  }, []);

  const outputs = notificationStore.activeHudOutputs;

  const handleDismiss = useCallback((id: string) => {
    notificationStore.dismissHudOutput(id);
  }, []);

  const handleDismissAll = useCallback(() => {
    notificationStore.dismissAllHudOutputs();
  }, []);

  // Compute dynamic title based on active tool or HUD cards
  const deriveDynamicHeader = () => {
    if (customTitle) {
      return {
        title: customTitle,
        subtitle: customSubtitle || 'Specialist tool interface & structured parameters',
        Icon: Wrench,
      };
    }

    if (outputs.length === 0) {
      return {
        title: 'HUD INTELLIGENCE DECK',
        subtitle: 'Active cognitive agent outputs, live tools, and structured media responses',
        Icon: FileText,
      };
    }

    const primary = outputs[0];
    switch (primary.type) {
      case 'spotify':
        return {
          title: 'SPOTIFY & VINYL ENGINE',
          subtitle: 'Active MPRIS media controls & live audio telemetry',
          Icon: Music,
        };
      case 'briefing':
        return {
          title: 'GOOGLE CALENDAR & AGENDA',
          subtitle: 'Two-way synchronized Google Calendar & task schedule',
          Icon: Calendar,
        };
      case 'transaction':
        return {
          title: 'FINANCIAL LEDGER & ACCOUNTS',
          subtitle: 'Supabase ledger transactions & financial accounting',
          Icon: CreditCard,
        };
      case 'weather':
        return {
          title: 'ATMOSPHERIC INTELLIGENCE',
          subtitle: 'Local weather sentry & forecast radar telemetry',
          Icon: Cloud,
        };
      case 'youtube':
        return {
          title: 'YOUTUBE MEDIA RUNTIME',
          subtitle: 'Video transcription, playback & metadata cache',
          Icon: Play,
        };
      case 'recipe':
        return {
          title: 'CULINARY & NUTRITION SPECIALIST',
          subtitle: 'Recipe breakdown, timers & ingredient parameters',
          Icon: ChefHat,
        };
      case 'tool_call':
        return {
          title: primary.title ? primary.title.toUpperCase() : 'TOOL EXECUTION DECK',
          subtitle: 'Deterministic agent tool call & execution parameters',
          Icon: Wrench,
        };
      default:
        return {
          title: primary.title ? primary.title.toUpperCase() : 'COGNITIVE EXECUTION DECK',
          subtitle: 'Specialist tool interface & structured parameters',
          Icon: Sliders,
        };
    }
  };

  const dynamicHeader = deriveDynamicHeader();
  const HeaderIcon = dynamicHeader.Icon;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="inset-x-0 mx-auto w-[54vw] min-w-[540px] max-w-[940px] max-h-[82vh] !bg-[#131313] !border-t !border-x !border-b-0 !border-white/[0.14] rounded-t-[24px] shadow-2xl flex flex-col text-[#E8E3DA] p-0 focus:outline-none">
        {/* Drawer Header */}
        <div className="px-6 sm:px-8 pt-4 pb-4 border-b border-white/[0.08]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-white/[0.06] border border-white/[0.10] text-[#E8E3DA]">
                <HeaderIcon size={16} strokeWidth={1.8} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-mono text-sm sm:text-base font-bold tracking-wider text-[#E8E3DA]">
                    {dynamicHeader.title}
                  </h2>
                  {outputs.length > 1 && (
                    <span className="font-mono text-[10px] text-[#A1A1AA] px-2 py-0.5 rounded-full bg-white/[0.06] border border-white/10 font-semibold">
                      +{outputs.length - 1} OTHER
                    </span>
                  )}
                </div>
                <p className="font-sans text-xs text-[#A1A1AA] mt-0.5">
                  {dynamicHeader.subtitle}
                </p>
              </div>
            </div>

            {outputs.length > 0 && (
              <button
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] bg-transparent text-[#8E8A83] font-mono text-xs hover:text-[#E8E3DA] hover:border-white/[0.18] hover:bg-white/[0.04] transition-colors cursor-pointer"
                onClick={handleDismissAll}
              >
                <Trash2 size={13} />
                <span>Dismiss All</span>
              </button>
            )}
          </div>
        </div>

        {/* Card list */}
        <div className="flex-1 overflow-y-auto px-6 sm:px-8 py-5 max-h-[60vh] space-y-3">
          {outputs.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#8E8A83]">
              <FileText size={28} strokeWidth={1.2} className="opacity-40" />
              <span className="font-sans text-sm">No active HUD cards</span>
            </div>
          ) : (
            <AnimatePresence mode="popLayout">
              {outputs.map((output) => (
                <HudCard key={output.id} output={output} onDismiss={handleDismiss} />
              ))}
            </AnimatePresence>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 sm:px-8 py-3.5 border-t border-white/[0.06] flex items-center justify-end">
          <DrawerClose asChild>
            <button className="px-5 py-2 rounded-lg border border-white/[0.12] bg-white/[0.04] text-[#E8E3DA] font-sans text-xs font-medium hover:bg-white/[0.08] hover:border-white/[0.22] transition-colors cursor-pointer">
              Close Deck
            </button>
          </DrawerClose>
        </div>
      </DrawerContent>
    </Drawer>
  );
};
