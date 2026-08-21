import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useThemeStore } from '../store/themeStore';

const ThemeSelector = () => {
  const { t } = useTranslation();
  const { themes, currentTheme, setTheme, fetchThemes } = useThemeStore();

  useEffect(() => {
    if (themes.length === 0) fetchThemes();
  }, [themes.length, fetchThemes]);

  if (themes.length === 0) return null;

  return (
    <fieldset className="space-y-2">
      <legend className="block text-gray-400 mb-1">{t('profile.visual_theme')}</legend>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {themes.map(theme => {
          const selected = currentTheme?.id === theme.id;
          return (
            <button
              key={theme.id}
              type="button"
              onClick={() => setTheme(theme)}
              aria-pressed={selected}
              className={`p-3 rounded-lg border transition-all flex flex-col items-center gap-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400 ${
                selected
                  ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500'
                  : 'border-gray-700 bg-gray-900/50 hover:bg-gray-800'
              }`}
            >
              <div className="flex gap-2" aria-hidden>
                <div className="w-6 h-6 rounded-full border border-gray-600" style={{ backgroundColor: theme.primary_color }} />
                <div className="w-6 h-6 rounded-full border border-gray-600" style={{ backgroundColor: theme.secondary_color }} />
              </div>
              <span className="text-xs font-medium text-gray-300">{theme.name}</span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
};

export default ThemeSelector;
