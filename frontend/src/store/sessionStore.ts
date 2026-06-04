// Session store — owns sessions list and active session selection.
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { Session } from '@/types';

interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
}

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
