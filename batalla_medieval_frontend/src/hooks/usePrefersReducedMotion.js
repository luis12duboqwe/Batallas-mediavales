import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

const getPreference = () => (
  typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia(QUERY).matches
);

const usePrefersReducedMotion = () => {
  const [reducedMotion, setReducedMotion] = useState(getPreference);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const mediaQuery = window.matchMedia(QUERY);
    const handleChange = (event) => setReducedMotion(event.matches);
    setReducedMotion(mediaQuery.matches);

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  return reducedMotion;
};

export default usePrefersReducedMotion;
