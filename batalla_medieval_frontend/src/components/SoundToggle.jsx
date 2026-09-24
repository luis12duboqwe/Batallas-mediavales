import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import soundManager from '../services/sound';
import GameIcon from './GameIcon';

const buttonBase = 'flex items-center gap-2 px-2 sm:px-3 py-2 rounded border border-yellow-700/50 text-sm transition hover:border-yellow-500 hover:text-yellow-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400';

const SoundToggle = () => {
  const { t } = useTranslation();
  const [settings, setSettings] = useState(soundManager.getSettings());

  useEffect(() => soundManager.subscribe(setSettings), []);

  const musicLabel = settings.musicEnabled ? t('sound.music_on') : t('sound.music_off');
  const sfxLabel = settings.sfxEnabled ? t('sound.sfx_on') : t('sound.sfx_off');

  return (
    <div className="relative flex items-center gap-1 sm:gap-2" aria-label={t('sound.controls')}>
      <button
        type="button"
        onClick={() => soundManager.setMusicEnabled(!settings.musicEnabled)}
        className={`${buttonBase} ${settings.musicEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
        aria-label={musicLabel}
        aria-pressed={settings.musicEnabled}
        data-testid="music-toggle"
      >
        <GameIcon name="music" size={18} />
        <span className="hidden md:inline">{musicLabel}</span>
      </button>
      <button
        type="button"
        onClick={() => soundManager.setSfxEnabled(!settings.sfxEnabled)}
        className={`${buttonBase} ${settings.sfxEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
        aria-label={sfxLabel}
        aria-pressed={settings.sfxEnabled}
        data-testid="sfx-toggle"
      >
        <GameIcon name="bell" size={18} />
        <span className="hidden md:inline">{sfxLabel}</span>
      </button>
      <details className="relative" data-testid="sound-settings">
        <summary className={`${buttonBase} cursor-pointer list-none [&::-webkit-details-marker]:hidden`} aria-label={t('sound.volume_settings')}>
          <span aria-hidden="true">Vol.</span>
          <span className="sr-only">{t('sound.volume_settings')}</span>
        </summary>
        <div className="absolute right-0 top-full z-50 mt-2 w-64 space-y-4 rounded-lg border border-yellow-800/60 bg-gray-950 p-4 shadow-2xl">
          <label htmlFor="music-volume" className="block text-xs text-gray-200">
            <span className="mb-1 flex justify-between gap-3"><span>{t('sound.music_volume')}</span><span>{Math.round(settings.musicVolume * 100)}%</span></span>
            <input
              id="music-volume"
              data-testid="music-volume"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={settings.musicVolume}
              onChange={(event) => soundManager.setMusicVolume(event.target.value)}
              className="w-full accent-yellow-500"
            />
          </label>
          <label htmlFor="sfx-volume" className="block text-xs text-gray-200">
            <span className="mb-1 flex justify-between gap-3"><span>{t('sound.sfx_volume')}</span><span>{Math.round(settings.sfxVolume * 100)}%</span></span>
            <input
              id="sfx-volume"
              data-testid="sfx-volume"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={settings.sfxVolume}
              onChange={(event) => soundManager.setSfxVolume(event.target.value)}
              className="w-full accent-yellow-500"
            />
          </label>
        </div>
      </details>
    </div>
  );
};

export default SoundToggle;
