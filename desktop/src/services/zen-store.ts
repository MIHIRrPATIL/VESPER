import { notificationStore } from './notification-store';
import { ambientAudio } from './ambient-audio';
import { gateway } from './gateway';

export interface ZenTaskItem {
  id: string;
  title: string;
  done: boolean;
  priority?: string;
  deadline?: string;
}

export type ZenStoreListener = () => void;

const API_MEDIA = 'http://localhost:8000/api/media';

class ZenStore {
  private _sprintMinutes = 25;
  private _secondsRemaining = 25 * 60;
  private _isRunning = false;
  private _endsAt: number | null = null;
  private _completedSprints = 0;
  private _soundscapeEnabled = false;
  private _activeTask: ZenTaskItem | null = null;
  private _showDebrief = false;
  private _sessionHeldCount = 0;

  private _timerId: ReturnType<typeof setInterval> | null = null;
  private _listeners: Set<ZenStoreListener> = new Set();
  private _suppressBroadcast = false;

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', () => {
        this.recalculate();
      });
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) this.recalculate();
      });
    }
  }

  get sprintMinutes() { return this._sprintMinutes; }
  get secondsRemaining() { return this._secondsRemaining; }
  get isRunning() { return this._isRunning; }
  get endsAt() { return this._endsAt; }
  get completedSprints() { return this._completedSprints; }
  get soundscapeEnabled() { return this._soundscapeEnabled; }
  get activeTask() { return this._activeTask; }
  get showDebrief() { return this._showDebrief; }
  get sessionHeldCount() { return this._sessionHeldCount; }

  subscribe(listener: ZenStoreListener): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  private _notify() {
    this._listeners.forEach((l) => {
      try {
        l();
      } catch (e) {
        console.error('[ZenStore] Listener error:', e);
      }
    });
  }

  public recalculate(): void {
    if (!this._isRunning) return;
    if (this._endsAt) {
      const remaining = Math.max(0, Math.round((this._endsAt - Date.now()) / 1000));
      this._secondsRemaining = remaining;
      if (remaining <= 0) {
        this.pause(true);
        this._completedSprints += 1;
        this._sessionHeldCount = notificationStore.heldNotificationsCount;
        this._showDebrief = true;
      }
      this._notify();
    }
  }

  start(broadcast = true) {
    if (this._isRunning) return;
    this._isRunning = true;
    if (!this._endsAt) {
      this._endsAt = Date.now() + this._secondsRemaining * 1000;
    }

    if (this._timerId) clearInterval(this._timerId);
    this._timerId = setInterval(() => {
      if (this._endsAt) {
        const remaining = Math.max(0, Math.round((this._endsAt - Date.now()) / 1000));
        this._secondsRemaining = remaining;
        if (remaining <= 0) {
          this._secondsRemaining = 0;
          this.pause(true);
          this._completedSprints += 1;
          this._sessionHeldCount = notificationStore.heldNotificationsCount;
          this._showDebrief = true;
          this._notify();
          return;
        }
      } else {
        if (this._secondsRemaining <= 1) {
          this._secondsRemaining = 0;
          this.pause(true);
          this._completedSprints += 1;
          this._sessionHeldCount = notificationStore.heldNotificationsCount;
          this._showDebrief = true;
          this._notify();
          return;
        } else {
          this._secondsRemaining -= 1;
        }
      }
      this._notify();
    }, 1000);

    if (broadcast && !this._suppressBroadcast) {
      gateway.sendZenTimerUpdate('start', {
        seconds_remaining: this._secondsRemaining,
        ends_at: this._endsAt,
      });
    }

    this._notify();
  }

  pause(broadcast = true) {
    this._isRunning = false;
    this._endsAt = null;
    if (this._timerId) {
      clearInterval(this._timerId);
      this._timerId = null;
    }

    if (broadcast && !this._suppressBroadcast) {
      gateway.sendZenTimerUpdate('pause', { seconds_remaining: this._secondsRemaining });
    }

    this._notify();
  }

  toggleRunning() {
    if (this._isRunning) {
      this.pause(true);
    } else {
      this.start(true);
    }
  }

  reset(broadcast = true) {
    this.pause(false);
    this._endsAt = null;
    this._secondsRemaining = this._sprintMinutes * 60;

    if (broadcast && !this._suppressBroadcast) {
      gateway.sendZenTimerUpdate('reset', { seconds_remaining: this._secondsRemaining });
    }

    this._notify();
  }

  setPreset(minutes: number, broadcast = true) {
    this._sprintMinutes = minutes;
    this._secondsRemaining = minutes * 60;
    this._endsAt = Date.now() + minutes * 60 * 1000;
    this.start(broadcast);

    if (broadcast && !this._suppressBroadcast) {
      gateway.sendZenTimerUpdate('preset', {
        minutes,
        seconds_remaining: this._secondsRemaining,
        ends_at: this._endsAt,
      });
    }

    this._notify();
  }

  addMinutes(mins: number) {
    this._secondsRemaining += mins * 60;
    if (this._endsAt) {
      this._endsAt += mins * 60 * 1000;
    }
    gateway.sendZenTimerUpdate('tick', {
      seconds_remaining: this._secondsRemaining,
      ends_at: this._endsAt,
    });
    this._notify();
  }

  setActiveTask(task: ZenTaskItem | null) {
    this._activeTask = task;
    this._notify();
  }

  setShowDebrief(show: boolean) {
    this._showDebrief = show;
    this._notify();
  }

  async toggleSoundscape() {
    const next = !this._soundscapeEnabled;
    this._soundscapeEnabled = next;
    this._notify();

    try {
      await fetch(`${API_MEDIA}/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: next ? 'play' : 'pause' }),
      });
    } catch {}
  }

  applyInboundTimerUpdate(action: string, timerData: any) {
    if (!timerData) return;
    this._suppressBroadcast = true;
    try {
      if (action === 'soundscape') {
        const newSoundscape = timerData.soundscape || timerData.timer?.soundscape;
        if (newSoundscape) {
          ambientAudio.setSoundscape(newSoundscape);
        }
        return;
      }

      if (typeof timerData.ends_at === 'number' || timerData.ends_at === null) {
        this._endsAt = timerData.ends_at;
      }

      if (this._endsAt && (action === 'start' || timerData.is_running === true)) {
        this._secondsRemaining = Math.max(0, Math.round((this._endsAt - Date.now()) / 1000));
      } else if (typeof timerData.seconds_remaining === 'number') {
        this._secondsRemaining = timerData.seconds_remaining;
      }

      if (typeof timerData.sprint_minutes === 'number') {
        this._sprintMinutes = timerData.sprint_minutes;
      }
      if (typeof timerData.completed_sprints === 'number') {
        this._completedSprints = timerData.completed_sprints;
      }

      if (action === 'start' || timerData.is_running === true) {
        if (!this._isRunning) {
          this.start(false);
        }
      } else if (action === 'pause' || action === 'reset') {
        if (this._isRunning) {
          this.pause(false);
        }
      } else if (timerData.is_running === false && action !== 'soundscape') {
        if (this._isRunning) {
          this.pause(false);
        }
      }

      if (timerData.soundscape) {
        ambientAudio.setSoundscape(timerData.soundscape);
      }
    } finally {
      this._suppressBroadcast = false;
      this._notify();
    }
  }

  onZenModeStateChange(zenActive: boolean, timerData?: any) {
    if (zenActive) {
      this._showDebrief = false;
      if (timerData?.ends_at) {
        this._endsAt = timerData.ends_at;
        this._secondsRemaining = Math.max(0, Math.round((timerData.ends_at - Date.now()) / 1000));
      } else if (timerData?.seconds_remaining) {
        this._secondsRemaining = timerData.seconds_remaining;
        this._endsAt = Date.now() + this._secondsRemaining * 1000;
      } else {
        this._secondsRemaining = this._sprintMinutes * 60;
        this._endsAt = Date.now() + this._secondsRemaining * 1000;
      }
      // Auto-start timer on Zen mode entry
      this.start(false);

      // Auto-start ambient sound on host speakers (default ocean)
      const targetSoundscape = timerData?.soundscape || 'ocean';
      ambientAudio.setSoundscape(targetSoundscape);
    } else {
      this.pause(false);
      this._endsAt = null;
      ambientAudio.setSoundscape('off');
      const held = notificationStore.heldNotificationsCount;
      if (held > 0 || this._completedSprints > 0) {
        this._sessionHeldCount = held;
        this._showDebrief = true;
      }
    }
    this._notify();
  }
}

export const zenStore = new ZenStore();
