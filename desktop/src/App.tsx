import { useState, useEffect, useCallback } from 'react';
import { LeftNavDock } from './components/LeftNavDock';
import { ChatStream } from './components/ChatStream';
import { WorkstationNavbar } from './components/WorkstationNavbar';
import { WorkstationFooter } from './components/WorkstationFooter';
import { gatewayService } from './services/gateway';
import { AgentState, ConversationMessage, VesperEnvelope } from './types/vesper';
import { FloatingPathsBackground } from './components/ui/floating-paths';
import './App.css';

export function App() {
  const [isConnected, setIsConnected] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>('IDLE');
  const [currentIntent, setCurrentIntent] = useState<string>('');
  const [zenMode, setZenMode] = useState<boolean>(false);
  const [isWakeWordArmed, setIsWakeWordArmed] = useState<boolean>(true);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [activeView, setActiveView] = useState<string>('center');
  const [isLogExpanded, setIsLogExpanded] = useState<boolean>(false);
  const [activeHeadline, setActiveHeadline] = useState<string>(
    'What can I help you shape today?'
  );

  // Handle incoming Gateway WebSocket envelopes
  const handleEnvelope = useCallback(
    (envelope: VesperEnvelope) => {
      const { type, payload } = envelope;

      if (type === 'WAKE_WORD_DETECTED') {
        setAgentState('LISTENING');
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'system',
            text: `Wake word triggered: "${payload.wake_word || 'Hey Alfred'}"`,
            timestamp: Date.now(),
          },
        ]);
      } else if (type === 'VOICE_COMMAND') {
        if (payload.command) {
          setActiveHeadline(payload.command);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.sender === 'user' && last.text === payload.command) {
              return prev;
            }
            return [
              ...prev,
              {
                id: crypto.randomUUID(),
                sender: 'user',
                text: payload.command,
                timestamp: Date.now(),
              },
            ];
          });
        }
      } else if (type === 'AGENT_ACTIVATING') {
        setAgentState('THINKING');
        if (payload.command) {
          setActiveHeadline(payload.command);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.sender === 'user' && last.text === payload.command) {
              return prev;
            }
            return [
              ...prev,
              {
                id: crypto.randomUUID(),
                sender: 'user',
                text: payload.command,
                timestamp: Date.now(),
              },
            ];
          });
        }
      } else if (type === 'AGENT_RESPONSE') {
        setCurrentIntent(payload.intent || 'CONVERSE');
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'agent',
            text: payload.response || payload.markdown_body || '',
            markdown: payload.markdown_body,
            timestamp: Date.now(),
            cards: payload.hud_cards || [],
            intent: payload.intent,
            latencyMs: payload.latency_ms,
          },
        ]);
      } else if (type === 'AGENT_SPEAKING') {
        setAgentState('SPEAKING');
      } else if (type === 'AGENT_IDLE') {
        setAgentState('IDLE');
      } else if (type === 'ZEN_MODE_STATE') {
        const isZen = payload.zen_mode ?? payload.enabled ?? payload.toggle;
        if (typeof isZen === 'boolean') {
          setZenMode(isZen);
        }
      } else if (type === 'INTERRUPT_ACK') {
        setAgentState('IDLE');
      } else if (type === 'WAKE_WORD_STATE') {
        if (typeof payload.wakeword_active === 'boolean') {
          setIsWakeWordArmed(payload.wakeword_active);
        }
      } else if (type === 'NOTIFICATION_DIGEST' || envelope.channel === 'NOTIFY') {
        const notif = payload.notification || {};
        const title = notif.title || payload.title || 'Executive Briefing';
        const text = payload.speech || notif.text || '';
        if (text) {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              sender: 'agent',
              text: `[${title.toUpperCase()}]\n${text}`,
              markdown: payload.markdown_body,
              timestamp: Date.now(),
              cards: payload.hud_cards || [],
              intent: 'BRIEFING',
            },
          ]);
        }
      }
    },
    []
  );

  useEffect(() => {
    gatewayService.connect();

    const unsubConnection = gatewayService.subscribeConnection((conn) => {
      setIsConnected(conn);
    });

    const unsubEnvelope = gatewayService.subscribe(handleEnvelope);

    return () => {
      unsubConnection();
      unsubEnvelope();
    };
  }, [handleEnvelope]);

  const handleToggleWakeWord = () => {
    const next = !isWakeWordArmed;
    setIsWakeWordArmed(next);
    gatewayService.sendWakeWordToggle(next);
  };

  const handleSimulateWakeWord = () => {
    gatewayService.sendWakeWord('hey alfred', 0.98);
    setAgentState('LISTENING');
  };

  const handleToggleZenMode = () => {
    setZenMode((prev) => !prev);
  };

  const handleSendUserMessage = (text: string) => {
    setActiveHeadline(text);
    setAgentState('THINKING');

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        sender: 'user',
        text,
        timestamp: Date.now(),
      },
    ]);

    gatewayService.sendVoiceCommand(text);

    if (!isConnected) {
      setTimeout(() => {
        let reply = '';
        const lower = text.toLowerCase();
        if (lower.includes('status') || lower.includes('vitals')) {
          reply = 'Cluster telemetry stable. 8 physical cores active, optical pipeline armed.';
        } else if (lower.includes('screen') || lower.includes('vision')) {
          reply = 'Active workspace viewport mapped. High-contrast monochrome mode engaged.';
        } else if (lower.includes('meeting') || lower.includes('agenda')) {
          reply = 'Daily schedule parsed: 4 upcoming milestones. Next focus block: 10:00 AM System Architecture Sync.';
        } else if (lower.includes('diagnostic')) {
          reply = 'Diagnostics complete. Zero memory leaks detected.';
        } else {
          reply = `Synthesized execution plan for: "${text}". All subagents coordinated across local host.`;
        }

        setAgentState('SPEAKING');
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'agent',
            text: reply,
            timestamp: Date.now(),
            latencyMs: 18,
          },
        ]);

        setTimeout(() => {
          setAgentState('IDLE');
        }, 3000);
      }, 700);
    }
  };

  const [isCameraActive, setIsCameraActive] = useState<boolean>(false);

  const handleToggleVoice = () => {
    if (agentState === 'LISTENING') {
      setAgentState('IDLE');
      gatewayService.sendInterrupt();
    } else {
      handleSimulateWakeWord();
    }
  };

  const handleToggleCamera = () => {
    setIsCameraActive((prev) => !prev);
  };

  const handleToggleActivity = () => {
    setIsLogExpanded((prev) => !prev);
  };

  const handleSelectNavView = (view: string) => {
    setActiveView(view);
    if (view === 'logs') {
      setIsLogExpanded(true);
    }
  };

  return (
    <div
      className={`vesper-command-deck-root dark ${
        zenMode ? 'zen-mode-engaged' : ''
      }`}
      style={{ position: 'relative' }}
    >
      <FloatingPathsBackground position={1} style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 0, pointerEvents: 'none' }} />
      <FloatingPathsBackground position={1} style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 0, transform: 'rotate(180deg)', pointerEvents: 'none' }} />
      <div className="command-deck-frame" style={{ position: 'relative', zIndex: 10 }}>
        {/* Column 1: Vertically Centered Left Navigation Dock (10%) */}
        <div className="layout-sidebar-left">
          <LeftNavDock
            isVoiceActive={agentState === 'LISTENING'}
            onToggleVoice={handleToggleVoice}
            zenMode={zenMode}
            onToggleZenMode={handleToggleZenMode}
            isWakeWordArmed={isWakeWordArmed}
            onToggleWakeWord={handleToggleWakeWord}
            isCameraActive={isCameraActive}
            onToggleCamera={handleToggleCamera}
            isActivityActive={isLogExpanded}
            onToggleActivity={handleToggleActivity}
          />
        </div>

        {/* Column 2: Center Workstation Stage (80%) */}
        <main className="center-workstation-deck">
          <WorkstationNavbar
            isConnected={isConnected}
            agentState={agentState}
            isWakeWordArmed={isWakeWordArmed}
            zenMode={zenMode}
            onToggleZenMode={handleToggleZenMode}
            onToggleWakeWord={handleToggleWakeWord}
            activeView={activeView}
            onSelectView={handleSelectNavView}
          />

          <div className="center-deck-viewport">
            <div className="center-deck-content">
              <ChatStream
                messages={messages}
                agentState={agentState}
                intent={currentIntent}
                activeHeadline={activeHeadline}
                isLogExpanded={isLogExpanded}
                onToggleLog={() => setIsLogExpanded(!isLogExpanded)}
                onSimulateWakeWord={handleSimulateWakeWord}
                onSendUserMessage={handleSendUserMessage}
              />
            </div>
          </div>

          <WorkstationFooter
            agentState={agentState}
          />
        </main>
        
        {/* Column 3: Right Side (10%) */}
        <div className="layout-sidebar-right"></div>
      </div>
    </div>
  );
}

export default App;
