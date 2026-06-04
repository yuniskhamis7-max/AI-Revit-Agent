import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { Session, ChatMessage, ToolCall, Provider, RevitStatus } from '@/types';

// ─────────────────────────────────────────────────────────────────────────────
// State shape
// ─────────────────────────────────────────────────────────────────────────────

interface ChatState {
  // Sessions
  sessions: Session[];
  activeSessionId: string | null;

  // Messages for the active session
  messages: ChatMessage[];

  // Live streaming state
  isStreaming: boolean;
  streamingText: string;

  // Pending approval — set when agent emits agent_paused
  pendingApproval: { toolCall: ToolCall; sessionId: string } | null;

  // Providers
  providers: Provider[];
  activeProvider: string;
  activeModel: string;

  // Revit connection
  revitStatus: RevitStatus;
  revitToolCount: number | null;

  // UI
  sidebarOpen: boolean;
  settingsPanelOpen: boolean;
}

interface ChatActions {
  // Sessions
  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  removeSession: (id: string) => void;
  setActiveSession: (id: string | null) => void;
  renameSession: (id: string, name: string) => void;

  // Messages
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (msg: ChatMessage) => void;
  appendStreamingText: (chunk: string) => void;
  appendThinking: (chunk: string) => void;
  appendAgentThought: (thought: string) => void;
  updateToolCall: (msgId: string, callId: string, updates: Partial<ToolCall>) => void;
  finaliseStreamingMessage: (messageId: string) => void;
  clearStreamingState: () => void;

  // Approval
  setPendingApproval: (payload: { toolCall: ToolCall; sessionId: string } | null) => void;

  // Providers
  setProviders: (providers: Provider[]) => void;
  setActiveProvider: (provider: string, model: string) => void;

  // Revit
  setRevitStatus: (status: RevitStatus) => void;
  setRevitToolCount: (count: number | null) => void;

  // UI
  toggleSidebar: () => void;
  setSettingsPanelOpen: (open: boolean) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Store
// ─────────────────────────────────────────────────────────────────────────────

export const useChatStore = create<ChatState & ChatActions>()(
  immer((set) => ({
    // ── Initial state ───────────────────────────────────────────────────────
    sessions: [],
    activeSessionId: null,
    messages: [],
    isStreaming: false,
    streamingText: '',
    pendingApproval: null,
    providers: [],
    activeProvider: 'gemini',
    activeModel: 'gemini-2.5-flash',
    revitStatus: 'checking',
    revitToolCount: null,
    sidebarOpen: true,
    settingsPanelOpen: false,

    // ── Session actions ─────────────────────────────────────────────────────
    setSessions: (sessions) => set((s: any) => { s.sessions = sessions; }),
    addSession: (session) => set((s: any) => { s.sessions.unshift(session); }),
    removeSession: (id) =>
      set((s: any) => {
        s.sessions = s.sessions.filter((sx: Session) => sx.id !== id);
        if (s.activeSessionId === id) {
          s.activeSessionId = s.sessions[0]?.id ?? null;
          s.messages = [];
        }
      }),
    setActiveSession: (id) =>
      set((s: any) => {
        s.activeSessionId = id;
        s.messages = [];
        s.streamingText = '';
        s.isStreaming = false;
        s.pendingApproval = null;
      }),
    renameSession: (id, name) =>
      set((s: any) => {
        const sx = s.sessions.find((x: Session) => x.id === id);
        if (sx) sx.name = name;
      }),

    // ── Message actions ─────────────────────────────────────────────────────
    setMessages: (messages) => set((s: any) => { s.messages = messages; }),
    addMessage: (msg) =>
      set((s: any) => {
        // If we're transitioning from streaming, replace the placeholder
        const streamingIdx = s.messages.findIndex((m: ChatMessage) => m.isStreaming);
        if (streamingIdx >= 0 && msg.role === 'assistant') {
          s.messages[streamingIdx] = msg;
        } else {
          s.messages.push(msg);
        }
        s.isStreaming = false;
        s.streamingText = '';
      }),
    appendStreamingText: (chunk) =>
      set((s: any) => {
        s.streamingText += chunk;
        s.isStreaming = true;

        // Update or create the streaming placeholder message
        const streamingIdx = s.messages.findIndex((m: ChatMessage) => m.isStreaming);
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
      set((s: any) => {
        const streamingIdx = s.messages.findIndex((m: ChatMessage) => m.isStreaming);
        if (streamingIdx >= 0) {
          const current = s.messages[streamingIdx].thinking ?? '';
          s.messages[streamingIdx].thinking = current + chunk;
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
      set((s: any) => {
        const streamingIdx = s.messages.findIndex((m: ChatMessage) => m.isStreaming);
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
      set((s: any) => {
        // Find the streaming placeholder or the message by id
        const target = msgId === 'streaming-placeholder'
          ? s.messages.find((m: ChatMessage) => m.isStreaming)
          : s.messages.find((m: ChatMessage) => m.id === msgId);

        if (target) {
          if (!target.toolCalls) target.toolCalls = [];
          const existingIdx = target.toolCalls.findIndex((tc: ToolCall) => tc.id === callId);
          if (existingIdx >= 0) {
            Object.assign(target.toolCalls[existingIdx], updates);
          } else {
            // Add new tool call to the streaming message
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
      set((s: any) => {
        const idx = s.messages.findIndex((m: ChatMessage) => m.isStreaming);
        if (idx >= 0) {
          s.messages[idx].isStreaming = false;
          s.messages[idx].id = messageId;
        }
        s.isStreaming = false;
        s.streamingText = '';
      }),
    clearStreamingState: () =>
      set((s: any) => {
        s.isStreaming = false;
        s.streamingText = '';
        // Remove any orphaned streaming placeholder
        s.messages = s.messages.filter((m: ChatMessage) => !m.isStreaming);
      }),

    // ── Approval ────────────────────────────────────────────────────────────
    setPendingApproval: (payload) => set((s) => { s.pendingApproval = payload; }),

    // ── Providers ───────────────────────────────────────────────────────────
    setProviders: (providers) =>
      set((s) => {
        s.providers = providers;
        const active = providers.find((p) => p.active);
        if (active) {
          s.activeProvider = active.name;
          const m = active.active_model ?? active.models[0] ?? '';
          // Guard against [object Object] or non-string values
          s.activeModel = (typeof m === 'string' && !m.includes('[object')) ? m : (active.models[0] ?? '');
        }
      }),
    setActiveProvider: (provider, model) =>
      set((s) => {
        s.activeProvider = provider;
        // Guard against [object Object] or non-string values
        s.activeModel = (typeof model === 'string' && !model.includes('[object')) ? model : '';
      }),

    // ── Revit ───────────────────────────────────────────────────────────────
    setRevitStatus: (status) => set((s) => { s.revitStatus = status; }),
    setRevitToolCount: (count) => set((s) => { s.revitToolCount = count; }),

    // ── UI ──────────────────────────────────────────────────────────────────
    toggleSidebar: () => set((s) => { s.sidebarOpen = !s.sidebarOpen; }),
    setSettingsPanelOpen: (open) => set((s) => { s.settingsPanelOpen = open; }),
  })),
);
