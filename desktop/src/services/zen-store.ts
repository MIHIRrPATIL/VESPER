import { notificationStore } from './notification-store';
import { ambientAudio } from './ambient-audio';

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
  private _completedSprints = 0;
  private _soundscapeEnabled = false;
  private _activeTask: ZenTaskItem | null = null;
  private _showDebrief = false;
  private _sessionHeldCount = 0;

  private _timerId: ReturnType<typeof setInterval> | null = null;
  private _listeners: Set<ZenStoreListener> = new Set();

  get sprintMinutes() { return this._sprintMinutes; }
  get secondsRemaining() { return this._secondsRemaining; }
  get isRunning() { return this._isRunning; }
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

  start() {
    if (this._isRunning) return;
    this._isRunning = true;

    if (this._timerId) clearInterval(this._timerId);
    this._timerId = setInterval(() => {
      if (this._secondsRemaining <= 1) {
        this._secondsRemaining = 0;
        this.pause();
        this._completedSprints += 1;
        this._sessionHeldCount = notificationStore.heldNotificationsCount;
        this._showDebrief = true;
        this._notify();
      } else {
        this._secondsRemaining -= 1;
        this._notify();
      }
    }, 1000);

    this._notify();
  }

  pause() {
    this._isRunning = false;
    if (this._timerId) {
      clearInterval(this._timerId);
      this._timerId = null;
    }
    this._notify();
  }

  toggleRunning() {
    if (this._isRunning) {
      this.pause();
    } else {
      this.start();
    }
  }

  reset() {
    this.pause();
    this._secondsRemaining = this._sprintMinutes * 60;
    this._notify();
  }

  setPreset(minutes: number) {
    this._sprintMinutes = minutes;
    this._secondsRemaining = minutes * 60;
    this.start();
    this._notify();
  }

  addMinutes(mins: number) {
    this._secondsRemaining += mins * 60;
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
    } catch {
      // Audio optional
    }
  }

  onZenModeStateChange(zenActive: boolean) {
    if (zenActive) {
      this.start();
      this._showDebrief = false;
    } else {
      this.pause();
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
