// Approval store — owns the pending human-in-the-loop approval state.
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { ToolCall } from '@/types';

interface ApprovalState {
  pendingApproval: { toolCall: ToolCall; sessionId: string } | null;
}

interface ApprovalActions {
  setPendingApproval: (payload: { toolCall: ToolCall; sessionId: string } | null) => void;
}

export const useApprovalStore = create<ApprovalState & ApprovalActions>()(
  immer((set) => ({
    pendingApproval: null,

    setPendingApproval: (payload) =>
      set((s) => { s.pendingApproval = payload; }),
  })),
);
