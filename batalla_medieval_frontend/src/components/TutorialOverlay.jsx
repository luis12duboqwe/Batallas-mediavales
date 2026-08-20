import { useEffect } from 'react';
import { useTutorialStore } from '../store/tutorialStore';
import { useUserStore } from '../store/userStore';

const TutorialOverlay = () => {
  const {
    step,
    totalSteps,
    isActive,
    nextAction,
    loading,
    fetchStatus,
  } = useTutorialStore();
  const { isAuthenticated } = useUserStore();

  useEffect(() => {
    if (!isAuthenticated()) return undefined;

    fetchStatus().catch(() => {});
    const interval = window.setInterval(() => {
      fetchStatus().catch(() => {});
    }, 3000);

    return () => window.clearInterval(interval);
  }, [fetchStatus, isAuthenticated]);

  if (!isActive) return null;

  return (
    <aside
      className="fixed bottom-4 right-4 z-40 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-amber-600/60 bg-gray-950/95 p-4 shadow-2xl backdrop-blur"
      aria-live="polite"
      data-testid="tutorial-panel"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-bold text-amber-300">Tutorial de inicio</h2>
        <span className="rounded-full border border-amber-800 bg-amber-950 px-2 py-0.5 text-xs text-amber-200">
          {Math.min(step + 1, totalSteps)}/{totalSteps}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-gray-200">{nextAction}</p>
      <p className="mt-3 text-xs text-gray-500">
        {loading
          ? 'Comprobando progreso…'
          : 'El servidor avanza este tutorial únicamente cuando confirma la acción.'}
      </p>
    </aside>
  );
};

export default TutorialOverlay;
