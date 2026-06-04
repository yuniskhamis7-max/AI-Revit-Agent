import { api, openSSEStream } from './client';
import type { Session, SessionDetail, SSEEvent } from '@/types';

// ── Sessions ─────────────────────────────────────────────────────────────────

export const sessionsApi = {
  list:   ()                               => api.get<Session[]>('/sessions'),
  create: (name: string)                   => api.post<Session>('/sessions', { name }),
  get:    (id: string)                     => api.get<SessionDetail>(`/sessions/${id}`),
  rename: (id: string, name: string)       => api.patch<Session>(`/sessions/${id}`, { name }),
  delete: (id: string)                     => api.delete<void>(`/sessions/${id}`),
};

// ── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatPayload {
  session_id: string;
  message: string;
  provider?: string;
  model?: string;
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
