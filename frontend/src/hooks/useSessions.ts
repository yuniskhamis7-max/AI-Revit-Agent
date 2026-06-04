import { useEffect, useCallback } from 'react';
import { sessionsApi } from '@/api/chat';
import { useSessionStore } from '@/store/sessionStore';
import { useMessageStore } from '@/store/messageStore';
import type { ChatMessage, MessageRole, ToolCall } from '@/types';

export function useSessions() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const sessions = useSessionStore((s) => s.sessions);

  // Fetch all sessions
  const loadSessions = useCallback(async () => {
    try {
      const list = await sessionsApi.list();
      useChatStore.getState().setSessions(list);
      // Do NOT auto-activate any session — start with a clean blank page.
      // The user explicitly clicks a session to open it.
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }, []);

  // Fetch detail for active session
  const loadActiveSessionMessages = useCallback(async (id: string) => {
    try {
      const detail = await sessionsApi.get(id);
      const chatMessages: ChatMessage[] = detail.messages.map((m: any) => {
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

  const deleteSession = useCallback(async (id: string) => {
    try {
      await sessionsApi.delete(id);
      useSessionStore.getState().removeSession(id);
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  }, []);

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
