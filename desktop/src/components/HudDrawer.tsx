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
  Mail,
  CheckSquare,
  Search,
  GitPullRequest,
  Cpu,
  Check,
  ChevronDown,
  ChevronUp,
  Star,
  Wallet,
  Copy,
  Disc,
  HardDrive,
  Activity,
  Pause,
  SkipBack,
  SkipForward,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { notificationStore } from '../services/notification-store';
import { mediaService } from '../services/media-service';
import { HudOutput, HudCardType, NowPlayingTrack } from '../types/vesper';
import { cn } from '../lib/utils';
import {
  Drawer,
  DrawerContent,
  DrawerClose,
} from './ui/drawer';

// ── Card icon map ───────────────────────────────────────────────────────────

const CARD_ICONS: Record<HudCardType, React.FC<{ size?: number; strokeWidth?: number; className?: string }>> = {
  weather: Cloud,
  youtube: Play,
  recipe: ChefHat,
  transaction: CreditCard,
  spotify: Music,
  briefing: Calendar,
  email: Mail,
  task: CheckSquare,
  calendar: Calendar,
  research: Search,
  github: GitPullRequest,
  system_status: Cpu,
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
  if (data.url && typeof data.url === 'string') return data.url;
  if (data.link && typeof data.link === 'string') return data.link;
  if (data.href && typeof data.href === 'string') return data.href;
  if (data.video_id) return `https://www.youtube.com/watch?v=${data.video_id}`;
  if (data.youtube_id) return `https://www.youtube.com/watch?v=${data.youtube_id}`;
  if (data.uri && typeof data.uri === 'string') {
    if (data.uri.startsWith('http')) return data.uri;
    if (data.uri.startsWith('spotify:track:')) {
      return `https://open.spotify.com/track/${data.uri.replace('spotify:track:', '')}`;
    }
    if (data.uri.startsWith('spotify:playlist:')) {
      return `https://open.spotify.com/playlist/${data.uri.replace('spotify:playlist:', '')}`;
    }
  }
  return null;
}

function sanitizeText(str?: string): string {
  if (!str) return '';
  return str.replace(/[\u034f\ufeff\u200b-\u200d\u00ad]/g, '').trim();
}

