import { useEffect } from 'react';
import { useThemeStore } from '../store/themeStore';

const ThemeSelector = () => {
  const { themes, currentTheme, setTheme, fetchThemes } = useThemeStore();

  useEffect(() => {
    if (themes.length === 0) fetchThemes();
  }, []);

  if (themes.length === 0) return null;

  return (
    <div className="space-y-2">
      <label className="block text-gray-400 mb-1">Tema Visual</label>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {themes.map(theme => (
          <button
            key={theme.id}
            onClick={() => setTheme(theme)}
            className={`p-3 rounded-lg border transition-all flex flex-col items-center gap-2 ${
              currentTheme?.id === theme.id 
                ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500' 
                : 'border-gray-700 bg-gray-900/50 hover:bg-gray-800'
            }`}
          >
            <div className="flex gap-2">
              <div className="w-6 h-6 rounded-full border border-gray-600" style={{ backgroundColor: theme.primary_color }} />
              <div className="w-6 h-6 rounded-full border border-gray-600" style={{ backgroundColor: theme.secondary_color }} />
            </div>
            <span className="text-xs font-medium text-gray-300">{theme.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default ThemeSelector;
