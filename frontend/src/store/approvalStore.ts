/**
 * Approval store — owns the pending human-in-the-loop approval state.
 *
 * When the agent loop pauses for a write tool that requires approval, the
 * useChat hook sets pendingApproval here. The ApprovalModal reads this state
 * to display the modal overlay. Once the user decides, pendingApproval is
 * cleared and the decision is sent to the backend.
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { ToolCall } from '@/types';

/**
 * Approval state shape.
 *
 * @property pendingApproval - The tool call awaiting approval and its session ID,
 *                             or null when no approval is pending.
 */
interface ApprovalState {
  pendingApproval: { toolCall: ToolCall; sessionId: string } | null;
}

/**
 * Approval actions.
 *
 * @property setPendingApproval - Set or clear the pending approval.
 *                                Pass null to dismiss the approval modal.
 */
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
