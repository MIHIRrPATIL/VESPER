// Procedural Ambient Soundscape Engine using Web Audio API
// Infinite, seamless, zero-network generation of Rain, Ocean Tides, Fireplace, and Spotify integration.

import { mediaService } from './media-service';

export type SoundscapeType = 'off' | 'rain' | 'ocean' | 'fireplace' | 'spotify';

class AmbientAudioEngine {
  private _ctx: AudioContext | null = null;
  private _masterGain: GainNode | null = null;
  private _currentType: SoundscapeType = 'off';
  private _volume = 0.45;
  private _activeNodes: { stop: () => void }[] = [];
  private _listeners: Set<() => void> = new Set();

  get currentType(): SoundscapeType {
    return this._currentType;
  }

  get volume(): number {
    return this._volume;
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

  private _initContext() {
    if (!this._ctx) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      this._ctx = new AudioCtx();
      this._masterGain = this._ctx.createGain();
      this._masterGain.gain.setValueAtTime(this._volume, this._ctx.currentTime);
      this._masterGain.connect(this._ctx.destination);
    }
    if (this._ctx.state === 'suspended') {
      this._ctx.resume();
    }
  }

  setVolume(vol: number) {
    this._volume = Math.max(0, Math.min(1, vol));
    if (this._masterGain && this._ctx) {
      this._masterGain.gain.setValueAtTime(this._volume, this._ctx.currentTime);
    }
    this._notify();
  }

  async setSoundscape(type: SoundscapeType) {
    if (this._currentType === type) return;

    // Stop current generators
    this.stopInternalNodes();

    // If leaving Spotify, pause Spotify playback
    if (this._currentType === 'spotify') {
      try {
        await mediaService.control('pause');
      } catch {
        // Fallback
      }
    }

    this._currentType = type;

    if (type === 'off') {
      this._notify();
      return;
    }

    if (type === 'spotify') {
      try {
        await mediaService.control('play');
      } catch {
        // Fallback
      }
      this._notify();
      return;
    }

    // Initialize Web Audio context on user gesture
    this._initContext();
    if (!this._ctx || !this._masterGain) return;

    if (type === 'rain') {
      this._startRain();
    } else if (type === 'ocean') {
      this._startOcean();
    } else if (type === 'fireplace') {
      this._startFireplace();
    }

    this._notify();
  }

  stopInternalNodes() {
    this._activeNodes.forEach((node) => {
      try {
        node.stop();
      } catch {
        // Node already stopped
      }
    });
    this._activeNodes = [];
  }

  // ── 1. Rain Soundscape Generator ───────────────────────────────────────────
  private _startRain() {
    if (!this._ctx || !this._masterGain) return;
    const ctx = this._ctx;

    // Continuous pink noise buffer (4 seconds looped)
    const bufferSize = ctx.sampleRate * 4;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;

    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      b3 = 0.86650 * b3 + white * 0.3104856;
      b4 = 0.55000 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.0168980;
      data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.08;
      b6 = white * 0.115926;
    }

    const noiseSource = ctx.createBufferSource();
    noiseSource.buffer = buffer;
    noiseSource.loop = true;

    // Filter to soft gentle rain spectrum (lowpass 1100Hz)
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(1100, ctx.currentTime);

