import React, { useState } from 'react';
import { 
  Play, 
  Sparkles, 
  RotateCcw, 
  Sliders, 
  Mail, 
  Cloud, 
  Search, 
  Globe, 
  GitBranch, 
  Cpu, 
  Database, 
  Music, 
  CheckSquare, 
  Calendar, 
  CreditCard, 
  Wrench,
  ExternalLink
} from 'lucide-react';
import { HudOutput, HudCardType } from '../types/vesper';
import { notificationStore } from '../services/notification-store';
import { HudCard } from './HudDrawer';

export type ToolCategory = 'all' | 'productivity' | 'finance' | 'intel' | 'media' | 'system_code';

export interface MockToolDefinition {
  id: string;
  name: string;
  specialist: string;
  category: ToolCategory;
  description: string;
  icon: React.FC<{ size?: number; className?: string }>;
  hudType: HudCardType;
  cardTitle: string;
  mockArgs: Record<string, any>;
  mockResult: Record<string, any>;
  hudData: Record<string, any>;
}

export const MOCK_TOOLS_REGISTRY: MockToolDefinition[] = [
  // ── 1. Productivity ──────────────────────────────────────────────────────────
  {
    id: 'email.list_emails',
    name: 'email.list_emails',
    specialist: 'Email & Correspondence Specialist',
    category: 'productivity',
    description: 'Fetches unread inbox messages, parses senders, snippets, and priorities',
    icon: Mail,
    hudType: 'email',
    cardTitle: 'UNREAD INBOX & CORRESPONDENCE',
    mockArgs: { max_results: 5, query: 'is:unread' },
    mockResult: { status: 'success', total_unread: 2 },
    hudData: {
      title: 'Unread Executive Correspondence',
      emails: [
        {
          id: 'em_1',
          sender: 'Satya Nadella <satya@microsoft.com>',
          subject: 'VESPER Edge AI Deployment Review',
          snippet: 'Mihir, following up on our discussion regarding edge inference benchmarks and Jetson Orin integration...',
          date: '10m ago',
          unread: true,
        },
        {
          id: 'em_2',
          sender: 'GitHub Notifications <notifications@github.com>',
          subject: '[VESPER] PR #42 merged: TensorRT Jetson Zero-Copy DMA',
          snippet: 'Your pull request was successfully verified and merged into main branch.',
          date: '28m ago',
          unread: true,
        },
      ],
    },
  },
  {
    id: 'task.list_tasks',
    name: 'task.list_tasks',
    specialist: 'Task & Google Calendar Manager',
    category: 'productivity',
    description: 'Queries active deliverables, overdue priorities, and completion states',
    icon: CheckSquare,
    hudType: 'task',
    cardTitle: 'ACTIVE TASKS & EXECUTIVE AGENDA',
    mockArgs: { status: 'pending', sort: 'deadline' },
    mockResult: { count: 3, source: 'Supabase + Google Tasks' },
    hudData: {
      title: 'Today’s High-Priority Deliverables',
      tasks: [
        { id: 't1', title: 'Finalize Jetson MIPI CSI zero-copy pipeline', done: false, priority: 'urgent', deadline: '17:00' },
        { id: 't2', title: 'Review Google Calendar sync cron logs', done: true, priority: 'high', deadline: '12:00' },
        { id: 't3', title: 'Audit Supabase ledger balance triggers', done: false, priority: 'normal', deadline: 'Tomorrow' },
      ],
    },
  },
  {
    id: 'calendar.list_events',
    name: 'calendar.list_events',
    specialist: 'Task & Google Calendar Manager',
    category: 'productivity',
    description: 'Fetches today’s synchronized appointments and Google Meet schedules',
    icon: Calendar,
    hudType: 'calendar',
    cardTitle: 'GOOGLE CALENDAR & APPOINTMENTS',
    mockArgs: { time_min: 'now', time_max: 'end_of_day' },
    mockResult: { event_count: 2, sync_status: 'ok' },
    hudData: {
      title: 'Google Calendar Agenda',
      date: 'Thursday, September 10',
      events: [
        { id: 'ev_1', title: 'VESPER Cognitive Mesh Architecture Review', time: '15:00 - 16:00', location: 'Google Meet', attendees: 4 },
        { id: 'ev_2', title: 'Edge Inference Latency Benchmark', time: '17:30 - 18:15', location: 'Lab Workstation', attendees: 2 },
      ],
    },
  },

  // ── 2. Finance ───────────────────────────────────────────────────────────────
  {
    id: 'finance.get_balance',
    name: 'finance.get_balance',
    specialist: 'Financial Ledger & Intelligence',
    category: 'finance',
    description: 'Retrieves current account balances, recent debits, and credits from Supabase',
    icon: CreditCard,
    hudType: 'transaction',
    cardTitle: 'FINANCIAL LEDGER & TRANSACTIONS',
    mockArgs: { account_id: 'primary_hdfc', include_recent: true },
    mockResult: { current_balance: 428450.00, currency: 'INR' },
    hudData: {
      account: 'HDFC Premium Imperia **8492',
      total_balance: '₹4,28,450.00',
      currency: 'INR',
      transactions: [
        {
          id: 'tx_01',
          description: 'NVIDIA Developer Store (Jetson Orin)',
          amount: '-₹48,900.00',
          type: 'debit',
          date: 'Today, 14:15',
          category: 'Hardware R&D',
        },
        {
          id: 'tx_02',
          description: 'Stripe Payout (SaaS Licensing)',
          amount: '+₹1,85,000.00',
          type: 'credit',
          date: 'Yesterday, 09:30',
          category: 'Revenue',
        },
      ],
    },
  },

  // ── 3. Intelligence & Intel ──────────────────────────────────────────────────
  {
    id: 'weather.get_current_weather',
    name: 'weather.get_current_weather',
    specialist: 'Atmospheric & Weather Intelligence',
    category: 'intel',
    description: 'Queries live meteorological radar, humidity, wind, and rain projections',
    icon: Cloud,
    hudType: 'weather',
    cardTitle: 'ATMOSPHERIC INTELLIGENCE & RADAR',
    mockArgs: { latitude: 19.076, longitude: 72.877, hourly: true },
    mockResult: { temp: 28.4, condition: 'Partly Cloudy', rain_prob: 15 },
    hudData: {
      city: 'Mumbai',
      temp: '28°C',
      condition: 'Partly Cloudy',
      humidity: '68%',
      wind: '14 km/h SW',
      uv_index: '3 Moderate',
      forecast: [
        { day: 'Today', temp: '31° / 26°', condition: 'Partly Cloudy' },
        { day: 'Tomorrow', temp: '30° / 25°', condition: 'Scattered Rain' },
        { day: 'Saturday', temp: '29° / 24°', condition: 'Thunderstorm' },
      ],
    },
  },
  {
    id: 'research.web_search',
    name: 'research.web_search',
    specialist: 'Deep Web & Research Specialist',
    category: 'intel',
    description: 'Executes multi-source DuckDuckGo queries and synthesizes verified citations',
    icon: Search,
    hudType: 'research',
    cardTitle: 'DEEP RESEARCH & SYNTHESIS',
    mockArgs: { query: 'NVIDIA Jetson Orin TensorRT zero copy DMA latency', num_results: 3 },
    mockResult: { sources_found: 2, synthesis_token_count: 142 },
    hudData: {
      query: 'NVIDIA Jetson Orin TensorRT zero copy DMA latency',
      summary: 'Hardware zero-copy direct memory access (NVMM) bypassing host CPU memory achieves sub-5ms inference times on Orin Nano/NX for lightweight vision models. Network transmission over gigabit LAN adds < 1ms overhead.',
      sources: [
        { title: 'NVIDIA Jetson Linux Developer Guide: Direct DMA ISP', url: 'https://docs.nvidia.com/jetson' },
        { title: 'TensorRT FP16 Execution Benchmarks', url: 'https://developer.nvidia.com/tensorrt' },
      ],
    },
  },
  {
    id: 'crawl.scrape_url',
    name: 'crawl.scrape_url',
    specialist: 'Web Extraction & Scraper Specialist',
    category: 'intel',
    description: 'Extracts clean structured markdown and metadata from target web pages',
    icon: Globe,
    hudType: 'generic',
    cardTitle: 'WEB EXTRACTION & ARTICLE SCRAPER',
    mockArgs: { url: 'https://developer.nvidia.com/embedded/jetson-modules', format: 'markdown' },
    mockResult: { byte_size: 4210, extracted_headings: 6 },
    hudData: {
      title: 'NVIDIA Jetson Hardware Specifications Scraped',
      summary: 'Jetson Orin NX delivers up to 100 TOPS of AI performance in the smallest Jetson form factor, with power configurable between 10W and 25W. Includes 1024-core Ampere GPU and 32 Tensor Cores.',
      url: 'https://developer.nvidia.com/embedded/jetson-modules',
    },
  },

  // ── 4. Media & Audio ─────────────────────────────────────────────────────────
  {
    id: 'media.get_current_playback',
    name: 'media.get_current_playback',
    specialist: 'Spotify & Media Audio Engine',
    category: 'media',
    description: 'Inspects active Spotify track, artist, album art, and progress timestamp',
    icon: Music,
    hudType: 'spotify',
    cardTitle: 'SPOTIFY AUDIO ENGINE & PLAYBACK',
    mockArgs: { include_progress: true },
    mockResult: { is_playing: true, service: 'Spotify Web API' },
    hudData: {
      track: 'Starboy',
      track_title: 'Starboy',
      artist: 'The Weeknd, Daft Punk',
      album: 'Starboy',
      is_playing: true,
      duration_ms: 230453,
      progress_ms: 114200,
      cover_url: 'https://i.scdn.co/image/ab67616d0000b2734718e2b124f79258be7bc452',
      url: 'https://open.spotify.com/track/7MXVkk9YM5IZxh0WSlVIk0',
    },
  },
  {
    id: 'youtube.search_videos',
    name: 'youtube.search_videos',
    specialist: 'Media & Entertainment Specialist',
    category: 'media',
    description: 'Searches YouTube videos, transcribes key chapters, and caches playback links',
    icon: Play,
    hudType: 'youtube',
    cardTitle: 'YOUTUBE MEDIA RUNTIME',
    mockArgs: { query: 'Lex Fridman Personal AI Companions', max_results: 1 },
    mockResult: { video_id: 'dQw4w9WgXcQ', duration: '2:45:10' },
    hudData: {
      title: 'Lex Fridman Podcast: Building Autonomous Personal AI Companions',
      channel: 'Lex Fridman',
      video_id: 'dQw4w9WgXcQ',
      url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      link: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      thumbnail: 'https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg',
      duration: '2:45:10',
      snippet: 'A deep dive into local multimodal intelligence, edge hardware, and tactile personal assistants.',
    },
  },
  {
    id: 'recipe.get_recipe',
    name: 'recipe.get_recipe',
    specialist: 'Culinary & Nutrition Specialist',
    category: 'media',
    description: 'Parses culinary recipes into ingredients, prep times, and step-by-step timers',
    icon: Sliders,
    hudType: 'recipe',
    cardTitle: 'CULINARY & NUTRITION SPECIALIST',
    mockArgs: { dish: 'Espresso Tonic', servings: 1 },
    mockResult: { prep_time_min: 5, difficulty: 'easy' },
    hudData: {
      title: 'Classic Pour-Over Espresso Tonic',
      prep_time: '5 mins',
      ingredients: [
        'Double shot espresso (chilled)',
        '200ml Premium Indian Tonic Water',
        'Fresh orange peel or slice',
        'Cubed ice',
      ],
      steps: [
        'Fill a chilled highball glass to the brim with clear ice cubes.',
        'Pour 200ml of tonic water down the side of the glass.',
        'Gently float the double espresso shot over the back of a bar spoon.',
        'Express orange peel oils over the surface and drop in the slice.',
      ],
    },
  },

  // ── 5. System & Code ─────────────────────────────────────────────────────────
  {
    id: 'system.get_system_stats',
    name: 'system.get_system_stats',
    specialist: 'System Operations & Hardware Manager',
    category: 'system_code',
    description: 'Reads host CPU, RAM, GPU temperature, uptime, and DPMS screen power states',
    icon: Cpu,
    hudType: 'system_status',
    cardTitle: 'SYSTEM TELEMETRY & HARDWARE SENTRY',
    mockArgs: { probe_sensors: true, include_gpu: true },
    mockResult: { cpu_cores: 16, ram_total_gb: 32.0, dpms: 'on' },
    hudData: {
      hostname: 'mihir-arch',
      os: 'Arch Linux (Kernel 6.16.8-zen)',
      uptime: '4 days, 18 hours',
      cpu_pct: 14.2,
      cpu_temp: '46°C',
      ram_used_gb: 6.8,
      ram_total_gb: 32.0,
      gpu_model: 'NVIDIA RTX 4070 Laptop',
      gpu_util_pct: 8.0,
      display_power: 'DPMS On (Active)',
    },
  },
  {
    id: 'github.list_pull_requests',
    name: 'github.list_pull_requests',
    specialist: 'GitHub & DevOps Specialist',
    category: 'system_code',
    description: 'Queries repository pull requests, commit status, and diff statistics',
    icon: GitBranch,
    hudType: 'github',
    cardTitle: 'GITHUB REPOSITORY & DEVOPS',
    mockArgs: { repo: 'MIHIRrPATIL/VESPER', state: 'all' },
    mockResult: { open_prs: 1, closed_prs: 1 },
    hudData: {
      repo: 'MIHIRrPATIL/VESPER',
      branch: 'main',
      prs: [
        {
          number: 42,
          title: 'feat: touchless air tap drawer toggle & monastic zen mode',
          author: 'mihir',
          status: 'open',
          additions: 380,
          deletions: 12,
        },
        {
          number: 41,
          title: 'fix: Supabase financial ledger sync webhook retry',
          author: 'mihir',
          status: 'merged',
          additions: 45,
          deletions: 8,
        },
      ],
      issues: [
        {
          number: 19,
          title: 'Support MIPI CSI-2 hardware ISP pipeline on Jetson Orin',
          author: 'mihir',
          status: 'open',
        },
      ],
    },
  },
  {
    id: 'memory.recall_memory',
    name: 'memory.recall_memory',
    specialist: 'Episodic & Semantic Memory Specialist',
    category: 'system_code',
    description: 'Searches semantic vector memory for stored user preferences and instructions',
    icon: Database,
    hudType: 'generic',
    cardTitle: 'EPISODIC & VECTOR MEMORY',
    mockArgs: { query: 'user terminal and emoji rules', top_k: 2 },
    mockResult: { matches: 2, avg_similarity: 0.94 },
    hudData: {
      title: 'Stored User Preferences & Rules',
      summary: 'Matched rule: "NEVER USE EMOJIS UNLESS SPECIFICALLY SAID TO especially in terminal and logs." Also matched user preference for terminal commands using the "rtk" proxy.',
      url: 'file:///home/mihir/Codes/VESPER/.agents/rules/graphify.md',
    },
  },
  {
    id: 'system.control_display_power',
    name: 'system.control_display_power',
    specialist: 'System Operations & Hardware Manager',
    category: 'system_code',
    description: 'Direct DPMS hardware control for waking or locking desktop monitors',
    icon: Wrench,
    hudType: 'tool_call',
    cardTitle: 'TOOL EXECUTION DECK',
    mockArgs: { action: 'wake', target_display: 'DP-3', method: 'dpms_force' },
    mockResult: { status: 'success', dpms_state: 'active', physical_latency_ms: 18 },
    hudData: {
      title: 'system.control_display_power',
      tool_name: 'system.control_display_power',
      specialist: 'System Operations & Hardware Manager',
      arguments: { action: 'wake', target_display: 'DP-3', method: 'dpms_force' },
      result: { status: 'success', dpms_state: 'active', latency_ms: 18 },
    },
  },
];

