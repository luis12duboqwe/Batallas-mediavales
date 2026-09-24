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
  const musicPercent = Math.round(settings.musicVolume * 100);
  const sfxPercent = Math.round(settings.sfxVolume * 100);

  return (
    <div className="flex items-center gap-1 sm:gap-2" aria-label={t('sound.controls')}>
      <button
        type="button"
        data-testid="sound-music-toggle"
        onClick={() => soundManager.setMusicEnabled(!settings.musicEnabled)}
        className={`${buttonBase} ${settings.musicEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
        aria-label={musicLabel}
        aria-pressed={settings.musicEnabled}
      >
        <GameIcon name="music" size={18} />
        <span className="hidden md:inline">{musicLabel}</span>
      </button>
      <button
        type="button"
        data-testid="sound-sfx-toggle"
        onClick={() => soundManager.setSfxEnabled(!settings.sfxEnabled)}
        className={`${buttonBase} ${settings.sfxEnabled ? 'bg-yellow-900/40' : 'bg-gray-900/60 text-gray-300'}`}
        aria-label={sfxLabel}
        aria-pressed={settings.sfxEnabled}
      >
        <GameIcon name="bell" size={18} />
        <span className="hidden md:inline">{sfxLabel}</span>
      </button>
      <details data-testid="sound-settings" className="relative">
        <summary className={`${buttonBase} list-none cursor-pointer`} aria-label={t('sound.controls')}>
          <GameIcon name="scales" size={18} />
          <span className="sr-only">{t('sound.controls')}</span>
        </summary>
        <div className="absolute right-0 top-full z-[70] mt-2 w-64 space-y-4 rounded-lg border border-yellow-800/60 bg-gray-950 p-4 shadow-2xl">
          <label className="block space-y-2 text-xs text-gray-200">
            <span>{musicLabel}: {musicPercent}%</span>
            <input
              data-testid="music-volume"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={settings.musicVolume}
              onChange={(event) => soundManager.setMusicVolume(event.target.value)}
              className="w-full accent-yellow-400"
              aria-label={`${musicLabel}: ${musicPercent}%`}
            />
          </label>
          <label className="block space-y-2 text-xs text-gray-200">
            <span>{sfxLabel}: {sfxPercent}%</span>
            <input
              data-testid="sfx-volume"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={settings.sfxVolume}
              onChange={(event) => soundManager.setSfxVolume(event.target.value)}
              className="w-full accent-yellow-400"
              aria-label={`${sfxLabel}: ${sfxPercent}%`}
            />
          </label>
        </div>
      </details>
    </div>
  );
};

export default SoundToggle;
