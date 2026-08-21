import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import soundManager from '../services/sound';

const buttonBase =
  'flex items-center gap-2 px-2 sm:px-3 py-2 rounded border border-yellow-700/50 text-sm transition hover:border-yellow-500 hover:text-yellow-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400';

const SoundToggle = () => {
  const { t } = useTranslation();
  const [settings, setSettings] = useState(soundManager.getSettings());

  useEffect(() => {
    const unsubscribe = soundManager.subscribe(setSettings);
    return unsubscribe;
  }, []);

  const musicLabel = settings.musicEnabled ? t('sound.music_on') : t('sound.music_off');
  const sfxLabel = settings.sfxEnabled ? t('sound.sfx_on') : t('sound.sfx_off');

  return (
    <div className="flex items-center gap-1 sm:gap-2" aria-label={t('sound.controls')}>
      <button
        type="button"
        onClick={() => soundManager.setMusicEnabled(!settings.musicEnabled)}
        className={`${buttonBase} ${settings.musicEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
        aria-label={musicLabel}
        aria-pressed={settings.musicEnabled}
      >
        <span aria-hidden>🎵</span>
        <span className="hidden md:inline">{musicLabel}</span>
      </button>
      <button
        type="button"
        onClick={() => soundManager.setSfxEnabled(!settings.sfxEnabled)}
        className={`${buttonBase} ${settings.sfxEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
        aria-label={sfxLabel}
        aria-pressed={settings.sfxEnabled}
      >
        <span aria-hidden>🔔</span>
        <span className="hidden md:inline">{sfxLabel}</span>
      </button>
    </div>
  );
};

export default SoundToggle;