interface ToolEmitterViewProps {
  onOpenHudDrawer?: () => void;
}

export const ToolEmitterView: React.FC<ToolEmitterViewProps> = ({ onOpenHudDrawer }) => {
  const [activeCategory, setActiveCategory] = useState<ToolCategory>('all');
  const [selectedToolId, setSelectedToolId] = useState<string>(MOCK_TOOLS_REGISTRY[0].id);
  const [activeHudCard, setActiveHudCard] = useState<HudOutput | null>(null);
  const [lastEmittedTool, setLastEmittedTool] = useState<MockToolDefinition | null>(null);
  const [lastExecutionLatency, setLastExecutionLatency] = useState<number>(24);
  const [activeTab, setActiveTab] = useState<'preview' | 'telemetry'>('preview');
  const [pushToDrawer, setPushToDrawer] = useState<boolean>(true);
  const [isSimulatingSequence, setIsSimulatingSequence] = useState<boolean>(false);
  const [executionLog, setExecutionLog] = useState<Array<{ id: string; name: string; time: string; latency: number }>>([]);

  const selectedTool = MOCK_TOOLS_REGISTRY.find((t) => t.id === selectedToolId) || MOCK_TOOLS_REGISTRY[0];

  const filteredTools = MOCK_TOOLS_REGISTRY.filter((t) => {
    if (activeCategory === 'all') return true;
    return t.category === activeCategory;
  });

  // Emit a specific tool
  const handleEmitTool = (tool: MockToolDefinition) => {
    const randomLatency = Math.floor(Math.random() * 45) + 12;
    setLastExecutionLatency(randomLatency);
    setLastEmittedTool(tool);

    const hudCard: HudOutput = {
      id: crypto.randomUUID(),
      type: tool.hudType,
      title: tool.cardTitle,
      data: tool.hudData,
      timestamp: Date.now(),
      dismissed: false,
    };

    setActiveHudCard(hudCard);

    // Optionally push to global notificationStore so HUD drawer gets it
    if (pushToDrawer) {
      notificationStore.injectHudOutput(hudCard);
    }

    setExecutionLog((prev) => [
      {
        id: crypto.randomUUID(),
        name: tool.name,
        time: new Date().toLocaleTimeString([], { hour12: false }),
        latency: randomLatency,
      },
      ...prev.slice(0, 19),
    ]);
  };

  // Emit an entire group of tools
  const handleEmitGroup = async (cat: ToolCategory) => {
    const targets = MOCK_TOOLS_REGISTRY.filter((t) => cat === 'all' || t.category === cat);
    if (targets.length === 0) return;

    setIsSimulatingSequence(true);
    for (let i = 0; i < targets.length; i++) {
      setSelectedToolId(targets[i].id);
      handleEmitTool(targets[i]);
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
    setIsSimulatingSequence(false);
  };

  // Emit all tools in swarm sequence
  const handleEmitAll = () => {
    handleEmitGroup('all');
  };

  const handleClearHistory = () => {
    setExecutionLog([]);
    setActiveHudCard(null);
    setLastEmittedTool(null);
  };

  const categories: Array<{ key: ToolCategory; label: string }> = [
    { key: 'all', label: 'All Tools' },
    { key: 'productivity', label: 'Productivity' },
    { key: 'finance', label: 'Finance' },
    { key: 'intel', label: 'Atmospheric & Intel' },
    { key: 'media', label: 'Media & Audio' },
    { key: 'system_code', label: 'System & Code' },
  ];

  return (
    <div className="w-full max-w-6xl flex flex-col items-start gap-8 py-4 select-none">
      {/* Header */}
      <div className="flex flex-col gap-2 text-left w-full border-b border-white/[0.08] pb-6">
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
          <Wrench size={14} className="text-[#E8E3DA]" />
          SPECIALIST TOOL EXECUTION & HUD SIMULATOR
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Specialist Tool Emitter Deck</h1>
            <p className="font-sans text-sm text-[#8E8A83]">
              Deterministic mock tool dispatcher and HUD visual contract inspector. Emit individual specialist tools, category clusters, or swarm-wide test sequences.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {onOpenHudDrawer && (
              <button
                type="button"
                onClick={onOpenHudDrawer}
                className="px-3 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 text-xs font-mono font-medium text-[#E8E3DA] transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <span>OPEN HUD DECK</span>
                <ExternalLink size={13} />
              </button>
            )}
            <button
              type="button"
              onClick={handleClearHistory}
              className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-[#8E8A83] hover:text-[#E8E3DA] transition-colors cursor-pointer"
              title="Clear Session"
            >
              <RotateCcw size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Category Pills & Global Actions */}
      <div className="w-full flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        {/* Category Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
          {categories.map((cat) => {
            const count = cat.key === 'all' 
              ? MOCK_TOOLS_REGISTRY.length 
              : MOCK_TOOLS_REGISTRY.filter((t) => t.category === cat.key).length;
            const active = activeCategory === cat.key;
            return (
              <button
                key={cat.key}
                type="button"
                onClick={() => setActiveCategory(cat.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono uppercase tracking-wider transition-all cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  active
                    ? 'bg-white/[0.15] text-white border border-white/20 font-semibold'
                    : 'bg-white/[0.04] text-[#8E8A83] hover:text-[#D1CFC0] hover:bg-white/[0.08] border border-transparent'
                }`}
              >
                <span>{cat.label}</span>
                <span className="text-[10px] opacity-60">({count})</span>
              </button>
            );
          })}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            disabled={isSimulatingSequence}
            onClick={() => handleEmitGroup(activeCategory)}
            className="px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/15 text-xs font-mono text-[#D1CFC0] hover:text-white transition-colors cursor-pointer disabled:opacity-50"
          >
            Emit Active Group
          </button>
          <button
            type="button"
            disabled={isSimulatingSequence}
            onClick={handleEmitAll}
            className="px-3.5 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 text-emerald-300 font-mono text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <Sparkles size={13} />
            <span>Emit All (Swarm Sequence)</span>
          </button>
        </div>
      </div>

      {/* Main Two-Column Workbench */}
      <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Tool Selector List */}
        <div className="lg:col-span-5 flex flex-col gap-3">
          <div className="flex items-center justify-between font-mono text-xs text-[#8E8A83] px-1">
            <span>AVAILABLE SPECIALIST TOOLS</span>
            <span>{filteredTools.length} TOOLS</span>
          </div>

          <div className="flex flex-col gap-2 max-h-[640px] overflow-y-auto pr-1">
            {filteredTools.map((tool) => {
              const isSelected = tool.id === selectedToolId;
              const ToolIcon = tool.icon;
              return (
                <div
                  key={tool.id}
                  onClick={() => setSelectedToolId(tool.id)}
                  className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer flex items-start justify-between gap-3 ${
                    isSelected
                      ? 'bg-[#1e1e1e] border-white/30 shadow-lg'
                      : 'bg-[#151515] border-white/[0.06] hover:bg-[#1a1a1a] hover:border-white/15'
                  }`}
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className={`p-2 rounded-lg shrink-0 mt-0.5 ${
                      isSelected ? 'bg-white/15 text-white' : 'bg-white/[0.04] text-[#8E8A83]'
                    }`}>
                      <ToolIcon size={16} />
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="font-mono text-xs font-semibold text-[#E8E3DA] truncate">
                        {tool.name}
                      </span>
                      <span className="font-sans text-[11px] text-[#8E8A83] truncate mt-0.5">
                        {tool.specialist}
                      </span>
                      <p className="font-sans text-xs text-[#A1A1AA] line-clamp-1 mt-1">
                        {tool.description}
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedToolId(tool.id);
                      handleEmitTool(tool);
                    }}
                    className="px-2.5 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.18] text-[#E8E3DA] font-mono text-[10px] font-semibold tracking-wider transition-colors shrink-0 mt-1 cursor-pointer flex items-center gap-1"
                    title={`Emit ${tool.name}`}
                  >
                    <span>EMIT</span>
                    <Play size={10} fill="currentColor" />
                  </button>
                </div>
              );
            })}
          </div>

          {/* Settings & Toggle */}
          <div className="p-3.5 rounded-xl bg-[#141414] border border-white/[0.08] flex items-center justify-between text-left mt-2">
            <div className="flex flex-col">
              <span className="font-sans text-xs text-[#E8E3DA] font-medium">Auto-Push to HUD Deck</span>
              <span className="font-sans text-[11px] text-[#8E8A83]">
                Inject emitted cards directly into bottom slide drawer
              </span>
            </div>
            <button
              type="button"
              onClick={() => setPushToDrawer(!pushToDrawer)}
              className={`w-9 h-5 rounded-full transition-colors relative cursor-pointer ${
                pushToDrawer ? 'bg-emerald-500/50' : 'bg-white/10'
              }`}
            >
              <span
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                  pushToDrawer ? 'left-4.5' : 'left-0.5'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Right Column: Execution Inspector & Live Card Preview */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          {/* Header of Preview Box */}
          <div className="p-4 rounded-xl bg-[#161616] border border-white/[0.08] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-left">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-white/[0.06] text-[#E8E3DA]">
                {React.createElement(selectedTool.icon, { size: 18 })}
              </div>
              <div className="flex flex-col">
                <span className="font-mono text-xs font-bold text-[#E8E3DA]">
                  {selectedTool.name}
                </span>
                <span className="font-sans text-xs text-[#8E8A83]">
                  {selectedTool.specialist}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex rounded-lg bg-black/40 p-0.5 border border-white/10 font-mono text-[11px]">
                <button
                  type="button"
                  onClick={() => setActiveTab('preview')}
                  className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                    activeTab === 'preview' ? 'bg-white/15 text-white font-semibold' : 'text-[#8E8A83]'
                  }`}
                >
                  HUD Preview
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('telemetry')}
                  className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                    activeTab === 'telemetry' ? 'bg-white/15 text-white font-semibold' : 'text-[#8E8A83]'
                  }`}
                >
                  Raw Telemetry
                </button>
              </div>

              <button
                type="button"
                onClick={() => handleEmitTool(selectedTool)}
                className="px-4 py-1.5 rounded-lg bg-white/[0.12] hover:bg-white/[0.22] text-[#E8E3DA] font-mono text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 border border-white/15"
              >
                <Play size={12} fill="currentColor" />
                <span>DISPATCH TOOL</span>
              </button>
            </div>
          </div>

          {/* Tab 1: Live HUD Card Preview */}
          {activeTab === 'preview' && (
            <div className="w-full flex flex-col gap-3">
              <div className="flex items-center justify-between font-mono text-xs text-[#8E8A83] px-1">
                <span>RENDERED HUD CARD PREVIEW</span>
                {lastEmittedTool && (
                  <span className="text-emerald-400 font-semibold">
                    DISPATCHED IN {lastExecutionLatency}ms
                  </span>
                )}
              </div>

              {activeHudCard ? (
                <div className="w-full">
                  <HudCard
                    output={activeHudCard}
                    onDismiss={() => setActiveHudCard(null)}
                  />
                </div>
              ) : (
                <div className="p-12 rounded-2xl border border-dashed border-white/15 bg-[#141414] flex flex-col items-center justify-center gap-3 text-center">
                  <Sliders size={32} className="text-[#8E8A83] opacity-40" />
                  <span className="font-mono text-xs uppercase tracking-wider text-[#8E8A83]">
                    No tool emitted yet in this session
                  </span>
                  <p className="font-sans text-xs text-[#A1A1AA] max-w-sm">
                    Click "DISPATCH TOOL" above or "EMIT" on any specialist tool in the left list to generate realistic output.
                  </p>
                  <button
                    type="button"
                    onClick={() => handleEmitTool(selectedTool)}
                    className="mt-2 px-4 py-2 rounded-xl bg-white/[0.08] hover:bg-white/[0.16] text-[#E8E3DA] font-mono text-xs font-semibold transition-colors cursor-pointer"
                  >
                    Dispatch {selectedTool.name}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Raw Telemetry (JSON Arguments & Result) */}
          {activeTab === 'telemetry' && (
            <div className="w-full flex flex-col gap-4 text-left">
              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-xs text-[#8E8A83]">DISPATCHED ARGUMENTS (JSON):</span>
                <pre className="p-4 rounded-xl bg-black/60 border border-white/10 font-mono text-xs text-amber-200/90 overflow-x-auto max-h-48">
                  {JSON.stringify(selectedTool.mockArgs, null, 2)}
                </pre>
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-xs text-[#8E8A83]">RETURNED SPECIALIST RESULT (JSON):</span>
                <pre className="p-4 rounded-xl bg-black/60 border border-white/10 font-mono text-xs text-emerald-300/90 overflow-x-auto max-h-56">
                  {JSON.stringify(selectedTool.mockResult, null, 2)}
                </pre>
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-xs text-[#8E8A83]">HUD CARD PAYLOAD (JSON):</span>
                <pre className="p-4 rounded-xl bg-black/60 border border-white/10 font-mono text-xs text-sky-200/90 overflow-x-auto max-h-56">
                  {JSON.stringify(selectedTool.hudData, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Execution Log / History Strip */}
          {executionLog.length > 0 && (
            <div className="p-4 rounded-xl bg-[#141414] border border-white/[0.06] flex flex-col gap-2 text-left mt-2">
              <div className="flex items-center justify-between font-mono text-[11px] text-[#8E8A83]">
                <span>RECENT DISPATCH LOG ({executionLog.length})</span>
                <button
                  type="button"
                  onClick={handleClearHistory}
                  className="hover:text-[#E8E3DA] transition-colors cursor-pointer"
                >
                  Clear
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                {executionLog.map((log) => (
                  <div
                    key={log.id}
                    className="px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.08] font-mono text-[10px] text-[#D1CFC0] flex items-center gap-1.5"
                  >
                    <span className="text-[#8E8A83]">{log.time}</span>
                    <span className="font-semibold">{log.name}</span>
                    <span className="text-emerald-400">{log.latency}ms</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
