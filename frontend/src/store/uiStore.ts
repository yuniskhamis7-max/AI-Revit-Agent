/**
 * UI store — owns sidebar, settings panel, and Revit bridge connection state.
 *
 * Manages purely visual/UI state that doesn't belong in the data stores.
 * The Revit status is updated by the polling loop in App.tsx.
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { RevitStatus } from '@/types';

/**
 * UI state shape.
 *
 * @property sidebarOpen       - Whether the session sidebar is expanded.
 * @property settingsPanelOpen - Whether the settings drawer is visible.
 * @property revitStatus       - Current Revit bridge connection status.
 * @property revitToolCount    - Number of tools discovered from the bridge, or null.
 */
interface UIState {
  sidebarOpen: boolean;
  settingsPanelOpen: boolean;
  revitStatus: RevitStatus;
  revitToolCount: number | null;
}

/**
 * UI actions.
 *
 * @property toggleSidebar          - Toggle the sidebar open/closed.
 * @property setSettingsPanelOpen   - Open or close the settings drawer.
 * @property setRevitStatus         - Update the Revit bridge connection status.
 * @property setRevitToolCount      - Update the number of discovered tools.
 */
interface UIActions {
  toggleSidebar: () => void;
  setSettingsPanelOpen: (open: boolean) => void;
  setRevitStatus: (status: RevitStatus) => void;
  setRevitToolCount: (count: number | null) => void;
}

export const useUIStore = create<UIState & UIActions>()(
  immer((set) => ({
    sidebarOpen: true,
    settingsPanelOpen: false,
    revitStatus: 'checking',
    revitToolCount: null,

    toggleSidebar: () =>
      set((s) => { s.sidebarOpen = !s.sidebarOpen; }),

    setSettingsPanelOpen: (open) =>
      set((s) => { s.settingsPanelOpen = open; }),

    setRevitStatus: (status) =>
      set((s) => { s.revitStatus = status; }),

    setRevitToolCount: (count) =>
      set((s) => { s.revitToolCount = count; }),
  })),
);
