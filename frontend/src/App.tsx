import React, { useEffect } from 'react';
import { useChatStore } from '@/store/chatStore';
import { SessionSidebar } from './components/SessionSidebar';
import { ChatWindow } from './components/ChatWindow';
import { ProviderSelector } from './components/ProviderSelector';
import { ApprovalModal } from './components/ApprovalModal';
import { SettingsPanel } from './components/SettingsPanel';
import { providersApi, revitApi } from './api/settings';
import type { Session } from './types';

const App: React.FC = () => {
  const { 
    sidebarOpen, 
    toggleSidebar, 
    setProviders, 
    setRevitStatus,
    setRevitToolCount,
    activeSessionId,
    sessions
  } = useChatStore();

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

  // 2. Poll Revit Bridge status every 5 seconds
  useEffect(() => {
    const checkRevit = async () => {
      try {
        const res = await revitApi.status();
        setRevitStatus(res.connected ? 'connected' : 'disconnected');
        setRevitToolCount(res.connected ? (res.tool_count ?? null) : null);
      } catch (err) {
        setRevitStatus('disconnected');
        setRevitToolCount(null);
      }
    };

    checkRevit(); // check immediately
    const interval = setInterval(checkRevit, 5000);
    return () => clearInterval(interval);
  }, [setRevitStatus, setRevitToolCount]);

  // Get active session name
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

        {/* Conversation interface */}
        <ChatWindow />
      </main>

      {/* Slide-out settings pane */}
      <SettingsPanel />

      {/* Human-in-the-loop modal overlay */}
      <ApprovalModal />
    </div>
  );
};

export default App;
