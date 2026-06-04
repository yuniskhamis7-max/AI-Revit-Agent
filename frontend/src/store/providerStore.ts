// Provider store — owns AI provider list, active provider, and active model.
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { Provider } from '@/types';

interface ProviderState {
  providers: Provider[];
  activeProvider: string;
  activeModel: string;
}

interface ProviderActions {
  setProviders: (providers: Provider[]) => void;
  setActiveProvider: (provider: string, model: string) => void;
}

/** Guard against [object Object] serialisation artifacts from React state */
function sanitiseModel(m: unknown, fallback: string): string {
  if (typeof m !== 'string' || m.includes('[object') || !m.trim()) return fallback;
  return m.trim();
}

export const useProviderStore = create<ProviderState & ProviderActions>()(
  immer((set) => ({
    providers: [],
    activeProvider: 'gemini',
    activeModel: 'gemini-2.5-flash',

    setProviders: (providers) =>
      set((s) => {
        s.providers = providers;
        const active = providers.find((p) => p.active);
        if (active) {
          s.activeProvider = active.name;
          s.activeModel = sanitiseModel(active.active_model, active.models[0] ?? '');
        }
      }),

    setActiveProvider: (provider, model) =>
      set((s) => {
        s.activeProvider = provider;
        s.activeModel = sanitiseModel(model, '');
      }),
  })),
);
