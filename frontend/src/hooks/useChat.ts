import { useEffect, useRef, useCallback } from 'react';
import { streamChat, approveToolCall } from '@/api/chat';
import { useMessageStore } from '@/store/messageStore';
import { useApprovalStore } from '@/store/approvalStore';
import { useSessionStore } from '@/store/sessionStore';
import { useProviderStore } from '@/store/providerStore';
import type { SSEEvent, ToolCall, ChatMessage } from '@/types';

/**
 * useChat — drives the entire conversation lifecycle.
 *
 * Encapsulates:
 *  - Sending a message and opening the SSE stream
 *  - Dispatching each SSE event type into the focused Zustand stores
 *  - Approval gate (approve / reject tool calls)
 *  - Stream cancellation via AbortController
 *
 * @returns {{ sendMessage, approve, cancelStream }}
 *   sendMessage   — Send a user message and start the SSE stream.
 *   approve       — Approve or reject the currently pending tool call.
 *   cancelStream  — Abort the in-flight SSE stream and clear streaming state.
 */
export function useChat() {
  /** Ref to the current AbortController for cancelling in-flight streams. */
  const abortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight stream on unmount
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  /**
   * Send a user message to the backend and process the SSE response stream.
   *
   * Adds the user message optimistically to the UI, opens the SSE stream,
   * and dispatches each incoming event to the appropriate store. On error,
   * clears streaming state and adds an error message.
   *
   * @param userText - The user's input text (trimmed before sending).
   */
  const sendMessage = useCallback(async (userText: string, images?: string[]) => {
    const { activeSessionId } = useSessionStore.getState();
    const { activeProvider, activeModel } = useProviderStore.getState();
    const messageStore = useMessageStore.getState();

    const trimmed = userText.trim();
    if (!activeSessionId || (!trimmed && !images?.length)) return;

    // Cancel previous stream if still open
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    // Add the user message to the UI immediately (optimistic)
    messageStore.addMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      createdAt: new Date(),
      images: images?.length ? images : undefined,
    });

    try {
      const stream = streamChat(
        {
          session_id: activeSessionId,
          message: trimmed,
          provider: activeProvider,
          model: activeModel,
          images: images?.length ? images : undefined,
        },
        abortRef.current.signal,
      );

      for await (const event of stream) {
        _handleSSEEvent(event as SSEEvent, activeSessionId);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      useMessageStore.getState().clearStreamingState();
      useMessageStore.getState().addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `⚠️ Connection error: ${err instanceof Error ? err.message : String(err)}`,
        createdAt: new Date(),
      });
    }
  }, []);

  /**
   * Approve or reject the currently pending tool call.
   *
   * Dismisses the approval modal immediately, updates the tool call card status,
   * and sends the decision to the backend to unblock the paused agent.
   *
   * @param approved - True to allow execution, False to reject.
   */
  const approve = useCallback(async (approved: boolean) => {
    const { pendingApproval, setPendingApproval } = useApprovalStore.getState();
    if (!pendingApproval) return;

    const { toolCall, sessionId } = pendingApproval;

    // Dismiss the modal immediately for snappy UX
    setPendingApproval(null);

    // Update the tool call card status in the message
    useMessageStore.getState().updateToolCall('streaming-placeholder', toolCall.id, {
      status: approved ? 'executing' : 'rejected',
      approved,
    });

    try {
      await approveToolCall(sessionId, toolCall.id, approved);
    } catch (err) {
      console.error('Approval request failed:', err);
    }
  }, []);

  /**
   * Cancel the in-flight SSE stream and clear streaming UI state.
   * Safe to call even if no stream is active.
   */
  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
    useMessageStore.getState().clearStreamingState();
  }, []);

  return { sendMessage, approve, cancelStream };
}

// ─────────────────────────────────────────────────────────────────────────────
// SSE event dispatcher
// ─────────────────────────────────────────────────────────────────────────────

/**
 * SSE event dispatcher — routes each event type to the appropriate store action.
 *
 * Called synchronously for every event yielded by the backend SSE stream.
 * Handles text accumulation, tool call lifecycle, agent thoughts, errors,
 * and stream finalisation.
 *
 * @param event     - Parsed SSE event from the backend.
 * @param sessionId - UUID of the session this stream belongs to.
 */
function _handleSSEEvent(event: SSEEvent, sessionId: string) {
  const msg      = useMessageStore.getState();
  const approval = useApprovalStore.getState();

  switch (event.type) {
    case 'text_delta':
      msg.appendStreamingText(event.content ?? '');
      break;

    case 'thinking_delta':
      msg.appendThinking(event.content ?? '');
      break;

    case 'agent_thought':
      msg.appendAgentThought(event.content ?? '');
      break;

    case 'tool_call_pending': {
      const tc: ToolCall = {
        id: event.id!,
        name: event.tool!,
        args: event.args ?? {},
        requires_approval: event.requires_approval ?? false,
        status: event.requires_approval ? 'awaiting' : 'pending',
      };
      msg.updateToolCall('streaming-placeholder', tc.id, tc);
      break;
    }

    case 'tool_call_executing':
      msg.updateToolCall('streaming-placeholder', event.id!, { status: 'executing' });
      break;

    case 'tool_result':
      msg.updateToolCall('streaming-placeholder', event.id!, {
        status: 'done',
        result: event.result,
        approved: event.approved ?? undefined,
      });
      break;

    case 'agent_paused': {
      const { messages } = useMessageStore.getState();
      const streamingMsg = messages.find((m: ChatMessage) => m.isStreaming);
      const tc = streamingMsg?.toolCalls?.find((t: ToolCall) => t.id === event.awaiting_approval_id);
      if (tc) {
        approval.setPendingApproval({ toolCall: tc, sessionId });
      }
      break;
    }

    case 'error':
      msg.clearStreamingState();
      msg.addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `⚠️ ${event.message ?? 'Unknown error'}${event.detail ? `\n\n${event.detail}` : ''}`,
        createdAt: new Date(),
      });
      break;

    case 'done':
      msg.finaliseStreamingMessage(event.message_id ?? crypto.randomUUID());
      break;
  }
}
