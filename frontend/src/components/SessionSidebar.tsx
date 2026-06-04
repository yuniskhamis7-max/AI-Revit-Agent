import React, { useState } from 'react';
import { useSessions } from '@/hooks/useSessions';
import { useUIStore } from '@/store/uiStore';
import { useSessionStore } from '@/store/sessionStore';
import { revitApi } from '@/api/settings';
import type { Session } from '@/types';

export const SessionSidebar: React.FC = () => {
  const { sessions, activeSessionId, createSession, deleteSession, renameSession } = useSessions();
  const { revitStatus, sidebarOpen, toggleSidebar, setSettingsPanelOpen, revitToolCount, setRevitToolCount } = useUIStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [isRefreshingTools, setIsRefreshingTools] = useState(false);

  // Sort sessions by most recently updated first
  const sortedSessions = [...sessions].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  );

  const handleCreateSession = async () => {
    const name = `Session ${sessions.length + 1}`;
    await createSession(name);
  };

  const handleStartEdit = (id: string, currentName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(id);
    setEditName(currentName);
  };

  const handleSaveRename = async (id: string) => {
    if (editName.trim()) {
      await renameSession(id, editName.trim());
    }
    setEditingId(null);
  };

  const handleKeyDown = (id: string, e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveRename(id);
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  };

  if (!sidebarOpen) {
    return (
      <button className="sidebar-toggle-collapsed" onClick={toggleSidebar} title="Open Sidebar">
        ➡️
      </button>
    );
  }

  return (
    <aside className="session-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <svg viewBox="0 0 24 24" width="24" height="24" className="logo-icon">
            <path fill="currentColor" d="M12 2L2 22h20L12 2zm0 3.99L19.53 19H4.47L12 5.99zM13 16h-2v2h2v-2zm0-6h-2v4h2v-4z"/>
          </svg>
          <h2>Revit AI</h2>
        </div>
        <button className="sidebar-close-btn" onClick={toggleSidebar} title="Collapse Sidebar">
          ◀
        </button>
      </div>

      <button className="new-session-btn" onClick={handleCreateSession}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
        </svg>
        New Session
      </button>

      <div className="sessions-list">
        {sortedSessions.map((session: Session) => {
          const isActive = session.id === activeSessionId;
          const isEditing = session.id === editingId;

          return (
            <div
              key={session.id}
              className={`session-item ${isActive ? 'active' : ''}`}
              onClick={() => !isEditing && useSessionStore.getState().setActiveSession(session.id)}
            >
              <div className="session-item-content">
                <svg viewBox="0 0 24 24" width="16" height="16" className="chat-icon">
                  <path fill="currentColor" d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z"/>
                </svg>
                
                {isEditing ? (
                  <input
                    type="text"
                    className="session-rename-input"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onBlur={() => handleSaveRename(session.id)}
                    onKeyDown={(e) => handleKeyDown(session.id, e)}
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="session-name" title={session.name}>
                    {session.name}
                  </span>
                )}
              </div>

              {!isEditing && (
                <div className="session-item-actions">
                  <button
                    className="action-btn rename-btn"
                    onClick={(e) => handleStartEdit(session.id, session.name, e)}
                    title="Rename"
                  >
                    ✏️
                  </button>
                  <button
                    className="action-btn delete-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('Delete this session?')) {
                        deleteSession(session.id);
                      }
                    }}
                    title="Delete"
                  >
                    🗑️
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="sidebar-footer">
        <div className="revit-status-container">
          <div className={`status-dot ${revitStatus}`} />
          <span className="status-label">
            Revit: {revitStatus === 'connected' 
              ? `Connected${revitToolCount !== null ? ` (${revitToolCount} tools)` : ''}` 
              : revitStatus === 'checking' ? 'Checking...' : 'Disconnected'}
          </span>
          {revitStatus === 'connected' && (
            <button
              className="refresh-tools-btn"
              title="Refresh tool registry from Revit bridge"
              disabled={isRefreshingTools}
              onClick={async (e) => {
                e.stopPropagation();
                setIsRefreshingTools(true);
                try {
                  const res = await revitApi.refreshTools();
                  setRevitToolCount(res.tool_count);
                } catch (err) {
                  console.error('Failed to refresh tools:', err);
                } finally {
                  setIsRefreshingTools(false);
                }
              }}
            >
              {isRefreshingTools ? 'Refreshing...' : '↻'}
            </button>
          )}
        </div>
        
        <button 
          className="settings-toggle-btn" 
          onClick={() => setSettingsPanelOpen(true)}
          title="Settings"
        >
          ⚙️ Configure
        </button>
      </div>
    </aside>
  );
};
