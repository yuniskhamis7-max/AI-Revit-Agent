import { api } from './client';
import type { Provider } from '@/types';

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

export const settingsApi = {
  getAll:  ()                                          => api.get<Record<string, string>>('/settings'),
  upsert:  (settings: Record<string, string>)          => api.put<Record<string, string>>('/settings', { settings }),
};

export const revitApi = {
  status: ()                                           => api.get<{ connected: boolean; tool_count: number }>('/revit/status'),
  refreshTools: ()                                     => api.post<{ status: string; tool_count: number; tools: string[] }>('/revit/refresh-tools', {}),
};
