import React, { useState, useEffect, useCallback, useRef } from 'react';
import { X, Phone, PhoneOff } from 'lucide-react';
import { motion, AnimatePresence, PanInfo } from 'motion/react';
import { notificationStore } from '../services/notification-store';
import { ProactiveAlert } from '../types/vesper';

// ── Constants ───────────────────────────────────────────────────────────────

const AUTO_DISMISS_MS = 5000;
const MAX_VISIBLE = 5;
const TOAST_GAP = 8;
const DISMISS_THRESHOLD = 120;

// ── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return 'now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  return `${Math.floor(diff / 3600)}h`;
}

// ── Single Toast ────────────────────────────────────────────────────────────

interface ToastProps {
  alert: ProactiveAlert;
  index: number;
  onDismiss: (id: string) => void;
  onResolve: (id: string, resolution: 'confirmed' | 'dismissed') => void;
}

const Toast: React.FC<ToastProps> = ({ alert, index, onDismiss, onResolve }) => {
  const [isPaused, setIsPaused] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isCall = !!alert.callState;
  const isActionable =
    isCall ||
    alert.actionRequired === true ||
    !!alert.stagedActionId ||
    !!alert.stagedAction ||
    alert.appName?.toLowerCase().includes('alfred');

  // Auto-dismiss timer (5 seconds, pause on hover).
  // Calls stay visible while ringing; actionable advisories remain in drawer!
  useEffect(() => {
    if (isPaused || (isCall && alert.callState?.state === 'ringing')) return;

    timerRef.current = setTimeout(() => {
      onDismiss(alert.id);
    }, AUTO_DISMISS_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [alert.id, isPaused, isCall, alert.callState?.state, onDismiss]);

  const handleDragEnd = useCallback(
    (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
      if (Math.abs(info.offset.x) > DISMISS_THRESHOLD) {
        onDismiss(alert.id);
      }
    },
    [alert.id, onDismiss]
  );

  const stackScale = Math.max(0.92, 1 - index * 0.03);
  const stackOpacity = Math.max(0.4, 1 - index * 0.15);

  return (
    <motion.div
      className={`relative p-4 rounded-2xl border bg-[#141414]/95 backdrop-blur-xl select-none w-full cursor-grab active:cursor-grabbing shadow-2xl ${
        isCall ? 'border-amber-400/40 shadow-[0_0_24px_rgba(245,158,11,0.12)]' : 'border-white/[0.12]'
      }`}
      style={{ zIndex: MAX_VISIBLE - index, pointerEvents: 'auto' }}
      layout
      initial={{ x: '110%', opacity: 0 }}
      animate={{
        x: 0,
        opacity: stackOpacity,
        scale: stackScale,
        y: index * (TOAST_GAP + 2),
      }}
      exit={{ x: '110%', opacity: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      drag="x"
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.3}
      onDragEnd={handleDragEnd}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded-full font-mono text-[10px] text-[#E8E3DA] uppercase tracking-wider bg-white/[0.08] border border-white/15 font-semibold">
            {alert.appName}
          </span>
          {alert.urgency === 'critical' && (
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
          )}
          {isActionable && !isCall && (
            <span className="px-1.5 py-0.2 rounded font-mono text-[9px] text-[#D1CFC0] bg-white/[0.06] border border-white/10 uppercase">
              Action Required
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-[#A1A1AA]">
            {timeAgo(alert.timestamp)}
          </span>
          <button
            type="button"
            className="flex items-center justify-center w-5 h-5 rounded-md border border-white/[0.08] bg-white/[0.04] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.12] transition-colors cursor-pointer"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onDismiss(alert.id);
            }}
          >
            <X size={11} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-col gap-1">
        <span className="font-sans text-xs font-semibold text-[#E8E3DA] leading-snug tracking-tight">
          {alert.title}
        </span>
        {alert.body && (
          <span className="font-sans text-xs text-[#D1CFC0] leading-relaxed line-clamp-3">
            {alert.body}
          </span>
        )}
      </div>

      {/* Call actions */}
      {isCall && alert.callState?.state === 'ringing' && (
        <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-white/[0.08]">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/20 bg-white/[0.12] hover:bg-white/[0.2] text-[#E8E3DA] font-mono text-xs font-semibold transition-colors cursor-pointer"
            onPointerDown={(e) => e.stopPropagation()}
          >
            <Phone size={13} />
            <span>Answer</span>
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.1] bg-transparent text-[#A1A1AA] hover:text-[#E8E3DA] hover:bg-white/[0.08] font-mono text-xs transition-colors cursor-pointer"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onDismiss(alert.id);
            }}
          >
            <PhoneOff size={13} />
            <span>Decline</span>
          </button>
        </div>
      )}

      {/* Staged action buttons */}
      {alert.actionRequired && !isCall && (
        <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-white/[0.08]">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/20 bg-white/[0.10] hover:bg-white/[0.18] text-[#E8E3DA] font-mono text-xs font-semibold transition-colors cursor-pointer"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onResolve(alert.id, 'confirmed');
            }}
          >
            <span>Confirm</span>
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.1] bg-transparent text-[#A1A1AA] hover:text-[#E8E3DA] hover:bg-white/[0.08] font-mono text-xs transition-colors cursor-pointer"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onResolve(alert.id, 'dismissed');
            }}
          >
            <span>Dismiss</span>
          </button>
        </div>
      )}
    </motion.div>
  );
};

// ── Toast Container ─────────────────────────────────────────────────────────

export const ProactiveToastContainer: React.FC = () => {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const unsub = notificationStore.subscribe(() => {
      forceUpdate((n) => n + 1);
    });
    return unsub;
  }, []);

  const handleDismiss = useCallback((id: string) => {
    notificationStore.dismissToast(id);
  }, []);

  const handleResolve = useCallback((id: string, resolution: 'confirmed' | 'dismissed') => {
    notificationStore.resolveAlert(id, resolution);
  }, []);

  const visibleAlerts = notificationStore.activeToasts.slice(0, MAX_VISIBLE);

  return (
    <div className="fixed top-16 right-4 z-[100] flex flex-col gap-2 pointer-events-none w-80">
      <AnimatePresence mode="popLayout">
        {visibleAlerts.map((alert, i) => (
          <Toast
            key={alert.id}
            alert={alert}
            index={i}
            onDismiss={handleDismiss}
            onResolve={handleResolve}
          />
        ))}
      </AnimatePresence>
    </div>
  );
};

