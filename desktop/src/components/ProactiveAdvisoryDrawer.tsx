import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { ChevronDown, Check, Trash2, ShieldCheck, Bot, Bell, CheckCheck, Copy } from 'lucide-react';
import { notificationStore } from '../services/notification-store';
import { deviceService } from '../services/device-service';
import { ProactiveAlert, MobileNotification } from '../types/vesper';
import { cn } from '../lib/utils';
import {
  SidePanelDrawer,
  SidePanelTrigger,
  SidePanelContent,
  SidePanelHeader,
  SidePanelTitle,
  SidePanelBody,
  SidePanelClose,
} from './ui/side-panel-drawer';

function timeAgo(ts: number): string {
  const diff = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

interface AppBadgeStyle {
  label: string;
  badgeClass: string;
}

function resolveAppBadge(appName: string, pkg?: string): AppBadgeStyle {
  const name = (appName || '').toLowerCase();
  const packageLower = (pkg || '').toLowerCase();

  if (name.includes('whatsapp') || packageLower.includes('whatsapp')) {
    return { label: 'WhatsApp', badgeClass: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300' };
  }
  if (name.includes('telegram') || packageLower.includes('telegram')) {
    return { label: 'Telegram', badgeClass: 'border-sky-500/20 bg-sky-500/10 text-sky-300' };
  }
  if (name.includes('slack') || packageLower.includes('slack')) {
    return { label: 'Slack', badgeClass: 'border-amber-500/20 bg-amber-500/10 text-amber-300' };
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
    return { label: appName || 'Banking', badgeClass: 'border-amber-400/20 bg-amber-400/10 text-amber-200' };
  }
  if (name.includes('gmail') || name.includes('mail') || packageLower.includes('gm')) {
    return { label: 'Gmail', badgeClass: 'border-rose-500/20 bg-rose-500/10 text-rose-300' };
  }
  if (name.includes('messages') || name.includes('sms') || packageLower.includes('mms')) {
    return { label: 'Messages', badgeClass: 'border-purple-500/20 bg-purple-500/10 text-purple-300' };
  }
  if (name.includes('phone') || name.includes('call') || packageLower.includes('dialer')) {
    return { label: 'Phone', badgeClass: 'border-blue-500/20 bg-blue-500/10 text-blue-300' };
  }
  return { label: appName || 'App', badgeClass: 'border-white/15 bg-white/[0.06] text-[#E8E3DA]' };
}

interface ProactiveAdvisoryDrawerProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
}

export const ProactiveAdvisoryDrawer: React.FC<ProactiveAdvisoryDrawerProps> = ({
  open,
  onOpenChange,
  hideTrigger = false,
}) => {
  const [, forceUpdate] = useState(0);
  const [activeTab, setActiveTab] = useState<'advisories' | 'notifications'>('advisories');
  const [notifFilterTab, setNotifFilterTab] = useState<'all' | 'direct' | 'promo'>('all');
  const [isBusy, setIsBusy] = useState<Record<string, boolean>>({});
  const [copiedOtpId, setCopiedOtpId] = useState<string | null>(null);

  useEffect(() => {
    const unsubStore = notificationStore.subscribe(() => {
      forceUpdate((n) => n + 1);
    });
    const unsubDevice = deviceService.subscribe(() => {
      forceUpdate((n) => n + 1);
    });

    deviceService.fetchStagedActions();

    return () => {
      unsubStore();
      unsubDevice();
    };
  }, []);

  const proactiveAlerts = notificationStore.activeProactiveAlerts;
  const pendingCount = notificationStore.pendingProactiveCount;
  const rawNotifications = notificationStore.notifications;
  const unreadCount = notificationStore.unreadCount;

  const filteredNotifications = useMemo(() => {
    if (notifFilterTab === 'direct') {
      return rawNotifications.filter((n) => {
        if (n.isPromo) return false;
        const cat = (n.category || '').toUpperCase();
        return cat === 'URGENT' || cat === 'DIRECT' || cat === 'FINANCIAL' || Boolean(n.otpCode);
      });
    }
    if (notifFilterTab === 'promo') {
      return rawNotifications.filter((n) => n.isPromo || (n.category || '').toUpperCase() === 'PROMO');
    }
    return rawNotifications;
  }, [notifFilterTab, rawNotifications]);

  const handleResolve = useCallback(async (alert: ProactiveAlert, resolution: 'confirmed' | 'dismissed') => {
    setIsBusy((prev) => ({ ...prev, [alert.id]: true }));
    try {
      await notificationStore.resolveAlert(alert.id, resolution);
    } finally {
      setIsBusy((prev) => ({ ...prev, [alert.id]: false }));
    }
  }, []);

  const handleCopyCode = useCallback((code: string, id: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(code);
      setCopiedOtpId(id);
      setTimeout(() => setCopiedOtpId(null), 2500);
    }
  }, []);

  const handleClearAllAdvisories = useCallback(() => {
    notificationStore.dismissAllAlerts();
  }, []);

  const handleMarkAllRead = useCallback(() => {
    notificationStore.markAllRead();
  }, []);

  const handleClearAllNotifications = useCallback(() => {
    notificationStore.clearAllNotifications();
  }, []);

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      notificationStore.dismissAllToasts();
    }
    if (onOpenChange) {
      onOpenChange(nextOpen);
    }
  }, [onOpenChange]);

  return (
    <SidePanelDrawer
      direction="top"
      open={open}
      onOpenChange={handleOpenChange}
    >
      <SidePanelTrigger asChild>
        <button
          type="button"
          className={cn(
            "group relative flex items-center gap-2 px-3 py-1.5 rounded-xl border border-white/[0.12] bg-[#181818]/90 hover:bg-[#222222] hover:border-white/[0.22] text-[#8E8A83] hover:text-[#E8E3DA] backdrop-blur-xl transition-all duration-150 cursor-pointer shadow-lg select-none",
            hideTrigger && "hidden"
          )}
          aria-label={`Proactive Advisories${pendingCount > 0 ? ` (${pendingCount} pending)` : ''}`}
        >
          <span className="w-2 h-2 rounded-full bg-amber-400/80 shrink-0" />
          <span className="font-mono text-xs uppercase tracking-wider font-medium hidden sm:inline">
            Advisories
          </span>
          {pendingCount > 0 && (
            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#E8E3DA] text-[#141414] font-mono text-[10px] font-bold leading-[18px] text-center">
              {pendingCount > 9 ? '9+' : pendingCount}
            </span>
          )}
          <ChevronDown
            size={13}
            strokeWidth={2.4}
            className="text-[#8E8A83] group-hover:text-[#E8E3DA] group-hover:translate-y-0.5 transition-transform"
          />
        </button>
      </SidePanelTrigger>

      <SidePanelContent
        direction="top"
        className="max-w-3xl mx-auto max-h-[82vh] border-x border-b border-white/[0.14] rounded-b-2xl bg-[#141414]/98 backdrop-blur-2xl shadow-2xl"
      >
        <SidePanelHeader className="px-6 py-4 border-b border-white/[0.08] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-white/[0.06] border border-white/10">
              {activeTab === 'advisories' ? (
                <Bot size={17} className="text-[#E8E3DA]" />
              ) : (
                <Bell size={17} className="text-[#E8E3DA]" />
              )}
            </div>
            <div className="flex flex-col text-left">
              <SidePanelTitle className="font-mono text-sm uppercase tracking-widest text-[#E8E3DA] font-semibold flex items-center gap-2">
                <span>{activeTab === 'advisories' ? 'PROACTIVE ADVISORIES' : 'COMPANION NOTIFICATIONS'}</span>
                {activeTab === 'advisories' && pendingCount > 0 && (
                  <span className="font-mono text-[10px] text-amber-300 px-2 py-0.5 rounded-full bg-amber-400/10 border border-amber-400/20 font-semibold lowercase">
                    {pendingCount} pending
                  </span>
                )}
                {activeTab === 'notifications' && unreadCount > 0 && (
                  <span className="font-mono text-[10px] text-[#141414] bg-[#E8E3DA] px-2 py-0.5 rounded-full font-bold">
                    {unreadCount} unread
                  </span>
                )}
              </SidePanelTitle>
              <span className="font-sans text-xs text-[#8E8A83]">
                {activeTab === 'advisories'
                  ? 'Autonomous recommendations, staged ledger entries, and executive sentry briefings'
                  : 'Synchronized mobile alerts, WhatsApp messages, and bank communications'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Tab switch buttons */}
            <div className="flex items-center gap-1 bg-black/40 p-1 rounded-lg border border-white/[0.08]">
              <button
                type="button"
                onClick={() => setActiveTab('advisories')}
                className={`px-3 py-1 rounded font-mono text-xs uppercase tracking-wider transition-colors cursor-pointer ${
                  activeTab === 'advisories'
                    ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold'
                    : 'text-[#8E8A83] hover:text-[#D1CFC0]'
                }`}
              >
                Advisories ({pendingCount})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('notifications')}
                className={`px-3 py-1 rounded font-mono text-xs uppercase tracking-wider transition-colors cursor-pointer ${
                  activeTab === 'notifications'
                    ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold'
                    : 'text-[#8E8A83] hover:text-[#D1CFC0]'
                }`}
              >
                Notifications ({rawNotifications.length})
              </button>
            </div>

            <SidePanelClose className="px-2.5 py-1 rounded-md text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] font-mono text-xs transition-colors cursor-pointer">
              Close
            </SidePanelClose>
          </div>
        </SidePanelHeader>

        {/* Subheader Toolbar */}
        {activeTab === 'advisories' ? (
          proactiveAlerts.length > 0 && (
            <div className="flex items-center justify-between px-6 py-2 border-b border-white/[0.06] bg-black/30 font-mono text-[11px]">
              <span className="text-[#8E8A83]">
                Active focus items awaiting confirmation
              </span>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] border border-white/[0.08] transition-colors cursor-pointer"
                onClick={handleClearAllAdvisories}
              >
                <Trash2 size={12} />
                <span>Dismiss all</span>
              </button>
            </div>
          )
        ) : (
          <div className="flex items-center justify-between px-6 py-2 border-b border-white/[0.06] bg-black/30 font-mono text-[11px]">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setNotifFilterTab('all')}
                className={`px-2 py-0.5 rounded text-[10px] font-mono cursor-pointer transition-colors ${
                  notifFilterTab === 'all' ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold' : 'text-[#8E8A83]'
                }`}
              >
                All ({rawNotifications.length})
              </button>
              <button
                type="button"
                onClick={() => setNotifFilterTab('direct')}
                className={`px-2 py-0.5 rounded text-[10px] font-mono cursor-pointer transition-colors ${
                  notifFilterTab === 'direct' ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold' : 'text-[#8E8A83]'
                }`}
              >
                Direct & Urgent
              </button>
              <button
                type="button"
                onClick={() => setNotifFilterTab('promo')}
                className={`px-2 py-0.5 rounded text-[10px] font-mono cursor-pointer transition-colors ${
                  notifFilterTab === 'promo' ? 'bg-white/[0.12] text-[#E8E3DA] font-semibold' : 'text-[#8E8A83]'
                }`}
              >
                Promos
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-white/[0.04] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] border border-white/[0.08] transition-colors cursor-pointer"
                onClick={handleMarkAllRead}
              >
                <CheckCheck size={11} />
                <span>Mark read</span>
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-white/[0.04] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] border border-white/[0.08] transition-colors cursor-pointer"
                onClick={handleClearAllNotifications}
              >
                <Trash2 size={11} />
                <span>Clear</span>
              </button>
            </div>
          </div>
        )}

        <SidePanelBody className="p-6 overflow-y-auto space-y-3 max-h-[calc(82vh-130px)]">
          {activeTab === 'advisories' ? (
            proactiveAlerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#8E8A83] font-sans text-xs">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-white/[0.04] border border-white/[0.08]">
                  <ShieldCheck size={22} strokeWidth={1.5} className="text-[#8E8A83]" />
                </div>
                <span className="font-mono text-xs uppercase tracking-wider text-[#D1CFC0]">
                  Zero pending proactive matters
                </span>
                <p className="text-center text-[#8E8A83] max-w-sm">
                  All autonomous proposals, staged tasks, and return briefings have been resolved.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {proactiveAlerts.map((alert) => {
                  const busy = !!isBusy[alert.id];
                  const staged = (alert.stagedAction || {}) as Record<string, any>;
                  const isOtp = alert.domain === 'security' || staged.action === 'display_otp';
                  const isLedger = alert.domain === 'finance' || staged.action === 'log_transaction';

                  // ── SPECIALIZED CARD: OTP VERIFICATION DISPLAY ──
                  if (isOtp) {
                    const otpCode = staged.params?.code || (alert.body.match(/\b\d{4,8}\b/) || [])[0] || '';
                    const otpSource = staged.params?.source || alert.appName || 'Security';

                    return (
                      <div
                        key={alert.id}
                        className="p-4 rounded-xl border border-white/20 bg-[#1A1A1A] flex flex-col gap-3"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-full font-mono text-[10px] uppercase border border-amber-400/25 bg-amber-400/10 text-amber-200 font-semibold">
                              SECURITY VERIFICATION CODE
                            </span>
                            <span className="font-sans text-xs font-semibold text-[#E8E3DA]">
                              {otpSource}
                            </span>
                          </div>
                          <span className="font-mono text-[11px] text-[#8E8A83]">
                            {timeAgo(alert.timestamp)}
                          </span>
                        </div>

                        {/* Monospace Code Display */}
                        <div className="flex items-center justify-between bg-black/40 px-4 py-3 rounded-lg border border-white/[0.10]">
                          <span className="font-mono text-2xl font-bold tracking-[0.3em] text-[#E8E3DA]">
                            {otpCode}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleCopyCode(otpCode, alert.id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white/[0.10] hover:bg-white/[0.20] text-[#E8E3DA] font-mono text-xs font-semibold border border-white/15 transition-all cursor-pointer"
                          >
                            {copiedOtpId === alert.id ? (
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

                        <div className="flex items-center justify-between pt-2 border-t border-white/[0.06]">
                          <span className="font-sans text-xs text-[#8E8A83]">
                            {alert.body}
                          </span>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleResolve(alert, 'dismissed')}
                            className="px-3 py-1 rounded border border-white/[0.1] bg-transparent hover:bg-white/[0.08] text-[#8E8A83] hover:text-[#E8E3DA] font-mono text-xs cursor-pointer"
                          >
                            Dismiss
                          </button>
                        </div>
                      </div>
                    );
                  }

                  // ── SPECIALIZED CARD: FINANCIAL LEDGER ADVISORY ──
                  if (isLedger) {
                    const amount = Number(staged.params?.amount || 0);
                    const txType = (staged.params?.transaction_type || staged.params?.type || 'expense').toUpperCase();
                    const category = staged.params?.category || 'General';
                    const description = staged.params?.description || alert.title;

                    return (
                      <div
                        key={alert.id}
                        className="p-4 rounded-xl border border-white/[0.15] bg-[#181818] flex flex-col gap-3"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-full font-mono text-[10px] uppercase border border-amber-400/25 bg-amber-400/10 text-amber-200 font-semibold">
                              PROACTIVE LEDGER ADVISORY
                            </span>
                            <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase border border-white/10 bg-white/[0.04] text-[#D1CFC0]">
                              {category}
                            </span>
                          </div>
                          <span className="font-mono text-[11px] text-[#8E8A83]">
                            {timeAgo(alert.timestamp)}
                          </span>
                        </div>

                        <div className="flex items-baseline justify-between">
                          <span className="font-sans text-sm font-semibold text-[#E8E3DA]">
                            {description}
                          </span>
                          <span className="font-mono text-lg font-bold text-[#E8E3DA]">
                            {txType === 'INCOME' ? '+' : '-'}₹{amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        </div>

                        {alert.body && (
                          <span className="font-sans text-xs text-[#8E8A83] leading-relaxed">
                            {alert.body}
                          </span>
                        )}

                        <div className="flex items-center justify-between pt-2.5 mt-1 border-t border-white/[0.06]">
                          <span className="font-mono text-[10px] text-[#8E8A83]">
                            Authorize entry to Supabase ledger
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => handleResolve(alert, 'dismissed')}
                              className="px-3 py-1.5 rounded-lg border border-white/[0.1] bg-transparent hover:bg-white/[0.08] text-[#8E8A83] hover:text-[#E8E3DA] font-mono text-xs transition-colors cursor-pointer disabled:opacity-50"
                            >
                              Ignore
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => handleResolve(alert, 'confirmed')}
                              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-white/20 bg-white/[0.12] hover:bg-white/[0.20] text-[#E8E3DA] font-mono text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
                            >
                              <Check size={12} />
                              <span>Log to Ledger</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  // ── STANDARD PROACTIVE ADVISORY CARD ──
                  return (
                    <div
                      key={alert.id}
                      className="p-4 rounded-xl border border-white/[0.12] bg-[#181818] flex flex-col gap-3"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-full font-mono text-[10px] text-[#E8E3DA] uppercase tracking-wider bg-white/[0.08] border border-white/15 font-semibold">
                            {alert.appName || 'Alfred'}
                          </span>
                          {alert.urgency && (
                            <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase border border-white/10 bg-white/[0.04] text-[#8E8A83]">
                              {alert.urgency}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[11px] text-[#8E8A83]">
                          {timeAgo(alert.timestamp)}
                        </span>
                      </div>

                      <div className="flex flex-col gap-1 text-left">
                        <span className="font-sans text-sm font-semibold text-[#E8E3DA] tracking-tight">
                          {alert.title}
                        </span>
                        {alert.body && (
                          <span className="font-sans text-xs text-[#D1CFC0] leading-relaxed">
                            {alert.body}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center justify-between pt-2.5 mt-1 border-t border-white/[0.06]">
                        <span className="font-mono text-[10px] text-[#8E8A83]">
                          {alert.actionRequired ? 'Awaiting authorization' : 'Advisory dispatch'}
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleResolve(alert, 'dismissed')}
                            className="px-3 py-1.5 rounded-lg border border-white/[0.1] bg-transparent hover:bg-white/[0.08] text-[#8E8A83] hover:text-[#E8E3DA] font-mono text-xs transition-colors cursor-pointer disabled:opacity-50"
                          >
                            Dismiss
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleResolve(alert, 'confirmed')}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-white/20 bg-white/[0.12] hover:bg-white/[0.20] text-[#E8E3DA] font-mono text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
                          >
                            <Check size={12} />
                            <span>Confirm</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            filteredNotifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#8E8A83] font-sans text-xs">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-white/[0.04] border border-white/[0.08]">
                  <Bell size={22} strokeWidth={1.5} className="text-[#8E8A83]" />
                </div>
                <span className="font-mono text-xs uppercase tracking-wider text-[#D1CFC0]">
                  No notifications in this view
                </span>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {filteredNotifications.map((notif: MobileNotification, index: number) => {
                  const badge = resolveAppBadge(notif.appName, notif.packageName);
                  const isLatest = index === 0;
                  const isPromo = Boolean(notif.isPromo || notif.category === 'PROMO');

                  return (
                    <div
                      key={notif.id}
                      className={`p-3.5 rounded-xl border transition-all text-left flex flex-col gap-1.5 ${
                        isPromo
                          ? 'bg-white/[0.02] border-white/[0.05] opacity-75'
                          : !notif.read
                          ? 'border-white/[0.16] bg-[#181818]'
                          : 'border-white/[0.06] bg-[#141414] opacity-85'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`px-1.5 py-0.5 rounded font-mono text-[9px] uppercase font-semibold border ${badge.badgeClass}`}>
                            {badge.label}
                          </span>
                          {isLatest && (
                            <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase border border-white/20 bg-white/[0.08] text-[#E8E3DA]">
                              Latest
                            </span>
                          )}
                          {isPromo && (
                            <span className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase border border-white/10 bg-white/[0.03] text-[#8E8A83]">
                              Promo
                            </span>
                          )}
                          <span className="font-sans text-xs font-semibold text-[#E8E3DA]">
                            {notif.title}
                          </span>
                        </div>
                        <span className="font-mono text-[10px] text-[#8E8A83]">
                          {timeAgo(notif.timestamp)}
                        </span>
                      </div>
                      <p className="font-sans text-xs text-[#D1CFC0] leading-relaxed pl-1">
                        {notif.body}
                      </p>
                    </div>
                  );
                })}
              </div>
            )
          )}
        </SidePanelBody>
      </SidePanelContent>
    </SidePanelDrawer>
  );
};
