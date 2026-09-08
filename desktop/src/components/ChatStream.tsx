import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  Settings,
  Terminal,
  Activity,
  Code
} from 'lucide-react';
import { ConversationMessage, AgentState } from '../types/vesper';
import { BentoGrid, BentoCard } from './ui/bento-grid';
import { DynamicGreeting } from './DynamicGreeting';
import { CommandInput } from './CommandInput';
import { DesignerChronometer } from './DesignerChronometer';

interface ChatStreamProps {
  messages: ConversationMessage[];
  agentState: AgentState;
  intent?: string;
  activeHeadline?: string;
  isLogExpanded?: boolean;
  onToggleLog?: () => void;
  onSimulateWakeWord: () => void;
  onSendUserMessage?: (text: string) => void;
}

export const ChatStream: React.FC<ChatStreamProps> = ({
  messages,
  agentState: _agentState,
  intent: _intent,
  activeHeadline: _activeHeadline = 'What can I help you shape today?',
  isLogExpanded: controlledLogExpanded,
  onToggleLog: controlledToggleLog,
  onSimulateWakeWord: _onSimulateWakeWord,
  onSendUserMessage,
}) => {
  const [internalLogExpanded, setInternalLogExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const isLogExpanded =
    controlledLogExpanded !== undefined ? controlledLogExpanded : internalLogExpanded;

  const toggleLog = () => {
    if (controlledToggleLog) {
      controlledToggleLog();
    } else {
      setInternalLogExpanded(!internalLogExpanded);
    }
  };

  useEffect(() => {
    if (isLogExpanded) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLogExpanded]);

  const dispatchCommand = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (onSendUserMessage) {
      onSendUserMessage(trimmed);
    }
  };

  return (
    <div className="center-stage-command-deck" style={{ width: '100%', position: 'relative' }}>
      <div className="center-stage-inner relative z-10 w-full flex flex-col items-center justify-center">
        <div className="hero-command-group w-full max-w-5xl flex flex-col items-start justify-start mb-32">
          <DynamicGreeting />
          
          <CommandInput 
            onSubmit={(val) => dispatchCommand(val)}
          />
        </div>

        <BentoGrid className="w-full max-w-5xl">
          <BentoCard 
            name="System Parameters" 
            description="Configure the underlying AI gateway logic, adjust memory buffers, and review telemetry." 
            Icon={Settings} 
            className="col-span-2"
          />
          <BentoCard 
            name="Active Terminals" 
            description="3 bash instances running." 
            Icon={Terminal} 
          />
          <BentoCard 
            name="Cluster Metrics" 
            description="Zero degradation in memory space. Latency optimal." 
            Icon={Activity} 
          />
          <BentoCard 
            name="Code Intelligence" 
            description="Semantic indexing up to date across local projects." 
            Icon={Code} 
            className="col-span-2"
          />
        </BentoGrid>

        {/* Bottom Designer Chronometer: Time, Date & Day */}
        <DesignerChronometer />

        {/* Expandable Dialogue Log Modal / Drawer */}
        {isLogExpanded && (
          <div className="command-log-drawer">
            <div className="drawer-header">
              <span className="drawer-title">SESSION CONVERSATION LOG</span>
              <button
                type="button"
                className="drawer-close-btn"
                onClick={toggleLog}
              >
                <ChevronDown size={15} />
              </button>
            </div>
            <div className="drawer-messages-list">
              {messages.length === 0 ? (
                <div className="empty-dialogue">No messages in current session history.</div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`dialogue-item ${msg.sender}`}>
                    <span className="sender-tag">[{msg.sender.toUpperCase()}]</span>
                    <span className="message-body">{msg.text}</span>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

