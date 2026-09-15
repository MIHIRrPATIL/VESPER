import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Bell, Check, Trash2, ChevronLeft, Copy, CheckCheck } from 'lucide-react';
import { notificationStore } from '../services/notification-store';
import {
  SidePanelDrawer,
  SidePanelTrigger,
  SidePanelContent,
  SidePanelHeader,
  SidePanelTitle,
  SidePanelBody,
} from './ui/side-panel-drawer';

// ── Time & Text Formatting ──────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const now = Date.now();
  const diff = Math.max(0, Math.floor((now - ts) / 1000));
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── App Brand Styling Badges (Clean, Minimal, No Neon/Glow) ──────────────────

interface AppBadgeStyle {
  label: string;
  badgeClass: string;
}

function resolveAppBadge(appName: string, pkg?: string): AppBadgeStyle {
  const name = (appName || '').toLowerCase();
  const packageLower = (pkg || '').toLowerCase();

  if (name.includes('whatsapp') || packageLower.includes('whatsapp')) {
    return {
      label: 'WhatsApp',
      badgeClass: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
    };
  }
  if (name.includes('telegram') || packageLower.includes('telegram')) {
    return {
      label: 'Telegram',
      badgeClass: 'border-sky-500/20 bg-sky-500/10 text-sky-300',
    };
  }
  if (name.includes('slack') || packageLower.includes('slack')) {
    return {
      label: 'Slack',
      badgeClass: 'border-amber-500/20 bg-amber-500/10 text-amber-300',
    };
  }
  if (
    name.includes('bank') ||
    name.includes('hdfc') ||
    name.includes('sbi') ||
    name.includes('icici') ||
    name.includes('axis') ||
    name.includes('kotak') ||
    name.includes('paytm') ||
    name.includes('phonepe') ||
    name.includes('gpay') ||
    name.includes('cred')
  ) {
    return {
      label: appName || 'Banking',
      badgeClass: 'border-amber-400/20 bg-amber-400/10 text-amber-200',
    };
  }
  if (name.includes('gmail') || name.includes('mail') || packageLower.includes('gm')) {
    return {
      label: 'Gmail',
      badgeClass: 'border-rose-500/20 bg-rose-500/10 text-rose-300',
    };
  }
  if (name.includes('messages') || name.includes('sms') || packageLower.includes('mms')) {
    return {
      label: 'Messages',
      badgeClass: 'border-purple-500/20 bg-purple-500/10 text-purple-300',
    };
  }
  if (name.includes('phone') || name.includes('call') || packageLower.includes('dialer')) {
    return {
      label: 'Phone',
      badgeClass: 'border-blue-500/20 bg-blue-500/10 text-blue-300',
    };
  }
  return {
    label: appName || 'App',
    badgeClass: 'border-white/15 bg-white/[0.06] text-[#E8E3DA]',
  };
}

// ── Filter Tabs ─────────────────────────────────────────────────────────────

type TabFilter = 'all' | 'direct_urgent' | 'promotions';

// ── Component ───────────────────────────────────────────────────────────────

