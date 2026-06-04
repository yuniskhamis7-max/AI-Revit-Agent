/**
 * chatStore.ts — Barrel re-export for backward compatibility.
 *
 * The monolithic store has been split into 5 focused slices:
 *   - useSessionStore  (store/sessionStore.ts)  — sessions, activeSessionId
 *   - useMessageStore  (store/messageStore.ts)  — messages, streaming state
 *   - useApprovalStore (store/approvalStore.ts) — pendingApproval
 *   - useProviderStore (store/providerStore.ts) — providers, active provider/model
 *   - useUIStore       (store/uiStore.ts)       — sidebar, settings, revit status
 *
 * This file re-exports everything so existing imports of useChatStore continue
 * to work during migration. New code should import directly from the slice files.
 *
 * @deprecated Import from the specific slice store instead of useChatStore.
 */

export { useSessionStore } from './sessionStore';
export { useMessageStore } from './messageStore';
export { useApprovalStore } from './approvalStore';
export { useProviderStore } from './providerStore';
export { useUIStore } from './uiStore';

// ─────────────────────────────────────────────────────────────────────────────
// Legacy useChatStore shim
//
// Provides a single hook that merges all slices so components that haven't
// been updated yet can still call useChatStore() and get all the state/actions
// they expect.
//
// Performance note: this hook re-renders whenever ANY slice changes. Prefer
// importing from individual slice stores to subscribe only to what you need.
// ─────────────────────────────────────────────────────────────────────────────

import { useSessionStore } from './sessionStore';
import { useMessageStore } from './messageStore';
import { useApprovalStore } from './approvalStore';
import { useProviderStore } from './providerStore';
import { useUIStore } from './uiStore';

/** @deprecated Use the individual slice stores for new code. */
export function useChatStore() {
  const session  = useSessionStore();
  const message  = useMessageStore();
  const approval = useApprovalStore();
  const provider = useProviderStore();
  const ui       = useUIStore();

  return {
    // Session
    sessions:           session.sessions,
    activeSessionId:    session.activeSessionId,
    setSessions:        session.setSessions,
    addSession:         session.addSession,
    removeSession:      session.removeSession,
    setActiveSession:   session.setActiveSession,
    renameSession:      session.renameSession,

    // Messages
    messages:               message.messages,
    isStreaming:             message.isStreaming,
    streamingText:           message.streamingText,
    setMessages:             message.setMessages,
    addMessage:              message.addMessage,
    appendStreamingText:     message.appendStreamingText,
    appendThinking:          message.appendThinking,
    appendAgentThought:      message.appendAgentThought,
    updateToolCall:          message.updateToolCall,
    finaliseStreamingMessage:message.finaliseStreamingMessage,
    clearStreamingState:     message.clearStreamingState,
    clearMessages:           message.clearMessages,

    // Approval
    pendingApproval:    approval.pendingApproval,
    setPendingApproval: approval.setPendingApproval,

    // Providers
    providers:          provider.providers,
    activeProvider:     provider.activeProvider,
    activeModel:        provider.activeModel,
    setProviders:       provider.setProviders,
    setActiveProvider:  provider.setActiveProvider,

    // UI
    sidebarOpen:           ui.sidebarOpen,
    settingsPanelOpen:     ui.settingsPanelOpen,
    revitStatus:           ui.revitStatus,
    revitToolCount:        ui.revitToolCount,
    toggleSidebar:         ui.toggleSidebar,
    setSettingsPanelOpen:  ui.setSettingsPanelOpen,
    setRevitStatus:        ui.setRevitStatus,
    setRevitToolCount:     ui.setRevitToolCount,
  };
}

// Expose getState() equivalent for the imperative usages in useChat.ts
// that call useChatStore.getState() directly.
useChatStore.getState = () => ({
  ...useSessionStore.getState(),
  ...useMessageStore.getState(),
  ...useApprovalStore.getState(),
  ...useProviderStore.getState(),
  ...useUIStore.getState(),
});