    // Highpass to remove heavy sub-bass drone
    const highpass = ctx.createBiquadFilter();
    highpass.type = 'highpass';
    highpass.frequency.setValueAtTime(200, ctx.currentTime);

    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.7, ctx.currentTime);

    noiseSource.connect(filter);
    filter.connect(highpass);
    highpass.connect(gain);
    gain.connect(this._masterGain);

    noiseSource.start();
    this._activeNodes.push({
      stop: () => {
        noiseSource.stop();
        noiseSource.disconnect();
      },
    });
  }

  // ── 2. Ocean Tides & Shore Generator ───────────────────────────────────────
  private _startOcean() {
    if (!this._ctx || !this._masterGain) return;
    const ctx = this._ctx;

    // Brown noise buffer for deep rolling water body
    const bufferSize = ctx.sampleRate * 6;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    let lastOut = 0.0;

    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      data[i] = (lastOut + 0.02 * white) / 1.02;
      lastOut = data[i];
      data[i] *= 1.2;
    }

    const noiseSource = ctx.createBufferSource();
    noiseSource.buffer = buffer;
    noiseSource.loop = true;

    // Sweeping lowpass filter simulating wave cresting and receding
    const sweepFilter = ctx.createBiquadFilter();
    sweepFilter.type = 'lowpass';
    sweepFilter.frequency.setValueAtTime(250, ctx.currentTime);

    // Dynamic wave gain
    const waveGain = ctx.createGain();
    waveGain.gain.setValueAtTime(0.3, ctx.currentTime);

    // LFO Oscillator controlling the 7-second tidal rhythm
    const lfo = ctx.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.setValueAtTime(0.14, ctx.currentTime); // ~7.1s wave cycle

    const lfoFilterGain = ctx.createGain();
    lfoFilterGain.gain.setValueAtTime(450, ctx.currentTime); // sweeps between ~200Hz and ~700Hz

    const lfoGainMod = ctx.createGain();
    lfoGainMod.gain.setValueAtTime(0.35, ctx.currentTime);

    lfo.connect(lfoFilterGain);
    lfoFilterGain.connect(sweepFilter.frequency);

    lfo.connect(lfoGainMod);
    lfoGainMod.connect(waveGain.gain);

    noiseSource.connect(sweepFilter);
    sweepFilter.connect(waveGain);
    waveGain.connect(this._masterGain);

    noiseSource.start();
    lfo.start();

    this._activeNodes.push({
      stop: () => {
        noiseSource.stop();
        lfo.stop();
        noiseSource.disconnect();
        lfo.disconnect();
      },
    });
  }

  // ── 3. Fireplace Hearth Generator ──────────────────────────────────────────
  private _startFireplace() {
    if (!this._ctx || !this._masterGain) return;
    const ctx = this._ctx;

    // 1. Warm low rumble (deep thermal fire roar)
    const rumbleSize = ctx.sampleRate * 4;
    const rumbleBuffer = ctx.createBuffer(1, rumbleSize, ctx.sampleRate);
    const rumbleData = rumbleBuffer.getChannelData(0);
    let lastOut = 0.0;
    for (let i = 0; i < rumbleSize; i++) {
      const white = Math.random() * 2 - 1;
      rumbleData[i] = (lastOut + 0.015 * white) / 1.015;
      lastOut = rumbleData[i];
      rumbleData[i] *= 0.6;
    }

    const rumbleSource = ctx.createBufferSource();
    rumbleSource.buffer = rumbleBuffer;
    rumbleSource.loop = true;

    const rumbleFilter = ctx.createBiquadFilter();
    rumbleFilter.type = 'lowpass';
    rumbleFilter.frequency.setValueAtTime(140, ctx.currentTime);

    const rumbleGain = ctx.createGain();
    rumbleGain.gain.setValueAtTime(0.4, ctx.currentTime);

    rumbleSource.connect(rumbleFilter);
    rumbleFilter.connect(rumbleGain);
    rumbleGain.connect(this._masterGain);
    rumbleSource.start();

    // 2. Intermittent pops & crackles scheduler
    let isCancelled = false;
    const scheduleCrackle = () => {
      if (isCancelled || !this._ctx || !this._masterGain) return;

      const clickBuffer = this._ctx.createBuffer(1, Math.floor(this._ctx.sampleRate * 0.04), this._ctx.sampleRate);
      const clickData = clickBuffer.getChannelData(0);
      for (let i = 0; i < clickData.length; i++) {
        clickData[i] = (Math.random() * 2 - 1) * Math.exp(-i / (this._ctx.sampleRate * 0.008));
      }

      const clickSource = this._ctx.createBufferSource();
      clickSource.buffer = clickBuffer;

      const clickFilter = this._ctx.createBiquadFilter();
      clickFilter.type = 'bandpass';
      clickFilter.frequency.setValueAtTime(1500 + Math.random() * 2500, this._ctx.currentTime);
      clickFilter.Q.setValueAtTime(3.0, this._ctx.currentTime);

      const clickGain = this._ctx.createGain();
      clickGain.gain.setValueAtTime(0.3 + Math.random() * 0.4, this._ctx.currentTime);

      clickSource.connect(clickFilter);
      clickFilter.connect(clickGain);
      clickGain.connect(this._masterGain);

      clickSource.start();

      // Next crackle randomly between 40ms and 350ms
      const delay = 40 + Math.random() * 310;
      setTimeout(scheduleCrackle, delay);
    };

    scheduleCrackle();

    this._activeNodes.push({
      stop: () => {
        isCancelled = true;
        rumbleSource.stop();
        rumbleSource.disconnect();
      },
    });
  }
}

export const ambientAudio = new AmbientAudioEngine();
