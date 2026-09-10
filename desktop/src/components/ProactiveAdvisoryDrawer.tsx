import React, { useState, useEffect, useCallback } from 'react';
import { Sparkles, ChevronDown, Check, Trash2, ShieldCheck, Bot, Bell, CheckCheck } from 'lucide-react';
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
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
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
  const [isBusy, setIsBusy] = useState<Record<string, boolean>>({});

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
  const notifications = notificationStore.notifications;
  const unreadCount = notificationStore.unreadCount;

  const handleResolve = useCallback(async (alert: ProactiveAlert, resolution: 'confirmed' | 'dismissed') => {
    setIsBusy((prev) => ({ ...prev, [alert.id]: true }));
    try {
      await notificationStore.resolveAlert(alert.id, resolution);
    } finally {
      setIsBusy((prev) => ({ ...prev, [alert.id]: false }));
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
          <Sparkles
            size={14}
            className={pendingCount > 0 ? "text-amber-400 animate-pulse" : "text-[#8E8A83] group-hover:text-[#E8E3DA]"}
          />
          <span className="font-mono text-xs uppercase tracking-wider font-medium hidden sm:inline">
            Advisories
          </span>
          {pendingCount > 0 && (
            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#E8E3DA] text-[#141414] font-mono text-[10px] font-bold leading-[18px] text-center shadow">
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
                  ? 'Autonomous recommendations, staged tasks, and executive sentry briefings'
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
                Notifications ({notifications.length})
              </button>
            </div>

            <SidePanelClose className="px-2.5 py-1 rounded-md text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] font-mono text-xs transition-colors cursor-pointer">
              Close
            </SidePanelClose>
          </div>
        </SidePanelHeader>

        {/* Actions Subheader */}
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
          notifications.length > 0 && (
            <div className="flex items-center justify-between px-6 py-2 border-b border-white/[0.06] bg-black/30 font-mono text-[11px]">
              <span className="text-[#8E8A83]">
                Device correspondence stream
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] border border-white/[0.08] transition-colors cursor-pointer"
                  onClick={handleMarkAllRead}
                >
                  <CheckCheck size={12} />
                  <span>Mark all read</span>
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] border border-white/[0.08] transition-colors cursor-pointer"
                  onClick={handleClearAllNotifications}
                >
                  <Trash2 size={12} />
                  <span>Clear stream</span>
                </button>
              </div>
            </div>
          )
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
                  const isCritical = alert.urgency === 'critical';

                  return (
                    <div
                      key={alert.id}
                      className={`p-4 rounded-xl border bg-[#181818]/90 border-white/[0.10] flex flex-col gap-3 transition-all ${
                        isCritical ? 'border-amber-400/30 shadow-[0_0_20px_rgba(245,158,11,0.08)]' : ''
                      }`}
                    >
                      {/* Header */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-full font-mono text-[10px] text-[#E8E3DA] uppercase tracking-wider bg-white/[0.08] border border-white/15 font-semibold">
                            {alert.appName || 'Alfred'}
                          </span>
                          {alert.urgency && (
                            <span className={`px-2 py-0.5 rounded-full font-mono text-[9px] uppercase tracking-wider font-semibold ${
                              alert.urgency === 'critical' ? 'bg-amber-400/15 text-amber-300 border border-amber-400/30' : 'bg-white/[0.04] text-[#A1A1AA] border border-white/10'
                            }`}>
                              {alert.urgency}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[11px] text-[#8E8A83]">
                          {timeAgo(alert.timestamp)}
                        </span>
                      </div>

                      {/* Title & Body */}
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

                      {/* Interactive Action Bar */}
                      <div className="flex items-center justify-between pt-2.5 mt-1 border-t border-white/[0.06]">
                        <span className="font-mono text-[10px] text-[#8E8A83]">
                          {alert.actionRequired ? 'Awaiting human authorization' : 'Advisory notification'}
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleResolve(alert, 'dismissed')}
                            className="px-3 py-1.5 rounded-lg border border-white/[0.1] bg-transparent hover:bg-white/[0.08] text-[#A1A1AA] hover:text-[#E8E3DA] font-mono text-xs transition-colors cursor-pointer disabled:opacity-50"
                          >
                            Dismiss
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleResolve(alert, 'confirmed')}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-white/20 bg-white/[0.12] hover:bg-white/[0.22] text-[#E8E3DA] font-mono text-xs font-semibold transition-all cursor-pointer shadow hover:scale-105 active:scale-95 disabled:opacity-50"
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
            notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#8E8A83] font-sans text-xs">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-white/[0.04] border border-white/[0.08]">
                  <Bell size={22} strokeWidth={1.5} className="text-[#8E8A83]" />
                </div>
                <span className="font-mono text-xs uppercase tracking-wider text-[#D1CFC0]">
                  No device notifications
                </span>
                <p className="text-center text-[#8E8A83] max-w-sm">
                  Incoming mobile communications from WhatsApp, SMS, and Android companion will appear here.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {notifications.map((notif: MobileNotification) => (
                  <div
                    key={notif.id}
                    className={`p-3.5 rounded-xl border bg-[#181818]/90 transition-all text-left flex flex-col gap-1.5 ${
                      !notif.read ? 'border-white/[0.18] bg-[#1c1c1c]' : 'border-white/[0.06] opacity-80'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded font-mono text-[10px] text-[#E8E3DA] uppercase bg-white/[0.08] border border-white/10 font-medium">
                          {notif.appName || 'Phone'}
                        </span>
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
                ))}
              </div>
            )
          )}
        </SidePanelBody>
      </SidePanelContent>
    </SidePanelDrawer>
  );
};
