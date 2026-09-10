import React, { useState, useEffect, useCallback } from 'react';
import {
  CalendarCheck,
  CheckCircle2,
  Circle,
  Plus,
  Trash2,
  Clock,
  AlertCircle,
  Calendar,
  ExternalLink,
  Search,
  RefreshCw,
  ArrowRight
} from 'lucide-react';
import { cn } from '../lib/utils';

const API_BASE = 'http://localhost:8000/api/tasks';

interface Task {
  id: string;
  user_id?: string;
  title: string;
  deadline?: string | null;
  done: boolean;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  category?: 'today' | 'overdue' | 'upcoming' | 'completed';
  age_label?: string;
  metadata?: Record<string, any>;
  created_at?: string;
}

interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end?: string;
  html_link?: string;
  location?: string;
}

interface TasksAgendaViewProps {
  onSendUserMessage?: (text: string) => void;
}

export const TasksAgendaView: React.FC<TasksAgendaViewProps> = ({ onSendUserMessage }) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [activeCategory, setActiveCategory] = useState<'all' | 'today' | 'overdue' | 'upcoming' | 'completed'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  // New task form state
  const [newTitle, setNewTitle] = useState('');
  const [newPriority, setNewPriority] = useState<'normal' | 'high' | 'urgent'>('normal');
  const [newDeadline, setNewDeadline] = useState('');

  const fetchTasksData = useCallback(async () => {
    try {
      const res = await fetch(API_BASE);
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
        if (data.calendar_events) {
          setCalendarEvents(data.calendar_events);
        }
      }
    } catch (err) {
      console.error('[TasksView] Error loading tasks:', err);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchTasksData();
  }, [fetchTasksData]);

  const handleToggleTask = async (task: Task) => {
    // Optimistic UI update
    setTasks((prev) =>
      prev.map((t) => (t.id === task.id ? { ...t, done: !t.done } : t))
    );

    try {
      const res = await fetch(`${API_BASE}/${task.id}/toggle`, {
        method: 'PATCH',
      });
      if (res.ok) {
        const updated = await res.json();
        setTasks((prev) =>
          prev.map((t) => (t.id === task.id ? { ...t, done: updated.done } : t))
        );
      }
    } catch {
      fetchTasksData();
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
    try {
      await fetch(`${API_BASE}/${taskId}`, { method: 'DELETE' });
    } catch {
      fetchTasksData();
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    const payload = {
      title: newTitle.trim(),
      priority: newPriority,
      deadline: newDeadline ? new Date(newDeadline).toISOString() : null,
    };

    try {
      const res = await fetch(API_BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setNewTitle('');
        setNewDeadline('');
        setNewPriority('normal');
        fetchTasksData();
      }
    } catch (err) {
      console.error('[TasksView] Error creating task:', err);
    }
  };

  // Derived counts
  const todayTasks = tasks.filter((t) => t.category === 'today' && !t.done);
  const overdueTasks = tasks.filter((t) => t.category === 'overdue' && !t.done);
  const upcomingTasks = tasks.filter((t) => t.category === 'upcoming' && !t.done);
  const completedTasks = tasks.filter((t) => t.done);

  // Filtered task items
  const filteredTasks = tasks.filter((t) => {
    if (activeCategory === 'today') return t.category === 'today' && !t.done;
    if (activeCategory === 'overdue') return t.category === 'overdue' && !t.done;
    if (activeCategory === 'upcoming') return t.category === 'upcoming' && !t.done;
    if (activeCategory === 'completed') return t.done;
    return true;
  }).filter((t) => {
    if (!searchQuery.trim()) return true;
    return t.title.toLowerCase().includes(searchQuery.toLowerCase());
  });

  return (
    <div className="w-full max-w-6xl flex flex-col items-start gap-8 py-4 text-left">
      {/* View Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between w-full border-b border-white/[0.08] pb-6 gap-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[#8E8A83]">
            <CalendarCheck size={14} className="text-[#E8E3DA]" />
            EXECUTIVE AGENDA & GOOGLE CALENDAR ENGINE
          </div>
          <h1 className="font-serif text-3xl font-medium text-[#E8E3DA]">Tasks & Schedule Command Deck</h1>
          <p className="font-sans text-sm text-[#8E8A83]">
            Synchronized task priorities, deadline schedules, and two-way Google Calendar v3 events.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setIsRefreshing(true);
            fetchTasksData();
          }}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-[#8E8A83] hover:text-[#E8E3DA] font-mono text-xs transition-colors border border-white/[0.08] cursor-pointer disabled:opacity-50"
        >
          <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
          <span>Sync Now</span>
        </button>
      </div>

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
        <div className="p-4 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col gap-1">
          <span className="font-mono text-[11px] text-[#8E8A83] uppercase tracking-wider">Today's Agenda</span>
          <span className="font-mono text-2xl font-bold text-[#E8E3DA]">{todayTasks.length}</span>
          <span className="font-sans text-xs text-[#8E8A83]">Due before midnight</span>
        </div>

        <div className={`p-4 rounded-xl bg-[#181818] border flex flex-col gap-1 ${
          overdueTasks.length > 0 ? 'border-red-500/30 bg-red-950/10' : 'border-white/[0.08]'
        }`}>
          <span className="font-mono text-[11px] text-red-300 uppercase tracking-wider flex items-center gap-1">
            {overdueTasks.length > 0 && <AlertCircle size={12} />}
            Overdue Matters
          </span>
          <span className="font-mono text-2xl font-bold text-red-200">{overdueTasks.length}</span>
          <span className="font-sans text-xs text-[#8E8A83]">Past deadline</span>
        </div>

        <div className="p-4 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col gap-1">
          <span className="font-mono text-[11px] text-[#8E8A83] uppercase tracking-wider">Upcoming Schedule</span>
          <span className="font-mono text-2xl font-bold text-[#E8E3DA]">{upcomingTasks.length}</span>
          <span className="font-sans text-xs text-[#8E8A83]">Future calendar dates</span>
        </div>

        <div className="p-4 rounded-xl bg-[#181818] border border-white/[0.08] flex flex-col gap-1">
          <span className="font-mono text-[11px] text-[#8E8A83] uppercase tracking-wider">Completed</span>
          <span className="font-mono text-2xl font-bold text-emerald-400">{completedTasks.length}</span>
          <span className="font-sans text-xs text-[#8E8A83]">Resolved tasks</span>
        </div>
      </div>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 w-full">
        {/* Left Column: Task Stream (2 Columns) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          {/* Quick Task Creation Bar */}
          <form
            onSubmit={handleCreateTask}
            className="p-3.5 rounded-xl bg-[#181818] border border-white/[0.10] flex flex-col sm:flex-row items-center gap-2.5 shadow-lg"
          >
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Add an actionable directive or task..."
              className="flex-1 bg-transparent px-3 py-1.5 text-sm text-[#E8E3DA] placeholder-[#8E8A83] focus:outline-none font-sans"
            />

            <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
              <select
                value={newPriority}
                onChange={(e) => setNewPriority(e.target.value as any)}
                className="bg-black/50 border border-white/[0.1] rounded-lg px-2.5 py-1.5 font-mono text-xs text-[#E8E3DA] focus:outline-none cursor-pointer"
              >
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>

              <button
                type="submit"
                disabled={!newTitle.trim()}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-white/[0.14] hover:bg-white/[0.22] text-[#E8E3DA] font-mono text-xs font-semibold transition-all cursor-pointer disabled:opacity-40"
              >
                <Plus size={13} />
                <span>Add Task</span>
              </button>
            </div>
          </form>

          {/* Category Filter & Search Strip */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-2">
            <div className="flex items-center gap-1 bg-black/40 p-1 rounded-lg border border-white/[0.08] overflow-x-auto max-w-full">
              {(['all', 'today', 'overdue', 'upcoming', 'completed'] as const).map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setActiveCategory(cat)}
                  className={cn(
                    "px-3 py-1 rounded font-mono text-xs uppercase tracking-wider transition-colors cursor-pointer whitespace-nowrap",
                    activeCategory === cat
                      ? "bg-white/[0.14] text-[#E8E3DA] font-semibold"
                      : "text-[#8E8A83] hover:text-[#D1CFC0]"
                  )}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="relative w-full sm:w-48">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8E8A83]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search tasks..."
                className="w-full bg-black/30 border border-white/[0.08] rounded-lg pl-8 pr-3 py-1 text-xs text-[#E8E3DA] placeholder-[#8E8A83] focus:outline-none"
              />
            </div>
          </div>

          {/* Tasks List */}
          <div className="flex flex-col gap-2.5 min-h-[300px]">
            {filteredTasks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-[#8E8A83] font-sans text-xs border border-dashed border-white/[0.08] rounded-xl bg-black/20">
                <CalendarCheck size={26} strokeWidth={1.4} className="mb-2 text-[#5C5A56]" />
                <span className="font-mono text-xs text-[#D1CFC0]">No tasks in category "{activeCategory}"</span>
                <p className="text-xs text-[#8E8A83] mt-1">Directives created via Alfred voice or Google Calendar will populate here.</p>
              </div>
            ) : (
              filteredTasks.map((task) => {
                const isOverdue = task.category === 'overdue' && !task.done;

                return (
                  <div
                    key={task.id}
                    className={cn(
                      "p-3.5 rounded-xl border bg-[#181818] hover:border-white/20 transition-all flex items-center justify-between gap-3 group",
                      task.done ? "border-white/[0.04] opacity-60" : "border-white/[0.08]",
                      isOverdue ? "border-red-500/25 bg-red-950/5" : ""
                    )}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <button
                        type="button"
                        onClick={() => handleToggleTask(task)}
                        className="cursor-pointer text-[#8E8A83] hover:text-[#E8E3DA] transition-colors shrink-0"
                      >
                        {task.done ? (
                          <CheckCircle2 size={18} className="text-emerald-400" />
                        ) : (
                          <Circle size={18} />
                        )}
                      </button>

                      <div className="flex flex-col min-w-0 flex-1">
                        <span className={cn(
                          "font-sans text-sm tracking-tight truncate",
                          task.done ? "line-through text-[#8E8A83]" : "text-[#E8E3DA]"
                        )}>
                          {task.title}
                        </span>

                        <div className="flex items-center gap-2 mt-1">
                          {task.age_label && (
                            <span className="font-mono text-[10px] text-[#8E8A83] flex items-center gap-1">
                              <Clock size={10} />
                              {task.age_label}
                            </span>
                          )}
                          {task.priority && (
                            <span className={cn(
                              "font-mono text-[9px] px-1.5 py-0.2 rounded uppercase font-semibold",
                              task.priority === 'urgent'
                                ? "bg-red-500/20 text-red-300 border border-red-500/30"
                                : task.priority === 'high'
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                : "bg-white/[0.06] text-[#A1A1AA]"
                            )}>
                              {task.priority}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleDeleteTask(task.id)}
                      className="opacity-0 group-hover:opacity-100 p-1.5 rounded text-[#8E8A83] hover:text-red-400 hover:bg-white/[0.06] transition-all cursor-pointer"
                      title="Delete task"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Synchronized Google Calendar Agenda Panel */}
        <div className="flex flex-col gap-4">
          <div className="p-5 rounded-2xl bg-[#181818] border border-white/[0.08] flex flex-col gap-3 shadow-lg">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-[#E8E3DA]" />
                <span className="font-mono text-xs uppercase tracking-wider text-[#E8E3DA] font-semibold">
                  Google Calendar
                </span>
              </div>
              <a
                href="https://calendar.google.com"
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 font-mono text-[10px] text-[#8E8A83] hover:text-[#E8E3DA] transition-colors"
              >
                <span>Open Web</span>
                <ExternalLink size={10} />
              </a>
            </div>

            {/* Calendar Events List */}
            <div className="flex flex-col gap-2.5 pt-1">
              {calendarEvents.length === 0 ? (
                <div className="py-8 text-center text-[#8E8A83] font-sans text-xs">
                  No upcoming calendar appointments today.
                </div>
              ) : (
                calendarEvents.map((ev) => (
                  <a
                    key={ev.id}
                    href={ev.html_link || 'https://calendar.google.com'}
                    target="_blank"
                    rel="noreferrer"
                    className="p-3 rounded-xl bg-black/40 border border-white/[0.06] hover:border-white/20 transition-all flex flex-col gap-1 group cursor-pointer"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] text-amber-300">
                        {ev.start ? new Date(ev.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'All Day'}
                      </span>
                      <ExternalLink size={10} className="opacity-0 group-hover:opacity-100 text-[#8E8A83] transition-opacity" />
                    </div>
                    <span className="font-sans text-xs font-semibold text-[#E8E3DA] group-hover:text-white transition-colors truncate">
                      {ev.title}
                    </span>
                    {ev.location && (
                      <span className="font-sans text-[10px] text-[#8E8A83] truncate">
                        {ev.location}
                      </span>
                    )}
                  </a>
                ))
              )}
            </div>

            {/* Natural Language Voice Directives Hint */}
            {onSendUserMessage && (
              <div className="pt-3 border-t border-white/[0.06] mt-2">
                <span className="font-mono text-[10px] text-[#5C5A56] uppercase tracking-wider block mb-2">
                  Voice Agent Shortcuts
                </span>
                <div className="flex flex-col gap-1.5">
                  <button
                    type="button"
                    onClick={() => onSendUserMessage("What is on my calendar today?")}
                    className="text-left font-sans text-xs text-[#8E8A83] hover:text-[#E8E3DA] transition-colors flex items-center justify-between p-1.5 rounded hover:bg-white/[0.04] cursor-pointer"
                  >
                    <span>"What's on my calendar today?"</span>
                    <ArrowRight size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onSendUserMessage("List all high priority tasks")}
                    className="text-left font-sans text-xs text-[#8E8A83] hover:text-[#E8E3DA] transition-colors flex items-center justify-between p-1.5 rounded hover:bg-white/[0.04] cursor-pointer"
                  >
                    <span>"List all high priority tasks"</span>
                    <ArrowRight size={11} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
