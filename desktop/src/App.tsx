import { useState, useEffect, useCallback, useRef } from 'react';
import { LeftNavDock } from './components/LeftNavDock';
import { ChatStream } from './components/ChatStream';
import { WorkstationNavbar } from './components/WorkstationNavbar';
import { WorkstationFooter } from './components/WorkstationFooter';
import { NotificationPanel } from './components/NotificationPanel';
import { HudDrawer } from './components/HudDrawer';
import { ProactiveToastContainer } from './components/ProactiveToast';
import { gatewayService } from './services/gateway';
import { notificationStore } from './services/notification-store';
import { AgentState, ConversationMessage, VesperEnvelope } from './types/vesper';
import { VinylAlbumCard } from './components/VinylAlbumCard';
import { FloatingPathsBackground } from './components/ui/floating-paths';
import { CascadePageTransition } from './components/ui/CascadePageTransition';
import { DirectivesView, LogsView } from './components/WorkstationViews';
import { TransactionsView } from './components/TransactionsView';
import { AgentStatusPill } from './components/AgentStatusPill';
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
  const [isHudDrawerOpen, setIsHudDrawerOpen] = useState<boolean>(false);
  const [hudDrawerTitle, setHudDrawerTitle] = useState<string>('HUD INTELLIGENCE DECK');
  const [hudDrawerSubtitle, setHudDrawerSubtitle] = useState<string>('Cognitive specialist output & structured execution parameters');

  const [transitionTrigger, setTransitionTrigger] = useState<number>(0);
  const [pendingView, setPendingView] = useState<string>('center');

  const activeViewRef = useRef(activeView);
  useEffect(() => {
    activeViewRef.current = activeView;
  }, [activeView]);

  const handleSelectNavView = useCallback((view: string) => {
    if (view === activeViewRef.current) return;
    setPendingView(view);
    setTransitionTrigger((prev) => prev + 1);
  }, []);

  const handleViewSwap = () => {
    setActiveView(pendingView);
    if (pendingView === 'logs') {
      setIsLogExpanded(true);
    }
  };

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

        // Auto-cascade to Directives page on agent response
        handleSelectNavView('voice');

        // Dynamically compute tool title
        let derivedTitle = 'HUD INTELLIGENCE DECK';
        let derivedSubtitle = 'Cognitive specialist output & structured execution parameters';
        const firstCard = (payload.hud_cards || [])[0];
        if (firstCard) {
          const cType = (firstCard.type || '').toLowerCase();
          if (cType === 'spotify') {
            derivedTitle = 'SPOTIFY & VINYL ENGINE';
            derivedSubtitle = 'Active MPRIS media controls & live audio telemetry';
          } else if (cType === 'briefing' || cType === 'calendar') {
            derivedTitle = 'GOOGLE CALENDAR & AGENDA';
            derivedSubtitle = 'Two-way synchronized Google Calendar & task schedule';
          } else if (cType === 'transaction' || cType === 'finance') {
            derivedTitle = 'FINANCIAL LEDGER & ACCOUNTS';
            derivedSubtitle = 'Supabase ledger transactions & financial accounting';
          } else if (cType === 'weather') {
            derivedTitle = 'ATMOSPHERIC INTELLIGENCE';
            derivedSubtitle = 'Local weather sentry & forecast radar telemetry';
          } else if (cType === 'youtube') {
            derivedTitle = 'YOUTUBE MEDIA RUNTIME';
            derivedSubtitle = 'Video transcription, playback & metadata cache';
          } else if (firstCard.title) {
            derivedTitle = firstCard.title.toUpperCase();
          }
        } else if (payload.intent) {
          const intentUpper = payload.intent.toUpperCase();
          if (intentUpper.includes('SPOTIFY') || intentUpper.includes('MEDIA') || intentUpper.includes('MUSIC')) {
            derivedTitle = 'SPOTIFY & VINYL ENGINE';
          } else if (intentUpper.includes('CALENDAR') || intentUpper.includes('SCHEDULE') || intentUpper.includes('TASK')) {
            derivedTitle = 'GOOGLE CALENDAR & AGENDA';
          } else if (intentUpper.includes('LEDGER') || intentUpper.includes('FINANC')) {
            derivedTitle = 'FINANCIAL LEDGER & ACCOUNTS';
          } else if (intentUpper.includes('WEATHER')) {
            derivedTitle = 'ATMOSPHERIC INTELLIGENCE';
          }
        }
        setHudDrawerTitle(derivedTitle);
        setHudDrawerSubtitle(derivedSubtitle);

        // If this response has HUD cards, open the drawer
        if (payload.hud_cards && payload.hud_cards.length > 0) {
          setIsHudDrawerOpen(true);
        }
      } else if (type === 'AGENT_SPEAKING') {
        setAgentState('SPEAKING');
        handleSelectNavView('voice');
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
      }
      // Note: NOTIFICATION_RELAY, NOTIFICATION_DIGEST, CALL_STATE, and
      // AGENT_RESPONSE with hud_cards are also handled by the notificationStore
      // via its own gateway subscription. We don't need to duplicate that here.
    },
    []
  );

  useEffect(() => {
    gatewayService.connect();
    notificationStore.connect();

    const unsubConnection = gatewayService.subscribeConnection((conn) => {
      setIsConnected(conn);
    });

    const unsubEnvelope = gatewayService.subscribe(handleEnvelope);

    return () => {
      unsubConnection();
      unsubEnvelope();
      notificationStore.disconnect();
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

    // Automatically navigate to Directives page via cascading curtain transition
    handleSelectNavView('voice');

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
        let derivedTitle = 'HUD INTELLIGENCE DECK';
        let derivedSubtitle = 'Cognitive specialist output & structured parameters';

        if (lower.includes('status') || lower.includes('vitals')) {
          reply = 'Cluster telemetry stable. 8 physical cores active, optical pipeline armed.';
          derivedTitle = 'CLUSTER TELEMETRY & VITALS';
          derivedSubtitle = 'Hardware sensors, core metrics and optical pipeline';
        } else if (lower.includes('screen') || lower.includes('vision')) {
          reply = 'Active workspace viewport mapped. High-contrast monochrome mode engaged.';
          derivedTitle = 'OPTICAL WORKSPACE SENTRY';
          derivedSubtitle = 'Real-time screen presence & gesture sentry interface';
        } else if (lower.includes('meeting') || lower.includes('agenda') || lower.includes('calendar')) {
          reply = 'Daily schedule parsed: 4 upcoming milestones. Next focus block: 10:00 AM System Architecture Sync.';
          derivedTitle = 'GOOGLE CALENDAR & AGENDA';
          derivedSubtitle = 'Two-way synchronized Google Calendar & task schedule';
        } else if (lower.includes('diagnostic')) {
          reply = 'Diagnostics complete. Zero memory leaks detected.';
          derivedTitle = 'DIAGNOSTIC TELEMETRY';
          derivedSubtitle = 'Local system diagnostic analysis & log telemetry';
        } else if (lower.includes('music') || lower.includes('play') || lower.includes('spotify')) {
          reply = 'Spotify MPRIS playback active. High-fidelity vinyl playback engaged.';
          derivedTitle = 'SPOTIFY & VINYL ENGINE';
          derivedSubtitle = 'Active MPRIS media controls & audio synthesis telemetry';
        } else {
          reply = `Synthesized execution plan for: "${text}". All subagents coordinated across local host.`;
          derivedTitle = 'COGNITIVE SWARM EXECUTION';
          derivedSubtitle = 'Specialist agent coordination & execution parameters';
        }

        setHudDrawerTitle(derivedTitle);
        setHudDrawerSubtitle(derivedSubtitle);

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
        }, 3200);
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

  return (
    <div
      className={`vesper-command-deck-root dark ${
        zenMode ? 'zen-mode-engaged' : ''
      }`}
      style={{ position: 'relative' }}
    >
      {/* Top Left Area: Live Music Vinyl Album Card */}
      <div className="fixed top-16 left-20 z-40">
        <VinylAlbumCard />
      </div>

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
            activeView={pendingView || activeView}
            onSelectView={handleSelectNavView}
          />

          <div className="center-deck-viewport relative overflow-hidden">
            {/* Cascade Page Transition (Constrained strictly to 90% center stage, navbar/sidebar/footer unaffected) */}
            <CascadePageTransition
              trigger={transitionTrigger}
              onViewSwap={handleViewSwap}
              direction="top"
              columns={14}
            />

            <div className="center-deck-content">
              {activeView === 'center' && (
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
              )}

              {activeView === 'voice' && (
                <DirectivesView
                  agentState={agentState}
                  activeHeadline={activeHeadline}
                  messages={messages}
                  isWakeWordArmed={isWakeWordArmed}
                  onToggleWakeWord={handleToggleWakeWord}
                  onSimulateWakeWord={handleSimulateWakeWord}
                  onSendUserMessage={handleSendUserMessage}
                  onOpenHudDrawer={() => setIsHudDrawerOpen(true)}
                  hudDrawerTitle={hudDrawerTitle}
                  hasActiveHudCards={isHudDrawerOpen || notificationStore.activeHudOutputs.length > 0}
                />
              )}

              {(activeView === 'transactions' || activeView === 'services' || activeView === 'telemetry') && (
                <TransactionsView onSendUserMessage={handleSendUserMessage} />
              )}

              {activeView === 'logs' && (
                <LogsView
                  messages={messages}
                  onClearLogs={() => setMessages([])}
                />
              )}
            </div>
          </div>

          <WorkstationFooter
            agentState={agentState}
          />
        </main>
        
        {/* Column 3: Right Side -- Notification Panel Trigger */}
        <div className="layout-sidebar-right">
          <NotificationPanel />
        </div>
      </div>

      {/* Proactive Agent Toasts -- Top Right Corner */}
      <ProactiveToastContainer />

      {/* Animated Agent Status Pill -- Bottom Left */}
      <AgentStatusPill agentState={agentState} isWakeWordArmed={isWakeWordArmed} />

      {/* HUD Output Drawer -- Bottom */}
      <HudDrawer 
        open={isHudDrawerOpen} 
        onOpenChange={setIsHudDrawerOpen} 
        customTitle={hudDrawerTitle}
        customSubtitle={hudDrawerSubtitle}
      />
    </div>
  );
}

export default App;
