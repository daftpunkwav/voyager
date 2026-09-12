/**
 * @file ErrorBoundary
 * @description App-level error boundary that catches synchronous render errors in its subtree.
 *
 * Prevents a full blank page, supports a custom fallback with a reset action,
 * and forwards errors through the optional onError hook (Sentry / DataDog etc.),
 * falling back to console.error when no hook is provided.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { i18n } from '@/i18n';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /**
   * External error reporting hook (Sentry / DataDog etc.); falls back to console.error when omitted.
   *
   * Responsibilities:
   * - Catch synchronous render errors in the subtree and render the fallback
   * - Forward caught errors through the optional onError hook, else console.error
   * - Reset the boundary state from the fallback's retry action
   */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Prefer the external onError hook; fall back to console.error when absent.
    if (this.props.onError) {
      this.props.onError(error, info);
      return;
    }
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  private readonly reset = () => {
    this.setState({ error: null });
  };

  override render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return (
      <div className="app-error-fallback" role="alert" data-testid="app-error-fallback">
        {/* Class component: resolve copy through the i18n instance instead of the hook */}
        <h2>{i18n.t('common:errorBoundary.title')}</h2>
        <p>{i18n.t('common:errorBoundary.description')}</p>
        <pre className="app-error-fallback__detail">{error.message}</pre>
        <button type="button" className="btn btn-primary" onClick={this.reset}>
          {i18n.t('common:action.retry')}
        </button>
      </div>
    );
  }
}
