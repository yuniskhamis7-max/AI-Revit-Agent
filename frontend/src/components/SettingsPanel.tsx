import React, { useState, useEffect } from 'react';
import { useChatStore } from '@/store/chatStore';
import { providersApi } from '@/api/settings';
import type { Provider } from '@/types';

export const SettingsPanel: React.FC = () => {
  const { settingsPanelOpen, setSettingsPanelOpen, providers, setProviders } = useChatStore();
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [maskedKeys, setMaskedKeys] = useState<Record<string, string | null>>({});
  const [isSaving, setIsSaving] = useState<Record<string, boolean>>({});
  const [saveStatus, setSaveStatus] = useState<Record<string, string>>({});
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Initialize keys empty; masked keys will be fetched on eye click
  useEffect(() => {
    const initialKeys: Record<string, string> = {};
    providers.forEach((p: Provider) => {
      initialKeys[p.name] = '';
    });
    setKeys(initialKeys);
    setMaskedKeys({});
    setVisibleKeys({});
  }, [providers]);

  // Refresh provider list (with dynamic models) when panel opens
  useEffect(() => {
    if (settingsPanelOpen) {
      const refresh = async () => {
        setIsRefreshing(true);
        try {
          const refreshed = await providersApi.refreshModels();
          setProviders(refreshed);
        } catch (err) {
          console.error('Failed to refresh providers:', err);
        } finally {
          setIsRefreshing(false);
        }
      };
      refresh();
    }
  }, [settingsPanelOpen, setProviders]);

  if (!settingsPanelOpen) return null;

  const handleKeyChange = (providerName: string, val: string) => {
    setKeys((prev) => ({ ...prev, [providerName]: val }));
    // If user starts typing, hide the masked key display
    if (val.length > 0 && maskedKeys[providerName]) {
      setMaskedKeys((prev) => ({ ...prev, [providerName]: null }));
    }
  };

  const toggleVisibility = async (providerName: string) => {
    const isVisible = visibleKeys[providerName] || false;

    // If showing the key and user hasn't typed anything, hide the masked key
    if (isVisible && !keys[providerName]) {
      setVisibleKeys((prev) => ({ ...prev, [providerName]: false }));
      setMaskedKeys((prev) => ({ ...prev, [providerName]: null }));
      return;
    }

    // If hiding and provider is configured, fetch masked key first
    if (!isVisible && maskedKeys[providerName] === undefined) {
      try {
        const result = await providersApi.getMaskedKey(providerName);
        setMaskedKeys((prev) => ({ ...prev, [providerName]: result.masked_key }));
      } catch (err) {
        console.error('Failed to fetch masked key:', err);
      }
    }

    setVisibleKeys((prev) => ({ ...prev, [providerName]: !prev[providerName] }));
  };

  const handleSaveKey = async (providerName: string) => {
    const key = keys[providerName]?.trim();
    if (!key) return;

    setIsSaving((prev) => ({ ...prev, [providerName]: true }));
    setSaveStatus((prev) => ({ ...prev, [providerName]: '' }));

    try {
      const updatedProvider = await providersApi.update(providerName, {
        api_key: key,
      });

      const updatedList = providers.map((p: Provider) =>
        p.name === providerName ? { ...p, configured: updatedProvider.configured } : p
      );
      setProviders(updatedList);

      setSaveStatus((prev) => ({ ...prev, [providerName]: 'saved' }));
      // Clear key input and cached masked key after success
      setKeys((prev) => ({ ...prev, [providerName]: '' }));
      setMaskedKeys((prev) => ({ ...prev, [providerName]: null }));
      setVisibleKeys((prev) => ({ ...prev, [providerName]: false }));
    } catch (err: any) {
      console.error(err);
      setSaveStatus((prev) => ({ ...prev, [providerName]: 'error' }));
    } finally {
      setIsSaving((prev) => ({ ...prev, [providerName]: false }));
    }
  };

  return (
    <div className="settings-drawer-backdrop" onClick={() => setSettingsPanelOpen(false)}>
      <div className="settings-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h3>Configuration</h3>
          <button className="close-drawer-btn" onClick={() => setSettingsPanelOpen(false)}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          <div className="settings-section">
            <h4>API Keys</h4>
            <p className="settings-help-text">
              Enter your API keys below. They are saved in a local SQLite database on your machine.
              {isRefreshing && <span style={{ color: 'var(--color-info)', marginLeft: '8px' }}>Refreshing models...</span>}
            </p>

            {providers.map((p: Provider) => {
              const isTyping = (keys[p.name] || '').length > 0;
              const isVisible = visibleKeys[p.name] || false;
              // Show masked key when visibility is toggled and user hasn't typed
              const displayValue = !isTyping && isVisible && maskedKeys[p.name]
                ? maskedKeys[p.name]!
                : (keys[p.name] || '');
              const saving = isSaving[p.name] || false;
              const status = saveStatus[p.name] || '';

              return (
                <div key={p.name} className="provider-key-card">
                  <div className="provider-key-header">
                    <span className="provider-label">{p.label}</span>
                    <span className={`config-badge ${p.configured ? 'configured' : 'missing'}`}>
                      {p.configured ? 'Configured' : 'No Key'}
                    </span>
                  </div>

                  <div className="provider-key-input-row">
                    <input
                      type={isVisible ? 'text' : 'password'}
                      className="text-input"
                      placeholder={p.configured ? '•••••••••••••••••••• (click eye to reveal)' : 'Enter API Key'}
                      value={displayValue}
                      onChange={(e) => handleKeyChange(p.name, e.target.value)}
                    />
                    
                    <button
                      className="visibility-btn"
                      onClick={() => toggleVisibility(p.name)}
                      title={isVisible ? 'Hide Key' : 'Show Key'}
                      disabled={!p.configured && !isTyping}
                    >
                      {isVisible ? '👁️' : '👁️‍🗨️'}
                    </button>
                    
                    <button
                      className="save-key-btn"
                      disabled={!isTyping || saving}
                      onClick={() => handleSaveKey(p.name)}
                    >
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                  </div>

                  {status === 'saved' && (
                    <div className="status-msg success">API key saved successfully!</div>
                  )}
                  {status === 'error' && (
                    <div className="status-msg error">Failed to save key. Verify format.</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
