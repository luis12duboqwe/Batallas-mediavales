const SOUND_STORAGE_KEY = 'bm_sound_settings';

const DEFAULT_SETTINGS = Object.freeze({
  musicEnabled: true,
  sfxEnabled: true,
  musicVolume: 0.6,
  sfxVolume: 0.7,
});

const MUSIC_TYPES = new Set(['calm_medieval', 'war_drums']);
const SFX_TYPES = new Set([
  'click_ui',
  'building_complete',
  'troop_trained',
  'attack_incoming',
  'message_received',
]);

const clampVolume = (value, fallback) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(1, parsed));
};

const normalizeSettings = (value = {}) => ({
  musicEnabled: typeof value.musicEnabled === 'boolean' ? value.musicEnabled : DEFAULT_SETTINGS.musicEnabled,
  sfxEnabled: typeof value.sfxEnabled === 'boolean' ? value.sfxEnabled : DEFAULT_SETTINGS.sfxEnabled,
  musicVolume: clampVolume(value.musicVolume, DEFAULT_SETTINGS.musicVolume),
  sfxVolume: clampVolume(value.sfxVolume, DEFAULT_SETTINGS.sfxVolume),
});

class SoundManager {
  constructor() {
    this.settings = { ...DEFAULT_SETTINGS };
    this.context = null;
    this.musicBus = null;
    this.sfxBus = null;
    this.requestedMusicKey = null;
    this.playingMusicKey = null;
    this.musicTimer = null;
    this.musicNodes = new Set();
    this.subscribers = new Set();
    this.unlockInFlight = null;

    this._loadSettings();
    this._installActivationGate();
  }

  _loadSettings() {
    try {
      const stored = localStorage.getItem(SOUND_STORAGE_KEY);
      if (stored) this.settings = normalizeSettings(JSON.parse(stored));
    } catch (error) {
      console.warn('Failed to load sound settings', error);
      this.settings = { ...DEFAULT_SETTINGS };
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

  _installActivationGate() {
    if (typeof document === 'undefined') return;
    const activate = () => { void this.unlock(); };
    // Keep these listeners for the life of the singleton. Browsers may suspend
    // an AudioContext after backgrounding; the next real gesture must be able
    // to resume it without creating a second context.
    document.addEventListener('pointerdown', activate, true);
    document.addEventListener('keydown', activate, true);
  }

  _ensureContext() {
    if (this.context?.state === 'closed') {
      this.context = null;
      this.musicBus = null;
      this.sfxBus = null;
      this.playingMusicKey = null;
      this.musicNodes.clear();
    }
    if (this.context) return true;
    if (typeof window === 'undefined') return false;

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return false;

    this.context = new AudioContextClass();
    this.musicBus = this.context.createGain();
    this.sfxBus = this.context.createGain();
    this.musicBus.gain.value = this.settings.musicVolume;
    this.sfxBus.gain.value = this.settings.sfxVolume;
    this.musicBus.connect(this.context.destination);
    this.sfxBus.connect(this.context.destination);
    return true;
  }

  async unlock() {
    if (!this._ensureContext()) return false;
    if (this.context.state === 'running') {
      this._startRequestedMusic();
      return true;
    }
    if (this.unlockInFlight) return this.unlockInFlight;

    this.unlockInFlight = this.context.resume()
      .then(() => {
        const unlocked = this.context?.state === 'running';
        if (unlocked) this._startRequestedMusic();
        return unlocked;
      })
      .catch(() => false)
      .finally(() => {
        this.unlockInFlight = null;
      });
    return this.unlockInFlight;
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    callback(this.getSettings());
    return () => this.subscribers.delete(callback);
  }

  getSettings() {
    return { ...this.settings };
  }

  _setBusVolume(bus, value) {
    if (!bus || !this.context) return;
    bus.gain.setTargetAtTime(value, this.context.currentTime, 0.015);
  }

  _trackMusicNode(node, cleanup) {
    this.musicNodes.add(node);
    node.addEventListener('ended', () => {
      this.musicNodes.delete(node);
      cleanup?.();
    }, { once: true });
  }

  _tone({ frequency, endFrequency = frequency, type = 'sine', offset = 0, duration = 0.12, level = 0.08 }, bus, trackAsMusic = false) {
    if (!this.context || !bus || this.context.state !== 'running') return;
    const now = this.context.currentTime + offset;
    const oscillator = this.context.createOscillator();
    const gain = this.context.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(Math.max(1, frequency), now);
    oscillator.frequency.exponentialRampToValueAtTime(Math.max(1, endFrequency), now + duration);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, level), now + Math.min(0.04, duration / 4));
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    oscillator.connect(gain);
    gain.connect(bus);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.02);

