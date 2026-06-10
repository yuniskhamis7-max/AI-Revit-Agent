import { api } from './client';
import type { Provider } from '@/types';

/**
 * Provider, Settings, and Revit bridge API clients.
 *
 * Typed wrappers for managing AI provider configuration, application
 * settings, and the Revit bridge connection status.
 */

/**
 * AI provider management API.
 *
 * @property list          - Fetch all providers with their DB config state.
 * @property refreshModels - Re-fetch models from providers (dynamic for Gemini).
 * @property getMaskedKey  - Fetch a masked version of a provider's API key.
 * @property update        - Update a provider's API key, active model, or active status.
 */
export const providersApi = {
  list: ()                                             => api.get<Provider[]>('/providers'),
  refreshModels: ()                                    => api.get<Provider[]>('/providers/models'),
  getMaskedKey: (name: string)                         => api.get<{ masked_key: string | null }>(`/providers/${name}/key`),
  update: (name: string, payload: {
    api_key?: string;
    active_model?: string;
    active?: boolean;
  })                                                   => api.put<Provider>(`/providers/${name}`, payload),
};

/**
 * Application settings API (key/value store for frontend preferences).
 *
 * @property getAll - Fetch all settings as a {key: value} dict.
 * @property upsert - Bulk insert or update settings. Existing keys not in
 *                    the payload are left unchanged.
 */
export const settingsApi = {
  getAll:  ()                                          => api.get<Record<string, string>>('/settings'),
  upsert:  (settings: Record<string, string>)          => api.put<Record<string, string>>('/settings', { settings }),
};

/**
 * Revit bridge status and tool management API.
 *
 * @property status       - Health check with auto-recovery. Returns connection
 *                          status and number of registered tools.
 * @property refreshTools - Force a fresh tool discovery from the bridge.
 *                          Returns status, count, and list of tool names.
 */
export const revitApi = {
  status: ()                                           => api.get<{ connected: boolean; tool_count: number }>('/revit/status'),
  refreshTools: ()                                     => api.post<{ status: string; tool_count: number; tools: string[] }>('/revit/refresh-tools', {}),
};
