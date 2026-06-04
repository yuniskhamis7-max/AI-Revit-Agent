// UI store — owns sidebar, settings panel, and Revit bridge connection state.
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { RevitStatus } from '@/types';

interface UIState {
  sidebarOpen: boolean;
  settingsPanelOpen: boolean;
  revitStatus: RevitStatus;
  revitToolCount: number | null;
}

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
