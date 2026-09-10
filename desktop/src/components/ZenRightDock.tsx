import React, { useState, useEffect } from 'react';
import { Bell, LayoutGrid, Receipt, Terminal } from 'lucide-react';
import { notificationStore } from '../services/notification-store';
import { cn } from '../lib/utils';

interface ZenRightDockProps {
  activeView: string;
  onSelectView: (view: string) => void;
  onOpenNotifications: () => void;
}

export const ZenRightDock: React.FC<ZenRightDockProps> = ({
  activeView,
  onSelectView,
  onOpenNotifications,
}) => {
  const [heldCount, setHeldCount] = useState<number>(notificationStore.heldNotificationsCount);

  useEffect(() => {
    const unsub = notificationStore.subscribe(() => {
      setHeldCount(notificationStore.heldNotificationsCount);
    });
    return unsub;
  }, []);

  const items = [
    {
      id: 'notifications',
      label: 'Notifications & Advisories',
      shortcut: 'Held Alerts',
      icon: Bell,
      badge: heldCount > 0 ? heldCount : undefined,
      onClick: onOpenNotifications,
      isActive: false,
    },
    {
      id: 'center',
      label: 'Workstation Cockpit',
      shortcut: 'Cockpit',
      icon: LayoutGrid,
      onClick: () => onSelectView('center'),
      isActive: activeView === 'center',
    },
    {
      id: 'transactions',
      label: 'Financial Ledger',
      shortcut: 'Ledger',
      icon: Receipt,
      onClick: () => onSelectView('transactions'),
      isActive: activeView === 'transactions',
    },
    {
      id: 'logs',
      label: 'Event Stream & Logs',
      shortcut: 'Logs',
      icon: Terminal,
      onClick: () => onSelectView('logs'),
      isActive: activeView === 'logs',
    },
  ];

  return (
    <aside
      className="h-full w-14 flex flex-col items-center justify-center py-6 px-1 border-l border-white/[0.08] bg-[#101010]/90 backdrop-blur-md select-none z-30"
      aria-label="Zen Quick Navigation Dock"
    >
      {/* 4 Essential Actions */}
      <nav className="flex flex-col items-center gap-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.id} className="relative group">
              <button
                type="button"
                onClick={item.onClick}
                className={cn(
                  "relative w-10 h-10 rounded-xl flex items-center justify-center transition-all cursor-pointer border",
                  item.isActive
                    ? "bg-white/[0.14] text-white border-white/20 shadow-[0_2px_12px_rgba(0,0,0,0.5)]"
                    : "bg-white/[0.04] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] border-white/[0.06]"
                )}
                aria-label={item.label}
              >
                <Icon size={16} strokeWidth={1.75} />
                {typeof item.badge === 'number' && item.badge > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-white/20 text-[#E8E3DA] font-mono text-[9px] font-bold flex items-center justify-center border border-black/40">
                    {item.badge}
                  </span>
                )}
              </button>

              {/* Minimalist Hover Tooltip */}
              <div className="absolute right-full top-1/2 -translate-y-1/2 mr-3 px-2.5 py-1.5 rounded-lg bg-[#181818] border border-white/10 shadow-2xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 flex flex-col gap-0.5 text-left">
                <span className="font-sans text-xs font-medium text-[#E8E3DA]">{item.label}</span>
                <span className="font-mono text-[9px] text-[#8E8A83]">{item.shortcut}</span>
              </div>
            </div>
          );
        })}
      </nav>
    </aside>
  );
};

export default ZenRightDock;
