import React from 'react';
import { AgentState } from '../types/vesper';

interface AgentCoreProps {
  state: AgentState;
  intent?: string;
  latencyMs?: number;
}

export const AgentCore: React.FC<AgentCoreProps> = ({ state, intent, latencyMs }) => {
  const getStatusLabel = () => {
    switch (state) {
      case 'LISTENING':
        return 'Listening for utterance...';
      case 'THINKING':
        return intent ? `Cognitive swarm reasoning (${intent})...` : 'Agent swarm processing...';
      case 'SPEAKING':
        return 'Synthesizing response output...';
      case 'IDLE':
      default:
        return 'Standby - Awaiting trigger or wake word';
    }
  };

  return (
    <div className={`agent-core-container state-${state.toLowerCase()}`}>
      <div className="agent-core-visual">
        <div className="agent-core-outer-ring" />
        <div className="agent-core-middle-ring" />
        <div className="agent-core-orb">
          <div className="agent-core-inner-glow" />
        </div>
      </div>

      <div className="agent-core-meta">
        <div className="agent-core-badge">
          <span className="agent-state-dot" />
          <span className="agent-state-title">{state}</span>
        </div>
        <div className="agent-core-status">{getStatusLabel()}</div>
        {latencyMs !== undefined && latencyMs > 0 && (
          <div className="agent-core-latency">Swarm Latency: {latencyMs.toFixed(1)} ms</div>
        )}
      </div>
    </div>
  );
};
