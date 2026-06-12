import React, { useCallback, useEffect, useRef } from 'react';
import { useUIStore } from '@/store/uiStore';
import { useProviderStore } from '@/store/providerStore';
import { useSessionStore } from '@/store/sessionStore';
import { SessionSidebar } from './components/SessionSidebar';
import { ChatWindow } from './components/ChatWindow';
import { ProviderSelector } from './components/ProviderSelector';
import { ApprovalModal } from './components/ApprovalModal';
import { SettingsPanel } from './components/SettingsPanel';
import { ChatErrorBoundary } from './components/ErrorBoundary';
import { providersApi, revitApi } from './api/settings';
import type { Session } from './types';

// ─────────────────────────────────────────────────────────────────────────────
// Revit status polling with exponential backoff
//
// Connected:    polls every POLL_CONNECTED_MS (10s)
// Disconnected: polls at POLL_DISCONNECTED_MS doubling up to POLL_MAX_MS (60s)
// Reconnection: delay resets to POLL_DISCONNECTED_MS on next connected response
// ─────────────────────────────────────────────────────────────────────────────
const POLL_CONNECTED_MS    = 10_000;
const POLL_DISCONNECTED_MS = 5_000;
const POLL_MAX_MS          = 60_000;

/**
 * App — root application component.
 *
 * Composes the full application layout:
 * - SessionSidebar (left panel)
 * - Header with session title and ProviderSelector
 * - ChatWindow (wrapped in ChatErrorBoundary)
 * - SettingsPanel (slide-out drawer)
 * - ApprovalModal (human-in-the-loop overlay)
 *
 * On mount:
 * 1. Fetches configured providers from the backend
 * 2. Starts polling the Revit bridge health status with exponential backoff
 *
 * Polling strategy:
 * - Connected:    polls every 10 seconds
 * - Disconnected: polls starting at 5 seconds, doubling up to 60 seconds max
 * - Reconnection resets the backoff delay
 *
 * @component
 */
const App: React.FC = () => {
  const { sidebarOpen, toggleSidebar, setRevitStatus, setRevitToolCount } = useUIStore();
  const { setProviders } = useProviderStore();
  const { sessions, activeSessionId } = useSessionStore();

  // 1. Fetch configured providers on mount
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const list = await providersApi.list();
        setProviders(list);
      } catch (err) {
        console.error('Failed to fetch provider configurations:', err);
      }
    };
    fetchProviders();
  }, [setProviders]);

  // 2. Poll Revit Bridge status with exponential backoff
  const backoffRef = useRef(POLL_DISCONNECTED_MS);
  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleNextCheck = useCallback((delayMs: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(doCheck, delayMs);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const doCheck = useCallback(async () => {
    try {
      const res = await revitApi.status();
      if (res.connected) {
        setRevitStatus('connected');
        setRevitToolCount(res.tool_count ?? null);
        backoffRef.current = POLL_DISCONNECTED_MS; // reset on reconnect
        scheduleNextCheck(POLL_CONNECTED_MS);
      } else {
        setRevitStatus('disconnected');
        setRevitToolCount(null);
        const next = Math.min(backoffRef.current * 2, POLL_MAX_MS);
        backoffRef.current = next;
        scheduleNextCheck(next);
      }
    } catch {
      setRevitStatus('disconnected');
      setRevitToolCount(null);
      const next = Math.min(backoffRef.current * 2, POLL_MAX_MS);
      backoffRef.current = next;
      scheduleNextCheck(next);
    }
  }, [setRevitStatus, setRevitToolCount, scheduleNextCheck]);

  useEffect(() => {
    doCheck();
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [doCheck]);

  const activeSession = sessions.find((s: Session) => s.id === activeSessionId);

  const [copied, setCopied] = React.useState(false);

  const handleCopySession = useCallback(async () => {
    if (!activeSessionId) return;
    try {
      const response = await fetch(`/api/sessions/${activeSessionId}/export?format=markdown`);
      if (!response.ok) {
        throw new Error('Failed to fetch session export data');
      }
      const text = await response.text();
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy session chat:', err);
    }
  }, [activeSessionId]);

  const handleExportSession = useCallback(() => {
    if (!activeSessionId) return;
    const url = `/api/sessions/${activeSessionId}/export`;
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `session_export_${activeSessionId}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [activeSessionId]);

  return (
    <div className={`app-container ${sidebarOpen ? 'sidebar-expanded' : 'sidebar-collapsed'}`}>
      {/* Left Sidebar */}
      <SessionSidebar />

      {/* Main chat section */}
      <main className="main-content">
        <header className="app-header">
          <div className="header-left">
            {!sidebarOpen && (
              <button
                className="header-sidebar-toggle"
                onClick={toggleSidebar}
                title="Expand Sidebar"
              >
                ☰
              </button>
            )}
            <h1 className="header-title">
              {activeSession ? activeSession.name : 'AI Revit Orchestrator'}
            </h1>
            {activeSession && (
              <div className="header-actions-group">
                <button
                  className="header-export-btn header-copy-btn"
                  onClick={handleCopySession}
                  title="Copy Chat History to Clipboard"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                    <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
                  </svg>
                  <span>{copied ? 'Copied!' : 'Copy Chat'}</span>
                </button>
                <button
                  className="header-export-btn"
                  onClick={handleExportSession}
                  title="Export Chat History as Markdown"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                    <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/>
                  </svg>
                  <span>Export Chat</span>
                </button>
              </div>
            )}
          </div>

          <div className="header-right">
            <ProviderSelector />
          </div>
        </header>

        {/* Conversation interface — wrapped in error boundary */}
        <ChatErrorBoundary>
          <ChatWindow />
        </ChatErrorBoundary>
      </main>

      {/* Slide-out settings pane */}
      <SettingsPanel />

      {/* Human-in-the-loop modal overlay */}
      <ApprovalModal />
    </div>
  );
};

export default App;