export const NotificationPanel: React.FC = () => {
  const [, forceUpdate] = useState(0);
  const [activeTab, setActiveTab] = useState<TabFilter>('all');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [copiedOtpId, setCopiedOtpId] = useState<string | null>(null);

  useEffect(() => {
    const unsub = notificationStore.subscribe(() => {
      forceUpdate((n) => n + 1);
    });
    return unsub;
  }, []);

  const rawNotifications = notificationStore.notifications;
  const unreadCount = notificationStore.unreadCount;

  // Filter lists based on tab
  const directUrgentNotifications = useMemo(() => {
    return rawNotifications.filter((n) => {
      if (n.isPromo) return false;
      const cat = (n.category || '').toUpperCase();
      const prio = (n.urgency || '').toLowerCase();
      return (
        cat === 'URGENT' ||
        cat === 'DIRECT' ||
        cat === 'FINANCIAL' ||
        prio === 'critical' ||
        prio === 'high' ||
        Boolean(n.otpCode)
      );
    });
  }, [rawNotifications]);

  const promoNotifications = useMemo(() => {
    return rawNotifications.filter((n) => {
      if (n.isPromo) return true;
      const cat = (n.category || '').toUpperCase();
      return cat === 'PROMO';
    });
  }, [rawNotifications]);

  const filteredNotifications = useMemo(() => {
    if (activeTab === 'direct_urgent') return directUrgentNotifications;
    if (activeTab === 'promotions') return promoNotifications;
    return rawNotifications;
  }, [activeTab, rawNotifications, directUrgentNotifications, promoNotifications]);

  // Find recent OTP alert (if any) to display in the dedicated high-priority slot
  const recentOtpNotif = useMemo(() => {
    return rawNotifications.find((n) => Boolean(n.otpCode));
  }, [rawNotifications]);

  const handleCopyOtp = useCallback((otp: string, notifId: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(otp);
      setCopiedOtpId(notifId);
      setTimeout(() => setCopiedOtpId(null), 2500);
    }
  }, []);

  const handleMarkAllRead = useCallback(() => {
    notificationStore.markAllRead();
  }, []);

  const handleClearAll = useCallback(() => {
    notificationStore.clearAllNotifications();
  }, []);

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleOpen = useCallback(() => {
    notificationStore.markAllRead();
    notificationStore.dismissAllToasts();
  }, []);

  return (
    <SidePanelDrawer direction="right" onOpenChange={(open) => { if (open) handleOpen(); }}>
      <SidePanelTrigger asChild>
        <button
          className="group relative flex items-center gap-1.5 pl-2.5 pr-2 py-3 rounded-l-xl rounded-r-none border-y border-l border-r-0 border-white/[0.1] bg-[#1A1A1A] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-[#222222] hover:border-white/[0.2] transition-all duration-150 cursor-pointer shadow-lg select-none mr-0"
          aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        >
          <ChevronLeft
            size={13}
            strokeWidth={2.4}
            className="text-[#8E8A83] group-hover:text-[#E8E3DA] group-hover:-translate-x-0.5 transition-transform"
          />
          <Bell size={15} strokeWidth={1.8} />
          {unreadCount > 0 && (
            <span className="absolute -top-1.5 -left-1.5 min-w-[17px] h-[17px] px-1 rounded-full bg-[#E8E3DA] text-[#141414] font-mono text-[9px] font-bold leading-[17px] text-center shadow">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>
      </SidePanelTrigger>

      <SidePanelContent direction="right" variant="headroom">
        {/* Header */}
        <SidePanelHeader className="pb-3 border-b border-white/[0.08]">
          <div className="flex items-center justify-between w-full pr-6">
            <div className="flex items-center gap-2">
              <SidePanelTitle className="font-serif text-lg font-medium text-[#E8E3DA]">Notifications</SidePanelTitle>
              {unreadCount > 0 && (
                <span className="font-mono text-[10px] text-[#141414] bg-[#E8E3DA] px-2 py-0.5 rounded-full font-bold">
                  {unreadCount} new
                </span>
              )}
            </div>
          </div>
        </SidePanelHeader>

        {/* Filter Tabs Bar (Strictly Minimalist, Warm Obsidian, No Glow) */}
        <div className="px-4 pt-3 pb-2 border-b border-white/[0.06] bg-black/20">
          <div className="flex items-center gap-1 bg-[#141414] p-1 rounded-lg border border-white/[0.08]">
            <button
              type="button"
              onClick={() => setActiveTab('all')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md font-mono text-[11px] uppercase tracking-wider transition-colors cursor-pointer ${
                activeTab === 'all'
                  ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold'
                  : 'text-[#8E8A83] hover:text-[#D1CFC0]'
              }`}
            >
              <span>All</span>
              <span className="font-mono text-[9px] text-[#8E8A83] px-1 py-0.2 rounded bg-white/[0.04]">
                {rawNotifications.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('direct_urgent')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md font-mono text-[11px] uppercase tracking-wider transition-colors cursor-pointer ${
                activeTab === 'direct_urgent'
                  ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold'
                  : 'text-[#8E8A83] hover:text-[#D1CFC0]'
              }`}
            >
              <span>Direct & Urgent</span>
              <span className="font-mono text-[9px] text-[#8E8A83] px-1 py-0.2 rounded bg-white/[0.04]">
                {directUrgentNotifications.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('promotions')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md font-mono text-[11px] uppercase tracking-wider transition-colors cursor-pointer ${
                activeTab === 'promotions'
                  ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold'
                  : 'text-[#8E8A83] hover:text-[#D1CFC0]'
              }`}
            >
              <span>Promos</span>
              <span className="font-mono text-[9px] text-[#8E8A83] px-1 py-0.2 rounded bg-white/[0.04]">
                {promoNotifications.length}
              </span>
            </button>
          </div>
        </div>

        {/* Global Actions subheader */}
        {filteredNotifications.length > 0 && (
          <div className="flex items-center justify-between px-5 py-2 border-b border-white/[0.06] bg-black/10">
            <span className="font-mono text-[11px] text-[#8E8A83]">
              {filteredNotifications.length} alert{filteredNotifications.length === 1 ? '' : 's'}
            </span>
            <div className="flex items-center gap-2">
              <button
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.05] hover:bg-white/[0.10] text-[#E8E3DA] text-[11px] font-mono border border-white/[0.08] transition-colors cursor-pointer"
                onClick={handleMarkAllRead}
              >
                <CheckCheck size={12} className="text-[#D1CFC0]" />
                <span>Mark read</span>
              </button>
              <button
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.05] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] text-[11px] font-mono border border-white/[0.08] transition-colors cursor-pointer"
                onClick={handleClearAll}
              >
                <Trash2 size={12} />
                <span>Clear all</span>
              </button>
            </div>
          </div>
        )}

        <SidePanelBody className="p-4 space-y-3">
          {/* Prominent Dedicated OTP Section (Screen Top) */}
          {recentOtpNotif && recentOtpNotif.otpCode && (
            <div className="p-3.5 rounded-xl border border-white/20 bg-[#1A1A1A] flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase border border-amber-400/25 bg-amber-400/10 text-amber-200 font-semibold">
                    SECURITY CODE
                  </span>
                  <span className="font-sans text-xs text-[#E8E3DA] font-semibold truncate max-w-[170px]">
                    {recentOtpNotif.appName || recentOtpNotif.title}
                  </span>
                </div>
                <span className="font-mono text-[10px] text-[#8E8A83]">
                  {timeAgo(recentOtpNotif.timestamp)}
                </span>
              </div>

              <div className="flex items-center justify-between bg-black/40 px-3.5 py-2.5 rounded-lg border border-white/[0.08]">
                <span className="font-mono text-xl font-bold tracking-[0.25em] text-[#E8E3DA]">
                  {recentOtpNotif.otpCode}
                </span>
                <button
                  type="button"
                  onClick={() => handleCopyOtp(recentOtpNotif.otpCode!, recentOtpNotif.id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.10] hover:bg-white/[0.20] text-[#E8E3DA] font-mono text-xs font-semibold border border-white/15 transition-all cursor-pointer"
                >
                  {copiedOtpId === recentOtpNotif.id ? (
                    <>
                      <Check size={12} className="text-emerald-400" />
                      <span>Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
                      <span>Copy Code</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Empty state */}
          {filteredNotifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#8E8A83] font-sans text-xs">
              <div className="flex items-center justify-center w-10 h-10 rounded-full bg-white/[0.04] border border-white/[0.08]">
                <Bell size={18} strokeWidth={1.5} className="text-[#8E8A83]" />
              </div>
              <span className="font-mono text-xs">Zero notifications in this view</span>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {filteredNotifications.map((item, index) => {
                const isExpanded = expandedIds.has(item.id);
                const isLatest = index === 0;
                const badge = resolveAppBadge(item.appName, item.packageName);
                const isPromoItem = Boolean(item.isPromo || item.category === 'PROMO');

                return (
                  <div
                    key={item.id}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all duration-150 flex flex-col gap-1.5 ${
                      isPromoItem
                        ? 'bg-white/[0.02] hover:bg-white/[0.04] border-white/[0.05] opacity-75 hover:opacity-100'
                        : item.read
                        ? 'bg-white/[0.02] hover:bg-white/[0.05] border-white/[0.06]'
                        : 'bg-[#181818] hover:bg-[#1E1E1E] border-white/[0.14]'
                    }`}
                    onClick={() => {
                      toggleExpand(item.id);
                      if (!item.read) notificationStore.markNotificationRead(item.id);
                    }}
                  >
                    {/* Header Row: App Origin Pill + Latest Tag + Relative Time */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {/* App Origin Badge */}
                        <span
                          className={`px-1.5 py-0.5 rounded font-mono text-[9px] uppercase tracking-wider font-semibold border ${badge.badgeClass}`}
                        >
                          {badge.label}
                        </span>

                        {/* Crisp, Non-Glowing LATEST Pill */}
                        {isLatest && (
                          <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase tracking-wider font-semibold border border-white/20 bg-white/[0.08] text-[#E8E3DA]">
                            Latest
                          </span>
                        )}

                        {/* Promo Tag */}
                        {isPromoItem && (
                          <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase tracking-wider border border-white/10 bg-white/[0.03] text-[#8E8A83]">
                            Promo
                          </span>
                        )}

                        {!item.read && (
                          <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA] shrink-0" />
                        )}
                      </div>

                      <span className="font-mono text-[10px] text-[#8E8A83] shrink-0">
                        {timeAgo(item.timestamp)}
                      </span>
                    </div>

                    {/* Notification Title */}
                    <span className="font-sans text-xs font-semibold text-[#E8E3DA] truncate">
                      {item.title}
                    </span>

                    {/* Notification Body with clean expansion */}
                    <div
                      className={`font-sans text-xs text-[#D1CFC0] leading-relaxed transition-all duration-200 ${
                        isExpanded ? 'whitespace-normal max-h-[300px]' : 'truncate max-h-[20px]'
                      }`}
                    >
                      {item.body}
                    </div>

                    {/* Quick OTP inline card if item contains code */}
                    {item.otpCode && (
                      <div className="mt-1 flex items-center justify-between bg-black/30 px-2.5 py-1.5 rounded border border-white/[0.08]">
                        <span className="font-mono text-xs font-bold tracking-widest text-[#E8E3DA]">
                          CODE: {item.otpCode}
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopyOtp(item.otpCode!, item.id);
                          }}
                          className="px-2 py-0.5 rounded text-[10px] font-mono border border-white/15 bg-white/[0.08] text-[#E8E3DA] hover:bg-white/[0.15] cursor-pointer"
                        >
                          {copiedOtpId === item.id ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </SidePanelBody>
      </SidePanelContent>
    </SidePanelDrawer>
  );
};
