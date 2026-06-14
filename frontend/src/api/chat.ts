import { api, openSSEStream } from './client';
import type { Session, SessionDetail, SSEEvent } from '@/types';

/**
 * Session and Chat API client.
 *
 * Provides typed wrappers for session CRUD operations and the streaming
 * chat endpoint that drives the agent conversation loop.
 */

/**
 * Session CRUD operations.
 *
 * @property list   - Fetch all sessions (newest first).
 * @property create - Create a new session with the given name.
 * @property get    - Fetch a single session with its full message history.
 * @property rename - Update the name of an existing session.
 * @property delete - Delete a session and all its messages.
 */
export const sessionsApi = {
  list:   ()                               => api.get<Session[]>('/sessions'),
  create: (name: string)                   => api.post<Session>('/sessions', { name }),
  get:    (id: string)                     => api.get<SessionDetail>(`/sessions/${id}`),
  rename: (id: string, name: string)       => api.patch<Session>(`/sessions/${id}`, { name }),
  delete: (id: string)                     => api.delete<void>(`/sessions/${id}`),
};

// ── Chat ─────────────────────────────────────────────────────────────────────

/**
 * Payload for initiating a chat turn via POST /api/chat.
 *
 * @property session_id - UUID of the session this message belongs to.
 * @property message    - User's natural language input text.
 * @property provider   - Optional override for the AI provider name.
 * @property model      - Optional override for the model ID.
 */
export interface ChatPayload {
  session_id: string;
  message: string;
  provider?: string;
  model?: string;
  images?: string[];
}

/**
 * Opens the SSE chat stream. The caller iterates the async generator and
 * processes each event. Pass an AbortSignal to cancel mid-stream.
 */
export function streamChat(
  payload: ChatPayload,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  return openSSEStream('/chat', payload, signal) as AsyncGenerator<SSEEvent>;
}

/**
 * Send a tool call approval or rejection to the backend.
 *
 * Unblocks the paused agent loop for the given session. The agent resumes
 * asynchronously after this call.
 *
 * @param session_id  - UUID of the session whose agent is paused.
 * @param approval_id - UUID of the specific tool call being decided.
 * @param approved    - True to allow execution, False to reject.
 * @returns Server acknowledgement with the approval decision.
 */
export const approveToolCall = (
  session_id: string,
  approval_id: string,
  approved: boolean,
) =>
  api.post<{ status: string; approved: boolean }>('/chat/approve', {
    session_id,
    approval_id,
    approved,
  });
