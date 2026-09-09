import { ApiTask, TaskStats } from '../types/vesper';

export type TaskListener = () => void;

const DEFAULT_STATS: TaskStats = {
  total: 6,
  today_count: 2,
  overdue_count: 2,
  upcoming_count: 1,
  completed_count: 1,
  pending_count: 5,
};

const INITIAL_FALLBACK_TASKS: ApiTask[] = [
  {
    id: 'task_demo_1',
    title: 'Review PR #42 & verification test suite',
    done: false,
    priority: 'high',
    category: 'today',
    age_label: 'Today • 14:30',
    tag: 'DEV',
  },
  {
    id: 'task_demo_2',
    title: 'Synchronize Android node notification relay',
    done: false,
    priority: 'normal',
    category: 'today',
    age_label: 'Today • 16:00',
    tag: 'SYNC',
  },
  {
    id: 'task_demo_3',
    title: 'Quarterly infrastructure security audit and API key rotation',
    done: false,
    priority: 'urgent',
    category: 'overdue',
    age_label: '2 days overdue',
    tag: 'SECURITY',
  },
  {
    id: 'task_demo_4',
    title: 'Re-index graphify knowledge graph for mobile subproject',
    done: false,
    priority: 'normal',
    category: 'overdue',
    age_label: '1 day overdue',
    tag: 'DOCS',
  },
  {
    id: 'task_demo_5',
    title: 'Deploy Caelestia QML lock-screen power sentry daemon',
    done: false,
    priority: 'normal',
    category: 'upcoming',
    age_label: 'Tomorrow • 10:00',
    tag: 'LINUX',
  },
  {
    id: 'task_demo_6',
    title: 'Calibrate BlazeFace camera presence sentry',
    done: true,
    priority: 'normal',
    category: 'completed',
    age_label: 'Completed',
    tag: 'VISION',
  },
];

class TaskService {
  private tasks: ApiTask[] = INITIAL_FALLBACK_TASKS;
  private stats: TaskStats = DEFAULT_STATS;
  private listeners: Set<TaskListener> = new Set();
  private baseUrl = 'http://127.0.0.1:8000';
  private pollInterval: number | null = null;
  private isLoading = false;

  constructor() {
    this.fetchTasks();
    // Refresh tasks every 20 seconds to stay in sync with background agents
    if (typeof window !== 'undefined') {
      this.pollInterval = window.setInterval(() => {
        this.fetchTasks();
      }, 20000);
    }
  }

  public subscribe(listener: TaskListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((cb) => {
      try {
        cb();
      } catch (err) {
        console.error('[TASK SERVICE] Listener error:', err);
      }
    });
  }

  public getTasks(category?: 'today' | 'overdue' | 'upcoming' | 'completed' | 'all'): ApiTask[] {
    if (!category || category === 'all') {
      return this.tasks;
    }
    if (category === 'completed') {
      return this.tasks.filter((t) => t.done);
    }
    return this.tasks.filter((t) => !t.done && t.category === category);
  }

  public getStats(): TaskStats {
    return this.stats;
  }

  public getIsLoading(): boolean {
    return this.isLoading;
  }

  public async fetchTasks(): Promise<void> {
    try {
      this.isLoading = true;
      const res = await fetch(`${this.baseUrl}/api/tasks?include_completed=true`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      if (Array.isArray(data.tasks)) {
        this.tasks = data.tasks;
      }
      if (data.stats) {
        this.stats = data.stats;
      }
      this.notify();
    } catch (err) {
      // Graceful fallback: maintain current state
    } finally {
      this.isLoading = false;
    }
  }

  public async toggleTask(id: string, newDoneStatus?: boolean): Promise<void> {
    // 1. Optimistic local update
    const target = this.tasks.find((t) => t.id === id);
    if (!target) return;

    const nextDone = newDoneStatus !== undefined ? newDoneStatus : !target.done;
    this.tasks = this.tasks.map((t) =>
      t.id === id ? { ...t, done: nextDone, category: nextDone ? 'completed' : t.category } : t
    );
    this.recalculateStats();
    this.notify();

    // 2. Background API call
    try {
      const res = await fetch(`${this.baseUrl}/api/tasks/${id}/toggle`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: nextDone }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data.task) {
        this.tasks = this.tasks.map((t) => (t.id === id ? data.task : t));
        this.recalculateStats();
        this.notify();
      }
    } catch (err) {
      console.warn('[TASK SERVICE] Toggle failed on backend, refreshing state:', err);
      this.fetchTasks();
    }
  }

  public async createTask(title: string, priority: 'low' | 'normal' | 'high' | 'urgent' = 'normal', tag = 'TASK'): Promise<void> {
    try {
      const res = await fetch(`${this.baseUrl}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, priority, tag }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await this.fetchTasks();
    } catch (err) {
      console.error('[TASK SERVICE] Task creation failed:', err);
      // Fallback local insert
      const fallbackTask: ApiTask = {
        id: `local_${Date.now()}`,
        title,
        done: false,
        priority,
        category: 'today',
        age_label: 'Today',
        tag: tag.toUpperCase(),
      };
      this.tasks = [fallbackTask, ...this.tasks];
      this.recalculateStats();
      this.notify();
    }
  }

  private recalculateStats(): void {
    const today = this.tasks.filter((t) => !t.done && t.category === 'today');
    const overdue = this.tasks.filter((t) => !t.done && t.category === 'overdue');
    const upcoming = this.tasks.filter((t) => !t.done && t.category === 'upcoming');
    const completed = this.tasks.filter((t) => t.done);

    this.stats = {
      total: this.tasks.length,
      today_count: today.length,
      overdue_count: overdue.length,
      upcoming_count: upcoming.length,
      completed_count: completed.length,
      pending_count: today.length + overdue.length + upcoming.length,
    };
  }

  public destroy(): void {
    if (this.pollInterval !== null) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.listeners.clear();
  }
}

export const taskService = new TaskService();
