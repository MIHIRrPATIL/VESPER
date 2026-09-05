import { useState, useEffect, useCallback } from 'react';
import { AgentCore } from './components/AgentCore';
import { HUDHeader } from './components/HUDHeader';
import { ChatStream } from './components/ChatStream';
import { CameraDrawer } from './components/CameraDrawer';
import { gatewayService } from './services/gateway';
import { cameraGestureManager, GestureStatus } from './services/camera';
import { AgentState, ConversationMessage, VesperEnvelope } from './types/vesper';
import './App.css';

export function App() {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>('IDLE');
  const [currentIntent, setCurrentIntent] = useState<string>('');
  const [currentLatency, setCurrentLatency] = useState<number>(0);
  const [volume, setVolume] = useState<number>(50);
  const [zenMode, setZenMode] = useState<boolean>(false);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [gestureStatus, setGestureStatus] = useState<GestureStatus>({
    isWorkerReady: false,
    isCameraActive: false,
    activeGesture: 'NONE',
    lastConfirmedGesture: 'NONE',
    confidence: 0,
    handedness: '',
    hasHand: false,
    isSafetyLocked: false,
  });

  // Handle incoming Gateway WebSocket envelopes
  const handleEnvelope = useCallback((envelope: VesperEnvelope) => {
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
      setCurrentLatency(payload.latency_ms || 0);
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
    } else if (type === 'SET_VOLUME') {
      if (typeof payload.volume === 'number') {
        setVolume(payload.volume);
      }
    } else if (type === 'ZEN_MODE_STATE') {
      const isZen = payload.zen_mode ?? payload.enabled ?? payload.toggle;
      if (typeof isZen === 'boolean') {
        setZenMode(isZen);
      }
    } else if (type === 'INTERRUPT_ACK') {
      setAgentState('IDLE');
    } else if (type === 'GESTURE_EVENT') {
      const gestureName = payload.gesture || '';
      const conf = typeof payload.confidence === 'number' ? payload.confidence : 1.0;
      setGestureStatus((prev) => ({
        ...prev,
        activeGesture: gestureName,
        lastConfirmedGesture: gestureName !== 'NONE' && !gestureName.startsWith('GESTURE_TOGGLE') ? gestureName : prev.lastConfirmedGesture,
        confidence: conf,
        handedness: payload.handedness || 'Right',
        hasHand: gestureName !== 'NONE',
      }));
    }
  }, []);

  useEffect(() => {
    // Connect to Gateway WebSocket
    gatewayService.connect();

    const unsubConnection = gatewayService.subscribeConnection((conn, connecting) => {
      setIsConnected(conn);
      setIsConnecting(connecting);
    });

    const unsubEnvelope = gatewayService.subscribe(handleEnvelope);

    const unsubGesture = cameraGestureManager.subscribe((status) => {
      setGestureStatus(status);
    });

    return () => {
      unsubConnection();
      unsubEnvelope();
      unsubGesture();
    };
  }, [handleEnvelope]);

  const handleToggleSafetyLock = () => {
    cameraGestureManager.toggleSafetyLock();
  };

  const handleSimulateWakeWord = () => {
    gatewayService.sendWakeWord('hey alfred', 0.98);
  };

  return (
    <div className={`vesper-app-root ${zenMode ? 'zen-mode-active' : ''}`}>
      <HUDHeader
        isConnected={isConnected}
        isConnecting={isConnecting}
        volume={volume}
        zenMode={zenMode}
        safetyLocked={gestureStatus.isSafetyLocked}
        onToggleSafetyLock={handleToggleSafetyLock}
      />

      <main className="hud-main-content">
        <section className="hud-hero-section">
          <AgentCore
            state={agentState}
            intent={currentIntent}
            latencyMs={currentLatency}
          />
        </section>

        <section className="hud-split-section">
          <div className="hud-left-panel">
            <ChatStream
              messages={messages}
              onSimulateWakeWord={handleSimulateWakeWord}
            />
          </div>

          <div className="hud-right-panel">
            <CameraDrawer
              status={gestureStatus}
              onToggleSafetyLock={handleToggleSafetyLock}
            />
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
