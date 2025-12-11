import { useEffect, useMemo, useState } from 'react';

const gradients = [
  'radial-gradient(circle at 20% 20%, rgba(255, 209, 102, 0.08), transparent 35%)',
  'radial-gradient(circle at 80% 10%, rgba(255, 152, 90, 0.08), transparent 30%)',
  'linear-gradient(135deg, rgba(17, 24, 39, 0.85), rgba(3, 7, 18, 0.95))',
];

const LoadingScreen = ({ onComplete }) => {
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(true);
  const [ready, setReady] = useState(false);

  const backgroundStyle = useMemo(
    () => ({
      backgroundImage: gradients.join(','),
    }),
    [],
  );

  useEffect(() => {
    const showTimer = setTimeout(() => setReady(true), 50);
    let intervalId;

    intervalId = setInterval(() => {
      setProgress((prev) => {
        const increment = Math.random() * 12 + 5;
        const next = Math.min(prev + increment, 100);
        if (next >= 100) {
          clearInterval(intervalId);
          setTimeout(() => setVisible(false), 350);
          setTimeout(() => {
            onComplete?.();
          }, 800);
        }
        return next;
      });
    }, 260);

    return () => {
      clearInterval(intervalId);
      clearTimeout(showTimer);
    };
  }, [onComplete]);

  return (
    <div
      className={`fixed inset-0 z-30 flex items-center justify-center transition-opacity duration-700 ${
        ready && visible ? 'opacity-100' : 'opacity-0 pointer-events-none'
      }`}
      style={backgroundStyle}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,215,128,0.08),transparent_55%)]" />
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative z-10 max-w-xl px-6 text-center space-y-6">
        <div className="flex flex-col items-center gap-2">
          <h1 className="text-4xl sm:text-5xl font-display tracking-[0.2em] text-yellow-200 drop-shadow-lg">
            Batalla Medieval
          </h1>
          <p className="text-sm text-yellow-100/80">Consejo: Mejora tu Hacienda para más tropas</p>
        </div>
        <div className="w-full h-3 rounded-full overflow-hidden bg-gray-900/70 border border-yellow-800/40 shadow-inner">
          <div
            className="h-full bg-gradient-to-r from-yellow-600 via-amber-400 to-yellow-200 shadow-glow transition-all duration-200"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="text-xs uppercase tracking-[0.3em] text-yellow-100/60">
          Cargando... {Math.round(progress)}%
        </div>
      </div>
    </div>
  );
};

export default LoadingScreen;
