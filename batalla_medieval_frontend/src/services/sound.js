const SOUND_STORAGE_KEY = 'bm_sound_settings';

const musicSources = {
  calm_medieval: new URL('../assets/sounds/calm_medieval.mp3', import.meta.url).href,
  war_drums: new URL('../assets/sounds/war_drums.mp3', import.meta.url).href,
};

const sfxSources = {
  click_ui: new URL('../assets/sounds/click_ui.mp3', import.meta.url).href,
  building_complete: new URL('../assets/sounds/building_complete.mp3', import.meta.url).href,
  troop_trained: new URL('../assets/sounds/troop_trained.mp3', import.meta.url).href,
  attack_incoming: new URL('../assets/sounds/attack_incoming.mp3', import.meta.url).href,
  message_received: new URL('../assets/sounds/message_received.mp3', import.meta.url).href,
};

class SoundManager {
  constructor() {
    this.settings = {
      musicEnabled: true,
      sfxEnabled: true,
      musicVolume: 0.6,
      sfxVolume: 0.7,
    };
    this.currentMusic = null;
    this.currentMusicKey = null;
    this.subscribers = new Set();

    this._loadSettings();
  }

  _loadSettings() {
    try {
      const stored = localStorage.getItem(SOUND_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.settings = { ...this.settings, ...parsed };
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

  subscribe(callback) {
    this.subscribers.add(callback);
    callback(this.getSettings());
    return () => this.subscribers.delete(callback);
  }

  getSettings() {
    return { ...this.settings };
  }

  stopMusic() {
    if (this.currentMusic) {
      this.currentMusic.pause();
      this.currentMusic.currentTime = 0;
    }
    this.currentMusic = null;
    this.currentMusicKey = null;
  }

  playMusic(type) {
    if (!musicSources[type]) return;

    if (this.currentMusicKey === type && this.currentMusic) {
      if (this.settings.musicEnabled) {
        this.currentMusic.volume = this.settings.musicVolume;
        this.currentMusic.play().catch(() => {});
      }
      return;
    }

    if (this.currentMusic) {
      this.currentMusic.pause();
    }

    const audio = new Audio(musicSources[type]);
    audio.loop = true;
    audio.volume = this.settings.musicVolume;

    this.currentMusic = audio;
    this.currentMusicKey = type;

    if (this.settings.musicEnabled) {
      audio.play().catch(() => {});
    }
  }

  playSFX(effect) {
    if (!this.settings.sfxEnabled) return;
    const source = sfxSources[effect];
    if (!source) return;

    const audio = new Audio(source);
    audio.volume = this.settings.sfxVolume;
    audio.play().catch(() => {});
  }

  setMusicEnabled(enabled) {
    this.settings.musicEnabled = enabled;
    if (!enabled) {
      if (this.currentMusic) {
        this.currentMusic.pause();
      }
    } else if (this.currentMusicKey) {
      this.playMusic(this.currentMusicKey);
    }
    this._persistSettings();
  }

  setSfxEnabled(enabled) {
    this.settings.sfxEnabled = enabled;
    this._persistSettings();
  }

  setMusicVolume(volume) {
    this.settings.musicVolume = Math.max(0, Math.min(1, volume));
    if (this.currentMusic) {
      this.currentMusic.volume = this.settings.musicVolume;
    }
    this._persistSettings();
  }

  setSfxVolume(volume) {
    this.settings.sfxVolume = Math.max(0, Math.min(1, volume));
    this._persistSettings();
  }
}

const soundManager = new SoundManager();

export default soundManager;
