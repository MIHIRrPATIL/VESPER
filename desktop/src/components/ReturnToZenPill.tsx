import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { ArrowLeft } from 'lucide-react';
import { zenStore } from '../services/zen-store';

interface ReturnToZenPillProps {
  secondsRemaining?: number;
  onReturnToZen: () => void;
}

export const ReturnToZenPill: React.FC<ReturnToZenPillProps> = ({
  secondsRemaining: propSeconds,
  onReturnToZen,
}) => {
  const [storeSeconds, setStoreSeconds] = useState(zenStore.secondsRemaining);

  useEffect(() => {
    return zenStore.subscribe(() => {
      setStoreSeconds(zenStore.secondsRemaining);
    });
  }, []);

  const secondsRemaining = typeof propSeconds === 'number' ? propSeconds : storeSeconds;

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.2 }}
      className="fixed top-4 left-1/2 -translate-x-1/2 z-[55] select-none"
    >
      <button
        type="button"
        onClick={onReturnToZen}
        className="flex items-center gap-3 px-4 py-1.5 rounded-full border border-white/15 bg-[#141414]/95 hover:bg-[#1C1C1C] text-[#E8E3DA] shadow-[0_4px_24px_rgba(0,0,0,0.6)] backdrop-blur-xl transition-all cursor-pointer group"
      >
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA]/70" />
          <span className="font-mono text-[10px] uppercase tracking-wider text-[#8E8A83] font-semibold group-hover:text-[#E8E3DA] transition-colors">
            ZEN ACTIVE
          </span>
        </div>

        <span className="font-mono text-xs font-bold text-[#E8E3DA] px-2 py-0.5 rounded bg-white/[0.06] border border-white/[0.08]">
          {formatTime(secondsRemaining)}
        </span>

        <div className="flex items-center gap-1 font-mono text-[11px] text-[#8E8A83] group-hover:text-white transition-colors">
          <ArrowLeft size={12} className="group-hover:-translate-x-0.5 transition-transform" />
          <span>Return to Zen Screen</span>
        </div>
      </button>
    </motion.div>
  );
};

export default ReturnToZenPill;
