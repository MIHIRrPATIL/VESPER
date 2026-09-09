import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AgentState } from '../types/vesper';
import { cn } from '../lib/utils';

interface AgentStatusPillProps {
  agentState: AgentState;
  isWakeWordArmed: boolean;
  className?: string;
}

export const AgentStatusPill: React.FC<AgentStatusPillProps> = ({
  agentState,
  isWakeWordArmed,
  className,
}) => {
  const isVisible = agentState !== 'IDLE' || isWakeWordArmed;

  const getStateConfig = () => {
    switch (agentState) {
      case 'LISTENING':
        return {
          label: 'Listening',
          colorClass: 'text-amber-300',
          borderClass: 'border-amber-500/25',
          glowClass: 'shadow-[0_0_24px_rgba(245,158,11,0.18)]',
        };
      case 'THINKING':
        return {
          label: 'Thinking',
          colorClass: 'text-cyan-300',
          borderClass: 'border-cyan-500/25',
          glowClass: 'shadow-[0_0_24px_rgba(6,182,212,0.18)]',
        };
      case 'SPEAKING':
        return {
          label: 'Speaking',
          colorClass: 'text-[#E8E3DA]',
          borderClass: 'border-white/15',
          glowClass: 'shadow-[0_0_24px_rgba(232,227,218,0.14)]',
        };
      case 'IDLE':
      default:
        return {
          label: 'Standby',
          colorClass: 'text-[#8E8A83]',
          borderClass: 'border-white/[0.08]',
          glowClass: '',
        };
    }
  };

  const cfg = getStateConfig();

  return (
    <div className={cn('fixed bottom-6 left-6 z-50 pointer-events-none', className)}>
      <AnimatePresence mode="wait">
        {isVisible && (
          <motion.div
            key={agentState}
            initial={{ y: 28, opacity: 0, scale: 0.92 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 22, opacity: 0, scale: 0.92 }}
            transition={{ type: 'spring', stiffness: 320, damping: 26 }}
            className={cn(
              'px-4 py-2 rounded-full bg-[#141414]/95 backdrop-blur-xl border flex items-center pointer-events-auto select-none',
              cfg.borderClass,
              cfg.glowClass
            )}
          >
            {/* Status Label Only */}
            <span className={cn('text-[12px] font-semibold tracking-wider font-mono px-1 uppercase', cfg.colorClass)}>
              {cfg.label}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
