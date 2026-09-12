import React, { useState, useEffect, useRef } from 'react';
import {
  CheckSquare,
  Check,
  Network,
  Monitor,
  Smartphone,
  Eye,
  Calendar,
  X,
  CreditCard,
  Volume2,
  Bot,
  CalendarCheck,
  DollarSign,
  Music,
  Mic,
  Layers,
} from 'lucide-react';
import { motion, AnimatePresence, useMotionValue, animate } from 'motion/react';
import { ConversationMessage, AgentState, ApiTask } from '../types/vesper';
import { BentoGrid, BentoCard } from './ui/bento-grid';
import { DynamicGreeting } from './DynamicGreeting';
import { CommandInput } from './CommandInput';
import { DesignerChronometer } from './DesignerChronometer';
import { TextReveal } from './ui/TextReveal';
import { taskService } from '../services/task-service';
import { deviceService } from '../services/device-service';
import { cn } from '../lib/utils';

interface ChatStreamProps {
  messages: ConversationMessage[];
  agentState: AgentState;
  intent?: string;
  activeHeadline?: string;
  onSimulateWakeWord: () => void;
  onSendUserMessage?: (text: string) => void;
}

export const ChatStream: React.FC<ChatStreamProps> = ({
  messages,
  agentState,
  intent: _intent,
  activeHeadline: _activeHeadline = 'What can I help you shape today?',
  onSimulateWakeWord: _onSimulateWakeWord,
  onSendUserMessage,
}) => {
  const [taskTab, setTaskTab] = useState<'today' | 'overdue' | 'all' | 'completed'>('today');
  const [tasks, setTasks] = useState<ApiTask[]>(taskService.getTasks('today'));
  const [taskStats, setTaskStats] = useState(taskService.getStats());
  const [devices, setDevices] = useState(deviceService.getDevices());
  const [calendarEvents, setCalendarEvents] = useState(deviceService.getEvents());
  const [recentActivities, setRecentActivities] = useState<string[]>(deviceService.getRecentActivities());

  // TTS Speech Synchronization & 10-Second Auto-Dismiss Lifecycle
  const speechProgress = useMotionValue(1);
  const [activeSpokenText, setActiveSpokenText] = useState<string>('');
  const [showSpokenSurface, setShowSpokenSurface] = useState<boolean>(false);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSpokenMsgIdRef = useRef<string | null>(null);

  useEffect(() => {
    const unsubTasks = taskService.subscribe(() => {
      setTasks(taskService.getTasks(taskTab));
      setTaskStats(taskService.getStats());
    });
    const unsubDevices = deviceService.subscribe(() => {
      setDevices(deviceService.getDevices());
      setCalendarEvents(deviceService.getEvents());
      setRecentActivities(deviceService.getRecentActivities());
    });
    return () => {
      unsubTasks();
      unsubDevices();
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current);
        dismissTimerRef.current = null;
      }
    };
  }, [taskTab]);

  // Synchronize TextReveal with TTS speech and auto-dismiss 10s after TTS finishes
  useEffect(() => {
    const latestAgentMsg = [...messages].reverse().find((m) => m.sender === 'agent');
    if (!latestAgentMsg || !latestAgentMsg.text) return;

    // Detect if this is a newly arrived message
    if (latestAgentMsg.id !== lastSpokenMsgIdRef.current) {
      lastSpokenMsgIdRef.current = latestAgentMsg.id;
      setActiveSpokenText(latestAgentMsg.text);
      setShowSpokenSurface(true);
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current);
        dismissTimerRef.current = null;
      }
    }

    if (agentState === 'SPEAKING') {
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current);
        dismissTimerRef.current = null;
      }
      setShowSpokenSurface(true);
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
      // TTS finished (agentState is IDLE) — schedule fade out in 10 seconds
      if (showSpokenSurface && !dismissTimerRef.current) {
        dismissTimerRef.current = setTimeout(() => {
          setShowSpokenSurface(false);
          dismissTimerRef.current = null;
        }, 10000);
      }
    }
  }, [messages, agentState, speechProgress, showSpokenSurface]);

  const handleTabChange = (tab: 'today' | 'overdue' | 'all' | 'completed') => {
    setTaskTab(tab);
    setTasks(taskService.getTasks(tab));
  };

  const toggleTask = (id: string) => {
    taskService.toggleTask(id);
  };

  const dispatchCommand = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (onSendUserMessage) {
      onSendUserMessage(trimmed);
    }
  };

  const uniqueDevices = Array.from(new Map(devices.map((d) => [d.device_id, d])).values()).filter(
    (d) => d.is_online && d.device_id !== 'mobile_companion_provisioned'
  );

  const operationalServices = [
    {
      id: 'alfred-core',
      name: 'Alfred Core',
      role: 'Orchestrator Swarm',
      status: 'Active',
      Icon: Bot,
      action: () => onSendUserMessage?.('Provide an executive status briefing on active priorities'),
    },
    {
      id: 'google-cal-tasks',
      name: 'Google Cal & Tasks',
      role: 'Two-Way v3 Synced',
      status: 'Synced',
      Icon: CalendarCheck,
      action: () => onSendUserMessage?.("List today's high-priority tasks and calendar schedule"),
    },
    {
      id: 'financial-ledger',
      name: 'Financial Ledger',
      role: 'Supabase Postgres DB',
      status: 'Online',
      Icon: DollarSign,
      action: () => onSendUserMessage?.('Check current financial balance and recent transactions'),
    },
    {
      id: 'audio-engine',
      name: 'Spotify & Vinyl',
      role: 'MPRIS Audio Control',
      status: 'Ready',
      Icon: Music,
      action: () => onSendUserMessage?.('What is currently playing on Spotify?'),
    },
    {
      id: 'vision-sentry',
      name: 'Vision Sentry',
      role: 'BlazeFace Optical Lock',
      status: 'Armed',
      Icon: Eye,
      action: () => onSendUserMessage?.('Run optical presence scan'),
    },
    {
      id: 'voice-pipeline',
      name: 'Voice Engine',
      role: 'Whisper Base & Piper',
      status: 'Armed',
      Icon: Mic,
      action: () => {
        if (_onSimulateWakeWord) _onSimulateWakeWord();
      },
    },
  ];

  return (
    <div className="center-stage-command-deck" style={{ width: '100%', position: 'relative' }}>
      <div className="center-stage-inner relative z-10 w-full flex flex-col items-center justify-center">
        
        {/* Hero Command Section */}
        <div className="hero-command-group w-full max-w-6xl flex flex-col items-start justify-start mb-20">
          <DynamicGreeting />
          
          <CommandInput 
            onSubmit={(val) => dispatchCommand(val)}
          />
        </div>

        {/* TTS-Synchronized Agent Spoken Dialogue Surface with Fade-In / Auto 10s Fade-Out */}
        <AnimatePresence mode="wait">
          {showSpokenSurface && activeSpokenText && (
            <motion.div
              key={lastSpokenMsgIdRef.current || 'spoken-surface'}
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -12, scale: 0.98, transition: { duration: 0.5, ease: 'easeInOut' } }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-6xl mb-12 p-6 md:p-8 rounded-2xl bg-[#141414]/95 border border-white/[0.12] backdrop-blur-2xl shadow-2xl shadow-black/80 relative"
            >
              <div className="flex items-center justify-between pb-3 mb-4 border-b border-white/[0.08]">
                <div className="flex items-center gap-2.5">
                  <span className={cn(
                    "w-2 h-2 rounded-full",
                    agentState === 'SPEAKING' ? "bg-[#E8E3DA] animate-pulse" : "bg-white/40"
                  )} />
                  <span className="font-mono text-xs uppercase tracking-widest text-[#E8E3DA] font-semibold">
                    ALFRED {agentState === 'SPEAKING' ? '• SYNTHESIZING VOCAL SPEECH' : '• RESPONSE'}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {agentState === 'SPEAKING' ? (
                    <span className="font-mono text-[10px] text-[#8E8A83] uppercase tracking-wider flex items-center gap-1.5">
                      <Volume2 size={12} className="text-[#E8E3DA] animate-pulse" />
                      TTS IN SYNC
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        if (dismissTimerRef.current) {
                          clearTimeout(dismissTimerRef.current);
                          dismissTimerRef.current = null;
                        }
                        setShowSpokenSurface(false);
                      }}
                      className="p-1 rounded text-[#8E8A83] hover:text-[#E8E3DA] transition-colors cursor-pointer"
                      title="Dismiss"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>

              <TextReveal
                text={activeSpokenText}
                speechProgress={speechProgress}
                autoScroll={true}
                paragraphClassName="!text-xl md:!text-2xl !leading-relaxed font-sans font-medium text-[#E8E3DA]"
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Bento Grid — Scaled Up & Connected to Real Database */}
        <BentoGrid className="w-full max-w-6xl gap-6">
          {/* Card 1: Active Tasks (2 Columns) */}
          <BentoCard 
            name="Active Tasks" 
            description="Live synchronized database agenda, priorities & overdue classification" 
            Icon={CheckSquare} 
            className="col-span-2"
            headerRight={
              <div className="flex items-center gap-1 bg-black/50 p-1 rounded-lg border border-white/[0.08]">
                <button
                  type="button"
                  onClick={() => handleTabChange('today')}
                  className={cn(
                    "font-mono text-[11px] px-2.5 py-1 rounded transition-colors",
                    taskTab === 'today'
                      ? "bg-white/[0.14] text-[#E8E3DA] font-semibold"
                      : "text-[#8E8A83] hover:text-[#D1CFC0]"
                  )}
                >
                  Today ({taskStats.today_count})
                </button>
                <button
                  type="button"
                  onClick={() => handleTabChange('overdue')}
                  className={cn(
                    "font-mono text-[11px] px-2.5 py-1 rounded transition-colors flex items-center gap-1.5",
                    taskTab === 'overdue'
                      ? "bg-white/[0.14] text-[#E8E3DA] font-semibold"
                      : "text-[#8E8A83] hover:text-[#D1CFC0]"
                  )}
                >
                  {taskStats.overdue_count > 0 && (
                    <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA] animate-pulse" />
                  )}
                  Overdue ({taskStats.overdue_count})
                </button>
                <button
                  type="button"
                  onClick={() => handleTabChange('all')}
                  className={cn(
                    "font-mono text-[11px] px-2.5 py-1 rounded transition-colors",
                    taskTab === 'all'
                      ? "bg-white/[0.14] text-[#E8E3DA] font-semibold"
                      : "text-[#8E8A83] hover:text-[#D1CFC0]"
                  )}
                >
                  All ({taskStats.pending_count})
                </button>
                <button
                  type="button"
                  onClick={() => handleTabChange('completed')}
                  className={cn(
                    "font-mono text-[11px] px-2.5 py-1 rounded transition-colors",
                    taskTab === 'completed'
                      ? "bg-white/[0.14] text-[#E8E3DA] font-semibold"
                      : "text-[#8E8A83] hover:text-[#D1CFC0]"
                  )}
                >
                  Done ({taskStats.completed_count})
                </button>
              </div>
            }
          >
            <div className="flex flex-col gap-2 w-full max-h-[220px] overflow-y-auto pr-1">
              {tasks.length === 0 ? (
                <div className="py-8 flex flex-col items-center justify-center text-center">
                  <span className="font-sans text-sm text-[#8E8A83]">
                    {taskTab === 'overdue'
                      ? 'No overdue obligations. All matters are current, sir.'
                      : taskTab === 'today'
                      ? 'No tasks scheduled specifically for today.'
                      : 'No tasks found in this view.'}
                  </span>
                </div>
              ) : (
                tasks.map((task) => (
                  <div
                    key={task.id}
                    onClick={() => toggleTask(task.id)}
                    className={cn(
                      "flex items-center justify-between px-3.5 py-2.5 rounded-lg border transition-colors cursor-pointer select-none",
                      task.category === 'overdue' && !task.done
                        ? "bg-white/[0.04] hover:bg-white/[0.07] border-white/[0.08]"
                        : "bg-white/[0.02] hover:bg-white/[0.05] border-white/[0.04]"
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0 pr-2">
                      <div
                        className={cn(
                          "w-4 h-4 rounded border flex items-center justify-center transition-colors shrink-0",
                          task.done
                            ? "bg-[#E8E3DA] border-[#E8E3DA] text-[#141414]"
                            : "border-white/30 bg-transparent"
                        )}
                      >
                        {task.done && <Check size={11} strokeWidth={3} />}
                      </div>
                      <span
                        className={cn(
                          "font-sans text-sm truncate",
                          task.done ? "line-through text-[#8E8A83]" : "text-[#E8E3DA] font-medium"
                        )}
                      >
                        {task.title}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {task.category === 'overdue' && !task.done && (
                        <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-white/[0.08] text-[#E8E3DA] border border-white/20 font-bold">
                          OVERDUE • {task.age_label.toUpperCase()}
                        </span>
                      )}
                      {task.priority === 'high' && !task.done && task.category !== 'overdue' && (
                        <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-white/[0.06] text-[#D1CFC0] border border-white/15">
                          HIGH
                        </span>
                      )}
                      <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-white/[0.04] text-[#8E8A83]">
                        {task.tag || 'TASK'}
                      </span>
                      {task.category !== 'overdue' && (
                        <span className="font-mono text-[11px] text-[#8E8A83]">
                          {task.age_label}
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </BentoCard>

          {/* Card 2: Connected Systems (1 Column) */}
          <BentoCard 
            name="Connected Systems" 
            description="Dynamic LAN hardware mesh" 
            Icon={Network}
            headerRight={
              <span className="font-mono text-[11px] text-[#D1CFC0] px-2.5 py-1 rounded bg-white/[0.04] border border-white/[0.08]">
                {uniqueDevices.length} Online
              </span>
            }
          >
            <div className="flex flex-col gap-2.5 w-full max-h-[230px] overflow-y-auto pr-1 scrollbar-thin">
              {uniqueDevices.map((device) => {
                const isMobile =
                  device.device_type === 'mobile' ||
                  device.device_type?.includes('mobile') ||
                  device.device_type?.includes('android') ||
                  device.device_type?.includes('phone');
                const isCamera = device.device_type === 'camera';
                const isDesktop = device.device_type === 'desktop';
                const IconComp = isMobile ? Smartphone : isCamera ? Eye : Monitor;
                
                return (
                  <div
                    key={device.device_id}
                    className="flex flex-col gap-1.5 p-3 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.07] hover:border-white/[0.14] transition-all"
                  >
                    {/* Top Row: Device Icon, Name, and Status Badge */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="flex items-center justify-center w-6 h-6 rounded-md bg-white/[0.06] border border-white/[0.08] text-[#E8E3DA] shrink-0">
                          <IconComp size={13} strokeWidth={1.8} />
                        </div>
                        <span className="font-sans text-xs font-semibold text-[#E8E3DA] truncate">
                          {device.device_name}
                        </span>
                      </div>

                      {/* Status / Battery badge */}
                      <div className="flex items-center gap-1.5 font-mono text-[10px] text-[#D1CFC0] shrink-0">
                        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.08]">
                          <span className={cn("w-1.5 h-1.5 rounded-full", device.is_online ? "bg-[#E8E3DA] animate-pulse" : "bg-white/30")} />
                          <span className="font-mono text-[10px] text-[#E8E3DA] font-medium">
                            {device.battery_level !== undefined && device.battery_level !== null
                              ? `${device.battery_level}% bat${device.is_charging ? ' • chg' : ''}`
                              : device.cpu_usage_pct !== undefined
                              ? `${device.cpu_usage_pct}% cpu`
                              : device.is_online ? 'ONLINE' : 'OFFLINE'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Bottom Row: IP/Network + Platform Role */}
                    <div className="flex items-center justify-between gap-2 font-mono text-[11px] text-[#A1A1AA] pl-8.5">
                      <span className="truncate">
                        {device.ip_address || device.hostname || (isDesktop ? '192.168.0.x (Local Host)' : 'Node Relay')}
                      </span>
                      <span className="text-[10px] text-[#8E8A83] shrink-0 uppercase tracking-widest font-mono">
                        {isDesktop ? 'HOST' : isMobile ? 'PHONE' : 'EDGE'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </BentoCard>

          {/* Card 3: Active Agents & Core Services (1 Column) */}
          <BentoCard 
            name="Active Agents & Services" 
            description="Operational cognitive swarm & background services" 
            Icon={Layers} 
            headerRight={
              <span className="font-mono text-[11px] text-[#D1CFC0] px-2.5 py-1 rounded bg-white/[0.04] border border-white/[0.08]">
                {operationalServices.length} Active
              </span>
            }
          >
            <div className="grid grid-cols-2 gap-2 w-full max-h-[220px] overflow-y-auto pr-1 scrollbar-thin">
              {operationalServices.map((svc) => (
                <button
                  key={svc.id}
                  type="button"
                  onClick={svc.action}
                  className="p-2.5 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] hover:border-white/[0.14] transition-all flex flex-col justify-between text-left group select-none cursor-pointer h-[66px]"
                  title={`Trigger ${svc.name}`}
                >
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <svc.Icon size={13} className="text-[#8E8A83] group-hover:text-[#E8E3DA] transition-colors shrink-0" />
                      <span className="font-sans text-xs font-semibold text-[#E8E3DA] group-hover:text-white transition-colors truncate">
                        {svc.name}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between w-full gap-1">
                    <span className="font-mono text-[9px] text-[#8E8A83] group-hover:text-[#D1CFC0] transition-colors truncate">
                      {svc.role}
                    </span>
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-white/[0.05] text-[#D1CFC0] border border-white/[0.08] shrink-0">
                      {svc.status}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </BentoCard>

          {/* Card 4: Executive Cockpit — DB-Connected Agenda & Financial Ledger (2 Columns) */}
          <BentoCard 
            name="Executive Cockpit" 
            description="Live database financial ledger, calendar schedule & prioritized action queue" 
            Icon={Calendar} 
            className="col-span-2"
            headerRight={
              <span className="font-mono text-[11px] text-[#D1CFC0] px-2.5 py-1 rounded bg-white/[0.04] border border-white/[0.08]">
                {tasks.filter(t => t.category === 'overdue' && !t.done).length} Overdue • {recentActivities.length} Ledger
              </span>
            }
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
              {/* Left Column: Calendar & Real Financial Transactions Ledger */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between pb-1 border-b border-white/[0.04]">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-[#8E8A83]">Calendar & Financial Ledger</span>
                  <span className="font-mono text-[10px] text-[#8E8A83]">Supabase DB</span>
                </div>
                
                {calendarEvents.length > 0 ? (
                  calendarEvents.slice(0, 2).map((ev, i) => (
                    <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                      <div className="flex flex-col min-w-0 pr-2">
                        <span className="font-sans text-xs font-semibold text-[#E8E3DA] truncate">{ev.summary}</span>
                        <span className="font-mono text-[10px] text-[#8E8A83]">{ev.location || 'Scheduled Event'}</span>
                      </div>
                      <span className="font-mono text-[11px] text-[#D1CFC0] shrink-0">{ev.time}</span>
                    </div>
                  ))
                ) : (
                  <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] flex items-center justify-between">
                    <span className="font-sans text-xs text-[#E8E3DA] font-medium">Calendar is clear for today</span>
                    <span className="font-mono text-[9px] text-[#8E8A83] uppercase px-1.5 py-0.5 rounded bg-white/[0.05]">SYNCED</span>
                  </div>
                )}

                {/* Real Recent Financial Transactions from Supabase Database */}
                {recentActivities.slice(0, 2).map((act, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                    <div className="flex items-center gap-2 min-w-0">
                      <CreditCard size={13} className="text-[#8E8A83] shrink-0" />
                      <span className="font-sans text-xs text-[#E8E3DA] truncate font-medium">{act}</span>
                    </div>
                    <span className="font-mono text-[9px] text-[#8E8A83]">TRANSACTION</span>
                  </div>
                ))}
              </div>

              {/* Right Column: Real Overdue Action Queue from DB */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between pb-1 border-b border-white/[0.04]">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-[#8E8A83]">Action Required (Overdue Queue)</span>
                  <span className="font-mono text-[10px] text-[#8E8A83]">Supabase Tasks</span>
                </div>

                {tasks.filter((t) => t.category === 'overdue' && !t.done).length === 0 ? (
                  <div className="p-3 rounded-lg bg-white/[0.01] border border-white/[0.03] text-center">
                    <span className="font-sans text-xs text-[#8E8A83]">No pending overdue actions in queue.</span>
                  </div>
                ) : (
                  tasks
                    .filter((t) => t.category === 'overdue' && !t.done)
                    .slice(0, 2)
                    .map((task) => (
                      <div key={task.id} className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                        <div className="flex flex-col min-w-0 pr-2">
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <span className="font-mono text-[9px] uppercase px-1.5 py-0.2 rounded bg-white/[0.08] text-[#E8E3DA] font-bold">
                              {task.age_label.toUpperCase()}
                            </span>
                            {task.priority === 'high' && (
                              <span className="font-mono text-[9px] text-[#E8E3DA] font-bold">HIGH</span>
                            )}
                          </div>
                          <span className="font-sans text-xs text-[#E8E3DA] truncate font-medium">{task.title}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => toggleTask(task.id)}
                          className="p-1.5 rounded-md bg-white/[0.06] hover:bg-white/[0.14] text-[#E8E3DA] transition-colors shrink-0"
                          title="Resolve & Complete"
                        >
                          <Check size={13} strokeWidth={2.5} />
                        </button>
                      </div>
                    ))
                )}
              </div>
            </div>
          </BentoCard>
        </BentoGrid>

        {/* Bottom Designer Chronometer: Time, Date & Day */}
        <DesignerChronometer />
      </div>
    </div>
  );
};

export default ChatStream;
