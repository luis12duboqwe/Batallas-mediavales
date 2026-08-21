import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useTutorialStore } from '../store/tutorialStore';
import { useUserStore } from '../store/userStore';

const TutorialOverlay = () => {
  const { t } = useTranslation();
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
      className="pointer-events-none fixed bottom-24 md:bottom-4 left-4 right-4 md:left-auto md:right-4 z-40 md:w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-amber-600/60 bg-gray-950/95 p-4 shadow-2xl backdrop-blur"
      aria-live="polite"
      aria-label={t('tutorial.title')}
      data-testid="tutorial-panel"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-bold text-amber-300">{t('tutorial.title')}</h2>
        <span
          className="rounded-full border border-amber-800 bg-amber-950 px-2 py-0.5 text-xs text-amber-200"
          aria-label={t('tutorial.progress', { current: Math.min(step + 1, totalSteps), total: totalSteps })}
        >
          {Math.min(step + 1, totalSteps)}/{totalSteps}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-gray-200">
        {t(`tutorial.steps.${step}`, { defaultValue: nextAction })}
      </p>
      <p className="mt-3 text-xs text-gray-400">
        {loading ? t('tutorial.checking') : t('tutorial.server_authoritative')}
      </p>
    </aside>
  );
};

export default TutorialOverlay;
