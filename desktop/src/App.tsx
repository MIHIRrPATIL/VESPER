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
import { AnimatePresence } from 'motion/react';
import { DirectivesView, LogsView, ServicesView } from './components/WorkstationViews';
import { TasksAgendaView } from './components/TasksAgendaView';
import { TransactionsView } from './components/TransactionsView';
import { ZenFocusView } from './components/ZenFocusOverlay';
import { ZenRightDock } from './components/ZenRightDock';
import { ReturnToZenPill } from './components/ReturnToZenPill';
import { zenStore } from './services/zen-store';
import { AgentStatusPill } from './components/AgentStatusPill';
import { ProactiveAdvisoryDrawer } from './components/ProactiveAdvisoryDrawer';
import { ToolEmitterView } from './components/ToolEmitterView';
import { mediaService } from './services/media-service';
// ── Deterministic Page Resolution Helper ─────────────────────────────────────

export function resolveDeterministicView(
  query?: string,
  explicitTarget?: string,
  hudCards?: any[],
  intent?: string
): string | null {
  // 1. Explicit target from backend (e.g. fast-path or agent supervisor)
  if (explicitTarget) {
    const norm = explicitTarget.toLowerCase().trim();
    if (norm === 'agenda' || norm === 'tasks' || norm === 'calendar') return 'agenda';
    if (norm === 'finances' || norm === 'transactions' || norm === 'ledger' || norm === 'bank') return 'transactions';
    if (norm === 'workstation' || norm === 'center' || norm === 'overview' || norm === 'cockpit' || norm === 'dashboard') return 'center';
    if (norm === 'services' || norm === 'telemetry' || norm === 'swarm' || norm === 'devices') return 'services';
    if (norm === 'tools' || norm === 'emitter') return 'tools';
    if (norm === 'logs' || norm === 'stream' || norm === 'audit') return 'logs';
    if (norm === 'voice' || norm === 'directives' || norm === 'chat') return 'voice';
    if (norm === 'zen' || norm === 'focus' || norm === 'pomodoro') return 'zen';
  }

  const q = (query || '').toLowerCase().trim();
  if (!q) return null;

  if (
    /\b(zen(?:\s+mode)?|focus(?:\s+mode)?|pomodoro(?:\s+timer)?)\b/i.test(q) ||
    /^(open|start|go\s+to|switch\s+to)\s+(?:the\s+)?(zen|focus|pomodoro)/i.test(q)
  ) {
    return 'zen';
  }

  // 2. Deterministic regex matching on user utterance / query text
  if (
    /\b(workstation(?:\s+page)?|overview(?:\s+page)?|cockpit|dashboard|home\s+page)\b/i.test(q) ||
    /^(open|show|go\s+to|switch\s+to)\s+(the\s+)?workstation/i.test(q)
  ) {
    return 'center';
  }

  if (
    /\b(agenda(?:\s+page)?|tasks?(?:\s+page)?|todo(?:\s+page)?|schedule(?:\s+page)?|calendar(?:\s+page)?)\b/i.test(q) ||
    /^(what(?:'s|\s+is)\s+the\s+agenda|open\s+(?:the\s+)?agenda|show\s+(?:the\s+)?agenda|what\s+are\s+my\s+tasks|show\s+(?:my\s+)?tasks|what's\s+on\s+my\s+schedule)/i.test(q)
  ) {
    return 'agenda';
  }

  if (
    /\b(finances?(?:\s+page)?|ledger(?:\s+page)?|transactions?(?:\s+page)?|bank(?:\s+page)?|accounts?(?:\s+page)?|expenses?|spending)\b/i.test(q) ||
    /^(what(?:'s|\s+is)\s+the\s+finances?|open\s+(?:the\s+)?finances?|show\s+(?:the\s+)?finances?|open\s+ledger|show\s+ledger|open\s+transactions)/i.test(q) ||
    q === 'finances' ||
    q === 'finance' ||
    q === 'ledger' ||
    q === 'transactions'
  ) {
    return 'transactions';
  }

  if (
    /\b(services?(?:\s+page)?|telemetry(?:\s+page)?|swarm(?:\s+mesh|\s+page|\s+status)?|hardware(?:\s+page)?|cluster(?:\s+nodes)?)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(services|telemetry|swarm)/i.test(q)
  ) {
    return 'services';
  }

  if (
    /\b(tools?(?:\s+page)?|tool\s+emitter|specialist\s+tools?|emitter\s+deck)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(tools|tool\s+emitter)/i.test(q)
  ) {
    return 'tools';
  }

  if (
    /\b(logs?(?:\s+page)?|audit\s+logs?|event\s+stream(?:\s+page)?|system\s+stream)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(logs|audit|event\s+stream)/i.test(q)
  ) {
    return 'logs';
  }

  if (
    /\b(directives?(?:\s+page)?|voice\s+agent(?:\s+page)?|voice\s+page|chat\s+page|conversation\s+page)\b/i.test(q) ||
    /^(open|show|go\s+to)\s+(the\s+)?(directives|voice\s+agent|chat)/i.test(q)
  ) {
    return 'voice';
  }

  // 3. Fallback based on HUD card types
  if (hudCards && hudCards.length > 0) {
    const cardTypes = hudCards.map((c) => (c.type || '').toLowerCase());
    if (cardTypes.some((t) => t.includes('calendar') || t.includes('task') || t.includes('agenda'))) {
      return 'agenda';
    }
    if (cardTypes.some((t) => t.includes('transaction') || t.includes('finance') || t.includes('debt') || t.includes('ledger'))) {
      return 'transactions';
    }
  }

  // 4. Fallback based on intent
  if (intent) {
    const intUpper = intent.toUpperCase();
    if (intUpper.includes('TASK') || intUpper.includes('AGENDA') || intUpper.includes('CALENDAR')) {
      return 'agenda';
    }
    if (intUpper.includes('FINANC') || intUpper.includes('LEDGER') || intUpper.includes('TRANSACTION')) {
      return 'transactions';
    }
  }

  return null;
}

export function App() {
  const [isConnected, setIsConnected] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>('IDLE');
  const [currentIntent, setCurrentIntent] = useState<string>('');
  const [zenMode, setZenMode] = useState<boolean>(false);
  const [isWakeWordArmed, setIsWakeWordArmed] = useState<boolean>(true);
  const [isNotificationDeckOpen, setIsNotificationDeckOpen] = useState<boolean>(false);
  const [messages, setMessages] = useState<ConversationMessage[]>(() => {
    if (typeof window !== 'undefined') {
      try {
        const saved = sessionStorage.getItem('vesper_session_messages');
        if (saved) return JSON.parse(saved);
      } catch (e) {
        console.error('[VESPER] Failed to parse session messages:', e);
      }
    }
    return [];
  });
  const [activeView, setActiveView] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('vesper_session_active_view') || 'center';
    }
    return 'center';
  });
  const [activeHeadline, setActiveHeadline] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('vesper_session_headline') || 'What can I help you shape today?';
    }
    return 'What can I help you shape today?';
  });
  const [isHudDrawerOpen, setIsHudDrawerOpen] = useState<boolean>(false);
  const wasAutoOpenedByAgentRef = useRef<boolean>(false);
  const [hudDrawerTitle, setHudDrawerTitle] = useState<string>('HUD INTELLIGENCE DECK');
  const [hudDrawerSubtitle, setHudDrawerSubtitle] = useState<string>('Cognitive specialist output & structured execution parameters');

  const [transitionTrigger, setTransitionTrigger] = useState<number>(0);
  const [pendingView, setPendingView] = useState<string>('center');

  // Persist session messages across refresh (survives F5, wiped only on tab close or onClearLogs)
  useEffect(() => {
    if (typeof window !== 'undefined') {
      try {
        sessionStorage.setItem('vesper_session_messages', JSON.stringify(messages));
      } catch (e) {
        // Ignore quota limits
      }
    }
  }, [messages]);

  // Persist current view across page refresh
  useEffect(() => {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('vesper_session_active_view', activeView);
    }
  }, [activeView]);

  // Persist active headline across page refresh
  useEffect(() => {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('vesper_session_headline', activeHeadline);
    }
  }, [activeHeadline]);

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
            id: envelope.uuid || crypto.randomUUID(),
            sender: 'system',
            text: `Vocal Wake Word Perceived: "${payload.wake_word || 'Hey Alfred'}"`,
            timestamp: Date.now(),
            intent: 'WAKE_WORD',
            isSingleton: true,
            eventType: 'WAKE_WORD_DETECTED',
            channel: 'VOICE',
          },
        ]);
      } else if (type === 'VOICE_COMMAND') {
        if (payload.command) {
          setActiveHeadline(payload.command);
          const earlyView = resolveDeterministicView(payload.command);
          if (earlyView) {
            handleSelectNavView(earlyView);
          }
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
          const earlyView = resolveDeterministicView(payload.command);
          if (earlyView) {
            handleSelectNavView(earlyView);
          }
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.sender === 'user' && last.text === payload.command) {
              return prev;
            }
            return [
              ...prev,
              {
                id: envelope.uuid || crypto.randomUUID(),
                sender: 'user',
                text: payload.command,
                timestamp: Date.now(),
                queryId: envelope.uuid,
                queryText: payload.command,
                eventType: 'VOICE_COMMAND',
                channel: envelope.channel || 'VOICE',
              },
            ];
          });
        }
      } else if (type === 'AGENT_RESPONSE') {
        setCurrentIntent(payload.intent || 'CONVERSE');
        setMessages((prev) => [
          ...prev,
          {
            id: envelope.uuid || crypto.randomUUID(),
            sender: 'agent',
            text: payload.response || payload.markdown_body || '',
            markdown: payload.markdown_body,
            timestamp: Date.now(),
            cards: payload.hud_cards || [],
            intent: payload.intent,
            latencyMs: payload.latency_ms,
            queryId: envelope.uuid,
            queryText: payload.command,
            specialistActions: payload.specialist_actions || [],
            eventType: 'AGENT_RESPONSE',
            channel: envelope.channel || 'VOICE',
            navigateTo: payload.navigate_to,
          },
        ]);

        // Deterministic view routing: switch to target page
        const targetView = resolveDeterministicView(
          payload.command,
          payload.navigate_to,
          payload.hud_cards,
          payload.intent
        );
        if (targetView) {
          handleSelectNavView(targetView);
        } else if (activeViewRef.current === 'center') {
          handleSelectNavView('voice');
        }

        // Dynamically compute tool title
        let derivedTitle = 'HUD INTELLIGENCE DECK';
        let derivedSubtitle = 'Cognitive specialist output & structured execution parameters';
        const firstCard = (payload.hud_cards || [])[0];
        if (firstCard) {
          const cType = (firstCard.type || '').toLowerCase();
          if (cType === 'spotify') {
            derivedTitle = 'SPOTIFY & VINYL ENGINE';
            derivedSubtitle = 'Active MPRIS media controls & live audio telemetry';
          } else if (cType.includes('email')) {
            derivedTitle = 'UNREAD INBOX & CORRESPONDENCE';
            derivedSubtitle = 'IMAP & Gmail synchronized messages';
          } else if (cType === 'briefing') {
            derivedTitle = 'EXECUTIVE BRIEFING DOSSIER';
            derivedSubtitle = 'Synchronized agenda, correspondence & daily priorities';
          } else if (cType.includes('task') || cType.includes('todo')) {
            derivedTitle = 'ACTIVE TASKS & EXECUTIVE AGENDA';
            derivedSubtitle = 'Deterministic task priorities and daily agenda';
          } else if (cType.includes('calendar')) {
            derivedTitle = 'GOOGLE CALENDAR & APPOINTMENTS';
            derivedSubtitle = 'Two-way synchronized Google Calendar schedule';
          } else if (cType === 'transaction' || cType.includes('finance') || cType.includes('debt')) {
            derivedTitle = 'FINANCIAL LEDGER & ACCOUNTS';
            derivedSubtitle = 'Supabase ledger transactions & financial accounting';
          } else if (cType.includes('research')) {
            derivedTitle = 'DEEP RESEARCH & WEB INTELLIGENCE';
            derivedSubtitle = 'Real-time synthesis and verified citations';
          } else if (cType.includes('github')) {
            derivedTitle = 'GITHUB DEV ENGINE';
            derivedSubtitle = 'Repositories, pull requests & code search';
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
            derivedSubtitle = 'Active MPRIS media controls & live audio telemetry';
          } else if (intentUpper.includes('EMAIL') || intentUpper.includes('INBOX') || intentUpper.includes('GMAIL')) {
            derivedTitle = 'UNREAD INBOX & CORRESPONDENCE';
            derivedSubtitle = 'IMAP & Gmail synchronized messages';
          } else if (intentUpper.includes('BRIEFING')) {
            derivedTitle = 'EXECUTIVE BRIEFING DOSSIER';
            derivedSubtitle = 'Synchronized agenda, correspondence & daily priorities';
          } else if (intentUpper.includes('CALENDAR') || intentUpper.includes('SCHEDULE')) {
            derivedTitle = 'GOOGLE CALENDAR & APPOINTMENTS';
            derivedSubtitle = 'Two-way synchronized Google Calendar schedule';
          } else if (intentUpper.includes('TASK') || intentUpper.includes('TODO') || intentUpper.includes('AGENDA')) {
            derivedTitle = 'ACTIVE TASKS & EXECUTIVE AGENDA';
            derivedSubtitle = 'Deterministic task priorities and daily agenda';
          } else if (intentUpper.includes('LEDGER') || intentUpper.includes('FINANC') || intentUpper.includes('BANK')) {
            derivedTitle = 'FINANCIAL LEDGER & ACCOUNTS';
            derivedSubtitle = 'Supabase ledger transactions & financial accounting';
          } else if (intentUpper.includes('WEATHER')) {
            derivedTitle = 'ATMOSPHERIC INTELLIGENCE';
            derivedSubtitle = 'Local weather sentry & forecast radar telemetry';
          } else if (intentUpper.includes('RESEARCH') || intentUpper.includes('SEARCH')) {
            derivedTitle = 'DEEP RESEARCH & WEB INTELLIGENCE';
            derivedSubtitle = 'Real-time synthesis and verified citations';
          }
        }
        setHudDrawerTitle(derivedTitle);
        setHudDrawerSubtitle(derivedSubtitle);

        // If this response has HUD cards, open the drawer
        if (payload.hud_cards && payload.hud_cards.length > 0) {
          wasAutoOpenedByAgentRef.current = true;
          setIsHudDrawerOpen(true);
        }
      } else if (type === 'AGENT_SPEAKING') {
        setAgentState('SPEAKING');
        // Do not override active view so page remains open during TTS speech
      } else if (type === 'AGENT_IDLE') {
        setAgentState('IDLE');
        if (wasAutoOpenedByAgentRef.current) {
          setIsHudDrawerOpen(false);
          wasAutoOpenedByAgentRef.current = false;
        }
      } else if (type === 'PROACTIVE_RESOLVE') {
        const actionIds: string[] = payload?.action_ids || (payload?.action_id ? [payload.action_id] : []);
        for (const aid of actionIds) {
          notificationStore.dismissAlert(aid);
        }
      } else if (type === 'ZEN_MODE_STATE') {
        const isZen = payload.zen_mode ?? payload.enabled;
        if (typeof isZen === 'boolean') {
          setZenMode(isZen);
          zenStore.onZenModeStateChange(isZen, payload.timer);
          if (isZen) {
            handleSelectNavView('zen');
          } else if (activeViewRef.current === 'zen') {
            handleSelectNavView('center');
          }
          setMessages((prev) => [
            ...prev,
            {
              id: envelope.uuid || crypto.randomUUID(),
              sender: 'system',
              text: `Zen Mode: ${isZen ? 'Engaged (Monastic Focus & Sensory Suppression)' : 'Disengaged'}`,
              timestamp: Date.now(),
              intent: 'ZEN_MODE',
              isSingleton: true,
              eventType: 'ZEN_MODE_STATE',
              channel: 'CONTROL',
            },
          ]);
        }
      } else if (type === 'MEDIA_CONTROL') {
        if (payload.track) {
          mediaService.updateFromTrack(payload.track);
        } else {
          mediaService.fetchNowPlaying();
        }
        setMessages((prev) => [
          ...prev,
          {
            id: envelope.uuid || crypto.randomUUID(),
            sender: 'system',
            text: `Media Action: ${payload.action || 'Playback state updated'}`,
            timestamp: Date.now(),
            intent: 'MEDIA',
            isSingleton: true,
            eventType: 'MEDIA_CONTROL',
            channel: 'CONTROL',
          },
        ]);
      } else if (type === 'ZEN_TIMER_UPDATE') {
        zenStore.applyInboundTimerUpdate(payload.action, payload.timer || payload);
      } else if (type === 'SET_VOLUME') {
        setMessages((prev) => [
          ...prev,
          {
            id: envelope.uuid || crypto.randomUUID(),
            sender: 'system',
            text: `Master Volume Adjusted: ${payload.volume}%`,
            timestamp: Date.now(),
            intent: 'VOLUME',
            isSingleton: true,
            eventType: 'SET_VOLUME',
            channel: 'CONTROL',
          },
        ]);
      } else if (type === 'GESTURE_EVENT' || envelope.channel === 'GESTURE') {
        const gestureToken = payload?.gesture || 'GESTURE';
        const gestureAction = payload?.action ? ` (${payload.action})` : '';
        setMessages((prev) => [
          ...prev,
          {
            id: envelope.uuid || crypto.randomUUID(),
            sender: 'system',
            text: `Perceived Hand Gesture: ${gestureToken}${gestureAction}`,
            timestamp: Date.now(),
            intent: 'GESTURE',
            gesture: gestureToken,
            action: payload?.action,
            isSingleton: true,
            eventType: 'GESTURE_EVENT',
            channel: 'GESTURE',
          },
        ]);

        // Touchless Shaka (Hang Loose) gesture toggles open/closed the Notifications & Advisories deck
        if (payload?.gesture === 'SHAKA' || payload?.gesture === 'AIR_TAP') {
          setIsNotificationDeckOpen((prev) => {
            const next = !prev;
            if (next) {
              notificationStore.dismissAllToasts();
            }
            return next;
          });
        }
      } else if (type === 'INTERRUPT_ACK') {
        setAgentState('IDLE');
      } else if (type === 'WAKE_WORD_STATE') {
        const active = typeof payload.wakeword_active === 'boolean'
          ? payload.wakeword_active
          : typeof payload.active === 'boolean'
          ? payload.active
          : typeof payload.enabled === 'boolean'
          ? payload.enabled
          : typeof payload.is_armed === 'boolean'
          ? payload.is_armed
          : undefined;
        if (typeof active === 'boolean') {
          setIsWakeWordArmed(active);
        }
      } else if (type === 'STATE_SNAPSHOT' || type === 'STATE_SYNC') {
        const state = payload.state || payload;
        if (typeof state?.wakeword_active === 'boolean') {
          setIsWakeWordArmed(state.wakeword_active);
        }
        if (typeof state?.zen_mode === 'boolean') {
          setZenMode(state.zen_mode);
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

  const handleToggleWakeWord = (target?: boolean) => {
    const next = typeof target === 'boolean' ? target : !isWakeWordArmed;
    setIsWakeWordArmed(next);
    gatewayService.sendWakeWordToggle(next);
  };

  const handleSimulateWakeWord = () => {
    if (!isWakeWordArmed) {
      console.warn('[VOICE] Cannot trigger wake word while wake word acoustic detector is muted/disarmed.');
      return;
    }
    gatewayService.sendWakeWord('hey alfred', 0.98);
    setAgentState('LISTENING');
  };

  const handleToggleZenMode = (target?: boolean) => {
    setZenMode((prev) => {
      const next = target !== undefined ? target : !prev;
      gatewayService.sendZenModeToggle(next);
      zenStore.onZenModeStateChange(next);
      if (next) {
        handleSelectNavView('zen');
      } else if (activeViewRef.current === 'zen') {
        handleSelectNavView('center');
      }
      return next;
    });
  };

  const handleSendUserMessage = (text: string) => {
    setActiveHeadline(text);
    setAgentState('THINKING');

    // Deterministically navigate to requested view or Directives
    const target = resolveDeterministicView(text);
    if (target) {
      handleSelectNavView(target);
    } else if (activeViewRef.current === 'center') {
      handleSelectNavView('voice');
    }

    const userMsgId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        sender: 'user',
        text,
        timestamp: Date.now(),
        queryId: userMsgId,
        queryText: text,
        eventType: 'VOICE_COMMAND',
        channel: 'VOICE',
      },
    ]);

    gatewayService.sendVoiceCommand(text);

    if (!isConnected) {
      setTimeout(() => {
        let reply = '';
        const lower = text.toLowerCase();
        let derivedTitle = 'HUD INTELLIGENCE DECK';
        let derivedSubtitle = 'Cognitive specialist output & structured parameters';

        const detView = resolveDeterministicView(text);
        if (detView === 'agenda' || lower.includes('agenda') || lower.includes('task')) {
          reply = 'Opening your executive agenda and active tasks, sir.';
          derivedTitle = 'ACTIVE TASKS & EXECUTIVE AGENDA';
          derivedSubtitle = 'Deterministic task priorities and daily agenda';
        } else if (detView === 'transactions' || lower.includes('financ') || lower.includes('ledger') || lower.includes('transaction')) {
          reply = 'Opening financial ledger and transactions, sir.';
          derivedTitle = 'FINANCIAL LEDGER & ACCOUNTS';
          derivedSubtitle = 'Supabase ledger transactions & financial accounting';
        } else if (detView === 'center' || lower.includes('workstation')) {
          reply = 'Opening workstation cockpit overview, sir.';
          derivedTitle = 'WORKSTATION COCKPIT';
          derivedSubtitle = 'Master temporal display and system vitals';
        } else if (detView === 'services' || lower.includes('service') || lower.includes('telemetry') || lower.includes('status') || lower.includes('vitals')) {
          reply = 'Displaying cognitive swarm services and hardware telemetry, sir.';
          derivedTitle = 'SWARM SERVICES & HARDWARE';
          derivedSubtitle = 'Hardware sensors, core metrics and optical pipeline';
        } else if (detView === 'tools' || lower.includes('tool')) {
          reply = 'Opening specialist tool emitter, sir.';
          derivedTitle = 'SPECIALIST TOOL EMITTER';
          derivedSubtitle = 'Live specialist tool execution and HUD inspection';
        } else if (detView === 'logs' || lower.includes('log') || lower.includes('event stream')) {
          reply = 'Displaying workstation event stream and audit logs, sir.';
          derivedTitle = 'WORKSTATION EVENT STREAM';
          derivedSubtitle = 'Query-grouped event stream and system audit logs';
        } else if (lower.includes('screen') || lower.includes('vision')) {
          reply = 'Active workspace viewport mapped. High-contrast monochrome mode engaged.';
          derivedTitle = 'OPTICAL WORKSPACE SENTRY';
          derivedSubtitle = 'Real-time screen presence & gesture sentry interface';
        } else if (lower.includes('email') || lower.includes('inbox') || lower.includes('mail')) {
          reply = 'Inbox checked. 5 unread items identified across synchronized mail accounts.';
          derivedTitle = 'UNREAD INBOX & CORRESPONDENCE';
          derivedSubtitle = 'IMAP & Gmail synchronized messages';
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

        // HUD close is now driven by the backend AGENT_IDLE event (TTS duration + 5s linger)
      }, 700);
    }
  };

  const [isCameraActive, setIsCameraActive] = useState<boolean>(false);

  const handleInterrupt = () => {
    setAgentState('IDLE');
    if (wasAutoOpenedByAgentRef.current) {
      setIsHudDrawerOpen(false);
      wasAutoOpenedByAgentRef.current = false;
    }
    gatewayService.sendInterrupt('USER_BARGE_IN');
  };

  const handleToggleVoice = () => {
    if (agentState === 'LISTENING') {
      setAgentState('IDLE');
      if (wasAutoOpenedByAgentRef.current) {
        setIsHudDrawerOpen(false);
        wasAutoOpenedByAgentRef.current = false;
      }
      gatewayService.sendInterrupt();
    } else {
      handleSimulateWakeWord();
    }
  };

  const handleToggleCamera = () => {
    const next = !isCameraActive;
    setIsCameraActive(next);
    gatewayService.sendCameraToggle(next);
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

      {/* Top Right Area: Proactive Advisories Drop-Down Drawer (Trigger hidden in Zen Mode) */}
      <div className="fixed top-4 right-6 z-40">
        <ProactiveAdvisoryDrawer
          open={isNotificationDeckOpen}
          onOpenChange={setIsNotificationDeckOpen}
          hideTrigger={zenMode}
        />
      </div>

      {/* Persistent Return to Zen Pill when navigating external pages during Zen Mode */}
      <AnimatePresence>
        {zenMode && activeView !== 'zen' && (
          <ReturnToZenPill
            onReturnToZen={() => handleSelectNavView('zen')}
          />
        )}
      </AnimatePresence>

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
            isProcessing={agentState === 'LISTENING' || agentState === 'THINKING' || agentState === 'SPEAKING'}
            onInterrupt={handleInterrupt}
          />
        </div>

        {/* Column 2: Center Workstation Stage (80%) */}
        <main className="center-workstation-deck">
          {/* Workstation Navbar: Hidden during Zen Mode */}
          {!zenMode && (
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
          )}

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

              {(activeView === 'agenda' || activeView === 'tasks') && (
                <TasksAgendaView onSendUserMessage={handleSendUserMessage} />
              )}

              {activeView === 'transactions' && (
                <TransactionsView onSendUserMessage={handleSendUserMessage} />
              )}

              {(activeView === 'services' || activeView === 'telemetry') && (
                <ServicesView
                  onSendUserMessage={handleSendUserMessage}
                  onOpenTools={() => handleSelectNavView('tools')}
                />
              )}

              {(activeView === 'tools' || activeView === 'emitter') && (
                <ToolEmitterView onOpenHudDrawer={() => setIsHudDrawerOpen(true)} />
              )}

              {activeView === 'logs' && (
                <LogsView
                  messages={messages}
                  onClearLogs={() => {
                    setMessages([]);
                    if (typeof window !== 'undefined') {
                      try {
                        sessionStorage.removeItem('vesper_session_messages');
                      } catch (e) {}
                    }
                  }}
                />
              )}

              {activeView === 'zen' && (
                <ZenFocusView
                  onExitZen={handleToggleZenMode}
                  onOpenNotifications={() => setIsNotificationDeckOpen(true)}
                />
              )}
            </div>
          </div>

          <WorkstationFooter
            agentState={agentState}
          />
        </main>
        
        {/* Column 3: Right Side -- Notification Panel or Zen Right Dock */}
        <div className="layout-sidebar-right">
          {zenMode ? (
            <ZenRightDock
              activeView={activeView}
              onSelectView={handleSelectNavView}
              onOpenNotifications={() => setIsNotificationDeckOpen(true)}
            />
          ) : (
            <NotificationPanel />
          )}
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
