import React, { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

/**
 * Error boundary state shape.
 *
 * @property hasError - True after an error has been caught.
 * @property error    - The caught Error object, or null.
 */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error boundary props.
 *
 * @property children - React tree to protect from render errors.
 * @property fallback - Optional custom fallback render function.
 *                      Receives the error and a reset callback.
 *                      Defaults to the built-in recovery UI.
 */
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

/**
 * ChatErrorBoundary — catches uncaught JavaScript errors in the chat stream
 * (e.g. malformed SSE events causing render errors) and shows a recovery UI
 * instead of crashing the entire application.
 *
 * Usage:
 *   <ChatErrorBoundary>
 *     <ChatWindow />
 *   </ChatErrorBoundary>
 */
export class ChatErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ChatErrorBoundary] Caught error:', error, info.componentStack);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    const { hasError, error } = this.state;
    const { children, fallback } = this.props;

    if (hasError && error) {
      if (fallback) {
        return fallback(error, this.reset);
      }

      return (
        <div className="error-boundary-container">
          <div className="error-boundary-card">
            <div className="error-boundary-icon">⚠️</div>
            <h3 className="error-boundary-title">Something went wrong</h3>
            <p className="error-boundary-message">
              An unexpected error occurred in the chat interface.
            </p>
            <code className="error-boundary-detail">{error.message}</code>
            <button
              className="error-boundary-btn"
              onClick={this.reset}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return children;
  }
}
