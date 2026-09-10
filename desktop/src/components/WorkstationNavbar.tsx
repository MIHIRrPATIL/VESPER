import React from 'react';
import { AgentState } from '../types/vesper';
import PillNav from './PillNav';

interface WorkstationNavbarProps {
  isConnected: boolean;
  agentState: AgentState;
  isWakeWordArmed: boolean;
  zenMode: boolean;
  onToggleZenMode: () => void;
  onToggleWakeWord: () => void;
  activeView: string;
  onSelectView: (view: string) => void;
}

const VESPER_LOGO = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="%23E8E3DA" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5l8 14 8-14"/><circle cx="12" cy="11" r="1.8" fill="%23E8E3DA"/></svg>`;

export const WorkstationNavbar: React.FC<WorkstationNavbarProps> = ({
  activeView,
  onSelectView,
}) => {
  const navItems = [
    { label: 'WORKSTATION', href: '#center', onClick: () => onSelectView('center') },
    { label: 'DIRECTIVES', href: '#voice', onClick: () => onSelectView('voice') },
    { label: 'AGENDA', href: '#agenda', onClick: () => onSelectView('agenda') },
    { label: 'TRANSACTIONS', href: '#transactions', onClick: () => onSelectView('transactions') },
    { label: 'SERVICES', href: '#services', onClick: () => onSelectView('services') },
    { label: 'LOGS', href: '#logs', onClick: () => onSelectView('logs') },
  ];

  return (
    <header className="workstation-navbar">
      <PillNav
        logo={VESPER_LOGO}
        logoAlt="Vesper"
        items={navItems}
        activeHref={`#${activeView}`}
        baseColor="rgba(24, 24, 24, 0.85)"
        pillColor="rgba(255, 255, 255, 0.05)"
        pillTextColor="#E8E3DA"
        hoveredPillTextColor="#FFFFFF"
        className="backdrop-blur-xl border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] rounded-full"
      />
    </header>
  );
};
