import { NowPlayingTrack } from '../types/vesper';

export type MediaListener = () => void;

const DEFAULT_TRACK: NowPlayingTrack = {
  title: 'No Media Playing',
  artist: 'Spotify / Audio Sink',
  album: '',
  art_url: '',
  is_playing: false,
  status: 'Stopped',
  duration_ms: 0,
  position_ms: 0,
};

class MediaService {
  private currentTrack: NowPlayingTrack = DEFAULT_TRACK;
  private listeners: Set<MediaListener> = new Set();
  private baseUrl = 'http://127.0.0.1:8000';
  private pollInterval: number | null = null;
  private isUpdating = false;

  constructor() {
    this.fetchNowPlaying();
    if (typeof window !== 'undefined') {
      this.pollInterval = window.setInterval(() => {
        this.fetchNowPlaying();
      }, 2500);
    }
  }

  public subscribe(listener: MediaListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((cb) => {
      try {
        cb();
      } catch (err) {
        console.error('[MEDIA SERVICE] Listener error:', err);
      }
    });
  }

  public getTrack(): NowPlayingTrack {
    return this.currentTrack;
  }

  public async fetchNowPlaying(): Promise<void> {
    if (this.isUpdating) return;
    try {
      const res = await fetch(`${this.baseUrl}/api/media/now-playing`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: NowPlayingTrack = await res.json();
      
      const changed =
        data.title !== this.currentTrack.title ||
        data.is_playing !== this.currentTrack.is_playing ||
        data.art_url !== this.currentTrack.art_url;

      this.currentTrack = data;
      if (changed) {
        this.notify();
      }
    } catch (_) {
      // Keep existing track state if gateway unreachable
    }
  }

  public async control(action: 'play-pause' | 'play' | 'pause' | 'next' | 'previous'): Promise<void> {
    // 1. Optimistic update
    if (action === 'play-pause' || action === 'play' || action === 'pause') {
      const willPlay = action === 'play' ? true : action === 'pause' ? false : !this.currentTrack.is_playing;
      this.currentTrack = {
        ...this.currentTrack,
        is_playing: willPlay,
        status: willPlay ? 'Playing' : 'Paused',
      };
      this.notify();
    }

    this.isUpdating = true;
    try {
      const res = await fetch(`${this.baseUrl}/api/media/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      if (res.ok) {
        const data: NowPlayingTrack = await res.json();
        this.currentTrack = data;
        this.notify();
      }
    } catch (err) {
      console.warn('[MEDIA SERVICE] Control action failed:', err);
    } finally {
      this.isUpdating = false;
      // Follow-up fetch to ensure sync
      setTimeout(() => this.fetchNowPlaying(), 400);
    }
  }

  public playPause(): Promise<void> {
    return this.control('play-pause');
  }

  public next(): Promise<void> {
    return this.control('next');
  }

  public previous(): Promise<void> {
    return this.control('previous');
  }

  public destroy(): void {
    if (this.pollInterval !== null) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.listeners.clear();
  }
}

export const mediaService = new MediaService();