function parseSender(senderStr?: string): { name: string; email: string; initial: string } {
  if (!senderStr) return { name: 'Unknown', email: '', initial: '?' };
  const match = senderStr.match(/^(.*?)\s*<(.+?)>$/);
  if (match) {
    const name = match[1].trim().replace(/^["']|["']$/g, '');
    const email = match[2].trim();
    const initial = (name[0] || email[0] || '?').toUpperCase();
    return { name: name || email, email, initial };
  }
  const clean = senderStr.trim().replace(/^["']|["']$/g, '');
  const atIdx = clean.indexOf('@');
  let name = clean;
  let initial = (clean[0] || '?').toUpperCase();
  if (atIdx > 0) {
    const domain = clean.substring(atIdx + 1);
    const domainName = domain.split('.')[0];
    initial = (domainName[0] || clean[0]).toUpperCase();
  }
  return { name, email: clean, initial };
}

// ── Kinetic Staggered Text Reveal Component ─────────────────────────────────

export const AnimatedCardText: React.FC<{
  text: string;
  className?: string;
  delay?: number;
}> = ({ text, className, delay = 0 }) => {
  const clean = sanitizeText(text);
  if (!clean) return null;
  const words = clean.split(/\s+/).filter(Boolean);

  return (
    <motion.span
      className={cn('inline-block leading-relaxed', className)}
      initial="hidden"
      animate="visible"
      variants={{
        hidden: { opacity: 0 },
        visible: {
          opacity: 1,
          transition: {
            staggerChildren: 0.015,
            delayChildren: delay,
          },
        },
      }}
    >
      {words.map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          variants={{
            hidden: { opacity: 0, y: 4, filter: 'blur(2px)' },
            visible: {
              opacity: 1,
              y: 0,
              filter: 'blur(0px)',
              transition: {
                type: 'spring',
                stiffness: 140,
                damping: 20,
              },
            },
          }}
          className="inline-block mr-[0.26em]"
        >
          {word}
        </motion.span>
      ))}
    </motion.span>
  );
};

// ── Email List Card (Stitch Design) ─────────────────────────────────────────

interface EmailItem {
  id: string;
  sender: string;
  subject: string;
  snippet: string;
  date?: string;
  unread?: boolean;
  is_transaction?: boolean;
  amount?: string;
  transaction_type?: string;
  account_number?: string;
}

const EmailListCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const emails: EmailItem[] = Array.isArray(data.emails)
    ? data.emails
    : Array.isArray(data.items)
    ? data.items
    : [];
  const title = data.title || 'Unread Inbox';

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [starredIds, setStarredIds] = useState<Set<string>>(new Set());

  const toggleRead = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setReadIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleStar = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setStarredIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const unreadCount = emails.filter((em) => em.unread && !readIds.has(em.id)).length;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3">
      {/* Sub-header status strip */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs uppercase tracking-widest text-[#E8E3DA] font-semibold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
            {title}
          </span>
          <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-white/[0.08] border border-white/10 text-[#D1CFC0] font-bold">
            {unreadCount} UNREAD
          </span>
        </div>
        <span className="font-mono text-[10px] text-[#8E8A83]">
          IMAP & Gmail Sync
        </span>
      </div>

      {/* Double-Bezel Email List Container */}
      <div className="rounded-2xl border border-white/[0.08] bg-black/40 p-1.5 flex flex-col gap-1.5">
        {emails.length === 0 ? (
          <div className="py-8 text-center text-xs font-mono text-[#8E8A83]">
            No unread correspondence found.
          </div>
        ) : (
          emails.map((email, idx) => {
            const parsedSender = parseSender(email.sender);
            const isUnread = email.unread && !readIds.has(email.id);
            const isStarred = starredIds.has(email.id);
            const isExpanded = expandedId === email.id;
            const cleanSnippet = sanitizeText(email.snippet);

            let formattedDate = email.date || '';
            if (email.date) {
              const d = new Date(email.date);
              if (!isNaN(d.getTime())) {
                formattedDate = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              }
            }

            return (
              <motion.div
                key={email.id || idx}
                layout
                onClick={() => toggleExpand(email.id)}
                className={cn(
                  'rounded-xl border transition-all cursor-pointer p-3 text-left',
                  isExpanded
                    ? 'bg-[#1b1b1b] border-white/[0.18] shadow-lg'
                    : 'bg-[#141414] hover:bg-[#181818] border-white/[0.06] hover:border-white/[0.12]'
                )}
              >
                <div className="flex items-start gap-3">
                  {/* Avatar badge with initial */}
                  <div
                    className={cn(
                      'w-8 h-8 rounded-lg flex items-center justify-center font-mono font-bold text-xs shrink-0 border',
                      isUnread
                        ? 'bg-blue-500/10 border-blue-500/30 text-blue-300'
                        : 'bg-white/[0.04] border-white/[0.08] text-[#8E8A83]'
                    )}
                  >
                    {parsedSender.initial}
                  </div>

                  {/* Body preview */}
                  <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-sans text-xs sm:text-sm font-semibold text-[#E8E3DA] truncate">
                          {parsedSender.name}
                        </span>
                        {parsedSender.email && parsedSender.email !== parsedSender.name && (
                          <span className="font-mono text-[10px] text-[#8E8A83] truncate hidden sm:inline">
                            &lt;{parsedSender.email}&gt;
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {formattedDate && (
                          <span className="font-mono text-[10px] text-[#8E8A83]">
                            {formattedDate}
                          </span>
                        )}
                        {isUnread && (
                          <span className="w-2 h-2 rounded-full bg-blue-400 shrink-0" title="Unread" />
                        )}
                      </div>
                    </div>

                    <div className="font-sans text-xs sm:text-sm font-medium text-[#E8E3DA] truncate">
                      {email.subject || '(No Subject)'}
                    </div>

                    {/* Animated kinetic snippet */}
                    <div className="text-xs text-[#A1A1AA] leading-relaxed line-clamp-2 mt-0.5">
                      <AnimatedCardText text={cleanSnippet} delay={idx * 0.04} />
                    </div>

                    {/* Transaction metadata badge if detected */}
                    {(email.amount || email.is_transaction) && (
                      <div className="flex items-center gap-2 mt-1.5 pt-1 border-t border-white/[0.04]">
                        <span
                          className={cn(
                            'font-mono text-[10px] font-bold px-2 py-0.5 rounded border tracking-wider',
                            email.transaction_type?.toLowerCase() === 'credit'
                              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                              : 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                          )}
                        >
                          {email.amount || ''} {email.transaction_type || 'ALERT'}
                        </span>
                        {email.account_number && (
                          <span className="font-mono text-[10px] text-[#8E8A83]">
                            A/C {email.account_number}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Expand chevron */}
                  <div className="text-[#8E8A83] shrink-0 pt-1">
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </div>

                {/* Expanded Action Panel */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="mt-3 pt-3 border-t border-white/[0.08] flex flex-col gap-2.5 overflow-hidden"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.04] text-xs font-sans text-[#D1CFC0] leading-relaxed whitespace-pre-wrap">
                        {cleanSnippet}
                      </div>

                      <div className="flex items-center justify-between gap-2 pt-1">
                        <span className="font-mono text-[10px] text-[#5C5A56] truncate">
                          ID: {email.id}
                        </span>

                        <div className="flex items-center gap-2">
                          <a
                            href={`https://mail.google.com/mail/u/0/#inbox/${email.id || ''}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 rounded-md border border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.08] text-[#8E8A83] hover:text-[#E8E3DA] text-[11px] font-mono flex items-center gap-1.5 transition-colors no-underline"
                          >
                            <span>Gmail</span>
                            <ExternalLink size={11} />
                          </a>

                          <button
                            type="button"
                            onClick={(e) => toggleStar(email.id, e)}
                            className={cn(
                              'px-2.5 py-1 rounded-md border text-[11px] font-mono flex items-center gap-1.5 transition-colors',
                              isStarred
                                ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                                : 'bg-white/[0.04] border-white/[0.08] text-[#8E8A83] hover:text-[#E8E3DA]'
                            )}
                          >
                            <Star size={12} fill={isStarred ? 'currentColor' : 'none'} />
                            <span>{isStarred ? 'Starred' : 'Star'}</span>
                          </button>

                          <button
                            type="button"
                            onClick={(e) => toggleRead(email.id, e)}
                            className="px-2.5 py-1 rounded-md border border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.08] text-[#8E8A83] hover:text-[#E8E3DA] text-[11px] font-mono flex items-center gap-1.5 transition-colors"
                          >
                            <Check size={12} />
                            <span>{isUnread ? 'Mark Read' : 'Mark Unread'}</span>
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
};

// ── Single Email Card ───────────────────────────────────────────────────────

const EmailCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const email = data.email || data;
  const parsedSender = parseSender(email.sender || email.from);
  const subject = email.subject || 'Message';
  const cleanBody = sanitizeText(email.body || email.snippet || email.text || '');
  const to = email.to || 'Me';
  const date = email.date;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 text-blue-300 flex items-center justify-center font-mono font-bold text-sm shrink-0">
          {parsedSender.initial}
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-sans text-base sm:text-lg font-bold text-[#E8E3DA] truncate">
            {subject}
          </h4>
          <div className="flex items-center gap-2 font-mono text-xs text-[#8E8A83] mt-0.5">
            <span className="text-[#D1CFC0]">{parsedSender.name}</span>
            {parsedSender.email && <span>&lt;{parsedSender.email}&gt;</span>}
            {date && <span>• {new Date(date).toLocaleString()}</span>}
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-black/40 border border-white/[0.08] text-sm text-[#D1CFC0] leading-relaxed whitespace-pre-wrap">
        <AnimatedCardText text={cleanBody} />
      </div>

      <div className="flex items-center justify-between text-[11px] font-mono text-[#8E8A83] pt-2 border-t border-white/[0.06]">
        <span>To: {to}</span>
        <div className="flex items-center gap-3">
          {email.id && <span>Message ID: {email.id}</span>}
          <a
            href={`https://mail.google.com/mail/u/0/#inbox/${email.id || ''}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-[#E8E3DA] transition-colors no-underline"
          >
            <span>Open in Gmail</span>
            <ExternalLink size={11} />
          </a>
        </div>
      </div>
    </div>
  );
};

// ── Task List Card ──────────────────────────────────────────────────────────

const TaskListCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const tasks: any[] = Array.isArray(data.tasks) ? data.tasks : [];
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());

  const toggleTask = (id: string) => {
    setCompletedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-2.5 text-left">
      <div className="flex items-center justify-between px-1">
        <span className="font-mono text-xs uppercase tracking-wider text-[#E8E3DA] font-semibold">
          Executive Tasks & Priorities
        </span>
        <span className="font-mono text-[10px] text-[#8E8A83]">
          {tasks.length} Total
        </span>
      </div>

      <div className="rounded-2xl border border-white/[0.08] bg-black/40 p-1.5 flex flex-col gap-1.5">
        {tasks.length === 0 ? (
          <div className="py-6 text-center text-xs font-mono text-[#8E8A83]">
            No pending tasks.
          </div>
        ) : (
          tasks.map((task: any, idx: number) => {
            const id = task.id || String(idx);
            const isDone = task.done || completedIds.has(id);
            const priority = (task.priority || 'normal').toLowerCase();

            return (
              <div
                key={id}
                onClick={() => toggleTask(id)}
                className={cn(
                  'flex items-center justify-between p-3 rounded-xl border transition-all cursor-pointer',
                  isDone
                    ? 'bg-white/[0.02] border-white/[0.04] opacity-50'
                    : 'bg-[#141414] hover:bg-[#181818] border-white/[0.06] hover:border-white/[0.12]'
                )}
              >
                <div className="flex items-center gap-3 min-w-0 pr-2">
                  <div
                    className={cn(
                      'w-5 h-5 rounded border flex items-center justify-center transition-colors shrink-0',
                      isDone
                        ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                        : 'border-white/20 hover:border-white/40'
                    )}
                  >
                    {isDone && <Check size={12} />}
                  </div>

                  <span
                    className={cn(
                      'font-sans text-xs sm:text-sm font-medium truncate',
                      isDone ? 'line-through text-[#8E8A83]' : 'text-[#E8E3DA]'
                    )}
                  >
                    <AnimatedCardText text={task.title || task} delay={idx * 0.04} />
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={cn(
                      'font-mono text-[9px] uppercase px-1.5 py-0.5 rounded font-bold border',
                      priority === 'urgent'
                        ? 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                        : priority === 'high'
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                        : 'bg-white/[0.06] text-[#8E8A83] border-white/10'
                    )}
                  >
                    {priority}
                  </span>
                  {task.deadline && (
                    <span className="font-mono text-[10px] text-[#8E8A83]">
                      {task.deadline}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

// ── Calendar Card ───────────────────────────────────────────────────────────

const CalendarCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const events: any[] = Array.isArray(data.events)
    ? data.events
    : data.event
    ? [data.event]
    : [];

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-2.5 text-left">
      <div className="flex items-center justify-between px-1">
        <span className="font-mono text-xs uppercase tracking-wider text-[#E8E3DA] font-semibold">
          Synchronized Appointments
        </span>
        <span className="font-mono text-[10px] text-[#8E8A83]">
          Google Calendar
        </span>
      </div>

      <div className="rounded-2xl border border-white/[0.08] bg-black/40 p-1.5 flex flex-col gap-1.5">
        {events.length === 0 ? (
          <div className="py-6 text-center text-xs font-mono text-[#8E8A83]">
            No appointments scheduled.
          </div>
        ) : (
          events.map((ev: any, idx: number) => {
            const evLink = ev.html_link || ev.htmlLink || ev.link || ev.url || 'https://calendar.google.com';
            return (
              <a
                key={idx}
                href={evLink}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between p-3 rounded-xl bg-[#141414] hover:bg-[#1a1a1a] border border-white/[0.06] hover:border-white/[0.14] transition-all no-underline cursor-pointer group"
              >
                <div className="flex flex-col gap-0.5 min-w-0 pr-2">
                  <span className="font-sans text-xs sm:text-sm font-semibold text-[#E8E3DA] group-hover:text-blue-300 truncate transition-colors">
                    <AnimatedCardText text={ev.summary || ev.title || 'Event'} delay={idx * 0.04} />
                  </span>
                  {ev.location && (
                    <span className="font-mono text-[10px] text-[#8E8A83] truncate">
                      {ev.location}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-white/[0.06] border border-white/10 text-[#D1CFC0]">
                    {ev.time || (ev.start ? `${ev.start} - ${ev.end || ''}` : 'Scheduled')}
                  </span>
                  <span className="p-1 rounded text-[#8E8A83] group-hover:text-[#E8E3DA] transition-colors">
                    <ExternalLink size={12} />
                  </span>
                </div>
              </a>
            );
          })
        )}
      </div>
    </div>
  );
};

// ── Research Card ───────────────────────────────────────────────────────────

const ResearchCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const query = data.query || 'Research Synthesis';
  const answer = sanitizeText(data.answer || data.summary || data.text || '');
  const sources: any[] = Array.isArray(data.sources) ? data.sources : [];

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-white/[0.08] border border-white/10 text-[#E8E3DA] font-semibold">
          QUERY: {query}
        </span>
      </div>

      {answer && (
        <div className="p-3.5 rounded-xl bg-black/40 border border-white/[0.08] text-sm text-[#D1CFC0] leading-relaxed whitespace-pre-wrap">
          <AnimatedCardText text={answer} />
        </div>
      )}

      {sources.length > 0 && (
        <div className="flex flex-col gap-1.5 pt-1">
          <span className="font-mono text-[10px] text-[#8E8A83] uppercase tracking-wider">
            Verified Sources ({sources.length})
          </span>
          <div className="flex flex-wrap gap-2">
            {sources.map((src: any, idx: number) => {
              const link = typeof src === 'string' ? src : src.url || src.link;
              const srcTitle = typeof src === 'string' ? src : src.title || src.name || link;
              return (
                <a
                  key={idx}
                  href={link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] font-mono text-xs text-[#D1CFC0] hover:text-[#E8E3DA] transition-colors"
                >
                  <span className="truncate max-w-[200px]">{srcTitle}</span>
                  <ExternalLink size={11} />
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

// ── GitHub Card ─────────────────────────────────────────────────────────────

const GithubCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const repo = data.repo || data.repository || '';
  const issues = Array.isArray(data.issues) ? data.issues : [];
  const prs = Array.isArray(data.prs) ? data.prs : [];
  const commits = Array.isArray(data.commits) ? data.commits : [];
  const matches = Array.isArray(data.matches) ? data.matches : [];

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      {repo && (
        <a
          href={`https://github.com/${repo}`}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-xs text-[#E8E3DA] hover:text-blue-300 font-semibold inline-flex items-center gap-1.5 no-underline transition-colors"
        >
          <span>Repository: {repo}</span>
          <ExternalLink size={11} />
        </a>
      )}

      {issues.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Issues</span>
          {issues.map((iss: any, idx: number) => {
            const issLink = iss.html_url || iss.url || (repo ? `https://github.com/${repo}/issues/${iss.number}` : '#');
            return (
              <a
                key={idx}
                href={issLink}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] hover:border-white/[0.12] transition-colors group cursor-pointer no-underline"
              >
                <span className="font-sans text-xs text-[#E8E3DA] group-hover:text-blue-300 truncate">#{iss.number} {iss.title}</span>
                <span className="font-mono text-[10px] text-[#8E8A83] flex items-center gap-1">{iss.state} <ExternalLink size={10} /></span>
              </a>
            );
          })}
        </div>
      )}

      {prs.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Pull Requests</span>
          {prs.map((pr: any, idx: number) => {
            const prLink = pr.html_url || pr.url || (repo ? `https://github.com/${repo}/pull/${pr.number}` : '#');
            return (
              <a
                key={idx}
                href={prLink}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] hover:border-white/[0.12] transition-colors group cursor-pointer no-underline"
              >
                <span className="font-sans text-xs text-[#E8E3DA] group-hover:text-emerald-300 truncate">#{pr.number} {pr.title}</span>
                <span className="font-mono text-[10px] text-emerald-400 flex items-center gap-1">{pr.state} <ExternalLink size={10} /></span>
              </a>
            );
          })}
        </div>
      )}

      {commits.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Recent Commits</span>
          {commits.slice(0, 4).map((c: any, idx: number) => {
            const commitLink = c.html_url || c.url || (repo && c.sha ? `https://github.com/${repo}/commit/${c.sha}` : '#');
            return (
              <a
                key={idx}
                href={commitLink}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] hover:border-white/[0.12] transition-colors group cursor-pointer no-underline"
              >
                <span className="font-sans text-xs text-[#E8E3DA] group-hover:text-blue-300 truncate">{c.message || c.commit?.message}</span>
                <span className="font-mono text-[10px] text-[#8E8A83] flex items-center gap-1">{c.sha ? c.sha.substring(0, 7) : ''} <ExternalLink size={10} /></span>
              </a>
            );
          })}
        </div>
      )}

      {matches.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Code Matches</span>
          {matches.map((m: any, idx: number) => (
            <div key={idx} className="p-2 rounded-lg bg-black/40 border border-white/[0.06] font-mono text-xs text-[#D1CFC0]">
              <span className="text-[#8E8A83] block">{m.path}</span>
              <span className="text-[#E8E3DA]">{m.fragment || m.snippet}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── System Status Card ──────────────────────────────────────────────────────

const SystemStatusCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const devices = Array.isArray(data.devices) ? data.devices : [];
  const procs = Array.isArray(data.processes) ? data.processes : [];
  const volume = data.volume;
  const state = data.state || data.display_power;

  const cpuPct = data.cpu_pct ?? data.cpu ?? (data.cpu_load ? Number(data.cpu_load) : undefined);
  const cpuTemp = data.cpu_temp;
  const cpuCores = data.cpu_cores ?? data.cores;

  const ramUsedGb = data.ram_used_gb !== undefined ? Number(data.ram_used_gb) : undefined;
  const ramTotalGb = data.ram_total_gb !== undefined ? Number(data.ram_total_gb) : undefined;
  const ramPct = data.ram_pct !== undefined ? Number(data.ram_pct) : (ramUsedGb && ramTotalGb ? Math.round((ramUsedGb / ramTotalGb) * 100) : undefined);

  const gpuModel = data.gpu_model;
  const gpuUtil = data.gpu_util_pct ?? data.gpu_util ?? data.gpu_pct;
  const gpuTemp = data.gpu_temp;

  const hostname = data.hostname;
  const os = data.os;
  const uptime = data.uptime;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      {/* Primary Hardware Telemetry Gauges */}
      {(cpuPct !== undefined || ramUsedGb !== undefined || gpuModel || gpuUtil !== undefined) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          {/* CPU Gauge */}
          {cpuPct !== undefined && (
            <div className="flex flex-col p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
              <div className="flex items-center justify-between text-[#8E8A83] text-[10px] font-mono uppercase tracking-wider mb-1.5">
                <span className="flex items-center gap-1.5"><Cpu size={12} className="text-[#D1CFC0]" /> CPU LOAD</span>
                {cpuTemp && <span className="text-amber-400/90">{cpuTemp}</span>}
              </div>
              <div className="flex items-baseline justify-between mb-1.5">
                <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">{cpuPct}%</span>
                {cpuCores && <span className="font-mono text-[10px] text-[#8E8A83]">{cpuCores} Cores</span>}
              </div>
              <div className="w-full h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    cpuPct > 85 ? "bg-rose-500" : cpuPct > 60 ? "bg-amber-400" : "bg-emerald-400"
                  )}
                  style={{ width: `${Math.min(100, Math.max(0, cpuPct))}%` }}
                />
              </div>
            </div>
          )}

          {/* RAM Gauge */}
          {(ramUsedGb !== undefined || ramPct !== undefined) && (
            <div className="flex flex-col p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
              <div className="flex items-center justify-between text-[#8E8A83] text-[10px] font-mono uppercase tracking-wider mb-1.5">
                <span className="flex items-center gap-1.5"><HardDrive size={12} className="text-[#D1CFC0]" /> MEMORY</span>
                {ramPct !== undefined && <span className="text-[#D1CFC0]">{ramPct}%</span>}
              </div>
              <div className="flex items-baseline justify-between mb-1.5">
                <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
                  {ramUsedGb !== undefined ? `${ramUsedGb.toFixed(1)}` : `${ramPct}%`}
                  {ramTotalGb !== undefined && <span className="text-xs font-normal text-[#8E8A83]"> / {ramTotalGb.toFixed(0)} GB</span>}
                </span>
              </div>
              <div className="w-full h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    (ramPct || 0) > 85 ? "bg-rose-500" : (ramPct || 0) > 65 ? "bg-amber-400" : "bg-sky-400"
                  )}
                  style={{ width: `${Math.min(100, Math.max(0, ramPct || 0))}%` }}
                />
              </div>
            </div>
          )}

          {/* GPU Gauge */}
          {(gpuModel || gpuUtil !== undefined) && (
            <div className="flex flex-col p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
              <div className="flex items-center justify-between text-[#8E8A83] text-[10px] font-mono uppercase tracking-wider mb-1.5">
                <span className="flex items-center gap-1.5"><Activity size={12} className="text-[#D1CFC0]" /> GPU</span>
                {gpuTemp && <span className="text-amber-400/90">{gpuTemp}</span>}
              </div>
              <div className="flex items-baseline justify-between mb-1.5">
                <span className="font-mono text-2xl font-bold text-[#E8E3DA] tabular-nums">
                  {gpuUtil !== undefined ? `${gpuUtil}%` : 'ONLINE'}
                </span>
                {gpuModel && (
                  <span className="font-sans text-[10px] text-[#8E8A83] truncate max-w-[110px]" title={gpuModel}>
                    {gpuModel.replace(/NVIDIA\s+|GeForce\s+/gi, '')}
                  </span>
                )}
              </div>
              {gpuUtil !== undefined && (
                <div className="w-full h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-500",
                      gpuUtil > 85 ? "bg-rose-500" : gpuUtil > 60 ? "bg-amber-400" : "bg-purple-400"
                    )}
                    style={{ width: `${Math.min(100, Math.max(0, gpuUtil))}%` }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Host & Environment Banner */}
      {(hostname || os || uptime || state) && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04] text-xs">
          {hostname && (
            <div>
              <span className="block font-mono text-[9px] uppercase text-[#8E8A83]">Host</span>
              <span className="font-mono text-xs text-[#E8E3DA] truncate block">{hostname}</span>
            </div>
          )}
          {uptime && (
            <div>
              <span className="block font-mono text-[9px] uppercase text-[#8E8A83]">Uptime</span>
              <span className="font-mono text-xs text-[#E8E3DA] truncate block">{uptime}</span>
            </div>
          )}
          {state && (
            <div>
              <span className="block font-mono text-[9px] uppercase text-[#8E8A83]">Display</span>
              <span className="font-mono text-xs text-emerald-400 truncate block">{state}</span>
            </div>
          )}
          {os && (
            <div>
              <span className="block font-mono text-[9px] uppercase text-[#8E8A83]">Platform</span>
              <span className="font-mono text-xs text-[#D1CFC0] truncate block" title={os}>{os}</span>
            </div>
          )}
        </div>
      )}

      {/* Audio / Display Settings fallback if not rendered above */}
      {volume !== undefined && (
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <span className="font-mono text-[11px] text-[#8E8A83] uppercase">Master Audio Output</span>
          <span className="font-mono text-sm font-bold text-[#E8E3DA]">{volume}%</span>
        </div>
      )}

      {/* Registered Hardware list */}
      {devices.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Registered Hardware</span>
          {devices.map((d: any, idx: number) => (
            <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
              <span className="font-sans text-xs text-[#E8E3DA]">{d.name || d.device_name}</span>
              <span className="font-mono text-[10px] text-emerald-400">{d.status || (d.battery ? `${d.battery}%` : 'Online')}</span>
            </div>
          ))}
        </div>
      )}

      {/* Processes list */}
      {procs.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Top Processes</span>
          {procs.slice(0, 4).map((p: any, idx: number) => (
            <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
              <span className="font-mono text-xs text-[#E8E3DA]">{p.name || p.process_name}</span>
              <span className="font-mono text-[10px] text-[#8E8A83]">CPU {p.cpu}% • RAM {p.memory_mb}MB</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Weather Card ────────────────────────────────────────────────────────────

const WeatherCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const temp = data.temperature ?? data.temp ?? '--';
  const condition = data.condition || data.description || 'Current Conditions';
  const humidity = data.humidity;
  const wind = data.wind_speed || data.wind;
  const location = data.location || data.city;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4 text-left">
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
  const link = extractLink(data) || (data.video_id ? `https://www.youtube.com/watch?v=${data.video_id}` : null);
  const thumbnail = data.thumbnail || (data.video_id ? `https://img.youtube.com/vi/${data.video_id}/hqdefault.jpg` : null);
  const snippet = data.snippet || data.description;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      {thumbnail && (
        <div className="relative w-full aspect-video max-h-48 rounded-xl overflow-hidden bg-black/50 border border-white/[0.08] group">
          <img
            src={thumbnail}
            alt={title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
          {link && (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className="absolute inset-0 flex items-center justify-center bg-black/40 hover:bg-black/20 transition-colors"
            >
              <div className="w-12 h-12 rounded-full bg-red-600/90 text-white flex items-center justify-center shadow-lg shadow-black/50 hover:scale-110 transition-transform">
                <Play size={20} fill="currentColor" className="translate-x-0.5" />
              </div>
            </a>
          )}
          {duration && (
            <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-black/80 font-mono text-[11px] text-white font-medium">
              {duration}
            </div>
          )}
        </div>
      )}

      <div>
        {link ? (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="font-sans text-lg sm:text-xl font-bold text-[#E8E3DA] hover:text-white transition-colors tracking-tight leading-snug block"
          >
            {title}
          </a>
        ) : (
          <h4 className="font-sans text-lg sm:text-xl font-bold text-[#E8E3DA] tracking-tight leading-snug">
            {title}
          </h4>
        )}
        <div className="flex items-center gap-3 mt-1.5 font-sans text-sm text-[#8E8A83]">
          {channel && <span className="text-[#D1CFC0] font-medium">{channel}</span>}
          {channel && duration && <span>•</span>}
          {duration && !thumbnail && <span className="font-mono text-xs">{duration}</span>}
        </div>
        {snippet && (
          <p className="mt-2 font-sans text-xs text-[#8E8A83] line-clamp-2 leading-relaxed">
            {snippet}
          </p>
        )}
      </div>

      {link && (
        <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-xs text-[#8E8A83] hover:text-[#E8E3DA] truncate max-w-[240px] transition-colors underline underline-offset-2"
          >
            {link}
          </a>
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 text-sm font-sans font-medium text-red-200 transition-all no-underline cursor-pointer shrink-0"
          >
            <Play size={14} fill="currentColor" />
            <span>Watch on YouTube</span>
            <ExternalLink size={12} />
          </a>
        </div>
      )}
    </div>
  );
};

// ── Spotify Card ────────────────────────────────────────────────────────────

const SpotifyCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const [liveTrack, setLiveTrack] = useState<NowPlayingTrack>(mediaService.getTrack());
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    mediaService.fetchNowPlaying();
    const unsub = mediaService.subscribe(() => {
      setLiveTrack(mediaService.getTrack());
    });
    return unsub;
  }, []);

  const isLiveValid = Boolean(
    liveTrack &&
    liveTrack.title &&
    liveTrack.title !== 'No Media Playing' &&
    liveTrack.title !== 'Player Unavailable' &&
    liveTrack.title !== 'Unknown Track'
  );

  const track = isLiveValid
    ? liveTrack.title
    : (data.track || data.track_title || data.song || data.name || data.station || data.title || 'Spotify Audio');

  const artist = isLiveValid
    ? (liveTrack.artist || 'Spotify')
    : (data.artist || (Array.isArray(data.artists) ? data.artists.join(', ') : data.artist_name) || (data.owner ? `Curated by ${data.owner}` : null) || (data.station ? 'Spotify Radio' : 'Spotify'));

  const album = isLiveValid ? (liveTrack.album || '') : (data.album || data.album_name || '');
  const playlist = data.playlist_name || data.playlist || (data.type === 'spotify_playlist' ? data.name : null);
  const station = data.station || (data.type === 'spotify_radio' ? (data.station || data.title) : null);
  const coverUrl = (isLiveValid && liveTrack.art_url) ? liveTrack.art_url : (data.cover_url || data.album_art || data.art_url || data.image || '');
  const link = extractLink(data) || (isLiveValid && liveTrack.art_url ? 'https://open.spotify.com' : undefined);
  const isPlaying = isLiveValid ? liveTrack.is_playing : Boolean(data.is_playing ?? true);

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4 text-left">
      {/* Context Badge (Playlist, Radio Station, or Target Device) */}
      {(playlist || station || data.device) && (
        <div className="flex items-center gap-2 flex-wrap">
          {playlist && (
            <span className="px-2.5 py-0.5 rounded-md font-mono text-[10px] uppercase tracking-wider bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              Playlist: {playlist}
            </span>
          )}
          {station && (
            <span className="px-2.5 py-0.5 rounded-md font-mono text-[10px] uppercase tracking-wider bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              Radio: {station}
            </span>
          )}
          {data.device && (
            <span className="px-2.5 py-0.5 rounded-md font-mono text-[10px] uppercase tracking-wider bg-white/[0.04] text-[#8E8A83] border border-white/[0.06]">
              Device: {data.device}
            </span>
          )}
        </div>
      )}

      {/* Main Track & Artwork Row */}
      <div className="flex items-center gap-4">
        <div className="relative w-16 h-16 sm:w-20 sm:h-20 rounded-xl bg-white/[0.04] border border-white/[0.1] flex items-center justify-center shrink-0 overflow-hidden shadow-lg">
          {coverUrl && !imgError ? (
            <img
              src={coverUrl}
              alt={track}
              className="w-full h-full object-cover"
              onError={() => setImgError(true)}
            />
          ) : (
            <Music size={28} strokeWidth={1.5} className="text-[#D1CFC0]" />
          )}
          {isPlaying && (
            <div className="absolute bottom-1.5 right-1.5 flex items-end gap-0.5 h-3 bg-black/60 px-1 py-0.5 rounded">
              <span className="w-0.5 h-3 bg-[#E8E3DA] rounded-full animate-pulse" />
              <span className="w-0.5 h-2 bg-[#E8E3DA] rounded-full animate-pulse delay-75" />
              <span className="w-0.5 h-2.5 bg-[#E8E3DA] rounded-full animate-pulse delay-150" />
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <span className="inline-block px-2 py-0.5 mb-1 text-[10px] font-mono uppercase tracking-widest text-[#8E8A83] bg-white/[0.04] border border-white/[0.06] rounded">
            {isPlaying ? 'Now Playing' : 'Spotify Audio'}
          </span>
          <h4 className="font-sans text-lg sm:text-xl font-bold text-[#E8E3DA] tracking-tight truncate leading-snug">
            {track}
          </h4>
          <p className="font-sans text-sm sm:text-base font-medium text-[#D1CFC0] truncate mt-0.5">
            {artist}
          </p>
          {album && (
            <p className="font-sans text-xs text-[#8E8A83] truncate mt-1 flex items-center gap-1.5">
              <Disc size={13} className="text-[#8E8A83] shrink-0" />
              <span>{album}</span>
            </p>
          )}
        </div>
      </div>

      {/* Playback Controls & Open in Spotify Link */}
      <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
        <div className="flex items-center gap-2 bg-black/40 px-3 py-1 rounded-xl border border-white/[0.06]">
          <button
            type="button"
            onClick={() => mediaService.previous()}
            className="p-1.5 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] transition-colors cursor-pointer"
            title="Previous Track"
          >
            <SkipBack size={14} />
          </button>
          <button
            type="button"
            onClick={() => mediaService.playPause()}
            className="p-1.5 rounded-lg bg-white/[0.10] text-[#E8E3DA] hover:bg-white/[0.18] transition-colors cursor-pointer"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} className="ml-0.5" />}
          </button>
          <button
            type="button"
            onClick={() => mediaService.next()}
            className="p-1.5 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] transition-colors cursor-pointer"
            title="Next Track"
          >
            <SkipForward size={14} />
          </button>
        </div>

        {link && (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-xs font-sans font-medium text-emerald-300 transition-all no-underline cursor-pointer"
          >
            <span>Open in Spotify</span>
            <ExternalLink size={13} />
          </a>
        )}
      </div>
    </div>
  );
};

// ── Recipe Card ─────────────────────────────────────────────────────────────

const RecipeCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const prepTime = data.prep_time || data.cook_time;
  const servings = data.servings;
  const rawIngredients = Array.isArray(data.ingredients) ? data.ingredients : [];
  const rawSteps = Array.isArray(data.steps) ? data.steps : (Array.isArray(data.instructions) ? data.instructions : []);
  const instructionsText = typeof data.instructions === 'string' ? data.instructions : (data.summary || data.description);
  const title = data.title || data.recipe_name || 'Recipe';
  const link = extractLink(data);

  const [checkedIngredients, setCheckedIngredients] = useState<Record<number, boolean>>({});
  const [checkedSteps, setCheckedSteps] = useState<Record<number, boolean>>({});
  const [copied, setCopied] = useState(false);

  const toggleIngredient = (idx: number) => {
    setCheckedIngredients((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const toggleStep = (idx: number) => {
    setCheckedSteps((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const handleCopy = async () => {
    let copyText = `# ${title}\n`;
    if (prepTime) copyText += `Prep / Cook Time: ${prepTime}\n`;
    if (servings) copyText += `Servings: ${servings}\n`;
    if (rawIngredients.length > 0) {
      copyText += `\n## Ingredients\n`;
      rawIngredients.forEach((item: any) => {
        const itemStr = typeof item === 'string' ? item : `${item.amount || ''} ${item.unit || ''} ${item.name || item.item || ''}`.trim();
        copyText += `- [ ] ${itemStr}\n`;
      });
    }
    if (rawSteps.length > 0) {
      copyText += `\n## Instructions\n`;
      rawSteps.forEach((step: any, i: number) => {
        const stepStr = typeof step === 'string' ? step : (step.step || step.instruction || JSON.stringify(step));
        copyText += `${i + 1}. ${stepStr}\n`;
      });
    } else if (instructionsText) {
      copyText += `\n## Instructions\n${instructionsText}\n`;
    }
    if (link) copyText += `\nLink: ${link}\n`;

    try {
      await navigator.clipboard.writeText(copyText.trim());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore clipboard write failure
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      <div className="flex items-center justify-between">
        <h4 className="font-sans text-lg font-bold text-[#E8E3DA]">{title}</h4>
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] text-xs font-mono text-[#D1CFC0] transition-colors cursor-pointer"
          title="Copy recipe checklist to clipboard"
        >
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          <span>{copied ? 'Copied!' : 'Copy Recipe'}</span>
        </button>
      </div>

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

        {rawIngredients.length > 0 && (
          <div className="flex flex-col p-3 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center gap-1.5 text-[#8E8A83] text-xs font-sans uppercase tracking-wider mb-1">
              <ChefHat size={13} strokeWidth={1.8} />
              <span>Items</span>
            </div>
            <span className="font-mono text-base sm:text-lg font-medium text-[#E8E3DA]">
              {rawIngredients.length} ingredients
            </span>
          </div>
        )}
      </div>

      {/* Interactive Ingredients Checklist */}
      {rawIngredients.length > 0 && (
        <div className="flex flex-col gap-1.5 mt-1">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">
              Ingredients Checklist ({Object.values(checkedIngredients).filter(Boolean).length}/{rawIngredients.length})
            </span>
          </div>
          <div className="flex flex-col gap-1.5 max-h-52 overflow-y-auto pr-1">
            {rawIngredients.map((item: any, idx: number) => {
              const isChecked = !!checkedIngredients[idx];
              const itemText = typeof item === 'string' ? item : `${item.amount || ''} ${item.unit || ''} ${item.name || item.item || ''}`.trim();
              return (
                <div
                  key={idx}
                  onClick={() => toggleIngredient(idx)}
                  className={cn(
                    "flex items-center gap-2.5 p-2 rounded-lg border transition-all cursor-pointer select-none",
                    isChecked
                      ? "bg-white/[0.01] border-white/[0.03] opacity-60"
                      : "bg-white/[0.03] hover:bg-white/[0.06] border-white/[0.06]"
                  )}
                >
                  <div
                    className={cn(
                      "w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors",
                      isChecked
                        ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
                        : "border-white/20 hover:border-white/40"
                    )}
                  >
                    {isChecked ? <Check size={10} /> : null}
                  </div>
                  <span
                    className={cn(
                      "font-sans text-xs",
                      isChecked ? "line-through text-[#8E8A83]" : "text-[#E8E3DA]"
                    )}
                  >
                    {itemText}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Interactive Preparation Steps or Instructions */}
      {rawSteps.length > 0 ? (
        <div className="flex flex-col gap-1.5 mt-1">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">
            Preparation Steps ({Object.values(checkedSteps).filter(Boolean).length}/{rawSteps.length})
          </span>
          <div className="flex flex-col gap-1.5 max-h-52 overflow-y-auto pr-1">
            {rawSteps.map((step: any, idx: number) => {
              const isChecked = !!checkedSteps[idx];
              const stepText = typeof step === 'string' ? step : (step.step || step.instruction || JSON.stringify(step));
              return (
                <div
                  key={idx}
                  onClick={() => toggleStep(idx)}
                  className={cn(
                    "flex items-start gap-2.5 p-2 rounded-lg border transition-all cursor-pointer select-none",
                    isChecked
                      ? "bg-white/[0.01] border-white/[0.03] opacity-60"
                      : "bg-white/[0.03] hover:bg-white/[0.06] border-white/[0.06]"
                  )}
                >
                  <div
                    className={cn(
                      "w-4 h-4 rounded border flex items-center justify-center shrink-0 mt-0.5 transition-colors",
                      isChecked
                        ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
                        : "border-white/20 hover:border-white/40"
                    )}
                  >
                    {isChecked ? <Check size={10} /> : null}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="font-mono text-[10px] text-[#8E8A83] mr-1.5">{idx + 1}.</span>
                    <span
                      className={cn(
                        "font-sans text-xs leading-relaxed",
                        isChecked ? "line-through text-[#8E8A83]" : "text-[#D1CFC0]"
                      )}
                    >
                      {stepText}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : instructionsText ? (
        <p className="font-sans text-sm text-[#D1CFC0] leading-relaxed line-clamp-4 bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
          {instructionsText}
        </p>
      ) : null}

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
  // 1. Full Portfolio & Financial Summary Card
  const isSummaryCard =
    data.type === 'finance_summary_card' ||
    (data.total_net_worth !== undefined && Array.isArray(data.accounts));

  if (isSummaryCard) {
    const netWorth = Number(data.total_net_worth || 0);
    const accounts: Array<{ id: string; name: string; balance: number; type: string; is_default?: boolean }> =
      Array.isArray(data.accounts) ? data.accounts : [];
    const debts = data.debts || {};
    const owedToUser = Number(debts.total_owed_to_user || 0);
    const userOwes = Number(debts.total_user_owes || 0);
    const recentTxns: any[] = Array.isArray(data.recent_transactions) ? data.recent_transactions : [];

    return (
      <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4 text-left">
        {/* Total Net Worth */}
        <div className="p-4 rounded-xl border border-white/[0.08] bg-white/[0.02]">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-widest flex items-center gap-1.5">
              <Wallet size={13} className="text-emerald-400" />
              Total Liquid Net Worth
            </span>
            <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-semibold">
              Live Ledger
            </span>
          </div>
          <div className="font-mono text-3xl sm:text-4xl font-bold text-[#E8E3DA] tabular-nums tracking-tight">
            ₹ {netWorth.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        {/* Multi-Account Breakdown Grid */}
        {accounts.length > 0 && (
          <div className="flex flex-col gap-2">
            <span className="font-mono text-[11px] text-[#8E8A83] uppercase tracking-wider px-0.5">
              Account Reserves
            </span>
            <div className="grid grid-cols-2 gap-2">
              {accounts.map((acc) => (
                <div
                  key={acc.id || acc.name}
                  className="p-3 rounded-xl border border-white/[0.06] bg-[#141414] hover:border-white/[0.12] transition-colors"
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-sans font-medium text-[#E8E3DA] truncate">
                      {acc.name}
                    </span>
                    <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-white/[0.06] text-[#8E8A83]">
                      {acc.type}
                    </span>
                  </div>
                  <div className="font-mono text-sm sm:text-base font-bold text-[#E8E3DA] tabular-nums">
                    ₹ {Number(acc.balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Peer Debts Ledger */}
        {(owedToUser > 0 || userOwes > 0) && (
          <div className="grid grid-cols-2 gap-2 pt-1 border-t border-white/[0.04]">
            <div className="p-2.5 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04]">
              <span className="font-mono text-[10px] text-emerald-400/90 uppercase tracking-wider block mb-0.5">
                Owed to You
              </span>
              <span className="font-mono text-sm font-bold text-emerald-300 tabular-nums">
                + ₹ {owedToUser.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div className="p-2.5 rounded-lg border border-rose-500/20 bg-rose-500/[0.04]">
              <span className="font-mono text-[10px] text-rose-400/90 uppercase tracking-wider block mb-0.5">
                You Owe
              </span>
              <span className="font-mono text-sm font-bold text-rose-300 tabular-nums">
                - ₹ {userOwes.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        )}

        {/* Recent Activity Mini-Feed */}
        {recentTxns.length > 0 && (
          <div className="flex flex-col gap-1.5 pt-2 border-t border-white/[0.04]">
            <span className="font-mono text-[11px] text-[#8E8A83] uppercase tracking-wider px-0.5">
              Recent Movements
            </span>
            <div className="flex flex-col gap-1">
              {recentTxns.slice(0, 3).map((txn, idx) => {
                const isExpense = (txn.type || '').toLowerCase().includes('exp');
                return (
                  <div
                    key={txn.id || idx}
                    className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.04] text-xs"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-sans text-[#E8E3DA] truncate">
                        {txn.description || txn.category || 'Transaction'}
                      </span>
                    </div>
                    <span
                      className={cn(
                        'font-mono font-bold tabular-nums shrink-0 ml-2',
                        isExpense ? 'text-amber-400' : 'text-emerald-400'
                      )}
                    >
                      {isExpense ? '-' : '+'} ₹ {Number(txn.amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }

  // 2. Transaction List Card
  const isListCard =
    data.type === 'finance_transaction_list_card' ||
    (Array.isArray(data.transactions) && data.transactions.length > 0);

  if (isListCard) {
    const txns: any[] = Array.isArray(data.transactions) ? data.transactions : [];
    return (
      <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-widest">
            {data.title || 'Recorded Transactions'}
          </span>
          <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-white/[0.06] text-[#D1CFC0]">
            {txns.length} ITEMS
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          {txns.map((t, idx) => {
            const isExpense = (t.type || '').toLowerCase().includes('exp');
            return (
              <div
                key={t.id || idx}
                className="flex items-center justify-between p-2.5 rounded-xl bg-[#141414] border border-white/[0.06] text-xs"
              >
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="font-sans font-medium text-[#E8E3DA] truncate">
                    {t.description || t.category || 'Transaction'}
                  </span>
                  {t.category && (
                    <span className="font-mono text-[10px] text-[#8E8A83]">
                      {t.category}
                    </span>
                  )}
                </div>
                <span
                  className={cn(
                    'font-mono text-sm font-bold tabular-nums shrink-0 ml-3',
                    isExpense ? 'text-amber-400' : 'text-emerald-400'
                  )}
                >
                  {isExpense ? '-' : '+'} ₹ {Number(t.amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // 3. Single Transaction Processed / Balance Card
  const amount = data.amount;
  const merchant = data.merchant || data.payee || data.description;
  const category = data.category;
  const account = data.account || data.bank;
  const balance = data.balance ?? data.new_balance;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-3 text-left">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-widest block mb-1">
            {data.total_balance !== undefined ? 'Total Balance' : 'Amount Processed'}
          </span>
          <span className="font-mono text-3xl sm:text-4xl font-bold text-[#E8E3DA] tabular-nums tracking-tight">
            ₹ {Number(amount !== undefined ? amount : (data.total_balance ?? 0)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
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
          <span className="font-sans text-[#8E8A83]">Details / Note</span>
          <span className="font-sans font-medium text-[#E8E3DA] truncate max-w-[65%] text-right">{merchant}</span>
        </div>
      )}

      {account && (
        <div className="flex items-center justify-between text-xs">
          <span className="font-sans text-[#8E8A83]">Account</span>
          <span className="font-mono text-[#D1CFC0]">{account}</span>
        </div>
      )}

      {balance !== undefined && (
        <div className="flex items-center justify-between text-xs pt-1 border-t border-white/[0.04]">
          <span className="font-sans text-[#8E8A83]">Account Balance After</span>
          <span className="font-mono font-bold text-emerald-400">₹ {Number(balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
      )}
    </div>
  );
};

// ── Briefing Card ───────────────────────────────────────────────────────────

const BriefingCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  const overdueTasks = Array.isArray(data.overdue_tasks) ? data.overdue_tasks : [];
  const events = Array.isArray(data.events) ? data.events : [];
  const emails = Array.isArray(data.emails) ? data.emails : [];
  const todayTasksCount = data.today_tasks_count ?? 0;
  const overdueCount = data.overdue_tasks_count ?? overdueTasks.length;

  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-4 text-left">
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
          <span className="font-sans text-[10px] text-[#8E8A83] uppercase tracking-wider">Calendar & Mail</span>
          <span className="font-mono text-xl font-semibold text-[#E8E3DA] mt-0.5">{events.length + emails.length} Sync</span>
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

      {/* Briefing Emails Preview Section */}
      {emails.length > 0 && (
        <div className="flex flex-col gap-1.5 pt-1">
          <span className="font-mono text-[10px] uppercase text-[#8E8A83] tracking-wider">Priority Correspondence</span>
          {emails.slice(0, 3).map((em: any, idx: number) => (
            <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
              <span className="font-sans text-xs text-[#E8E3DA] truncate">{em.subject || em.title}</span>
              <span className="font-mono text-[10px] text-[#8E8A83]">{em.sender || ''}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Generic Card ────────────────────────────────────────────────────────────

const GenericCard: React.FC<{ data: Record<string, any> }> = ({ data }) => {
  // Gracefully route known structures if type was generic
  if (data.emails || (data.items && Array.isArray(data.items))) {
    return <EmailListCard data={data} />;
  }
  if (data.tasks && Array.isArray(data.tasks)) {
    return <TaskListCard data={data} />;
  }
  if (data.events && Array.isArray(data.events)) {
    return <CalendarCard data={data} />;
  }

  const body = data.response || data.markdown_body || data.text || data.message;
  return (
    <div className="mt-4 pt-4 border-t border-white/[0.08] flex flex-col gap-2 text-left">
      {body ? (
        <p className="font-sans text-base text-[#D1CFC0] leading-relaxed whitespace-pre-wrap">
          <AnimatedCardText text={String(body)} />
        </p>
      ) : (
        <div className="p-3 rounded-lg bg-black/40 border border-white/[0.04] font-mono text-xs text-[#8E8A83] whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </div>
      )}
    </div>
  );
};

// ── HUD Card Renderer ───────────────────────────────────────────────────────

export const HudCard: React.FC<{ output: HudOutput; onDismiss: (id: string) => void }> = ({
  output,
  onDismiss,
}) => {
  const Icon = CARD_ICONS[output.type] || FileText;

  const renderDetail = () => {
    switch (output.type) {
      case 'email':
        if (output.data.emails || Array.isArray(output.data.items)) {
          return <EmailListCard data={output.data} />;
        }
        return <EmailCard data={output.data.email || output.data} />;
      case 'task':
        return <TaskListCard data={output.data} />;
      case 'calendar':
        return <CalendarCard data={output.data} />;
      case 'research':
        return <ResearchCard data={output.data} />;
      case 'github':
        return <GithubCard data={output.data} />;
      case 'system_status':
        return <SystemStatusCard data={output.data} />;
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

  const link = extractLink(output.data);

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
            {link ? (
              <a
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                className="font-sans text-base sm:text-lg font-bold text-[#E8E3DA] hover:text-white truncate tracking-tight flex items-center gap-1.5 no-underline group cursor-pointer"
                title={`Open: ${link}`}
              >
                <span>{output.title}</span>
                <ExternalLink size={13} className="text-[#8E8A83] group-hover:text-[#E8E3DA] opacity-80 group-hover:opacity-100 transition-opacity" />
              </a>
            ) : (
              <h3 className="font-sans text-base sm:text-lg font-bold text-[#E8E3DA] truncate tracking-tight">
                {output.title}
              </h3>
            )}
            <div className="flex items-center gap-2 font-mono text-xs text-[#8E8A83] mt-0.5">
              <span className="uppercase tracking-wider">{output.type}</span>
              <span>•</span>
              <span>{timeAgo(output.timestamp)}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {link && (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center w-8 h-8 rounded-lg border border-white/[0.08] hover:border-white/[0.18] bg-white/[0.04] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.10] transition-colors cursor-pointer"
              aria-label="Open link"
              title={`Open ${link}`}
            >
              <ExternalLink size={14} />
            </a>
          )}
          <button
            type="button"
            className="flex items-center justify-center w-8 h-8 rounded-lg border border-transparent hover:border-white/[0.1] bg-transparent text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.06] transition-colors cursor-pointer"
            onClick={() => onDismiss(output.id)}
            aria-label="Dismiss card"
          >
            <X size={15} />
          </button>
        </div>
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
      case 'email':
        return {
          title: 'UNREAD INBOX & CORRESPONDENCE',
          subtitle: 'IMAP & Gmail synchronized mailboxes',
          Icon: Mail,
        };
      case 'task':
        return {
          title: 'ACTIVE TASKS & EXECUTIVE AGENDA',
          subtitle: 'Deterministic task priorities and daily agenda',
          Icon: CheckSquare,
        };
      case 'calendar':
        return {
          title: 'GOOGLE CALENDAR & APPOINTMENTS',
          subtitle: 'Two-way synchronized Google Calendar schedule',
          Icon: Calendar,
        };
      case 'research':
        return {
          title: 'DEEP RESEARCH & WEB INTELLIGENCE',
          subtitle: 'Real-time synthesis and verified citations',
          Icon: Search,
        };
      case 'github':
        return {
          title: 'GITHUB DEV ENGINE',
          subtitle: 'Repositories, pull requests & code search',
          Icon: GitPullRequest,
        };
      case 'system_status':
        return {
          title: 'CLUSTER TELEMETRY & HARDWARE SENSORS',
          subtitle: 'System load, device connections & power state',
          Icon: Cpu,
        };
      case 'spotify':
        return {
          title: 'SPOTIFY & VINYL ENGINE',
          subtitle: 'Active MPRIS media controls & live audio telemetry',
          Icon: Music,
        };
      case 'briefing':
        return {
          title: 'EXECUTIVE BRIEFING DOSSIER',
          subtitle: 'Synchronized agenda, correspondence & daily priorities',
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
