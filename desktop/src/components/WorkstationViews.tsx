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
  Wrench,
  Mail,
  Cloud,
  Search,
  Globe,
  GitBranch,
  Cpu,
  Database,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Clock,
  Hand
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
  onOpenTools?: () => void;
}

export const ServicesView: React.FC<ServicesViewProps> = ({ onSendUserMessage, onOpenTools }) => {
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
      id: 'email-specialist',
      name: 'Email & Correspondence Specialist',
      role: 'Gmail triage, VIP sender alerts, unread digests & thread summaries',
      model: 'Gmail OAuth v2 • FastPath',
      status: 'Online',
      Icon: Mail,
      actionPrompt: 'Check my unread emails and summarize urgent messages',
    },
    {
      id: 'weather-specialist',
      name: 'Atmospheric & Weather Intelligence',
      role: 'Local meteorological telemetry, rain radar & hourly forecast warnings',
      model: 'Open-Meteo REST API',
      status: 'Active',
      Icon: Cloud,
      actionPrompt: 'What is the current weather radar and today’s forecast?',
    },
    {
      id: 'research-specialist',
      name: 'Deep Web & Research Specialist',
      role: 'Multi-query web search, verified source synthesis & executive briefs',
      model: 'DuckDuckGo API • Gemini 2.5',
      status: 'Ready',
      Icon: Search,
      actionPrompt: 'Research the latest advancements in AI multi-agent swarms',
    },
    {
      id: 'crawl-specialist',
      name: 'Web Extraction & Scraper Specialist',
      role: 'Structured content extraction, article cleanup & markdown scraping',
      model: 'Firecrawl / BeautifulSoup4',
      status: 'Standby',
      Icon: Globe,
      actionPrompt: 'Scrape and summarize the latest project documentation',
    },
    {
      id: 'github-specialist',
      name: 'GitHub & DevOps Specialist',
      role: 'Pull request reviews, active repo issues & commit history auditing',
      model: 'GitHub REST API v3',
      status: 'Connected',
      Icon: GitBranch,
      actionPrompt: 'Check recent pull requests and open issues on our repository',
    },
    {
      id: 'system-specialist',
      name: 'System Operations & Hardware Manager',
      role: 'CPU/RAM load metrics, DPMS display sentry & shell execution engine',
      model: 'Linux sysfs • systemd • DPMS',
      status: 'Online',
      Icon: Cpu,
      actionPrompt: 'Report current system diagnostics, RAM usage, and display power',
    },
    {
      id: 'memory-specialist',
      name: 'Episodic & Semantic Memory Specialist',
      role: 'Persistent vector storage, user preference recall & cross-session continuity',
      model: 'pgvector • Supabase Embeddings',
      status: 'Indexed',
      Icon: Database,
      actionPrompt: 'Recall stored preferences and notes regarding our setup',
    },
    {
      id: 'vision-sentry',
      name: 'Vision & Workspace Sentry',
      role: 'BlazeFace camera presence detection, attention tracking & on-demand VLLM/OCR',
      model: 'BlazeFace XNNPACK / TensorRT',
      status: 'Armed',
      Icon: Eye,
      actionPrompt: 'Run optical presence scan',
    },
    {
      id: 'conversation-specialist',
      name: 'Persona & Conversation Specialist',
      role: 'Alfred conversational continuity, British butler persona & empathetic banter',
      model: 'Gemini 2.5 Flash / FastPath',
      status: 'Active',
      Icon: Sparkles,
      actionPrompt: 'Alfred, how are our operations running this evening?',
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
      <div className="flex flex-col md:flex-row items-start md:items-end justify-between gap-4 text-left w-full border-b border-white/[0.08] pb-6">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
            <Layers size={14} className="text-[#E8E3DA]" />
            VESPER COGNITIVE SWARM & SERVICE MESH
          </div>
          <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Specialist Agents & Active Services</h1>
          <p className="font-sans text-sm text-[#8E8A83]">
            Operational AI specialists, local background services, and synchronized hardware mesh.
          </p>
        </div>
        {onOpenTools && (
          <button
            type="button"
            onClick={onOpenTools}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.12] text-[#E8E3DA] hover:text-white font-mono text-xs transition-all cursor-pointer shrink-0"
          >
            <Wrench size={13} className="text-[#D1CFC0]" />
            Specialist Tool Emitter
            <ArrowRight size={12} className="text-[#8E8A83]" />
          </button>
        )}
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

// ── 3. Dedicated Logs Stream View with Query Grouping & Singleton Cards ─────

interface LogsViewProps {
  messages: ConversationMessage[];
  onClearLogs?: () => void;
}

interface QuerySessionGroup {
  type: 'query_group';
  id: string;
  queryId: string;
  queryText: string;
  timestamp: number;
  intent?: string;
  latencyMs?: number;
  userMessage?: ConversationMessage;
  agentResponse?: ConversationMessage;
  toolActions: Array<{
    toolName: string;
    specialist?: string;
    parameters?: Record<string, any>;
    status?: string;
    result?: any;
    latencyMs?: number;
  }>;
  hudCards: Array<{
    type?: string;
    title?: string;
  }>;
}

interface SingletonEvent {
  type: 'singleton';
  id: string;
  timestamp: number;
  category: 'gesture' | 'wakeword' | 'media' | 'zen' | 'system';
  title: string;
  detail?: string;
  intent?: string;
  gesture?: string;
  action?: string;
  rawMessage: ConversationMessage;
}

type EventStreamItem = QuerySessionGroup | SingletonEvent;

export const LogsView: React.FC<LogsViewProps> = ({ messages, onClearLogs }) => {
  const [filter, setFilter] = useState<'all' | 'queries' | 'gestures' | 'system'>('all');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const toggleGroupExpand = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  // Process and group raw messages into QuerySessionGroups and SingletonEvents
  const streamItems = React.useMemo(() => {
    const items: EventStreamItem[] = [];
    const queryGroupsMap = new Map<string, QuerySessionGroup>();

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];

      // Singleton detection: hand gestures, wake word, volume, zen mode, or explicit singletons
      if (
        msg.isSingleton ||
        msg.intent === 'GESTURE' ||
        msg.eventType === 'GESTURE_EVENT' ||
        msg.channel === 'GESTURE' ||
        msg.eventType === 'WAKE_WORD_DETECTED' ||
        msg.eventType === 'ZEN_MODE_STATE' ||
        msg.eventType === 'MEDIA_CONTROL' ||
        msg.eventType === 'SET_VOLUME'
      ) {
        let category: 'gesture' | 'wakeword' | 'media' | 'zen' | 'system' = 'system';
        if (msg.intent === 'GESTURE' || msg.eventType === 'GESTURE_EVENT' || msg.channel === 'GESTURE') {
          category = 'gesture';
        } else if (msg.intent === 'WAKE_WORD' || msg.eventType === 'WAKE_WORD_DETECTED') {
          category = 'wakeword';
        } else if (msg.intent === 'ZEN_MODE' || msg.eventType === 'ZEN_MODE_STATE') {
          category = 'zen';
        } else if (msg.intent === 'MEDIA' || msg.intent === 'VOLUME' || msg.eventType === 'MEDIA_CONTROL' || msg.eventType === 'SET_VOLUME') {
          category = 'media';
        }

        items.push({
          type: 'singleton',
          id: msg.id || `singleton-${i}`,
          timestamp: msg.timestamp,
          category,
          title: msg.text,
          detail: msg.intent ? `Intent: ${msg.intent}` : undefined,
          intent: msg.intent,
          gesture: msg.gesture,
          action: msg.action,
          rawMessage: msg,
        });
        continue;
      }

      // Query Grouping: User questions and corresponding Agent responses
      const qId = msg.queryId || msg.id;

      if (msg.sender === 'user') {
        const group: QuerySessionGroup = {
          type: 'query_group',
          id: qId,
          queryId: qId,
          queryText: msg.text || msg.queryText || 'User Directive',
          timestamp: msg.timestamp,
          intent: msg.intent,
          latencyMs: msg.latencyMs,
          userMessage: msg,
          toolActions: [],
          hudCards: [],
        };
        queryGroupsMap.set(qId, group);
        items.push(group);
      } else if (msg.sender === 'agent') {
        let group = queryGroupsMap.get(qId);
        if (!group) {
          // If queryId didn't match directly, attach to most recent query group if within 8s
          const recentGroup = [...items].reverse().find(
            (it): it is QuerySessionGroup => it.type === 'query_group' && (!it.agentResponse || it.id === qId)
          );
          if (recentGroup && Math.abs(msg.timestamp - recentGroup.timestamp) < 8000) {
            group = recentGroup;
          } else {
            group = {
              type: 'query_group',
              id: qId,
              queryId: qId,
              queryText: msg.queryText || 'Autonomous Agent Execution',
              timestamp: msg.timestamp,
              intent: msg.intent,
              latencyMs: msg.latencyMs,
              toolActions: [],
              hudCards: [],
            };
            items.push(group);
          }
        }

        group.agentResponse = msg;
        if (msg.intent) group.intent = msg.intent;
        if (msg.latencyMs) group.latencyMs = msg.latencyMs;

        // Populate tool actions from specialistActions metadata
        if (msg.specialistActions && msg.specialistActions.length > 0) {
          for (const act of msg.specialistActions) {
            group.toolActions.push({
              toolName: act.tool_name || act.action || 'specialist_action',
              specialist: act.specialist,
              parameters: act.parameters,
              status: act.status || 'SUCCESS',
              result: act.result,
              latencyMs: act.latency_ms,
            });
          }
        }

        // Also parse HUD cards into tool actions if specialistActions was empty
        if (group.toolActions.length === 0 && msg.cards && msg.cards.length > 0) {
          for (const card of msg.cards) {
            group.hudCards.push({
              type: card.type,
              title: card.title,
            });
            group.toolActions.push({
              toolName: `${card.type || 'tool'}.execute`,
              specialist: card.title || 'Cognitive Specialist',
              status: 'EXECUTED',
              result: card.data,
            });
          }
        }
      } else {
        // Fallback for generic system messages
        items.push({
          type: 'singleton',
          id: msg.id || `sys-${i}`,
          timestamp: msg.timestamp,
          category: 'system',
          title: msg.text,
          detail: msg.intent,
          rawMessage: msg,
        });
      }
    }

    return items;
  }, [messages]);

  // Apply active filter
  const filteredItems = streamItems.filter((item) => {
    if (filter === 'all') return true;
    if (filter === 'queries') return item.type === 'query_group';
    if (filter === 'gestures') return item.type === 'singleton' && item.category === 'gesture';
    if (filter === 'system') return item.type === 'singleton' && item.category !== 'gesture';
    return true;
  });

  // Calculate statistics
  const totalQueries = streamItems.filter((it) => it.type === 'query_group').length;
  const totalGestures = streamItems.filter((it) => it.type === 'singleton' && it.category === 'gesture').length;
  const totalTools = streamItems.reduce((acc, it) => (it.type === 'query_group' ? acc + it.toolActions.length : acc), 0);

  return (
    <div className="w-full max-w-5xl flex flex-col items-start gap-6 py-4 select-none">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between w-full border-b border-white/[0.08] pb-6 gap-4 text-left">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
            <Terminal size={14} className="text-[#E8E3DA]" />
            SYSTEM LOGS & ENVELOPE STREAM
          </div>
          <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Workstation Event Stream</h1>
          <p className="font-sans text-xs text-[#8E8A83]">
            Hierarchically grouped multi-step query timelines and direct singleton perception cards.
          </p>
        </div>

        {/* Action Controls & Filters */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-black/50 p-1 rounded-lg border border-white/[0.08] font-mono text-xs">
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={cn(
                "px-3 py-1 rounded transition-colors cursor-pointer",
                filter === 'all' ? "bg-white/[0.14] text-[#E8E3DA] font-semibold" : "text-[#8E8A83] hover:text-[#D1CFC0]"
              )}
            >
              All ({streamItems.length})
            </button>
            <button
              type="button"
              onClick={() => setFilter('queries')}
              className={cn(
                "px-3 py-1 rounded transition-colors cursor-pointer",
                filter === 'queries' ? "bg-white/[0.14] text-[#E8E3DA] font-semibold" : "text-[#8E8A83] hover:text-[#D1CFC0]"
              )}
            >
              Queries & Tools ({totalQueries})
            </button>
            <button
              type="button"
              onClick={() => setFilter('gestures')}
              className={cn(
                "px-3 py-1 rounded transition-colors cursor-pointer",
                filter === 'gestures' ? "bg-white/[0.14] text-[#E8E3DA] font-semibold" : "text-[#8E8A83] hover:text-[#D1CFC0]"
              )}
            >
              Gestures ({totalGestures})
            </button>
            <button
              type="button"
              onClick={() => setFilter('system')}
              className={cn(
                "px-3 py-1 rounded transition-colors cursor-pointer",
                filter === 'system' ? "bg-white/[0.14] text-[#E8E3DA] font-semibold" : "text-[#8E8A83] hover:text-[#D1CFC0]"
              )}
            >
              System / Audio
            </button>
          </div>

          {onClearLogs && (
            <button
              type="button"
              onClick={onClearLogs}
              className="p-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-[#8E8A83] hover:text-[#E8E3DA] transition-colors border border-white/[0.08] cursor-pointer"
              title="Clear Event Stream"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Telemetry Counter Strip */}
      <div className="w-full grid grid-cols-2 sm:grid-cols-4 gap-3 text-left font-mono text-xs">
        <div className="p-3 rounded-xl bg-[#141414] border border-white/[0.06] flex flex-col gap-1">
          <span className="text-[#8E8A83] text-[10px] uppercase">Logged Events</span>
          <span className="text-base font-bold text-[#E8E3DA]">{streamItems.length}</span>
        </div>
        <div className="p-3 rounded-xl bg-[#141414] border border-white/[0.06] flex flex-col gap-1">
          <span className="text-[#8E8A83] text-[10px] uppercase">Query Sessions</span>
          <span className="text-base font-bold text-cyan-300">{totalQueries}</span>
        </div>
        <div className="p-3 rounded-xl bg-[#141414] border border-white/[0.06] flex flex-col gap-1">
          <span className="text-[#8E8A83] text-[10px] uppercase">Tool Invocations</span>
          <span className="text-base font-bold text-amber-300">{totalTools}</span>
        </div>
        <div className="p-3 rounded-xl bg-[#141414] border border-white/[0.06] flex flex-col gap-1">
          <span className="text-[#8E8A83] text-[10px] uppercase">Gestures Perceived</span>
          <span className="text-base font-bold text-emerald-300">{totalGestures}</span>
        </div>
      </div>

      {/* Main Event Stream Timeline Console */}
      <div className="w-full flex flex-col gap-3 max-h-[640px] overflow-y-auto pr-1">
        {filteredItems.length === 0 ? (
          <div className="py-16 text-center text-[#5C5A56] font-mono text-sm bg-[#121212] rounded-2xl border border-white/[0.06]">
            No workstation events match filter "{filter}".
          </div>
        ) : (
          filteredItems.map((item) => {
            // ── TYPE A: Query Group (Multi-step User Query & Specialist Actions) ────
            if (item.type === 'query_group') {
              const isExpanded = expandedGroups.has(item.id);
              const hasTools = item.toolActions.length > 0;

              return (
                <div
                  key={item.id}
                  className="rounded-xl border border-white/[0.12] bg-[#161616] p-4 text-left shadow-lg flex flex-col gap-3 transition-all"
                >
                  {/* Group Header */}
                  <div
                    onClick={() => hasTools && toggleGroupExpand(item.id)}
                    className={cn(
                      "flex items-start justify-between gap-3 select-none",
                      hasTools && "cursor-pointer group"
                    )}
                  >
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="p-2 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/20 shrink-0 mt-0.5">
                        <Bot size={16} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold uppercase">
                            QUERY SESSION
                          </span>
                          {item.intent && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-[#D1CFC0] border border-white/10">
                              INTENT: {item.intent}
                            </span>
                          )}
                          {item.latencyMs && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/25 flex items-center gap-1 font-semibold">
                              <Clock size={10} />
                              {item.latencyMs}ms
                            </span>
                          )}
                          {hasTools && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/25 font-semibold">
                              {item.toolActions.length} TOOL ACTION{item.toolActions.length > 1 ? 'S' : ''}
                            </span>
                          )}
                        </div>
                        <span className="font-sans text-sm font-semibold text-[#E8E3DA] group-hover:text-white transition-colors">
                          "{item.queryText}"
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="font-mono text-[10px] text-[#5C5A56]">
                        {new Date(item.timestamp).toLocaleTimeString([], { hour12: false })}
                      </span>
                      {hasTools && (
                        <button
                          type="button"
                          className="p-1 rounded text-[#8E8A83] group-hover:text-[#E8E3DA] transition-colors"
                        >
                          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Agent Response Summary */}
                  {item.agentResponse?.text && (
                    <div className="pl-11 pr-2 py-2 text-xs font-sans text-[#D1CFC0] border-l-2 border-cyan-500/30 ml-4 leading-relaxed bg-black/20 rounded-r-lg">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-cyan-400 font-bold block mb-1">
                        ALFRED SYNTHESIS:
                      </span>
                      <p className="whitespace-pre-wrap">{item.agentResponse.text}</p>
                    </div>
                  )}

                  {/* Expandable Specialist Actions & Tools Timeline */}
                  {hasTools && isExpanded && (
                    <div className="mt-2 pl-4 border-l-2 border-amber-500/30 flex flex-col gap-2 ml-4 pt-2">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-amber-300 font-semibold">
                        SPECIALIST EXECUTION TIMELINE:
                      </span>
                      {item.toolActions.map((tool, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-lg bg-black/40 border border-white/[0.06] flex flex-col gap-1 font-mono text-[11px]"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-[#E8E3DA]">
                              <Wrench size={12} className="text-amber-400" />
                              <span className="font-bold">{tool.toolName}</span>
                              {tool.specialist && (
                                <span className="text-[#8E8A83] text-[10px]">({tool.specialist})</span>
                              )}
                            </div>
                            <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 text-[9px] font-bold">
                              {tool.status || 'SUCCESS'}
                            </span>
                          </div>
                          {tool.parameters && Object.keys(tool.parameters).length > 0 && (
                            <pre className="p-1.5 rounded bg-black/50 text-[10px] text-[#A1A1AA] overflow-x-auto">
                              Args: {JSON.stringify(tool.parameters)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            }

            // ── TYPE B: Singleton Commands & Direct Perceived Triggers ─────────
            const cat = item.category;
            let badgeBg = "bg-white/[0.08] text-[#8E8A83] border-white/10";
            let IconComponent = Terminal;

            if (cat === 'gesture') {
              badgeBg = "bg-purple-500/20 text-purple-300 border-purple-500/30";
              IconComponent = Hand;
            } else if (cat === 'wakeword') {
              badgeBg = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
              IconComponent = Mic;
            } else if (cat === 'zen') {
              badgeBg = "bg-indigo-500/20 text-indigo-300 border-indigo-500/30";
              IconComponent = Sparkles;
            } else if (cat === 'media') {
              badgeBg = "bg-pink-500/20 text-pink-300 border-pink-500/30";
              IconComponent = Music;
            }

            return (
              <div
                key={item.id}
                className="p-3.5 rounded-xl border border-white/[0.07] bg-[#121212] hover:bg-[#151515] transition-colors flex items-center justify-between gap-4 text-left shadow-sm"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-2 rounded-lg bg-white/[0.04] text-[#E8E3DA] shrink-0">
                    <IconComponent size={14} />
                  </div>
                  <div className="flex flex-col min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded border uppercase font-bold ${badgeBg}`}>
                        {cat === 'gesture' ? (item.gesture || 'GESTURE') : cat.toUpperCase()}
                      </span>
                      <span className="font-sans text-xs font-semibold text-[#E8E3DA] truncate">
                        {item.title}
                      </span>
                    </div>
                    {item.detail && (
                      <span className="font-mono text-[10px] text-[#8E8A83] truncate mt-0.5">
                        {item.detail}
                      </span>
                    )}
                  </div>
                </div>

                <span className="font-mono text-[10px] text-[#5C5A56] shrink-0">
                  {new Date(item.timestamp).toLocaleTimeString([], { hour12: false })}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

