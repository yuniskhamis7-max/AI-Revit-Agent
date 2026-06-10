/**
 * Message store — owns all message state including streaming and tool calls.
 *
 * This is the most complex store. It manages:
 * - The persisted message list (loaded when a session is selected)
 * - Real-time streaming state (accumulating text, thoughts, tool calls)
 * - Tool call lifecycle (pending → executing → done/rejected)
 *
 * The streaming flow works by maintaining a 'streaming-placeholder' message
 * that is updated in-place as SSE events arrive, then finalised with a
 * persistent UUID when the 'done' event is received.
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { ChatMessage, ToolCall } from '@/types';

/**
 * Immutable message state shape.
 *
 * @property messages      - All messages in the current session.
 * @property isStreaming   - True while an SSE stream is actively appending text.
 * @property streamingText - Accumulated text buffer for the current streaming message.
 */
interface MessageState {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingText: string;
}

/**
 * Mutable message actions.
 *
 * @property setMessages            - Replace the entire message list (e.g. on session load).
 * @property addMessage             - Append a complete message. Replaces streaming placeholder if present.
 * @property appendStreamingText    - Append a text chunk to the current streaming message.
 *                                    Creates the placeholder if none exists yet.
 * @property appendThinking         - Append model chain-of-thought to the streaming message.
 * @property appendAgentThought     - Append a synthetic agent status message to the streaming message.
 * @property updateToolCall         - Update or insert a tool call on a specific message.
 *                                    Pass msgId='streaming-placeholder' to target the active stream.
 * @property finaliseStreamingMessage - Mark the streaming message as complete and assign its persistent UUID.
 * @property clearStreamingState    - Remove the streaming message and reset streaming buffers.
 * @property clearMessages          - Clear all messages and streaming state.
 */
interface MessageActions {
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (msg: ChatMessage) => void;
  appendStreamingText: (chunk: string) => void;
  appendThinking: (chunk: string) => void;
  appendAgentThought: (thought: string) => void;
  updateToolCall: (msgId: string, callId: string, updates: Partial<ToolCall>) => void;
  finaliseStreamingMessage: (messageId: string) => void;
  clearStreamingState: () => void;
  clearMessages: () => void;
}

export const useMessageStore = create<MessageState & MessageActions>()(
  immer((set) => ({
    messages: [],
    isStreaming: false,
    streamingText: '',

    setMessages: (messages) =>
      set((s) => { s.messages = messages; }),

    clearMessages: () =>
      set((s) => {
        s.messages = [];
        s.streamingText = '';
        s.isStreaming = false;
      }),

    addMessage: (msg) =>
      set((s) => {
        const streamingIdx = s.messages.findIndex((m) => m.isStreaming);
        if (streamingIdx >= 0 && msg.role === 'assistant') {
          s.messages[streamingIdx] = msg;
        } else {
          s.messages.push(msg);
        }
        s.isStreaming = false;
        s.streamingText = '';
      }),

    appendStreamingText: (chunk) =>
      set((s) => {
        s.streamingText += chunk;
        s.isStreaming = true;

        const streamingIdx = s.messages.findIndex((m) => m.isStreaming);
        if (streamingIdx >= 0) {
          s.messages[streamingIdx].content = s.streamingText;
        } else {
          s.messages.push({
            id: 'streaming-placeholder',
            role: 'streaming',
            content: s.streamingText,
            createdAt: new Date(),
            isStreaming: true,
            toolCalls: [],
          });
        }
      }),

    appendThinking: (chunk) =>
      set((s) => {
        const streamingIdx = s.messages.findIndex((m) => m.isStreaming);
        if (streamingIdx >= 0) {
          s.messages[streamingIdx].thinking = (s.messages[streamingIdx].thinking ?? '') + chunk;
        } else {
          s.messages.push({
            id: 'streaming-placeholder',
            role: 'streaming',
            content: '',
            thinking: chunk,
            createdAt: new Date(),
            isStreaming: true,
            toolCalls: [],
          });
        }
      }),

    appendAgentThought: (thought) =>
      set((s) => {
        const streamingIdx = s.messages.findIndex((m) => m.isStreaming);
        if (streamingIdx >= 0) {
          const current = s.messages[streamingIdx].agentThoughts ?? [];
          s.messages[streamingIdx].agentThoughts = [...current, thought];
        } else {
          s.messages.push({
            id: 'streaming-placeholder',
            role: 'streaming',
            content: '',
            agentThoughts: [thought],
            createdAt: new Date(),
            isStreaming: true,
            toolCalls: [],
          });
        }
      }),

    updateToolCall: (msgId, callId, updates) =>
      set((s) => {
        const target =
          msgId === 'streaming-placeholder'
            ? s.messages.find((m) => m.isStreaming)
            : s.messages.find((m) => m.id === msgId);

        if (target) {
          if (!target.toolCalls) target.toolCalls = [];
          const existingIdx = target.toolCalls.findIndex((tc) => tc.id === callId);
          if (existingIdx >= 0) {
            Object.assign(target.toolCalls[existingIdx], updates);
          } else {
            target.toolCalls.push({
              id: callId,
              name: updates.name ?? '',
              args: updates.args ?? {},
              requires_approval: updates.requires_approval ?? false,
              status: updates.status ?? 'pending',
              ...updates,
            });
          }
        }
      }),

    finaliseStreamingMessage: (messageId) =>
      set((s) => {
        const idx = s.messages.findIndex((m) => m.isStreaming);
        if (idx >= 0) {
          s.messages[idx].isStreaming = false;
          s.messages[idx].id = messageId;
        }
        s.isStreaming = false;
        s.streamingText = '';
      }),

    clearStreamingState: () =>
      set((s) => {
        s.isStreaming = false;
        s.streamingText = '';
        s.messages = s.messages.filter((m) => !m.isStreaming);
      }),
  })),
);
