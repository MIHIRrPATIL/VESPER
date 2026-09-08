import React from 'react';
interface WorkstationFooterProps {
  agentState?: string;
}

export const WorkstationFooter: React.FC<WorkstationFooterProps> = ({
  agentState = 'IDLE',
}) => {
  return (
    <footer className="h-[38px] min-h-[38px] border-t border-white/5 px-6 flex items-center justify-between bg-transparent backdrop-blur-sm z-20">
      {/* Center: System state banner */}
      <div className="flex items-center justify-center w-full">
        <span className="text-[10px] font-mono tracking-widest text-muted-foreground uppercase">{agentState}</span>
      </div>
    </footer>
  );
};
