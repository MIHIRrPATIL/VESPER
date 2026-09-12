import React, { useState, useEffect, useCallback } from 'react';
import { 
  Play, 
  Pause, 
  RotateCcw, 
  Check, 
  Music, 
  X, 
  ChevronDown, 
  Bell, 
  ShieldCheck, 
  Calendar,
  CloudRain,
  Waves,
  Flame,
  Volume2,
  VolumeX,
  SkipBack,
  SkipForward,
  Disc3
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { zenStore, ZenTaskItem } from '../services/zen-store';
import { ambientAudio, SoundscapeType } from '../services/ambient-audio';
import { mediaService } from '../services/media-service';
import { gateway } from '../services/gateway';
import { NowPlayingTrack } from '../types/vesper';
import { cn } from '../lib/utils';

const API_TASKS = 'http://localhost:8000/api/tasks';

export interface ZenFocusViewProps {
  onExitZen: () => void;
  onOpenNotifications?: () => void;
}

export const ZenFocusView: React.FC<ZenFocusViewProps> = ({
  onExitZen,
  onOpenNotifications,
}) => {
  const [secondsRemaining, setSecondsRemaining] = useState<number>(zenStore.secondsRemaining);
  const [isRunning, setIsRunning] = useState<boolean>(zenStore.isRunning);
  const [sprintMinutes, setSprintMinutes] = useState<number>(zenStore.sprintMinutes);
  const [completedSprints, setCompletedSprints] = useState<number>(zenStore.completedSprints);
  const [activeTask, setActiveTask] = useState<ZenTaskItem | null>(zenStore.activeTask);
  const [showDebrief, setShowDebrief] = useState<boolean>(zenStore.showDebrief);
  const [sessionHeldCount, setSessionHeldCount] = useState<number>(zenStore.sessionHeldCount);

  const [pendingTasks, setPendingTasks] = useState<ZenTaskItem[]>([]);
  const [urgentTasks, setUrgentTasks] = useState<ZenTaskItem[]>([]);
  const [showTaskPicker, setShowTaskPicker] = useState<boolean>(false);
  const [nextCalendarEvent, setNextCalendarEvent] = useState<string | null>(null);

  const [soundscape, setSoundscape] = useState<SoundscapeType>(ambientAudio.currentType);
  const [soundscapeVol, setSoundscapeVol] = useState<number>(ambientAudio.volume);
  const [mediaTrack, setMediaTrack] = useState<NowPlayingTrack>(mediaService.getTrack());

  // Subscribe to zenStore
  useEffect(() => {
    return zenStore.subscribe(() => {
      setSecondsRemaining(zenStore.secondsRemaining);
      setIsRunning(zenStore.isRunning);
      setSprintMinutes(zenStore.sprintMinutes);
      setCompletedSprints(zenStore.completedSprints);
      setActiveTask(zenStore.activeTask);
      setShowDebrief(zenStore.showDebrief);
      setSessionHeldCount(zenStore.sessionHeldCount);
    });
  }, []);

  // Subscribe to ambientAudio
  useEffect(() => {
    return ambientAudio.subscribe(() => {
      setSoundscape(ambientAudio.currentType);
      setSoundscapeVol(ambientAudio.volume);
    });
  }, []);

  // Subscribe to mediaService for Spotify track info
  useEffect(() => {
    return mediaService.subscribe(() => {
      setMediaTrack(mediaService.getTrack());
    });
  }, []);

  // Fetch pending tasks from API
  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch(API_TASKS);
      if (res.ok) {
        const data = await res.json();
        const items: ZenTaskItem[] = (data.tasks || []).map((t: any) => ({
          id: String(t.id),
          title: t.title || t.task || 'Untitled Task',
          done: Boolean(t.done),
          priority: t.priority || 'normal',
          deadline: t.deadline || t.due_date,
        }));

        const uncompleted = items.filter((t) => !t.done);
        setPendingTasks(uncompleted);

        // Filter urgent tasks
        const urgents = uncompleted.filter((t) => t.priority === 'urgent' || t.priority === 'high');
        setUrgentTasks(urgents.slice(0, 2));

        // Auto-select active focus task if none set
        if (!zenStore.activeTask && uncompleted.length > 0) {
          zenStore.setActiveTask(uncompleted[0]);
        }
      }

      // Query upcoming calendar events
      try {
        const calRes = await fetch('http://localhost:8000/api/tasks/calendar');
        if (calRes.ok) {
          const calData = await calRes.json();
          const evList = calData.events || [];
          if (evList.length > 0) {
            const ev = evList[0];
            const startStr = ev.start?.dateTime ? new Date(ev.start.dateTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : (ev.start?.date || 'Upcoming');
            setNextCalendarEvent(`Next: ${startStr} • ${ev.summary || 'Scheduled Focus Block'}`);
          }
        }
      } catch {
        // Optional calendar
      }
    } catch {
      // Offline fallback
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // Keyboard shortcut: Escape exits Zen mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onExitZen();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onExitZen]);

  const handleToggleTaskDone = async (task: ZenTaskItem) => {
    try {
      await fetch(`${API_TASKS}/${task.id}/toggle`, { method: 'PATCH' });
      fetchTasks();
    } catch {
      // Non-blocking
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Progress metrics
  const totalSecs = Math.max(1, sprintMinutes * 60);
  const progressPct = Math.max(0, Math.min(100, ((totalSecs - secondsRemaining) / totalSecs) * 100));
  const radius = 105;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progressPct / 100) * circumference;

  const presets = [
    { label: '25m Focus', mins: 25 },
    { label: '50m Deep Work', mins: 50 },
    { label: '15m Sprint', mins: 15 },
    { label: '5m Rest', mins: 5 },
  ];

  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col items-center justify-between py-6 px-4 text-center select-none min-h-[78vh]">
      {/* ── Top Status Strip ──────────────────────────────────────────────── */}
      <div className="w-full flex items-center justify-between border-b border-white/[0.08] pb-4 mb-6">
        <div className="flex items-center gap-2.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA]/80" />
          <span className="font-mono text-xs uppercase tracking-widest text-[#8E8A83]">
            MONASTIC ZEN — DEEP FOCUS BLOCK
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onExitZen}
            className="px-3 py-1 rounded-lg border border-white/[0.12] bg-white/[0.04] hover:bg-white/[0.10] text-[#8E8A83] hover:text-[#E8E3DA] font-mono text-xs transition-colors cursor-pointer flex items-center gap-1.5"
            title="Exit Zen Mode (Esc)"
          >
            <span>Exit Zen</span>
            <kbd className="text-[10px] text-[#5C5A56] bg-black/40 px-1 py-0.2 rounded border border-white/[0.08]">Esc</kbd>
          </button>
        </div>
      </div>

      {/* ── Center Stage: Pomodoro Master Timer ───────────────────────────── */}
      <div className="flex flex-col items-center justify-center my-auto w-full max-w-md py-4">
        {/* Typographic Timer + Circular Hairline Track */}
        <div className="relative w-64 h-64 flex items-center justify-center my-2">
          <svg className="w-64 h-64 -rotate-90" viewBox="0 0 240 240">
            {/* Background Track */}
            <circle
              cx="120"
              cy="120"
              r={radius}
              stroke="#242424"
              strokeWidth="4"
              fill="none"
            />
            {/* Progress Arc */}
            <circle
              cx="120"
              cy="120"
              r={radius}
              stroke="#E8E3DA"
              strokeWidth="4"
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-1000 ease-linear"
            />
          </svg>

          {/* Centered Countdown Digits */}
          <div className="absolute flex flex-col items-center justify-center pointer-events-none">
            <span className="font-mono text-6xl font-bold tracking-tight text-[#E8E3DA]">
              {formatTime(secondsRemaining)}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-widest text-[#8E8A83] mt-1">
              {isRunning ? 'SPRINT IN PROGRESS' : 'PAUSED'}
            </span>
            {completedSprints > 0 && (
              <span className="font-mono text-[10px] text-[#5C5A56] mt-0.5">
                Completed: {completedSprints} {completedSprints === 1 ? 'sprint' : 'sprints'}
              </span>
            )}
          </div>
        </div>

        {/* Primary Timer Controls */}
        <div className="flex items-center gap-3 mt-4">
          <button
            type="button"
            onClick={() => zenStore.toggleRunning()}
            className={cn(
              "w-12 h-12 rounded-xl flex items-center justify-center transition-all cursor-pointer border",
              isRunning
                ? "bg-white/[0.14] text-white border-white/25 hover:bg-white/[0.22]"
                : "bg-white/[0.08] text-[#E8E3DA] border-white/15 hover:bg-white/[0.16]"
            )}
            title={isRunning ? 'Pause Timer' : 'Start Timer'}
          >
            {isRunning ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
          </button>

          <button
            type="button"
            onClick={() => zenStore.reset()}
            className="w-10 h-10 rounded-xl flex items-center justify-center bg-white/[0.04] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.10] border border-white/[0.08] transition-colors cursor-pointer"
            title="Reset to Preset"
          >
            <RotateCcw size={15} />
          </button>

          <button
            type="button"
            onClick={() => zenStore.addMinutes(5)}
            className="px-3 h-10 rounded-xl flex items-center justify-center bg-white/[0.04] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.10] border border-white/[0.08] font-mono text-xs transition-colors cursor-pointer"
            title="Add 5 Minutes"
          >
            +5m
          </button>

          <button
            type="button"
            onClick={() => {
              if (soundscape === 'off') {
                ambientAudio.setSoundscape('rain');
              } else {
                ambientAudio.setSoundscape('off');
              }
            }}
            className={cn(
              "w-10 h-10 rounded-xl flex items-center justify-center transition-all cursor-pointer border",
              soundscape !== 'off'
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                : "bg-white/[0.04] text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.10] border-white/[0.08]"
            )}
            title={soundscape !== 'off' ? `Mute Focus Soundscape (${soundscape})` : 'Enable Ambient Rain'}
          >
            <Music size={15} />
          </button>
        </div>

        {/* Minimal Preset Switcher */}
        <div className="flex items-center gap-1.5 mt-5">
          {presets.map((p) => (
            <button
              key={p.mins}
              type="button"
              onClick={() => zenStore.setPreset(p.mins)}
              className={cn(
                "px-2.5 py-1 rounded-md font-mono text-[11px] transition-all cursor-pointer border",
                sprintMinutes === p.mins
                  ? "bg-white/[0.14] text-[#E8E3DA] border-white/20 font-semibold"
                  : "bg-transparent text-[#8E8A83] border-transparent hover:text-[#D1CFC0] hover:bg-white/[0.04]"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Active Focus Objective & Important Items ───────────────────────── */}
      <div className="w-full max-w-xl flex flex-col gap-3 mt-4 text-left">
        {/* Primary Focus Target */}
        <div className="p-3.5 rounded-xl bg-[#181818] border border-white/[0.08] flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 overflow-hidden flex-1">
            <button
              type="button"
              onClick={() => activeTask && handleToggleTaskDone(activeTask)}
              className={cn(
                "w-5 h-5 rounded border flex items-center justify-center transition-colors cursor-pointer shrink-0",
                activeTask?.done
                  ? "bg-emerald-500 border-emerald-400 text-black"
                  : "border-white/30 hover:border-white/60 bg-black/30"
              )}
              title={activeTask?.done ? 'Mark pending' : 'Mark complete'}
            >
              {activeTask?.done && <Check size={12} strokeWidth={3} />}
            </button>

            <div className="flex flex-col truncate">
              <span className="font-mono text-[9px] uppercase tracking-wider text-[#8E8A83]">
                PRIMARY FOCUS OBJECTIVE
              </span>
              <span className={cn(
                "font-sans text-sm font-medium truncate",
                activeTask?.done ? "line-through text-[#8E8A83]" : "text-[#E8E3DA]"
              )}>
                {activeTask ? activeTask.title : 'No active focus target selected'}
              </span>
            </div>
          </div>

          <div className="relative shrink-0">
            <button
              type="button"
              onClick={() => setShowTaskPicker((prev) => !prev)}
              className="px-2.5 py-1 rounded bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 font-mono text-[10px] text-[#D1CFC0] flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span>Change</span>
              <ChevronDown size={11} />
            </button>

            {/* Task Picker Dropdown */}
            {showTaskPicker && pendingTasks.length > 0 && (
              <div className="absolute right-0 bottom-full mb-2 w-72 max-h-56 overflow-y-auto rounded-xl border border-white/15 bg-[#1a1a1a] shadow-2xl py-1 z-50 backdrop-blur-xl">
                <div className="px-3 py-1.5 font-mono text-[9px] uppercase tracking-wider text-[#8E8A83] border-b border-white/10">
                  Select Pinned Objective
                </div>
                {pendingTasks.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => {
                      zenStore.setActiveTask(t);
                      setShowTaskPicker(false);
                    }}
                    className={cn(
                      "w-full px-3 py-2 text-left text-xs truncate flex items-center justify-between hover:bg-white/10 transition-colors cursor-pointer",
                      activeTask?.id === t.id ? "text-emerald-400 font-semibold bg-white/5" : "text-[#D1CFC0]"
                    )}
                  >
                    <span className="truncate">{t.title}</span>
                    {t.priority === 'urgent' && (
                      <span className="text-[9px] font-mono text-rose-400 shrink-0 ml-1.5">URGENT</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Compact Urgent Tasks (Max 2) */}
        {urgentTasks.filter((t) => t.id !== activeTask?.id).length > 0 && (
          <div className="p-3 rounded-xl bg-[#141414] border border-white/[0.06] flex flex-col gap-2">
            <span className="font-mono text-[9px] uppercase tracking-wider text-[#8E8A83]">
              URGENT COMMITMENTS
            </span>
            {urgentTasks.filter((t) => t.id !== activeTask?.id).map((t) => (
              <div key={t.id} className="flex items-center justify-between text-xs text-[#D1CFC0]">
                <div className="flex items-center gap-2 truncate">
                  <button
                    type="button"
                    onClick={() => handleToggleTaskDone(t)}
                    className="w-3.5 h-3.5 rounded border border-white/30 hover:border-white/60 shrink-0 cursor-pointer"
                  />
                  <span className="truncate">{t.title}</span>
                </div>
                <span className="font-mono text-[9px] text-rose-400 shrink-0 ml-2">URGENT</span>
              </div>
            ))}
          </div>
        )}

        {/* Ambient Soundscape Deck */}
        <div className="p-3.5 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col gap-2.5 text-left">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[9px] uppercase tracking-wider text-[#8E8A83]">
                AMBIENT FOCUS SOUNDSCAPE
              </span>
              {soundscape !== 'off' && (
                <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA]/80" />
              )}
            </div>

            {soundscape !== 'off' && (
              <div className="flex items-center gap-2">
                <Volume2 size={12} className="text-[#8E8A83]" />
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={soundscapeVol}
                  onChange={(e) => ambientAudio.setVolume(parseFloat(e.target.value))}
                  className="w-20 h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-emerald-400"
                />
                <span className="font-mono text-[10px] text-[#8E8A83] w-7 text-right">
                  {Math.round(soundscapeVol * 100)}%
                </span>
              </div>
            )}
          </div>

          <div className="grid grid-cols-5 gap-2">
            {[
              { id: 'off' as SoundscapeType, label: 'Mute', icon: VolumeX },
              { id: 'rain' as SoundscapeType, label: 'Rain', icon: CloudRain },
              { id: 'ocean' as SoundscapeType, label: 'Ocean Tides', icon: Waves },
              { id: 'fireplace' as SoundscapeType, label: 'Fireplace', icon: Flame },
              { id: 'spotify' as SoundscapeType, label: 'Spotify', icon: Music },
            ].map((opt) => {
              const Icon = opt.icon;
              const isSelected = soundscape === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    ambientAudio.setSoundscape(opt.id);
                    gateway.sendZenTimerUpdate('soundscape', {
                      soundscape: opt.id,
                      music_source: opt.id === 'spotify' ? 'spotify' : 'ambient',
                      is_running: zenStore.isRunning,
                      seconds_remaining: zenStore.secondsRemaining,
                    });
                    if (opt.id === 'spotify') {
                      mediaService.fetchNowPlaying();
                    }
                  }}
                  className={cn(
                    "flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg border font-mono text-[11px] transition-all cursor-pointer",
                    isSelected
                      ? "bg-white/[0.14] text-[#E8E3DA] border-white/25 font-semibold shadow-sm"
                      : "bg-white/[0.03] text-[#8E8A83] hover:text-[#D1CFC0] hover:bg-white/[0.07] border-white/[0.06]"
                  )}
                >
                  <Icon size={13} className={isSelected ? "text-emerald-400" : "text-[#8E8A83]"} />
                  <span className="truncate">{opt.label}</span>
                </button>
              );
            })}
          </div>

          {/* Real Audio Soundscape Active Badge */}
          {soundscape !== 'off' && soundscape !== 'spotify' && (
            <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5 min-w-0 pr-2">
                <div className="w-7 h-7 rounded-md bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                  <Volume2 size={13} className="text-emerald-400" />
                </div>
                <div className="flex flex-col min-w-0 text-left">
                  <span className="text-[#E8E3DA] font-mono text-[11px] truncate font-medium">
                    {soundscape === 'ocean'
                      ? 'Pacific Ocean Waves'
                      : soundscape === 'rain'
                      ? 'Gentle Rainstorm'
                      : 'Crackling Hearth'}
                  </span>
                  <span className="text-emerald-400/80 font-mono text-[9px] truncate">
                    High-Definition Stereo Field Recording
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Spotify Now-Playing Micro Controller */}
          {soundscape === 'spotify' && (
            <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-xs">
              <div className="flex items-center gap-2.5 min-w-0 pr-2">
                {mediaTrack.art_url ? (
                  <img
                    src={mediaTrack.art_url}
                    alt={mediaTrack.title}
                    className="w-7 h-7 rounded-md object-cover border border-white/10 shrink-0"
                  />
                ) : (
                  <div className="w-7 h-7 rounded-md bg-white/[0.04] border border-white/10 flex items-center justify-center shrink-0">
                    <Disc3 size={14} className={cn("text-[#8E8A83]", mediaTrack.is_playing && "animate-spin text-emerald-400")} />
                  </div>
                )}
                <div className="flex flex-col min-w-0 text-left">
                  <span className="text-[#E8E3DA] font-mono text-[11px] truncate font-medium">
                    {mediaTrack.title || 'Spotify Audio Sink'}
                  </span>
                  <span className="text-[#8E8A83] font-mono text-[9px] truncate">
                    {mediaTrack.artist || 'Ready'}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => mediaService.previous()}
                  className="w-6 h-6 rounded flex items-center justify-center text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/10 transition-colors cursor-pointer"
                  title="Previous Track"
                >
                  <SkipBack size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => mediaService.playPause()}
                  className="w-6 h-6 rounded flex items-center justify-center text-[#E8E3DA] hover:bg-white/10 transition-colors cursor-pointer"
                  title={mediaTrack.is_playing ? 'Pause' : 'Play'}
                >
                  {mediaTrack.is_playing ? <Pause size={12} /> : <Play size={12} />}
                </button>
                <button
                  type="button"
                  onClick={() => mediaService.next()}
                  className="w-6 h-6 rounded flex items-center justify-center text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/10 transition-colors cursor-pointer"
                  title="Next Track"
                >
                  <SkipForward size={12} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Schedule Strip */}
        <div className="px-3 py-2 rounded-lg bg-black/20 border border-white/[0.04] flex items-center justify-between text-left">
          <div className="flex items-center gap-2 text-[#8E8A83] font-mono text-[11px]">
            <Calendar size={13} className="text-[#8E8A83] shrink-0" />
            <span>
              {nextCalendarEvent || 'Calendar clear for the next 4 hours — uninterrupted deep focus.'}
            </span>
          </div>
          {soundscape !== 'off' && (
            <div className="flex items-center gap-1.5 font-mono text-[10px] text-[#E8E3DA]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#E8E3DA]/80" />
              <span className="capitalize">{soundscape} active</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Post-Sprint Executive Debrief Catch-Up Modal ──────────────────── */}
      <AnimatePresence>
        {showDebrief && (
          <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/75 backdrop-blur-md">
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              className="w-full max-w-md p-6 rounded-2xl border border-white/15 bg-[#141414] shadow-2xl flex flex-col gap-4 text-left"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={18} className="text-emerald-400" />
                  <span className="font-serif text-lg font-medium text-[#E8E3DA]">Focus Sprint Summary</span>
                </div>
                <button
                  type="button"
                  onClick={() => zenStore.setShowDebrief(false)}
                  className="p-1 rounded-lg text-[#8E8A83] hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-black/40 border border-white/[0.06] flex flex-col">
                  <span className="font-mono text-[10px] text-[#8E8A83] uppercase">Completed Sprints</span>
                  <span className="font-mono text-2xl font-bold text-[#E8E3DA] mt-1">{completedSprints || 1}</span>
                  <span className="font-sans text-[11px] text-[#8E8A83] mt-0.5">{sprintMinutes} minutes total</span>
                </div>

                <div className="p-3 rounded-xl bg-black/40 border border-white/[0.06] flex flex-col">
                  <span className="font-mono text-[10px] text-[#8E8A83] uppercase">Held Notifications</span>
                  <span className="font-mono text-2xl font-bold text-emerald-400 mt-1">{sessionHeldCount}</span>
                  <span className="font-sans text-[11px] text-[#8E8A83] mt-0.5">Buffered silently</span>
                </div>
              </div>

              {activeTask && (
                <div className="p-3 rounded-xl bg-[#181818] border border-white/[0.08] flex items-center justify-between">
                  <div className="flex flex-col truncate pr-2">
                    <span className="font-mono text-[9px] uppercase text-[#8E8A83]">Pinned Target</span>
                    <span className="font-sans text-xs text-[#E8E3DA] truncate">{activeTask.title}</span>
                  </div>
                  <span className="font-mono text-[10px] text-emerald-400 shrink-0">
                    {activeTask.done ? 'COMPLETED' : 'IN PROGRESS'}
                  </span>
                </div>
              )}

              <div className="flex items-center gap-2 pt-2 border-t border-white/10">
                {sessionHeldCount > 0 && onOpenNotifications && (
                  <button
                    type="button"
                    onClick={() => {
                      zenStore.setShowDebrief(false);
                      onOpenNotifications();
                    }}
                    className="flex-1 py-2.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 font-mono text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <Bell size={13} />
                    Review Held Alerts ({sessionHeldCount})
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => zenStore.setShowDebrief(false)}
                  className="flex-1 py-2.5 rounded-xl bg-white/[0.08] hover:bg-white/[0.14] text-[#E8E3DA] font-mono text-xs transition-colors cursor-pointer flex items-center justify-center gap-1"
                >
                  Dismiss Summary
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

// Legacy alias for backwards compatibility
export const ZenFocusOverlay: React.FC<any> = (props) => {
  return <ZenFocusView onExitZen={props.onToggleZenMode} onOpenNotifications={props.onOpenAdvisories} />;
};

export default ZenFocusView;
