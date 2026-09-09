import React, { useState, useEffect } from 'react';
import { 
  Mic, 
  Terminal, 
  Radio, 
  Volume2, 
  CheckCircle2, 
  Trash2,
  Smartphone,
  Laptop,
  Bot,
  CalendarCheck,
  DollarSign,
  Music,
  Eye,
  Layers,
  ArrowRight,
  Wrench
} from 'lucide-react';
import { useMotionValue, animate } from 'motion/react';
import { AgentState, ConversationMessage } from '../types/vesper';
import { cn } from '../lib/utils';
import { deviceService } from '../services/device-service';
import TextReveal from './ui/TextReveal';

// ── 1. Directives & Voice Agent View ─────────────────────────────────────────

interface DirectivesViewProps {
  agentState: AgentState;
  activeHeadline?: string;
  messages: ConversationMessage[];
  isWakeWordArmed: boolean;
  onToggleWakeWord: () => void;
  onSimulateWakeWord?: () => void;
  onSendUserMessage?: (text: string) => void;
  onOpenHudDrawer?: () => void;
  hudDrawerTitle?: string;
  hasActiveHudCards?: boolean;
}

export const DirectivesView: React.FC<DirectivesViewProps> = ({
  agentState,
  activeHeadline,
  messages,
  isWakeWordArmed,
  onToggleWakeWord,
  onSimulateWakeWord,
  onSendUserMessage,
  onOpenHudDrawer,
  hudDrawerTitle,
  hasActiveHudCards = false,
}) => {
  const [testDirective, setTestDirective] = useState('');
  const speechProgress = useMotionValue(1);
  const voiceMessages = messages.filter((m) => m.sender === 'user' || m.sender === 'agent');
  const latestAgentMsg = [...messages].reverse().find((m) => m.sender === 'agent');
  const latestUserMsg = [...messages].reverse().find((m) => m.sender === 'user');

  // Synchronize TTS speech reveal in DirectivesView
  useEffect(() => {
    if (!latestAgentMsg || !latestAgentMsg.text) return;

    if (agentState === 'SPEAKING') {
      speechProgress.set(0);

      const words = latestAgentMsg.text.trim().split(/\s+/).filter(Boolean).length;
      const commas = (latestAgentMsg.text.match(/,/g) || []).length;
      const sentences = (latestAgentMsg.text.match(/[.!?]/g) || []).length;
      const duration = Math.max(2.2, words * 0.38 + commas * 0.18 + sentences * 0.35);

      const controls = animate(speechProgress, 1, {
        duration,
        ease: 'linear',
      });

      return () => controls.stop();
    } else {
      speechProgress.set(1);
    }
  }, [latestAgentMsg?.text, agentState, speechProgress]);

  const handleRunDirective = (text: string) => {
    if (onSendUserMessage && text.trim()) {
      onSendUserMessage(text.trim());
    }
  };

  return (
    <div className="w-full max-w-5xl flex flex-col items-start gap-8 py-4">
      {/* Header */}
      <div className="flex flex-col gap-1.5 text-left w-full border-b border-white/[0.08] pb-6">
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
          <Radio size={14} className="text-[#E8E3DA] animate-pulse" />
          DIRECTIVES & VOICE SYNTHESIS CONTROL
        </div>
        <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Voice Intent & Execution Pipeline</h1>
        <p className="font-sans text-sm text-[#8E8A83]">
          Manage live wake word detection, intent routing, and real-time audio directives.
        </p>
      </div>

      {/* Active Spoken Dialogue Surface & Animated TTS Transcript */}
      {latestAgentMsg && (
        <div className="w-full p-6 md:p-8 rounded-2xl bg-[#141414]/95 border border-white/[0.12] backdrop-blur-2xl shadow-2xl shadow-black/80 relative">
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-white/[0.08]">
            <div className="flex items-center gap-2.5">
              <span className={cn(
                "w-2.5 h-2.5 rounded-full",
                agentState === 'SPEAKING' ? "bg-[#E8E3DA] animate-pulse" : agentState === 'THINKING' ? "bg-cyan-400 animate-pulse" : "bg-white/40"
              )} />
              <span className="font-mono text-xs uppercase tracking-widest text-[#E8E3DA] font-semibold">
                ALFRED • {agentState === 'SPEAKING' ? 'SYNTHESIZING VOCAL SPEECH' : agentState === 'THINKING' ? 'ORCHESTRATING DIRECTIVE' : 'RESPONSE EXECUTED'}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {agentState === 'SPEAKING' && (
                <span className="font-mono text-[10px] text-[#A1A1AA] uppercase tracking-wider flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/[0.06] border border-white/10">
                  <Volume2 size={12} className="text-[#E8E3DA] animate-pulse" />
                  TTS IN SYNC
                </span>
              )}
              {hasActiveHudCards && (
                <button
                  type="button"
                  onClick={onOpenHudDrawer}
                  className="px-3.5 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.16] text-[#E8E3DA] border border-white/[0.16] font-mono text-xs flex items-center gap-2 transition-all hover:scale-105 active:scale-95 cursor-pointer shadow-lg"
                >
                  <Wrench size={13} className="text-[#D1CFC0]" />
                  <span>OPEN {hudDrawerTitle || 'HUD DECK'}</span>
                </button>
              )}
            </div>
          </div>

          {(activeHeadline || latestUserMsg?.text) && (
            <div className="flex items-center gap-2 font-mono text-xs text-[#A1A1AA] pb-3 mb-4 border-b border-white/[0.04]">
              <Terminal size={13} className="text-[#8E8A83]" />
              <span className="text-[#8E8A83]">Directive:</span>
              <span className="text-[#E8E3DA] truncate">"{activeHeadline || latestUserMsg?.text}"</span>
            </div>
          )}

          <TextReveal
            text={latestAgentMsg.text}
            speechProgress={speechProgress}
            autoScroll={true}
            darkWatermarkColor="#8E8A83"
            darkTextColor="#E8E3DA"
            highlightColor="#FFFFFF"
            paragraphClassName="!text-xl md:!text-2xl !leading-relaxed font-sans font-medium text-[#E8E3DA]"
          />

          {latestAgentMsg.latencyMs && (
            <div className="flex items-center justify-between pt-4 mt-4 border-t border-white/[0.06] font-mono text-[11px] text-[#8E8A83]">
              <span>Intent: {latestAgentMsg.intent || 'DIRECTIVE_EXECUTION'}</span>
              <span>Latency: {latestAgentMsg.latencyMs}ms</span>
            </div>
          )}
        </div>
      )}

      {/* Voice Status & Wake Word Card */}
      <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs text-[#8E8A83] uppercase">Agent State</span>
            <span className={cn(
              "w-2 h-2 rounded-full",
              agentState === 'SPEAKING' ? "bg-emerald-400 animate-ping" : agentState === 'LISTENING' ? "bg-amber-400 animate-pulse" : "bg-white/40"
            )} />
          </div>
          <span className="font-mono text-2xl font-bold text-[#E8E3DA]">{agentState}</span>
          <span className="font-sans text-xs text-[#8E8A83] mt-2">
            {agentState === 'LISTENING' ? 'Buffering acoustic input...' : agentState === 'SPEAKING' ? 'Synthesizing Piper/ElevenLabs speech' : 'Awaiting vocal directive'}
          </span>
        </div>

        <div className="p-5 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs text-[#8E8A83] uppercase">Wake Word</span>
            <button
              type="button"
              onClick={onToggleWakeWord}
              className={cn(
                "px-2.5 py-0.5 rounded font-mono text-[10px] border transition-colors",
                isWakeWordArmed ? "bg-white/[0.14] text-[#E8E3DA] border-white/20" : "bg-transparent text-[#8E8A83] border-white/10"
              )}
            >
              {isWakeWordArmed ? 'ARMED' : 'DISARMED'}
            </button>
          </div>
          <span className="font-mono text-xl font-semibold text-[#E8E3DA] truncate">"Hey Alfred" / "Jarvis"</span>
          <span className="font-sans text-xs text-[#8E8A83] mt-2">Threshold: 0.45 • OpenWakeWord v0.6</span>
        </div>

        <div className="p-5 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs text-[#8E8A83] uppercase">Interactive Test</span>
            <Mic size={14} className="text-[#8E8A83]" />
          </div>
          <button
            type="button"
            onClick={onSimulateWakeWord}
            className="w-full py-2 px-3 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-[#E8E3DA] text-xs font-mono border border-white/[0.10] transition-colors flex items-center justify-center gap-2"
          >
            <Volume2 size={13} />
            Simulate Wake Trigger
          </button>
          <span className="font-sans text-xs text-[#8E8A83] mt-2">Instantly engages listening state</span>
        </div>
      </div>

      {/* Manual Directive Dispatcher */}
      <div className="w-full p-5 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col gap-3">
        <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">Execute Text Directive</span>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="e.g. Schedule meeting with team tomorrow at 3pm, or play music..."
            value={testDirective}
            onChange={(e) => setTestDirective(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleRunDirective(testDirective);
                setTestDirective('');
              }
            }}
            className="flex-1 bg-black/50 border border-white/[0.10] rounded-lg px-3.5 py-2 text-sm text-[#E8E3DA] placeholder-[#5C5A56] focus:outline-none focus:border-white/30 font-sans"
          />
          <button
            type="button"
            onClick={() => {
              handleRunDirective(testDirective);
              setTestDirective('');
            }}
            className="px-4 py-2 rounded-lg bg-white/[0.10] hover:bg-white/[0.18] text-[#E8E3DA] font-mono text-xs border border-white/[0.12] transition-colors"
          >
            Dispatch
          </button>
        </div>
      </div>

      {/* Recent Directives History */}
      <div className="w-full flex flex-col gap-3">
        <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">Recent Directive Stream</span>
        <div className="w-full flex flex-col gap-2 max-h-96 overflow-y-auto pr-1">
          {voiceMessages.length === 0 ? (
            <div className="p-6 rounded-xl bg-[#141414] border border-white/[0.06] text-center text-[#8E8A83] font-sans text-sm">
              No recent vocal directives logged in this session.
            </div>
          ) : (
            voiceMessages.slice(-8).reverse().map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "p-4 rounded-xl border flex flex-col gap-1.5 transition-all text-left",
                  msg.sender === 'user'
                    ? "bg-[#181818] border-white/[0.10]"
                    : "bg-[#141414] border-white/[0.05]"
                )}
              >
                <div className="flex items-center justify-between font-mono text-[10px] text-[#8E8A83]">
                  <span className="uppercase font-semibold text-[#D1CFC0]">
                    {msg.sender === 'user' ? 'YOU (VOICE/DIRECTIVE)' : 'ALFRED (RESPONSE)'}
                  </span>
                  <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                </div>
                <p className="font-sans text-sm text-[#E8E3DA] whitespace-pre-wrap">{msg.text}</p>
                {msg.latencyMs && (
                  <span className="font-mono text-[9px] text-[#8E8A83]">Latency: {msg.latencyMs}ms</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

// ── 2. Full Cognitive Swarm & Services View ─────────────────────────────────

interface ServicesViewProps {
  onSendUserMessage?: (text: string) => void;
}

export const ServicesView: React.FC<ServicesViewProps> = ({ onSendUserMessage }) => {
  const [devices] = useState(deviceService.getDevices());

  const specialistAgents = [
    {
      id: 'alfred-core',
      name: 'Alfred Core Orchestrator',
      role: 'Intent routing, proactive briefings & cognitive swarm coordination',
      model: 'FastPath + Gemini Flash 2.5',
      status: 'Active',
      Icon: Bot,
      actionPrompt: 'Provide an executive status briefing on active priorities',
    },
    {
      id: 'task-calendar',
      name: 'Task & Google Calendar Manager',
      role: 'Two-way Google Calendar v3 sync, overdue alerts & task priorities',
      model: 'OAuth v3 • Supabase DB',
      status: 'Synchronized',
      Icon: CalendarCheck,
      actionPrompt: "List today's high-priority tasks and calendar schedule",
    },
    {
      id: 'finance-specialist',
      name: 'Financial Ledger & Intelligence',
      role: 'Realtime transaction logging, balance queries & expense categorization',
      model: 'Supabase Postgres',
      status: 'Online',
      Icon: DollarSign,
      actionPrompt: 'Check current financial balance and recent transactions',
    },
    {
      id: 'media-specialist',
      name: 'Spotify & Media Audio Engine',
      role: 'Turntable vinyl visualizer, MPRIS local daemon & playback state',
      model: 'Spotify Web API & MPRIS',
      status: 'Ready',
      Icon: Music,
      actionPrompt: 'What is currently playing on Spotify?',
    },
    {
      id: 'vision-sentry',
      name: 'Vision & Workspace Sentry',
      role: 'BlazeFace camera presence detection, attention tracking & lock',
      model: 'BlazeFace XNNPACK',
      status: 'Armed',
      Icon: Eye,
      actionPrompt: 'Run optical presence scan',
    },
    {
      id: 'voice-pipeline',
      name: 'Neural Voice Pipeline',
      role: 'openWakeWord "Hey Alfred", Faster-Whisper Base STT & Piper TTS',
      model: 'Whisper FP16 + Piper',
      status: 'Armed',
      Icon: Mic,
      actionPrompt: 'Test voice pipeline synthesis',
    },
  ];

  return (
    <div className="w-full max-w-5xl flex flex-col items-start gap-8 py-4">
      {/* Header */}
      <div className="flex flex-col gap-1.5 text-left w-full border-b border-white/[0.08] pb-6">
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
          <Layers size={14} className="text-[#E8E3DA]" />
          VESPER COGNITIVE SWARM & SERVICE MESH
        </div>
        <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Specialist Agents & Active Services</h1>
        <p className="font-sans text-sm text-[#8E8A83]">
          Operational AI specialists, local background services, and synchronized hardware mesh.
        </p>
      </div>

      {/* Specialist Agents Grid */}
      <div className="w-full flex flex-col gap-3 text-left">
        <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">Operational Specialist Agents</span>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {specialistAgents.map((agent) => (
            <div
              key={agent.id}
              className="p-5 rounded-xl bg-[#181818] border border-white/[0.08] hover:border-white/20 transition-all flex flex-col justify-between text-left"
            >
              <div className="flex items-start justify-between w-full mb-2">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.08] text-[#E8E3DA]">
                    <agent.Icon size={18} />
                  </div>
                  <div className="flex flex-col">
                    <span className="font-sans text-sm font-semibold text-[#E8E3DA]">{agent.name}</span>
                    <span className="font-mono text-[10px] text-[#8E8A83]">{agent.model}</span>
                  </div>
                </div>
                <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-white/[0.05] text-[#D1CFC0] border border-white/[0.10]">
                  {agent.status}
                </span>
              </div>
              <p className="font-sans text-xs text-[#8E8A83] my-2 leading-relaxed">{agent.role}</p>
              <div className="flex items-center justify-between pt-2 border-t border-white/[0.04] mt-2">
                <span className="font-mono text-[10px] text-[#5C5A56]">Specialist Swarm Node</span>
                {onSendUserMessage && (
                  <button
                    type="button"
                    onClick={() => onSendUserMessage(agent.actionPrompt)}
                    className="flex items-center gap-1 font-mono text-[10px] text-[#E8E3DA] hover:text-white px-2.5 py-1 rounded bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 transition-colors cursor-pointer"
                  >
                    Invoke <ArrowRight size={11} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Synchronized Hardware Mesh */}
      <div className="w-full flex flex-col gap-3 text-left">
        <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">Synchronized Hardware Mesh</span>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {devices.map((dev) => {
            const isProvisioned =
              dev.device_id.includes('provisioned') ||
              dev.ip_address === 'Provisioned' ||
              dev.network_type?.includes('Provisioned');
            return (
              <div
                key={dev.device_id}
                className="p-5 rounded-xl bg-[#181818] border border-white/[0.08] flex items-start justify-between"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.08] text-[#E8E3DA]">
                    {dev.device_type === 'phone' || dev.device_type === 'mobile' ? <Smartphone size={20} /> : <Laptop size={20} />}
                  </div>
                  <div className="flex flex-col">
                    <span className="font-sans text-sm font-semibold text-[#E8E3DA]">{dev.device_name}</span>
                    <span className="font-mono text-xs text-[#8E8A83] mt-0.5">
                      {isProvisioned ? 'Provisioned (Standby) • App in Dev' : dev.ip_address || 'Local IPC'}
                    </span>
                    <span className="font-mono text-[10px] text-[#8E8A83] mt-2">
                      Battery: {dev.battery_level !== undefined && dev.battery_level !== null ? `${dev.battery_level}%${dev.is_charging ? ' (Charging)' : ''}` : 'AC Power'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={cn(
                    "w-2 h-2 rounded-full",
                    dev.is_online ? "bg-[#E8E3DA] animate-pulse" : "bg-white/40"
                  )} />
                  <span className="font-mono text-[10px] uppercase text-[#D1CFC0]">
                    {isProvisioned ? 'PROVISIONED' : dev.is_online ? 'ONLINE' : 'STANDBY'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Core Background Subsystems */}
      <div className="w-full p-5 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col gap-4 text-left">
        <span className="font-mono text-xs text-[#8E8A83] uppercase tracking-wider">Subsystem Health Checklist</span>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="flex items-center gap-2.5 p-3 rounded-lg bg-black/40 border border-white/[0.05]">
            <CheckCircle2 size={16} className="text-[#E8E3DA]" />
            <div className="flex flex-col">
              <span className="font-mono text-xs text-[#E8E3DA]">FastAPI Gateway</span>
              <span className="font-mono text-[10px] text-[#8E8A83]">Port 8000 (Live Reload)</span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 p-3 rounded-lg bg-black/40 border border-white/[0.05]">
            <CheckCircle2 size={16} className="text-[#E8E3DA]" />
            <div className="flex flex-col">
              <span className="font-mono text-xs text-[#E8E3DA]">Supabase Postgres</span>
              <span className="font-mono text-[10px] text-[#8E8A83]">Tasks & Ledger Online</span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 p-3 rounded-lg bg-black/40 border border-white/[0.05]">
            <CheckCircle2 size={16} className="text-[#E8E3DA]" />
            <div className="flex flex-col">
              <span className="font-mono text-xs text-[#E8E3DA]">Google Calendar</span>
              <span className="font-mono text-[10px] text-[#8E8A83]">OAuth v3 Two-Way Sync</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const TelemetryView = ServicesView;

// ── 3. Dedicated Logs Stream View ────────────────────────────────────────────

interface LogsViewProps {
  messages: ConversationMessage[];
  onClearLogs?: () => void;
}

export const LogsView: React.FC<LogsViewProps> = ({ messages, onClearLogs }) => {
  const [filter, setFilter] = useState<'all' | 'user' | 'agent' | 'system'>('all');

  const filteredMessages = messages.filter((m) => {
    if (filter === 'all') return true;
    return m.sender === filter;
  });

  return (
    <div className="w-full max-w-5xl flex flex-col items-start gap-6 py-4">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between w-full border-b border-white/[0.08] pb-6 gap-4 text-left">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
            <Terminal size={14} className="text-[#E8E3DA]" />
            SYSTEM LOGS & ENVELOPE STREAM
          </div>
          <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Workstation Event Stream</h1>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-black/50 p-1 rounded-lg border border-white/[0.08]">
            {(['all', 'user', 'agent', 'system'] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  "px-3 py-1 rounded font-mono text-xs capitalize transition-colors",
                  filter === f
                    ? "bg-white/[0.14] text-[#E8E3DA] font-semibold"
                    : "text-[#8E8A83] hover:text-[#D1CFC0]"
                )}
              >
                {f}
              </button>
            ))}
          </div>
          {onClearLogs && (
            <button
              type="button"
              onClick={onClearLogs}
              className="p-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-[#8E8A83] hover:text-[#E8E3DA] transition-colors border border-white/[0.08]"
              title="Clear Event Stream"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Terminal Log Console */}
      <div className="w-full rounded-2xl bg-[#0e0e0e] border border-white/[0.10] p-6 shadow-2xl flex flex-col gap-2 font-mono text-xs max-h-[620px] overflow-y-auto text-left">
        {filteredMessages.length === 0 ? (
          <div className="py-12 text-center text-[#5C5A56]">No logged envelopes match filter "{filter}".</div>
        ) : (
          filteredMessages.map((msg, i) => (
            <div
              key={msg.id || i}
              className="py-2.5 px-3 rounded-lg hover:bg-white/[0.03] transition-colors flex items-start gap-4 border-b border-white/[0.03]"
            >
              <span className="text-[#5C5A56] shrink-0">{new Date(msg.timestamp).toLocaleTimeString()}</span>
              <span
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] uppercase font-bold shrink-0",
                  msg.sender === 'user'
                    ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                    : msg.sender === 'agent'
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "bg-white/[0.08] text-[#8E8A83] border border-white/[0.10]"
                )}
              >
                {msg.sender}
              </span>
              <div className="flex-1 flex flex-col gap-0.5">
                <span className="text-[#E8E3DA] font-sans text-sm whitespace-pre-wrap">{msg.text}</span>
                {msg.intent && (
                  <span className="text-[10px] text-[#8E8A83]">INTENT: {msg.intent}</span>
                )}
              </div>
              {msg.latencyMs && (
                <span className="text-[10px] text-[#5C5A56] shrink-0">{msg.latencyMs}ms</span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
