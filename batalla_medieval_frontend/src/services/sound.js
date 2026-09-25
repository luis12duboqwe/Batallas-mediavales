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

const normalizeVolume = (value, fallback) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(0, Math.min(1, numeric));
};

const normalizeToggle = (value, fallback) => (
  typeof value === 'boolean' ? value : fallback
);

export class SoundManager {
  constructor() {
    this.settings = {
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
    this.lifecycleGeneration = 0;
    this.audioTransition = Promise.resolve();
    this.activeMusicVoices = new Set();
    this.activeSfxVoices = new Set();
    this.subscribers = new Set();

    this._loadSettings();
  }

  _loadSettings() {
    try {
      if (typeof localStorage === 'undefined') return;
      const stored = localStorage.getItem(SOUND_STORAGE_KEY);
      if (!stored) return;
      const parsed = JSON.parse(stored);
      this.settings = {
        ...this.settings,
        musicEnabled: normalizeToggle(parsed.musicEnabled, this.settings.musicEnabled),
        sfxEnabled: normalizeToggle(parsed.sfxEnabled, this.settings.sfxEnabled),
        musicVolume: normalizeVolume(parsed.musicVolume, this.settings.musicVolume),
        sfxVolume: normalizeVolume(parsed.sfxVolume, this.settings.sfxVolume),
      };
    } catch (error) {
      console.warn('Failed to load sound settings', error);
    }
  }

  _persistSettings() {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(SOUND_STORAGE_KEY, JSON.stringify(this.settings));
      }
    } catch (error) {
      console.warn('Failed to save sound settings', error);
    }
    this._notify();
  }

  _notify() {
    const snapshot = this.getSettings();
    this.subscribers.forEach((callback) => callback(snapshot));
  }

  _queueAudioTransition(task) {
    const run = this.audioTransition.catch(() => {}).then(task);
    this.audioTransition = run.catch(() => {});
    return run;
  }

  _setGain(node, value) {
    if (!node?.gain) return;
    const now = this.audioContext?.currentTime || 0;
    try { node.gain.cancelScheduledValues?.(now); } catch { /* noop */ }
    if (typeof node.gain.setValueAtTime === 'function') node.gain.setValueAtTime(value, now);
    else node.gain.value = value;
  }

  _syncMasterGains() {
    this._setGain(
      this.musicGain,
      this.unlocked && this.settings.musicEnabled ? this.settings.musicVolume : 0,
    );
    this._setGain(
      this.sfxGain,
      this.unlocked && this.settings.sfxEnabled ? this.settings.sfxVolume : 0,
    );
  }

  _ensureContext() {
    if (this.audioContext || typeof window === 'undefined') return this.audioContext;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;

    const context = new AudioContextClass();
    this.audioContext = context;
    this.musicGain = context.createGain();
    this.sfxGain = context.createGain();
    this.musicGain.connect(context.destination);
    this.sfxGain.connect(context.destination);
    this._syncMasterGains();
    return context;
  }

  unlock() {
    const generation = this.lifecycleGeneration;
    const context = this._ensureContext();
    if (!context) return Promise.resolve(false);

    return this._queueAudioTransition(async () => {
      if (generation !== this.lifecycleGeneration) return false;
      try {
        if (context.state === 'suspended') await context.resume();
        if (generation !== this.lifecycleGeneration) {
          this._syncMasterGains();
          return false;
        }

        this.unlocked = context.state === 'running';
        this._syncMasterGains();
        if (
          this.unlocked
          && this.settings.musicEnabled
          && this.currentMusicKey
          && !this.musicTimer
        ) {
          this._startMusicLoop();
        }
        return this.unlocked;
      } catch {
        return false;
      }
    });
  }

  _playTone({ frequency, duration, gain, wave = 'sine', delay = 0 }, destination, voices) {
    const context = this.audioContext;
    if (!context || !destination || context.state !== 'running') return;

    const oscillator = context.createOscillator();
    const envelope = context.createGain();
    const start = context.currentTime + delay;
    const end = start + duration;
    const voice = { oscillator, envelope };
    let cleaned = false;

    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      voices?.delete(voice);
      try { oscillator.disconnect(); } catch { /* noop */ }
      try { envelope.disconnect(); } catch { /* noop */ }
    };

    voices?.add(voice);
    oscillator.type = wave;
    oscillator.frequency.setValueAtTime(frequency, start);
    envelope.gain.setValueAtTime(0.0001, start);
    envelope.gain.exponentialRampToValueAtTime(Math.max(gain, 0.0002), start + Math.min(0.025, duration / 3));
    envelope.gain.exponentialRampToValueAtTime(0.0001, end);
    oscillator.connect(envelope);
    envelope.connect(destination);
    oscillator.addEventListener('ended', cleanup, { once: true });

    try {
      oscillator.start(start);
      oscillator.stop(end + 0.02);
    } catch {
      cleanup();
    }
  }

  _stopVoices(voices) {
    const now = this.audioContext?.currentTime || 0;
    for (const voice of [...voices]) {
      try { voice.oscillator.stop(now); } catch { /* already stopped */ }
      try { voice.oscillator.disconnect(); } catch { /* noop */ }
      try { voice.envelope.disconnect(); } catch { /* noop */ }
    }
    voices.clear();
  }

  _stopMusicLoop() {
    if (this.musicTimer) clearInterval(this.musicTimer);
    this.musicTimer = null;
    this._stopVoices(this.activeMusicVoices);
  }

  _startMusicLoop() {
    this._stopMusicLoop();
    if (!this.unlocked || !this.settings.musicEnabled || !this.currentMusicKey) return;
    const pattern = MUSIC_PATTERNS[this.currentMusicKey];
    if (!pattern) return;

    this.musicStep = 0;
    this._syncMasterGains();
    const playStep = () => {
      if (!this.settings.musicEnabled || !this.currentMusicKey || !this.unlocked) return;
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
        this.activeMusicVoices,
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
    this._setGain(this.musicGain, 0);
    this._stopMusicLoop();
    this.currentMusicKey = null;
    this.musicStep = 0;
  }

  deactivate() {
    // Invalidate pending unlocks synchronously so callbacks scheduled before
    // logout cannot emit audio while the serialized suspension is waiting.
    this.lifecycleGeneration += 1;
    this.unlocked = false;
    this._syncMasterGains();
    this.stopMusic();
    this._setGain(this.sfxGain, 0);
    this._stopVoices(this.activeSfxVoices);

    const context = this.audioContext;
    return this._queueAudioTransition(async () => {
      if (context?.state === 'running') {
        try { await context.suspend(); } catch { /* best-effort resource release */ }
      }
      this._syncMasterGains();
    });
  }

  playMusic(type) {
    if (!MUSIC_PATTERNS[type]) return;
    const changed = this.currentMusicKey !== type;
    if (changed) this._stopMusicLoop();
    this.currentMusicKey = type;
    if (!this.settings.musicEnabled || !this.unlocked) return;
    if (changed || !this.musicTimer) this._startMusicLoop();
  }

  playSFX(effect) {
    if (!this.settings.sfxEnabled) return;
    const pattern = SFX_PATTERNS[effect];
    if (!pattern) return;

    void this.unlock().then((ready) => {
      if (!ready || !this.settings.sfxEnabled) return;
      pattern.forEach((tone) => this._playTone(tone, this.sfxGain, this.activeSfxVoices));
    });
  }

  setMusicEnabled(enabled) {
    this.settings.musicEnabled = Boolean(enabled);
    if (!this.settings.musicEnabled) {
      this._setGain(this.musicGain, 0);
      this._stopMusicLoop();
    } else {
      void this.unlock();
    }
    this._syncMasterGains();
    this._persistSettings();
  }

  setSfxEnabled(enabled) {
    this.settings.sfxEnabled = Boolean(enabled);
    if (!this.settings.sfxEnabled) this._stopVoices(this.activeSfxVoices);
    this._syncMasterGains();
    this._persistSettings();
  }

  setMusicVolume(volume) {
    this.settings.musicVolume = normalizeVolume(volume, this.settings.musicVolume);
    this._syncMasterGains();
    this._persistSettings();
  }

  setSfxVolume(volume) {
    this.settings.sfxVolume = normalizeVolume(volume, this.settings.sfxVolume);
    this._syncMasterGains();
    this._persistSettings();
  }
}

const soundManager = new SoundManager();

export default soundManager;
