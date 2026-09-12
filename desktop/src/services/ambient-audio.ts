// High-Fidelity Ambient Soundscape Engine
// Seamless playback of real stereo field recordings (Ocean Surf, Heavy Rain, Cozy Hearth) and Spotify integration.

import { mediaService } from './media-service';

export type SoundscapeType = 'off' | 'rain' | 'ocean' | 'fireplace' | 'spotify';

export interface SoundscapeInfo {
  type: SoundscapeType;
  title: string;
  subtitle: string;
  isPlaying: boolean;
}

const SOUNDSCAPE_DETAILS: Record<SoundscapeType, { title: string; subtitle: string; file?: string }> = {
  off: {
    title: 'Silent',
    subtitle: 'Ambient audio disengaged',
  },
  ocean: {
    title: 'Pacific Ocean Waves',
    subtitle: 'High-definition stereo tidal swell',
    file: '/audio/ocean.mp3',
  },
  rain: {
    title: 'Gentle Rainstorm',
    subtitle: 'Atmospheric rain on glass',
    file: '/audio/rain.mp3',
  },
  fireplace: {
    title: 'Crackling Hearth',
    subtitle: 'Warm wood-burning fire ambience',
    file: '/audio/fireplace.mp3',
  },
  spotify: {
    title: 'Spotify Audio Sink',
    subtitle: 'Streaming host playback',
  },
};

class AmbientAudioEngine {
  private _currentType: SoundscapeType = 'off';
  private _volume = 0.65;
  private _audioEl: HTMLAudioElement | null = null;
  private _listeners: Set<() => void> = new Set();

  get currentType(): SoundscapeType {
    return this._currentType;
  }

  get volume(): number {
    return this._volume;
  }

  get isPlaying(): boolean {
    return this._currentType !== 'off';
  }

  get currentInfo(): SoundscapeInfo {
    const details = SOUNDSCAPE_DETAILS[this._currentType] || SOUNDSCAPE_DETAILS.off;
    return {
      type: this._currentType,
      title: details.title,
      subtitle: details.subtitle,
      isPlaying: this.isPlaying,
    };
  }

  subscribe(listener: () => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  private _notify() {
    this._listeners.forEach((l) => {
      try {
        l();
      } catch (e) {
        console.error('[AmbientAudio] Listener error:', e);
      }
    });
  }

  private _getOrCreateAudio(): HTMLAudioElement {
    if (!this._audioEl) {
      this._audioEl = new Audio();
      this._audioEl.loop = true;
      this._audioEl.preload = 'auto';
      this._audioEl.volume = this._volume;
    }
    return this._audioEl;
  }

  setVolume(vol: number) {
    this._volume = Math.max(0, Math.min(1, vol));
    if (this._audioEl) {
      this._audioEl.volume = this._volume;
    }
    this._notify();
  }

  async setSoundscape(type: SoundscapeType) {
    if (this._currentType === type) return;

    // 1. If currently playing a nature file, pause it
    if (this._audioEl) {
      this._audioEl.pause();
    }

    // 2. If leaving Spotify, pause Spotify playback
    if (this._currentType === 'spotify') {
      try {
        await mediaService.control('pause');
      } catch {}
    }

    this._currentType = type;

    if (type === 'off') {
      this._notify();
      return;
    }

    if (type === 'spotify') {
      try {
        await mediaService.control('play');
      } catch {}
      this._notify();
      return;
    }

    // 3. Play selected real nature loop
    const details = SOUNDSCAPE_DETAILS[type];
    if (details?.file) {
      const audio = this._getOrCreateAudio();
      audio.src = details.file;
      audio.volume = this._volume;
      try {
        await audio.play();
      } catch (err) {
        console.warn('[AmbientAudio] Audio autoplay blocked or failed:', err);
      }
    }

    this._notify();
  }

  stopInternalNodes() {
    if (this._audioEl) {
      this._audioEl.pause();
    }
  }
}

export const ambientAudio = new AmbientAudioEngine();
