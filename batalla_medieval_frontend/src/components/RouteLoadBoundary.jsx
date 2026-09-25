import { Component } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const RETRY_PREFIX = 'bm_lazy_route_retry:';
const DYNAMIC_IMPORT_ERROR = /(failed to fetch dynamically imported module|importing a module script failed|error loading dynamically imported module|chunkloaderror|loading chunk .* failed)/i;

export const recoverableImport = (loader, key) => async () => {
  const storageKey = `${RETRY_PREFIX}${key}`;
  try {
    const loaded = await loader();
    if (typeof window !== 'undefined') {
      try { window.sessionStorage.removeItem(storageKey); } catch { /* storage may be unavailable */ }
    }
    return loaded;
  } catch (error) {
    const message = String(error?.message || error || '');
    if (typeof window !== 'undefined' && DYNAMIC_IMPORT_ERROR.test(message)) {
      try {
        if (window.sessionStorage.getItem(storageKey) !== '1') {
          window.sessionStorage.setItem(storageKey, '1');
          window.location.reload();
          return new Promise(() => {});
        }
        window.sessionStorage.removeItem(storageKey);
      } catch {
        // Fall through to the boundary when storage/reload recovery is unavailable.
      }
    }
    throw error;
  }
};

class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    console.error('Route chunk/render failure', error);
  }

  componentDidUpdate(previousProps) {
    if (this.state.error && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) return this.props.renderError(this.state.error);
    return this.props.children;
  }
}

const RouteLoadBoundary = ({ children, fullPage = false }) => {
  const { t } = useTranslation();
  const location = useLocation();

  const renderError = () => (
    <div
      role="alert"
      data-testid="route-load-error"
      className={fullPage
        ? 'min-h-screen flex flex-col items-center justify-center gap-4 bg-midnight px-6 text-center text-yellow-100'
        : 'card mx-auto max-w-xl space-y-4 p-6 text-center text-yellow-100'}
    >
      <p>{t('common.route_load_error')}</p>
      <button
        type="button"
        data-testid="route-reload"
        className="btn-primary"
        onClick={() => window.location.reload()}
      >
        {t('common.reload')}
      </button>
    </div>
  );

  return (
    <RouteErrorBoundary
      resetKey={`${location.key}:${location.pathname}`}
      renderError={renderError}
    >
      {children}
    </RouteErrorBoundary>
  );
};

export default RouteLoadBoundary;
