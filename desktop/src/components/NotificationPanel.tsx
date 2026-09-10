import React, { useState, useEffect, useCallback } from 'react';
import { Bell, Check, Trash2, ChevronLeft } from 'lucide-react';
import { notificationStore } from '../services/notification-store';
import { MobileNotification } from '../types/vesper';
import {
  SidePanelDrawer,
  SidePanelTrigger,
  SidePanelContent,
  SidePanelHeader,
  SidePanelTitle,
  SidePanelBody,
} from './ui/side-panel-drawer';

// ── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return 'now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function appInitial(name: string): string {
  return (name || '?')[0].toUpperCase();
}

// ── Grouped Notifications ───────────────────────────────────────────────────

interface NotifGroup {
  appName: string;
  items: MobileNotification[];
}

function groupByApp(notifications: readonly MobileNotification[]): NotifGroup[] {
  const map = new Map<string, MobileNotification[]>();
  for (const n of notifications) {
    const key = n.appName || 'Unknown';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(n);
  }
  return Array.from(map.entries()).map(([appName, items]) => ({ appName, items }));
}

// ── Component ───────────────────────────────────────────────────────────────

export const NotificationPanel: React.FC = () => {
  const [, forceUpdate] = useState(0);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    const unsub = notificationStore.subscribe(() => {
      forceUpdate((n) => n + 1);
    });
    return unsub;
  }, []);

  const notifications = notificationStore.notifications;
  const unreadCount = notificationStore.unreadCount;
  const groups = groupByApp(notifications);

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
        <SidePanelHeader className="pb-3 border-b border-white/[0.08]">
          <div className="flex items-center justify-between w-full pr-6">
            <div className="flex items-center gap-2">
              <SidePanelTitle className="font-serif text-lg font-medium text-[#E8E3DA]">Notifications</SidePanelTitle>
              {unreadCount > 0 && (
                <span className="font-mono text-[10px] text-[#E8E3DA] px-2 py-0.5 rounded-full bg-white/[0.10] border border-white/20 font-semibold">
                  {unreadCount} new
                </span>
              )}
            </div>
          </div>
        </SidePanelHeader>

        {/* Actions bar */}
        {notifications.length > 0 && (
          <div className="flex items-center gap-2 px-5 py-2.5 border-b border-white/[0.06] bg-black/20">
            <button
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.05] hover:bg-white/[0.12] text-[#E8E3DA] text-[11px] font-mono border border-white/[0.08] transition-colors cursor-pointer"
              onClick={handleMarkAllRead}
            >
              <Check size={12} className="text-[#D1CFC0]" />
              <span>Mark all read</span>
            </button>
            <button
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.05] hover:bg-white/[0.12] text-[#8E8A83] hover:text-[#E8E3DA] text-[11px] font-mono border border-white/[0.08] transition-colors cursor-pointer"
              onClick={handleClearAll}
            >
              <Trash2 size={12} />
              <span>Clear all</span>
            </button>
          </div>
        )}

        <SidePanelBody className="p-4 space-y-4">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#8E8A83] font-sans text-xs">
              <div className="flex items-center justify-center w-10 h-10 rounded-full bg-white/[0.04] border border-white/[0.08]">
                <Bell size={18} strokeWidth={1.5} className="text-[#8E8A83]" />
              </div>
              <span className="font-mono text-xs">Zero unread notifications</span>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {groups.map((group) => (
                <div key={group.appName} className="flex flex-col gap-2">
                  {/* Group header */}
                  <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-2">
                      <span className="flex items-center justify-center w-5 h-5 rounded-md bg-white/[0.08] text-[#E8E3DA] font-mono text-[10px] font-bold border border-white/10">
                        {appInitial(group.appName)}
                      </span>
                      <span className="font-mono text-xs font-semibold text-[#E8E3DA] uppercase tracking-wider">
                        {group.appName}
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-[#A1A1AA] px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06]">
                      {group.items.length}
                    </span>
                  </div>

                  {/* Items */}
                  <div className="flex flex-col gap-2">
                    {group.items.map((item) => {
                      const isExpanded = expandedIds.has(item.id);
                      return (
                        <div
                          key={item.id}
                          className={`p-3.5 rounded-xl border cursor-pointer transition-all duration-150 ${
                            item.read
                              ? 'bg-white/[0.02] hover:bg-white/[0.05] border-white/[0.06]'
                              : 'bg-white/[0.05] hover:bg-white/[0.08] border-white/[0.16] shadow-[0_0_15px_rgba(255,255,255,0.03)]'
                          }`}
                          onClick={() => {
                            toggleExpand(item.id);
                            if (!item.read) notificationStore.markNotificationRead(item.id);
                          }}
                        >
                          <div className="flex items-start justify-between gap-2.5">
                            <div className="flex items-center gap-2 min-w-0">
                              {!item.read && (
                                <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA] shrink-0 animate-pulse" />
                              )}
                              <span className="font-sans text-xs font-semibold text-[#E8E3DA] truncate">
                                {item.title}
                              </span>
                            </div>
                            <span className="font-mono text-[10px] text-[#8E8A83] shrink-0">
                              {timeAgo(item.timestamp)}
                            </span>
                          </div>
                          <div
                            className={`font-sans text-xs text-[#D1CFC0] leading-relaxed mt-1 transition-all duration-200 ${
                              isExpanded
                                ? 'whitespace-normal max-h-[300px]'
                                : 'truncate max-h-[20px]'
                            }`}
                          >
                            {item.body}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </SidePanelBody>
      </SidePanelContent>
    </SidePanelDrawer>
  );
};
