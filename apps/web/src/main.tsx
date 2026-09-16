/**
 * @file main
 * @description Application entry point: mounts Root with the theme bridge,
 * error boundary, React Query client and router; establishes the session.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '@/App';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { useThemeBridge } from '@/shell/themeBridge';
import { useLocaleBridge } from '@/shell/localeBridge';
import { ensureSession } from '@/bridge/session';
import { initI18n, i18n } from '@/i18n';

// Self-hosted variable fonts (offline-deterministic; no Google Fonts dependency)
import '@fontsource-variable/dm-sans/opsz.css';
import '@fontsource-variable/jetbrains-mono';

// Global styles (liquid-glass design system + shell + global + per-page private)
import '@/styles/design-system.css';
import '@/styles/liquid-glass.css';
import '@/styles/shell.css';
import '@/styles/global.css';
import '@/styles/pages/index.css';

// react-query client (keeps @tanstack/react-query 5.x compatible with the legacy hook shapes)
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/** Top-level fallback UI: rendered when the whole app crashes to avoid a blank
 * screen; the user can refresh or retry. Signature matches
 * ErrorBoundary.fallback: (error, reset) => ReactNode. Plain function — copy
 * resolves through the i18n instance directly. */
function RootErrorFallback(_error: Error, reset: () => void) {
  return (
    <div className="page-scaffold" role="alert">
      <div className="page-scaffold__state">
        <h2>{i18n.t('shell:rootError.title')}</h2>
        <p>{i18n.t('shell:rootError.desc')}</p>
        <button type="button" className="btn btn-primary" onClick={reset}>
          {i18n.t('common:action.retry')}
        </button>
      </div>
    </div>
  );
}

function Root() {
  useThemeBridge();
  useLocaleBridge();
  return (
    <StrictMode>
      <ErrorBoundary fallback={RootErrorFallback}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>
  );
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found');
}

// i18n kernel: initialize synchronously before render (defaults to zh-CN until
// shell/localeBridge takes over in the locale phase; no visible copy uses t() yet)
initI18n();

void ensureSession();
createRoot(rootEl).render(<Root />);
