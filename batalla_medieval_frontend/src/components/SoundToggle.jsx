import { useEffect, useState } from 'react';
import soundManager from '../services/sound';

const buttonBase =
  'flex items-center gap-2 px-3 py-2 rounded border border-yellow-700/50 text-sm transition hover:border-yellow-500 hover:text-yellow-200';

const SoundToggle = () => {
  const [settings, setSettings] = useState(soundManager.getSettings());

  useEffect(() => {
    const unsubscribe = soundManager.subscribe(setSettings);
    return unsubscribe;
  }, []);

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => soundManager.setMusicEnabled(!settings.musicEnabled)}
        className={`${buttonBase} ${settings.musicEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
      >
        <span aria-hidden>🎵</span>
        <span>{settings.musicEnabled ? 'Música' : 'Música off'}</span>
      </button>
      <button
        type="button"
        onClick={() => soundManager.setSfxEnabled(!settings.sfxEnabled)}
        className={`${buttonBase} ${settings.sfxEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
      >
        <span aria-hidden>🔔</span>
        <span>{settings.sfxEnabled ? 'SFX' : 'SFX off'}</span>
      </button>
    </div>
  );
};

export default SoundToggle;
