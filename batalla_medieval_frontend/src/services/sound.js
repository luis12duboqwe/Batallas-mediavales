const SOUND_STORAGE_KEY = 'bm_sound_settings';

const MUSIC_PATTERNS = {
  calm_medieval: {
    notes: [220, 261.63, 329.63, 293.66],
    interval: 1600,
    duration: 1.35,
    wave: 'sine',
    level: 0.12,
  },
  war_drums: {
    notes: [110, 146.83, 164.81, 123.47],
    interval: 720,
    duration: 0.55,
    wave: 'triangle',
    level: 0.14,
  },
};

const SFX_PATTERNS = {
  click_ui: [
    { frequency: 330, duration: 0.045, wave: 'sine', level: 0.18 },
    { frequency: 440, duration: 0.055, delay: 0.025, wave: 'sine', level: 0.12 },
  ],
  building_complete: [
    { frequency: 261.63, duration: 0.16, wave: 'triangle', level: 0.22 },
    { frequency: 392, duration: 0.24, delay: 0.09, wave: 'triangle', level: 0.18 },
  ],
  troop_trained: [
    { frequency: 196, duration: 0.09, wave: 'square', level: 0.12 },
    { frequency: 293.66, duration: 0.13, delay: 0.06, wave: 'square', level: 0.1 },
  ],
  attack_incoming: [
    { frequency: 98, duration: 0.34, wave: 'sawtooth', level: 0.2 },
    { frequency: 73.42, duration: 0.42, delay: 0.12, wave: 'triangle', level: 0.18 },
  ],
  message_received: [
    { frequency: 440, duration: 0.1, wave: 'sine', level: 0.16 },
    { frequency: 659.25, duration: 0.16, delay: 0.1, wave: 'sine', level: 0.14 },
  ],
};

const clamp01 = (value) => Math.max(0, Math.min(1, Number(value)));

class SoundManager {
  constructor() {
    this.settings = {
      musicEnabled: true,
      sfxEnabled: true,
      musicVolume: 0.6,
      sfxVolume: 0.7,
    };
    this.context = null;
    this.musicGain = null;
    this.sfxGain = null;
    this.currentMusicKey = null;
    this.musicTimer = null;
    this.musicStep = 0;
    this.unlocked = false;
    this.subscribers = new Set();
    this._loadSettings();
  }

  _loadSettings() {
    try {
      const stored = localStorage.getItem(SOUND_STORAGE_KEY);
      if (!stored) return;
      const parsed = JSON.parse(stored);
      this.settings = {
        ...this.settings,
        ...parsed,
        musicVolume: clamp01(parsed.musicVolume ?? this.settings.musicVolume),
        sfxVolume: clamp01(parsed.sfxVolume ?? this.settings.sfxVolume),
      };
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

  _updateMasterGains() {
    if (this.musicGain) this.musicGain.gain.value = this.settings.musicVolume;
    if (this.sfxGain) this.sfxGain.gain.value = this.settings.sfxVolume;
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    callback(this.getSettings());
    return () => this.subscribers.delete(callback);
  }

  getSettings() {
    return { ...this.settings, unlocked: this.unlocked };
  }

  isUnlocked() {
    return this.unlocked;
  }

  async unlock() {
    if (typeof window === 'undefined') return false;
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) return false;

    if (!this.context) {
      this.context = new AudioContextCtor();
      this.musicGain = this.context.createGain();
      this.sfxGain = this.context.createGain();
      this.musicGain.connect(this.context.destination);
      this.sfxGain.connect(this.context.destination);
      this._updateMasterGains();
    }

    if (this.context.state === 'suspended') {
      try {
        await this.context.resume();
      } catch (error) {
        console.warn('Unable to resume audio context', error);
      }
    }

    const wasUnlocked = this.unlocked;
    this.unlocked = this.context.state === 'running';
    if (this.unlocked && !wasUnlocked && this.settings.musicEnabled && this.currentMusicKey) {
      this._startMusicPattern();
    }
    if (this.unlocked !== wasUnlocked) this._notify();
    return this.unlocked;
  }

  _scheduleTone({ frequency, duration, delay = 0, wave = 'sine', level = 0.1 }, destination) {
    if (!this.context || !destination || this.context.state !== 'running') return;
    const start = this.context.currentTime + delay;
    const oscillator = this.context.createOscillator();
    const envelope = this.context.createGain();
    oscillator.type = wave;
    oscillator.frequency.setValueAtTime(frequency, start);
    envelope.gain.setValueAtTime(0.0001, start);
    envelope.gain.exponentialRampToValueAtTime(Math.max(0.0001, level), start + 0.02);
    envelope.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    oscillator.connect(envelope);
    envelope.connect(destination);
    oscillator.start(start);
    oscillator.stop(start + duration + 0.03);
  }

  _stopMusicTimer() {
    if (this.musicTimer) clearInterval(this.musicTimer);
    this.musicTimer = null;
  }

  _startMusicPattern() {
    this._stopMusicTimer();
    const pattern = MUSIC_PATTERNS[this.currentMusicKey];
    if (!pattern || !this.unlocked || !this.settings.musicEnabled || !this.musicGain) return;

    const playStep = () => {
      if (!this.settings.musicEnabled || !this.unlocked) return;
      const frequency = pattern.notes[this.musicStep % pattern.notes.length];
      this.musicStep += 1;
      this._scheduleTone({
        frequency,
        duration: pattern.duration,
        wave: pattern.wave,
        level: pattern.level,
      }, this.musicGain);
      this._scheduleTone({
        frequency: frequency * 1.5,
        duration: pattern.duration * 0.8,
        delay: 0.08,
        wave: 'sine',
        level: pattern.level * 0.45,
      }, this.musicGain);
    };

    playStep();
    this.musicTimer = window.setInterval(playStep, pattern.interval);
  }

  stopMusic() {
    this._stopMusicTimer();
    this.currentMusicKey = null;
    this.musicStep = 0;
  }

  playMusic(type) {
    if (!MUSIC_PATTERNS[type]) return;
    const changed = this.currentMusicKey !== type;
    this.currentMusicKey = type;
    if (changed) this.musicStep = 0;
    if (this.unlocked && this.settings.musicEnabled && (changed || !this.musicTimer)) {
      this._startMusicPattern();
    }
  }

  playSFX(effect) {
    if (!this.unlocked || !this.settings.sfxEnabled || !this.sfxGain) return;
    const pattern = SFX_PATTERNS[effect];
    if (!pattern) return;
    pattern.forEach((tone) => this._scheduleTone(tone, this.sfxGain));
  }

  setMusicEnabled(enabled) {
    this.settings.musicEnabled = Boolean(enabled);
    if (!this.settings.musicEnabled) this._stopMusicTimer();
    else if (this.unlocked && this.currentMusicKey) this._startMusicPattern();
    this._persistSettings();
  }

  setSfxEnabled(enabled) {
    this.settings.sfxEnabled = Boolean(enabled);
    this._persistSettings();
  }

  setMusicVolume(volume) {
    this.settings.musicVolume = clamp01(volume);
    this._updateMasterGains();
    this._persistSettings();
  }

  setSfxVolume(volume) {
    this.settings.sfxVolume = clamp01(volume);
    this._updateMasterGains();
    this._persistSettings();
  }
}

const soundManager = new SoundManager();

export default soundManager;