    const cleanup = () => {
      oscillator.disconnect();
      gain.disconnect();
    };
    if (trackAsMusic) this._trackMusicNode(oscillator, cleanup);
    else oscillator.addEventListener('ended', cleanup, { once: true });
  }

  _stopMusicPlayback() {
    if (this.musicTimer) clearTimeout(this.musicTimer);
    this.musicTimer = null;
    this.musicNodes.forEach((node) => {
      try { node.stop(); } catch { /* Already stopped. */ }
    });
    this.musicNodes.clear();
    this.playingMusicKey = null;
  }

  stopMusic() {
    this.requestedMusicKey = null;
    this._stopMusicPlayback();
  }

  _scheduleCalmMusic() {
    if (this.playingMusicKey !== 'calm_medieval' || !this.settings.musicEnabled) return;
    [110, 164.81, 220].forEach((frequency, index) => {
      this._tone({ frequency, type: 'triangle', offset: index * 0.08, duration: 2.8, level: 0.025 }, this.musicBus, true);
    });
    this.musicTimer = setTimeout(() => this._scheduleCalmMusic(), 3000);
  }

  _scheduleWarMusic() {
    if (this.playingMusicKey !== 'war_drums' || !this.settings.musicEnabled) return;
    this._tone({ frequency: 92, endFrequency: 48, type: 'sine', duration: 0.24, level: 0.13 }, this.musicBus, true);
    this._tone({ frequency: 76, endFrequency: 42, type: 'sine', offset: 0.48, duration: 0.2, level: 0.1 }, this.musicBus, true);
    this._tone({ frequency: 55, type: 'triangle', duration: 1.15, level: 0.018 }, this.musicBus, true);
    this.musicTimer = setTimeout(() => this._scheduleWarMusic(), 1200);
  }

  _startRequestedMusic() {
    if (!this.context || this.context.state !== 'running' || !this.settings.musicEnabled || !this.requestedMusicKey) return;
    if (this.playingMusicKey === this.requestedMusicKey) return;

    this._stopMusicPlayback();
    this.playingMusicKey = this.requestedMusicKey;
    if (this.playingMusicKey === 'war_drums') this._scheduleWarMusic();
    else this._scheduleCalmMusic();
  }

  playMusic(type) {
    if (!MUSIC_TYPES.has(type)) return;
    this.requestedMusicKey = type;
    if (this.context?.state === 'running') this._startRequestedMusic();
  }

  playSFX(effect) {
    if (!this.settings.sfxEnabled || !SFX_TYPES.has(effect) || this.context?.state !== 'running') return;

    switch (effect) {
      case 'click_ui':
        this._tone({ frequency: 520, endFrequency: 720, type: 'square', duration: 0.045, level: 0.035 }, this.sfxBus);
        break;
      case 'building_complete':
        this._tone({ frequency: 392, endFrequency: 440, type: 'triangle', duration: 0.18, level: 0.08 }, this.sfxBus);
        this._tone({ frequency: 523.25, endFrequency: 659.25, type: 'triangle', offset: 0.12, duration: 0.24, level: 0.07 }, this.sfxBus);
        break;
      case 'troop_trained':
        this._tone({ frequency: 220, endFrequency: 330, type: 'sawtooth', duration: 0.18, level: 0.055 }, this.sfxBus);
        this._tone({ frequency: 330, endFrequency: 440, type: 'triangle', offset: 0.1, duration: 0.18, level: 0.045 }, this.sfxBus);
        break;
      case 'attack_incoming':
        this._tone({ frequency: 130, endFrequency: 55, type: 'sawtooth', duration: 0.34, level: 0.11 }, this.sfxBus);
        this._tone({ frequency: 105, endFrequency: 48, type: 'sawtooth', offset: 0.22, duration: 0.32, level: 0.09 }, this.sfxBus);
        break;
      case 'message_received':
        this._tone({ frequency: 659.25, endFrequency: 659.25, type: 'sine', duration: 0.12, level: 0.06 }, this.sfxBus);
        this._tone({ frequency: 880, endFrequency: 880, type: 'sine', offset: 0.1, duration: 0.16, level: 0.05 }, this.sfxBus);
        break;
      default:
        break;
    }
  }

  setMusicEnabled(enabled) {
    this.settings.musicEnabled = Boolean(enabled);
    if (!this.settings.musicEnabled) this._stopMusicPlayback();
    else this._startRequestedMusic();
    this._persistSettings();
  }

  setSfxEnabled(enabled) {
    this.settings.sfxEnabled = Boolean(enabled);
    this._persistSettings();
  }

  setMusicVolume(volume) {
    this.settings.musicVolume = clampVolume(volume, this.settings.musicVolume);
    this._setBusVolume(this.musicBus, this.settings.musicVolume);
    this._persistSettings();
  }

  setSfxVolume(volume) {
    this.settings.sfxVolume = clampVolume(volume, this.settings.sfxVolume);
    this._setBusVolume(this.sfxBus, this.settings.sfxVolume);
    this._persistSettings();
  }
}

const soundManager = new SoundManager();

export default soundManager;
