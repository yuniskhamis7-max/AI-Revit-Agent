/**
 * Shared TypeScript types — the single source of truth for all data shapes
 * used across components, hooks, and the API client layer.
 *
 * These types mirror the backend Pydantic models and ORM schemas to ensure
 * type safety across the full stack.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Sessions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Summary of a chat session returned by the backend API.
 *
 * @property id         - Unique UUID assigned to the session at creation.
 * @property name       - Human-readable name displayed in the sidebar.
 * @property created_at - ISO 8601 UTC timestamp of session creation.
 * @property updated_at - ISO 8601 UTC timestamp of the last activity.
 */
export interface Session {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

/**
 * Extended session that includes the full message history.
 * Returned by GET /api/sessions/{id}.
 *
 * @property messages - Ordered list of all messages in the session.
 */
export interface SessionDetail extends Session {
  messages: Message[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Messages
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Possible roles for a persisted message.
 *
 * - 'user'        — Human input sent via the chat interface.
 * - 'assistant'   — AI model text output (may also contain tool_calls).
 * - 'tool_result' — Result returned to the model after tool execution.
 */
export type MessageRole = 'user' | 'assistant' | 'tool_result';

/**
 * Persisted message as returned by the backend API.
 *
 * @property id         - Unique UUID of the message.
 * @property session_id - UUID of the parent session.
 * @property role       - Message role (user, assistant, or tool_result).
 * @property content    - Text content. For tool messages, JSON-serialised result.
 * @property tool_calls - Optional array of tool calls (assistant messages only).
 * @property tool_name  - Name of the tool that produced this result (tool messages).
 * @property approved   - Approval decision for action tools (null for fetch tools).
 * @property created_at - ISO 8601 UTC timestamp.
 */
export interface Message {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  tool_calls?: ToolCall[] | null;
  tool_name?: string | null;
  approved?: boolean | null;
  created_at: string;
  images?: string[] | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tool Calls
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Lifecycle status of a tool call as it progresses through the agent loop.
 *
 * - 'pending'   — Emitted by agent, displayed but not yet approved/rejected.
 * - 'awaiting'  — Requires human approval; agent is paused.
 * - 'executing' — Approved and currently running on the Revit bridge.
 * - 'done'      — Completed successfully (result received).
 * - 'rejected'  — User rejected the action via the approval modal.
 */
export type ToolCallStatus =
  | 'pending'
  | 'awaiting'
  | 'executing'
  | 'done'
  | 'rejected';

/**
 * Represents a single tool call requested by the AI agent.
 *
 * @property id                - Unique UUID assigned to this call instance.
 * @property name              - Tool name (e.g. 'fetch_levels', 'create_grid').
 * @property args              - Arguments dict passed to the tool.
 * @property requires_approval - True if this is a write tool needing human approval.
 * @property status            - Current lifecycle status.
 * @property result            - Tool execution result dict (populated when status='done').
 * @property approved          - Whether the user approved this call.
 */
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

/**
 * AI provider configuration returned by the backend.
 *
 * @property name         - Internal identifier (e.g. 'gemini', 'openai').
 * @property label        - Human-readable display name.
 * @property models       - List of available model IDs.
 * @property configured   - True if an API key is stored.
 * @property active       - True if this is the currently selected provider.
 * @property active_model - Currently selected model ID, or null.
 */
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

/**
 * All possible SSE event types emitted by the backend agent loop.
 *
 * Each type corresponds to a specific stage in the agent's execution cycle.
 */
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

/**
 * Parsed SSE event payload received from the backend stream.
 *
 * Properties are optional and populated depending on the event type:
 * - text_delta / thinking_delta / agent_thought: `content`
 * - tool_call_pending / executing / result: `id`, `tool`, `args`, `result`
 * - agent_paused: `awaiting_approval_id`, `tool`
 * - error: `message`, `detail`
 * - done: `session_id`, `message_id`
 */
export interface SSEEvent {
  type: SSEEventType;
  /** Text chunk for text_delta / thinking_delta / agent_thought events. */
  content?: string;
  /** Tool call UUID (tool_call_pending, executing, result events). */
  id?: string;
  /** Tool name being called. */
  tool?: string;
  /** Arguments dict for the tool call. */
  args?: Record<string, unknown>;
  /** Whether the tool call requires human approval. */
  requires_approval?: boolean;
  /** Tool execution result dict. */
  result?: Record<string, unknown>;
  /** Whether the tool call was approved. */
  approved?: boolean;
  /** UUID of the tool call awaiting approval (agent_paused event). */
  awaiting_approval_id?: string;
  /** Error message (error event). */
  message?: string;
  /** Technical error detail (error event). */
  detail?: string;
  /** Session UUID (done event). */
  session_id?: string;
  /** Finalised assistant message UUID (done event). */
  message_id?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// UI Chat message (richer than the persisted Message — includes live state)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Enriched chat message used by the UI layer.
 *
 * Extends the persisted Message with transient streaming state and
 * accumulated agent thoughts for live display.
 *
 * @property id            - UUID (or 'streaming-placeholder' during streaming).
 * @property role          - Message role, or 'streaming' for in-progress messages.
 * @property content       - Accumulated text content.
 * @property thinking      - Accumulated model chain-of-thought reasoning.
 * @property agentThoughts - List of synthetic agent status messages.
 * @property toolCalls     - List of tool calls with their live status.
 * @property createdAt     - JavaScript Date when the message was created.
 * @property isStreaming   - True if this message is still being streamed.
 * @property images        - List of base64 images attached to this message.
 */
export interface ChatMessage {
  id: string;
  role: MessageRole | 'streaming';
  content: string;
  thinking?: string;
  agentThoughts?: string[];
  toolCalls?: ToolCall[];
  createdAt: Date;
  isStreaming?: boolean;
  images?: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Revit bridge status
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Connection status of the Revit bridge as tracked by the frontend.
 *
 * - 'connected'    — Bridge is reachable and responding.
 * - 'disconnected' — Bridge is unreachable or not running.
 * - 'checking'     — Initial status before first health check completes.
 */
export type RevitStatus = 'connected' | 'disconnected' | 'checking';
