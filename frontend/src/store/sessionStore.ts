/**
 * Session store — owns the sessions list and active session selection.
 *
 * Manages CRUD state for chat sessions displayed in the sidebar. The active
 * session ID drives which session's messages are loaded and displayed.
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { Session } from '@/types';

/**
 * Immutable session state shape.
 *
 * @property sessions          - Ordered list of all sessions (newest first after sort).
 * @property activeSessionId   - UUID of the currently selected session, or null.
 */
interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
}

/**
 * Mutable session actions.
 *
 * @property setSessions    - Replace the entire sessions list (e.g. from API fetch).
 * @property addSession     - Prepend a new session to the list.
 * @property removeSession  - Remove a session by ID. If it was active, select the first remaining.
 * @property setActiveSession - Set the active session ID (or null to deselect).
 * @property renameSession  - Update the name of an existing session in-place.
 */
interface SessionActions {
  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  removeSession: (id: string) => void;
  setActiveSession: (id: string | null) => void;
  renameSession: (id: string, name: string) => void;
}

export const useSessionStore = create<SessionState & SessionActions>()(
  immer((set) => ({
    sessions: [],
    activeSessionId: null,

    setSessions: (sessions) =>
      set((s) => { s.sessions = sessions; }),

    addSession: (session) =>
      set((s) => { s.sessions.unshift(session); }),

    removeSession: (id) =>
      set((s) => {
        s.sessions = s.sessions.filter((sx) => sx.id !== id);
        if (s.activeSessionId === id) {
          s.activeSessionId = s.sessions[0]?.id ?? null;
        }
      }),

    setActiveSession: (id) =>
      set((s) => {
        s.activeSessionId = id;
      }),

    renameSession: (id, name) =>
      set((s) => {
        const sx = s.sessions.find((x) => x.id === id);
        if (sx) sx.name = name;
      }),
  })),
);
