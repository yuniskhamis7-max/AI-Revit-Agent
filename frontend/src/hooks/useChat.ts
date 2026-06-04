import { useEffect, useRef, useCallback } from 'react';
import { streamChat, approveToolCall } from '@/api/chat';
import { useChatStore } from '@/store/chatStore';
import type { SSEEvent, ToolCall, ChatMessage } from '@/types';

/**
 * useChat — drives the entire conversation lifecycle.
 *
 * Encapsulates:
 *  - Sending a message and opening the SSE stream
 *  - Dispatching each SSE event type into the Zustand store
 *  - Approval gate (approve / reject tool calls)
 *  - Stream cancellation via AbortController
 */
export function useChat() {
  const abortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight stream on unmount
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const sendMessage = useCallback(async (userText: string) => {
    const { activeSessionId, activeProvider, activeModel } = useChatStore.getState();
    if (!activeSessionId || !userText.trim()) return;

    // Cancel previous stream if still open
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    // Add the user message to the UI immediately (optimistic)
    useChatStore.getState().addMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content: userText.trim(),
      createdAt: new Date(),
    });

    try {
      const stream = streamChat(
        {
          session_id: activeSessionId,
          message: userText.trim(),
          provider: activeProvider,
          model: activeModel,
        },
        abortRef.current.signal,
      );

      for await (const event of stream) {
        _handleSSEEvent(event as SSEEvent, activeSessionId);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      useChatStore.getState().clearStreamingState();
      useChatStore.getState().addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `⚠️ Connection error: ${err instanceof Error ? err.message : String(err)}`,
        createdAt: new Date(),
      });
    }
  }, []);

  const approve = useCallback(async (approved: boolean) => {
    const { pendingApproval } = useChatStore.getState();
    if (!pendingApproval) return;

    const { toolCall, sessionId } = pendingApproval;

    // Dismiss the modal immediately for snappy UX
    useChatStore.getState().setPendingApproval(null);

    // Update the tool call card status in the message
    useChatStore.getState().updateToolCall('streaming-placeholder', toolCall.id, {
      status: approved ? 'executing' : 'rejected',
      approved,
    });

    try {
      await approveToolCall(sessionId, toolCall.id, approved);
    } catch (err) {
      console.error('Approval request failed:', err);
    }
  }, []);

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
    useChatStore.getState().clearStreamingState();
  }, []);

  return { sendMessage, approve, cancelStream };
}

// ─────────────────────────────────────────────────────────────────────────────
// SSE event dispatcher
// ─────────────────────────────────────────────────────────────────────────────

function _handleSSEEvent(event: SSEEvent, sessionId: string) {
  const store = useChatStore.getState();

  switch (event.type) {
    case 'text_delta':
      store.appendStreamingText(event.content ?? '');
      break;

    case 'thinking_delta':
      store.appendThinking(event.content ?? '');
      break;

    case 'agent_thought':
      store.appendAgentThought(event.content ?? '');
      break;

    case 'tool_call_pending': {
      const tc: ToolCall = {
        id: event.id!,
        name: event.tool!,
        args: event.args ?? {},
        requires_approval: event.requires_approval ?? false,
        status: event.requires_approval ? 'awaiting' : 'pending',
      };
      store.updateToolCall('streaming-placeholder', tc.id, tc);
      break;
    }

    case 'tool_call_executing':
      store.updateToolCall('streaming-placeholder', event.id!, { status: 'executing' });
      break;

    case 'tool_result':
      store.updateToolCall('streaming-placeholder', event.id!, {
        status: 'done',
        result: event.result,
        approved: event.approved ?? undefined,
      });
      break;

    case 'agent_paused': {
      // Find the pending tool call from the streaming message
      const messages = store.messages;
      const streamingMsg = messages.find((m: ChatMessage) => m.isStreaming);
      const tc = streamingMsg?.toolCalls?.find((t: ToolCall) => t.id === event.awaiting_approval_id);
      if (tc) {
        store.setPendingApproval({ toolCall: tc, sessionId });
      }
      break;
    }

    case 'error':
      store.clearStreamingState();
      store.addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `⚠️ ${event.message ?? 'Unknown error'}${event.detail ? `\n\n${event.detail}` : ''}`,
        createdAt: new Date(),
      });
      break;

    case 'done':
      store.finaliseStreamingMessage(event.message_id ?? crypto.randomUUID());
      break;
  }
}
