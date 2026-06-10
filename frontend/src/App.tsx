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
