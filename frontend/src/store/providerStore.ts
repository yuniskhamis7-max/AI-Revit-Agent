/**
 * Provider store — owns AI provider list, active provider, and active model.
 *
 * Tracks which AI provider and model are currently selected. When providers
 * are loaded from the backend, the store automatically activates the one
 * marked as active in the database.
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { Provider } from '@/types';

/**
 * Provider state shape.
 *
 * @property providers      - List of all supported providers with their config state.
 * @property activeProvider - Internal name of the currently selected provider (e.g. 'gemini').
 * @property activeModel    - Model ID currently in use (e.g. 'gemini-2.5-flash').
 */
interface ProviderState {
  providers: Provider[];
  activeProvider: string;
  activeModel: string;
}

/**
 * Provider actions.
 *
 * @property setProviders      - Replace the provider list and auto-activate the marked one.
 * @property setActiveProvider - Manually select a provider and model pair.
 */
interface ProviderActions {
  setProviders: (providers: Provider[]) => void;
  setActiveProvider: (provider: string, model: string) => void;
}

/**
 * Guard against [object Object] serialisation artifacts from React state.
 *
 * @param m        - Raw model value that may be a string or artifact.
 * @param fallback - Default model ID to use if m is invalid.
 * @returns Sanitised model ID string.
 */
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
