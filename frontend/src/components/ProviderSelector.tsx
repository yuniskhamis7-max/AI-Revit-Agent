import React, { useCallback } from 'react';
import { useProviderStore } from '@/store/providerStore';
import { providersApi } from '@/api/settings';
import type { Provider } from '@/types';

/**
 * ProviderSelector — dropdown controls for selecting AI provider and model.
 *
 * Renders two <select> elements in the app header:
 * - Provider dropdown: lists all configured providers with their status
 * - Model dropdown: lists available models for the selected provider
 *
 * Selection changes are immediately persisted to the backend via PUT /api/providers.
 *
 * @component
 */
export const ProviderSelector: React.FC = () => {
  const { providers, activeProvider, activeModel, setActiveProvider, setProviders } = useProviderStore();

  const currentProvider = providers.find((p: Provider) => p.name === activeProvider);

  const handleProviderChange = useCallback(async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const provName = e.target.value;
    const prov = providers.find((p: Provider) => p.name === provName);
    if (!prov) return;

    const model = prov.active_model ?? prov.models[0] ?? '';
    setActiveProvider(provName, model);

    // Persist the provider activation to the backend
    try {
      const updated = await providersApi.update(provName, {
        active: true,
        active_model: model,
      });
      // Refresh provider list from backend (with dynamic models)
      const refreshed = await providersApi.refreshModels();
      setProviders(refreshed);
      // Re-select in case models changed
      setActiveProvider(updated.name, updated.active_model ?? model);
    } catch (err) {
      console.error('Failed to persist provider selection:', err);
    }
  }, [providers, setActiveProvider, setProviders]);

  const handleModelChange = useCallback(async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const model = e.target.value;
    setActiveProvider(activeProvider, model);

    // Persist the model selection to the backend
    try {
      await providersApi.update(activeProvider, {
        active_model: model,
        active: true,
      });
    } catch (err) {
      console.error('Failed to persist model selection:', err);
    }
  }, [activeProvider, setActiveProvider]);

  return (
    <div className="provider-selector-container">
      <div className="selector-group">
        <label htmlFor="provider-select">AI Provider</label>
        <select
          id="provider-select"
          className="select-input"
          value={activeProvider}
          onChange={handleProviderChange}
        >
          {providers.map((p: Provider) => (
            <option key={p.name} value={p.name}>
              {p.label} {!p.configured ? '(No API Key)' : ''}
            </option>
          ))}
        </select>
      </div>

      {currentProvider && currentProvider.models.length > 0 && (
        <div className="selector-group">
          <label htmlFor="model-select">Model</label>
          <select
            id="model-select"
            className="select-input"
            value={activeModel}
            onChange={handleModelChange}
          >
            {currentProvider.models.map((m: string) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
};
