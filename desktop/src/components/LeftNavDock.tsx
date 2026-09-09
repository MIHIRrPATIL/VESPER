import React from 'react';
import { Mic, Eye, Moon, Volume2, VolumeX } from 'lucide-react';
import { Dock, DockIcon, DockItem, DockLabel } from './ui/dock';
import { cn } from '../lib/utils';

interface LeftNavDockProps {
  isVoiceActive: boolean;
  onToggleVoice: () => void;
  zenMode: boolean;
  onToggleZenMode: () => void;
  isWakeWordArmed: boolean;
  onToggleWakeWord: () => void;
  isCameraActive: boolean;
  onToggleCamera: () => void;
}

export const LeftNavDock: React.FC<LeftNavDockProps> = ({
  isVoiceActive,
  onToggleVoice,
  zenMode,
  onToggleZenMode,
  isWakeWordArmed,
  onToggleWakeWord,
  isCameraActive,
  onToggleCamera,
}) => {
  return (
    <aside className="left-nav-dock-container" aria-label="Primary Navigation">
      <Dock magnification={48} distance={75} panelWidth={58}>
        {/* Voice Listening Control */}
        <DockItem 
          onClick={onToggleVoice} 
          ariaLabel={isVoiceActive ? 'Voice: Listening' : 'Voice: Standby'}
          className={cn(
            'rounded-[18px] p-2 transition-colors cursor-pointer border',
            isVoiceActive 
              ? 'bg-white/[0.12] text-white border-white/20' 
              : 'bg-white/[0.04] text-[#E8E3DA]/60 border-transparent hover:border-white/10 hover:text-[#E8E3DA] hover:bg-white/[0.08]'
          )}
        >
          <DockLabel>{isVoiceActive ? 'Voice: Listening' : 'Voice: Standby'}</DockLabel>
          <DockIcon>
            <Mic size={20} strokeWidth={2} />
          </DockIcon>
        </DockItem>

        {/* Focus / Zen Mode Control */}
        <DockItem 
          onClick={onToggleZenMode} 
          ariaLabel={zenMode ? 'Focus: Active' : 'Focus: Off'}
          className={cn(
            'rounded-[18px] p-2 transition-colors cursor-pointer border',
            zenMode 
              ? 'bg-white/[0.12] text-white border-white/20' 
              : 'bg-white/[0.04] text-[#E8E3DA]/60 border-transparent hover:border-white/10 hover:text-[#E8E3DA] hover:bg-white/[0.08]'
          )}
        >
          <DockLabel>{zenMode ? 'Focus: Active' : 'Focus: Off'}</DockLabel>
          <DockIcon>
            <Moon size={20} strokeWidth={2} />
          </DockIcon>
        </DockItem>

        {/* Wake Word Arm / Mute Control */}
        <DockItem 
          onClick={onToggleWakeWord} 
          ariaLabel={isWakeWordArmed ? 'Wake Word: Armed' : 'Wake Word: Muted'}
          className={cn(
            'rounded-[18px] p-2 transition-colors cursor-pointer border',
            !isWakeWordArmed 
              ? 'bg-white/[0.12] text-white border-white/20' 
              : 'bg-white/[0.04] text-[#E8E3DA]/60 border-transparent hover:border-white/10 hover:text-[#E8E3DA] hover:bg-white/[0.08]'
          )}
        >
          <DockLabel>{isWakeWordArmed ? 'Wake Word: Armed' : 'Wake Word: Muted'}</DockLabel>
          <DockIcon>
            {!isWakeWordArmed ? <VolumeX size={20} strokeWidth={2} /> : <Volume2 size={20} strokeWidth={2} />}
          </DockIcon>
        </DockItem>

        {/* Camera / Vision Sentry Control */}
        <DockItem 
          onClick={onToggleCamera} 
          ariaLabel={isCameraActive ? 'Vision: Armed' : 'Vision: Standby'}
          className={cn(
            'rounded-[18px] p-2 transition-colors cursor-pointer border',
            isCameraActive 
              ? 'bg-white/[0.12] text-white border-white/20' 
              : 'bg-white/[0.04] text-[#E8E3DA]/60 border-transparent hover:border-white/10 hover:text-[#E8E3DA] hover:bg-white/[0.08]'
          )}
        >
          <DockLabel>{isCameraActive ? 'Vision: Armed' : 'Vision: Standby'}</DockLabel>
          <DockIcon>
            <Eye size={20} strokeWidth={2} />
          </DockIcon>
        </DockItem>
      </Dock>
    </aside>
  );
};

