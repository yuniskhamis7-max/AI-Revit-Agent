import { useEffect, useCallback } from 'react';
import { sessionsApi } from '@/api/chat';
import { useSessionStore } from '@/store/sessionStore';
import { useMessageStore } from '@/store/messageStore';
import type { ChatMessage, MessageRole, ToolCall } from '@/types';

/**
 * useSessions — manages session lifecycle and message loading.
 *
 * Encapsulates:
 *  - Fetching the sessions list from the backend on mount
 *  - Loading messages when the active session changes
 *  - Creating, deleting, and renaming sessions
 *
 * @returns {{
 *   sessions, activeSessionId, createSession, deleteSession, renameSession, refresh
 * }}
 */
export function useSessions() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const sessions = useSessionStore((s) => s.sessions);

  /**
   * Fetch all sessions from the backend and update the store.
   * Called on mount and available for manual refresh.
   */
  const loadSessions = useCallback(async () => {
    try {
      const list = await sessionsApi.list();
      useSessionStore.getState().setSessions(list);
      // Do NOT auto-activate any session — start with a clean blank page.
      // The user explicitly clicks a session to open it.
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }, []);

  /**
   * Fetch full message history for a session and populate the message store.
   *
   * Parses tool_calls and agent_thoughts from JSON strings into typed objects.
   * Called automatically when activeSessionId changes.
   *
   * @param id - UUID of the session to load messages for.
   */
  const loadActiveSessionMessages = useCallback(async (id: string) => {
    try {
      const detail = await sessionsApi.get(id);
      const chatMessages: ChatMessage[] = detail.messages
        .filter((m: any) => m.role === 'user' || m.role === 'assistant')
        .map((m: any) => {
        let toolCalls: ToolCall[] | undefined = undefined;
        if (m.tool_calls) {
          try {
            toolCalls = typeof m.tool_calls === 'string' ? JSON.parse(m.tool_calls) : m.tool_calls;
          } catch (e) {
            console.error('Error parsing tool calls:', e);
          }
        }
        let agentThoughts: string[] | undefined = undefined;
        if (m.agent_thoughts) {
          try {
            agentThoughts = typeof m.agent_thoughts === 'string' ? JSON.parse(m.agent_thoughts) : m.agent_thoughts;
          } catch (e) {
            console.error('Error parsing agent thoughts:', e);
          }
        }
        return {
          id: m.id,
          role: m.role as MessageRole,
          content: m.content,
          toolCalls,
          agentThoughts,
          createdAt: new Date(m.created_at),
        };
      });
      useMessageStore.getState().setMessages(chatMessages);
    } catch (err) {
      console.error(`Failed to load messages for session ${id}:`, err);
    }
  }, []);

  // Load sessions list once on mount
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Load messages whenever activeSessionId changes
  useEffect(() => {
    if (activeSessionId) {
      loadActiveSessionMessages(activeSessionId);
    } else {
      useMessageStore.getState().setMessages([]);
    }
  }, [activeSessionId, loadActiveSessionMessages]);

  /**
   * Create a new session and immediately activate it.
   *
   * @param name - Human-readable name for the new session.
   * @returns The newly created Session object.
   * @throws Re-throws the API error for the caller to handle.
   */
  const createSession = useCallback(async (name: string) => {
    try {
      const newSession = await sessionsApi.create(name);
      useSessionStore.getState().addSession(newSession);
      useSessionStore.getState().setActiveSession(newSession.id);
      return newSession;
    } catch (err) {
      console.error('Failed to create session:', err);
      throw err;
    }
  }, []);

  /**
   * Delete a session and remove it from the store.
   * If the deleted session was active, the store auto-selects the next one.
   *
   * @param id - UUID of the session to delete.
   */
  const deleteSession = useCallback(async (id: string) => {
    try {
      await sessionsApi.delete(id);
      useSessionStore.getState().removeSession(id);
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  }, []);

  /**
   * Rename a session and update its name in the store.
   *
   * @param id   - UUID of the session to rename.
   * @param name - New human-readable name.
   */
  const renameSession = useCallback(async (id: string, name: string) => {
    try {
      await sessionsApi.rename(id, name);
      useSessionStore.getState().renameSession(id, name);
    } catch (err) {
      console.error('Failed to rename session:', err);
    }
  }, []);

  return {
    sessions,
    activeSessionId,
    createSession,
    deleteSession,
    renameSession,
    refresh: loadSessions,
  };
}
