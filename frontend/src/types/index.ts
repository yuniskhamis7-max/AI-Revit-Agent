// Shared TypeScript types — the single source of truth for all data shapes
// used across components, hooks, and the API client layer.

// ─────────────────────────────────────────────────────────────────────────────
// Sessions
// ─────────────────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends Session {
  messages: Message[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Messages
// ─────────────────────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'tool_result';

export interface Message {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  tool_calls?: ToolCall[] | null;
  tool_name?: string | null;
  approved?: boolean | null;
  created_at: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tool Calls
// ─────────────────────────────────────────────────────────────────────────────

export type ToolCallStatus =
  | 'pending'       // Emitted by agent, not yet approved/rejected
  | 'awaiting'      // Requires approval — agent is paused
  | 'executing'     // Approved and running
  | 'done'          // Completed (result received)
  | 'rejected';     // User rejected

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  requires_approval: boolean;
  status: ToolCallStatus;
  result?: Record<string, unknown>;
  approved?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Providers
// ─────────────────────────────────────────────────────────────────────────────

export interface Provider {
  name: string;
  label: string;
  models: string[];
  configured: boolean;
  active: boolean;
  active_model: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// SSE Events (incoming from the backend stream)
// ─────────────────────────────────────────────────────────────────────────────

export type SSEEventType =
  | 'text_delta'
  | 'thinking_delta'
  | 'agent_thought'
  | 'tool_call_pending'
  | 'tool_call_executing'
  | 'tool_result'
  | 'agent_paused'
  | 'error'
  | 'done';

export interface SSEEvent {
  type: SSEEventType;
  // text_delta / thinking_delta
  content?: string;
  // tool_call_pending / executing / result / agent_paused
  id?: string;
  tool?: string;
  args?: Record<string, unknown>;
  requires_approval?: boolean;
  result?: Record<string, unknown>;
  approved?: boolean;
  awaiting_approval_id?: string;
  // error
  message?: string;
  detail?: string;
  // done
  session_id?: string;
  message_id?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// UI Chat message (richer than the persisted Message — includes live state)
// ─────────────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: MessageRole | 'streaming';
  content: string;
  thinking?: string;
  agentThoughts?: string[];
  toolCalls?: ToolCall[];
  createdAt: Date;
  isStreaming?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Revit bridge status
// ─────────────────────────────────────────────────────────────────────────────

export type RevitStatus = 'connected' | 'disconnected' | 'checking';
