const SOUND_STORAGE_KEY = 'bm_sound_settings';

const MUSIC_PATTERNS = {
  calm_medieval: {
    intervalMs: 1800,
    wave: 'triangle',
    notes: [220, 261.63, 329.63, 293.66],
    gain: 0.045,
    duration: 1.25,
  },
  war_drums: {
    intervalMs: 900,
    wave: 'sine',
    notes: [82.41, 82.41, 110, 73.42],
    gain: 0.075,
    duration: 0.38,
  },
};

const SFX_PATTERNS = {
  click_ui: [{ frequency: 560, duration: 0.045, gain: 0.09, wave: 'sine' }],
  building_complete: [
    { frequency: 392, duration: 0.16, gain: 0.11, wave: 'triangle' },
    { frequency: 523.25, duration: 0.22, gain: 0.09, wave: 'triangle', delay: 0.08 },
  ],
  troop_trained: [
    { frequency: 196, duration: 0.09, gain: 0.1, wave: 'square' },
    { frequency: 293.66, duration: 0.12, gain: 0.07, wave: 'triangle', delay: 0.05 },
  ],
  attack_incoming: [
    { frequency: 98, duration: 0.28, gain: 0.13, wave: 'sawtooth' },
    { frequency: 82.41, duration: 0.32, gain: 0.11, wave: 'sawtooth', delay: 0.18 },
  ],
  message_received: [
    { frequency: 659.25, duration: 0.1, gain: 0.08, wave: 'sine' },
    { frequency: 783.99, duration: 0.12, gain: 0.07, wave: 'sine', delay: 0.08 },
  ],
};

const clamp01 = (value) => Math.max(0, Math.min(1, Number(value) || 0));

class SoundManager {
  constructor() {
    this.settings = {
      // Audio is opt-in for new players. Existing persisted preferences remain
      // authoritative, but no AudioContext is created until user interaction.
      musicEnabled: false,
      sfxEnabled: true,
      musicVolume: 0.45,
      sfxVolume: 0.65,
    };
    this.audioContext = null;
    this.musicGain = null;
    this.sfxGain = null;
    this.musicTimer = null;
    this.currentMusicKey = null;
    this.musicStep = 0;
    this.unlocked = false;
    this.subscribers = new Set();

    this._loadSettings();
  }

  _loadSettings() {
    try {
      const stored = localStorage.getItem(SOUND_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.settings = {
          ...this.settings,
          ...parsed,
          musicVolume: clamp01(parsed.musicVolume ?? this.settings.musicVolume),
          sfxVolume: clamp01(parsed.sfxVolume ?? this.settings.sfxVolume),
        };
      }
    } catch (error) {
      console.warn('Failed to load sound settings', error);
    }
  }

  _persistSettings() {
    try {
      localStorage.setItem(SOUND_STORAGE_KEY, JSON.stringify(this.settings));
    } catch (error) {
      console.warn('Failed to save sound settings', error);
    }
    this._notify();
  }

  _notify() {
    const snapshot = this.getSettings();
    this.subscribers.forEach((callback) => callback(snapshot));
  }

  _ensureContext() {
    if (this.audioContext || typeof window === 'undefined') return this.audioContext;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;

    const context = new AudioContextClass();
    this.audioContext = context;
    this.musicGain = context.createGain();
    this.sfxGain = context.createGain();
    this.musicGain.gain.value = this.settings.musicVolume;
    this.sfxGain.gain.value = this.settings.sfxVolume;
    this.musicGain.connect(context.destination);
    this.sfxGain.connect(context.destination);
    return context;
  }

  async unlock() {
    const context = this._ensureContext();
    if (!context) return false;
    try {
      if (context.state === 'suspended') await context.resume();
      this.unlocked = context.state === 'running';
      if (this.unlocked && this.settings.musicEnabled && this.currentMusicKey) {
        this._startMusicLoop();
      }
      return this.unlocked;
    } catch {
      return false;
    }
  }

  _playTone({ frequency, duration, gain, wave = 'sine', delay = 0 }, destination) {
    const context = this.audioContext;
    if (!context || !destination || context.state !== 'running') return;

    const oscillator = context.createOscillator();
    const envelope = context.createGain();
    const start = context.currentTime + delay;
    const end = start + duration;

    oscillator.type = wave;
    oscillator.frequency.setValueAtTime(frequency, start);
    envelope.gain.setValueAtTime(0.0001, start);
    envelope.gain.exponentialRampToValueAtTime(Math.max(gain, 0.0002), start + Math.min(0.025, duration / 3));
    envelope.gain.exponentialRampToValueAtTime(0.0001, end);
    oscillator.connect(envelope);
    envelope.connect(destination);
    oscillator.start(start);
    oscillator.stop(end + 0.02);
  }

  _stopMusicLoop() {
    if (this.musicTimer) clearInterval(this.musicTimer);
    this.musicTimer = null;
    this.musicStep = 0;
  }

  _startMusicLoop() {
    this._stopMusicLoop();
    if (!this.unlocked || !this.settings.musicEnabled || !this.currentMusicKey) return;
    const pattern = MUSIC_PATTERNS[this.currentMusicKey];
    if (!pattern) return;

    const playStep = () => {
      if (!this.settings.musicEnabled || !this.currentMusicKey) return;
      const frequency = pattern.notes[this.musicStep % pattern.notes.length];
      this.musicStep += 1;
      this._playTone(
        {
          frequency,
          duration: pattern.duration,
          gain: pattern.gain,
          wave: pattern.wave,
        },
        this.musicGain,
      );
    };

    playStep();
    this.musicTimer = setInterval(playStep, pattern.intervalMs);
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    callback(this.getSettings());
    return () => this.subscribers.delete(callback);
  }

  getSettings() {
    return { ...this.settings };
  }

  stopMusic() {
    this._stopMusicLoop();
    this.currentMusicKey = null;
  }

  playMusic(type) {
    if (!MUSIC_PATTERNS[type]) return;
    const changed = this.currentMusicKey !== type;
    this.currentMusicKey = type;
    if (!this.settings.musicEnabled || !this.unlocked) return;
    if (changed || !this.musicTimer) this._startMusicLoop();
  }

  playSFX(effect) {
    if (!this.settings.sfxEnabled) return;
    const pattern = SFX_PATTERNS[effect];
    if (!pattern) return;

    this.unlock().then((ready) => {
      if (!ready || !this.settings.sfxEnabled) return;
      pattern.forEach((tone) => this._playTone(tone, this.sfxGain));
    });
  }

  setMusicEnabled(enabled) {
    this.settings.musicEnabled = Boolean(enabled);
    if (!this.settings.musicEnabled) {
      this._stopMusicLoop();
    } else {
      this.unlock().then((ready) => {
        if (ready && this.currentMusicKey) this._startMusicLoop();
      });
    }
    this._persistSettings();
  }

  setSfxEnabled(enabled) {
    this.settings.sfxEnabled = Boolean(enabled);
    this._persistSettings();
  }

  setMusicVolume(volume) {
    this.settings.musicVolume = clamp01(volume);
    if (this.musicGain) this.musicGain.gain.value = this.settings.musicVolume;
    this._persistSettings();
  }

  setSfxVolume(volume) {
    this.settings.sfxVolume = clamp01(volume);
    if (this.sfxGain) this.sfxGain.gain.value = this.settings.sfxVolume;
    this._persistSettings();
  }
}

const soundManager = new SoundManager();

export default soundManager;
