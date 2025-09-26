'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'

export default function SettingsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeTab, setActiveTab] = useState<'general' | 'trading' | 'notifications' | 'api'>('general')

  // Mock settings data
  const [settings, setSettings] = useState({
    general: {
      theme: 'dark',
      timezone: 'UTC',
      language: 'en',
    },
    trading: {
      defaultVenue: 'SPOT',
      defaultLeverage: 1,
      confirmOrders: true,
      maxPositionSize: 1000,
      defaultStopLoss: 2,
      defaultTakeProfit: 4,
    },
    notifications: {
      emailAlerts: true,
      pushNotifications: false,
      tradeExecutions: true,
      priceAlerts: true,
      systemAlerts: true,
    },
    api: {
      spotConnected: true,
      futuresConnected: false,
      testnetMode: false,
    },
  })

  const handleSettingChange = (category: string, key: string, value: any) => {
    setSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category as keyof typeof prev],
        [key]: value,
      },
    }))
  }

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main className="app-main">
          <div className="page-container">
            <h1 className="page-title">Settings</h1>

            <div className="settings-container">
              <div className="settings-tabs">
                <button
                  className={`tab ${activeTab === 'general' ? 'active' : ''}`}
                  onClick={() => setActiveTab('general')}
                >
                  General
                </button>
                <button
                  className={`tab ${activeTab === 'trading' ? 'active' : ''}`}
                  onClick={() => setActiveTab('trading')}
                >
                  Trading
                </button>
                <button
                  className={`tab ${activeTab === 'notifications' ? 'active' : ''}`}
                  onClick={() => setActiveTab('notifications')}
                >
                  Notifications
                </button>
                <button
                  className={`tab ${activeTab === 'api' ? 'active' : ''}`}
                  onClick={() => setActiveTab('api')}
                >
                  API Keys
                </button>
              </div>

              <div className="settings-content">
                {activeTab === 'general' && (
                  <div className="settings-section">
                    <h2>General Settings</h2>
                    <div className="setting-item">
                      <label>Theme</label>
                      <select
                        value={settings.general.theme}
                        onChange={(e) => handleSettingChange('general', 'theme', e.target.value)}
                      >
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                      </select>
                    </div>
                    <div className="setting-item">
                      <label>Timezone</label>
                      <select
                        value={settings.general.timezone}
                        onChange={(e) => handleSettingChange('general', 'timezone', e.target.value)}
                      >
                        <option value="UTC">UTC</option>
                        <option value="America/New_York">Eastern Time</option>
                        <option value="America/Chicago">Central Time</option>
                        <option value="America/Los_Angeles">Pacific Time</option>
                        <option value="Europe/London">London</option>
                        <option value="Asia/Tokyo">Tokyo</option>
                      </select>
                    </div>
                    <div className="setting-item">
                      <label>Language</label>
                      <select
                        value={settings.general.language}
                        onChange={(e) => handleSettingChange('general', 'language', e.target.value)}
                      >
                        <option value="en">English</option>
                        <option value="es">Spanish</option>
                        <option value="fr">French</option>
                        <option value="de">German</option>
                        <option value="zh">Chinese</option>
                        <option value="ja">Japanese</option>
                      </select>
                    </div>
                  </div>
                )}

                {activeTab === 'trading' && (
                  <div className="settings-section">
                    <h2>Trading Settings</h2>
                    <div className="setting-item">
                      <label>Default Venue</label>
                      <select
                        value={settings.trading.defaultVenue}
                        onChange={(e) => handleSettingChange('trading', 'defaultVenue', e.target.value)}
                      >
                        <option value="SPOT">Spot</option>
                        <option value="FUTURES">Futures</option>
                      </select>
                    </div>
                    <div className="setting-item">
                      <label>Default Leverage</label>
                      <input
                        type="number"
                        min="1"
                        max="125"
                        value={settings.trading.defaultLeverage}
                        onChange={(e) => handleSettingChange('trading', 'defaultLeverage', parseInt(e.target.value))}
                      />
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.trading.confirmOrders}
                          onChange={(e) => handleSettingChange('trading', 'confirmOrders', e.target.checked)}
                        />
                        Confirm orders before submission
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>Max Position Size (USDT)</label>
                      <input
                        type="number"
                        value={settings.trading.maxPositionSize}
                        onChange={(e) => handleSettingChange('trading', 'maxPositionSize', parseInt(e.target.value))}
                      />
                    </div>
                    <div className="setting-item">
                      <label>Default Stop Loss (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={settings.trading.defaultStopLoss}
                        onChange={(e) => handleSettingChange('trading', 'defaultStopLoss', parseFloat(e.target.value))}
                      />
                    </div>
                    <div className="setting-item">
                      <label>Default Take Profit (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={settings.trading.defaultTakeProfit}
                        onChange={(e) => handleSettingChange('trading', 'defaultTakeProfit', parseFloat(e.target.value))}
                      />
                    </div>
                  </div>
                )}

                {activeTab === 'notifications' && (
                  <div className="settings-section">
                    <h2>Notification Settings</h2>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.emailAlerts}
                          onChange={(e) => handleSettingChange('notifications', 'emailAlerts', e.target.checked)}
                        />
                        Email Alerts
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.pushNotifications}
                          onChange={(e) => handleSettingChange('notifications', 'pushNotifications', e.target.checked)}
                        />
                        Push Notifications
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.tradeExecutions}
                          onChange={(e) => handleSettingChange('notifications', 'tradeExecutions', e.target.checked)}
                        />
                        Trade Execution Alerts
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.priceAlerts}
                          onChange={(e) => handleSettingChange('notifications', 'priceAlerts', e.target.checked)}
                        />
                        Price Alerts
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.systemAlerts}
                          onChange={(e) => handleSettingChange('notifications', 'systemAlerts', e.target.checked)}
                        />
                        System Alerts
                      </label>
                    </div>
                  </div>
                )}

                {activeTab === 'api' && (
                  <div className="settings-section">
                    <h2>API Configuration</h2>
                    <div className="api-status">
                      <div className="status-item">
                        <span>Spot Trading</span>
                        <span className={`status ${settings.api.spotConnected ? 'connected' : 'disconnected'}`}>
                          {settings.api.spotConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                      <div className="status-item">
                        <span>Futures Trading</span>
                        <span className={`status ${settings.api.futuresConnected ? 'connected' : 'disconnected'}`}>
                          {settings.api.futuresConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.api.testnetMode}
                          onChange={(e) => handleSettingChange('api', 'testnetMode', e.target.checked)}
                        />
                        Testnet Mode
                      </label>
                    </div>
                    <div className="api-keys-section">
                      <h3>API Keys</h3>
                      <p className="warning">⚠️ Never share your API keys with anyone</p>
                      <div className="key-input-group">
                        <label>Spot API Key</label>
                        <input type="password" placeholder="Enter your Spot API key" disabled />
                        <button className="update-btn" onClick={() => console.warn('TODO: Update Spot API key')}>
                          Update
                        </button>
                      </div>
                      <div className="key-input-group">
                        <label>Spot Secret Key</label>
                        <input type="password" placeholder="Enter your Spot secret key" disabled />
                        <button className="update-btn" onClick={() => console.warn('TODO: Update Spot secret key')}>
                          Update
                        </button>
                      </div>
                      <div className="key-input-group">
                        <label>Futures API Key</label>
                        <input type="password" placeholder="Enter your Futures API key" disabled />
                        <button className="update-btn" onClick={() => console.warn('TODO: Update Futures API key')}>
                          Update
                        </button>
                      </div>
                      <div className="key-input-group">
                        <label>Futures Secret Key</label>
                        <input type="password" placeholder="Enter your Futures secret key" disabled />
                        <button className="update-btn" onClick={() => console.warn('TODO: Update Futures secret key')}>
                          Update
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="settings-actions">
                <button className="save-btn" onClick={() => console.warn('TODO: Save settings to BFF')}>
                  Save Changes
                </button>
                <button className="cancel-btn" onClick={() => console.warn('TODO: Reset settings')}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>

      <style jsx>{`
        .app-layout {
          display: flex;
          flex-direction: column;
          min-height: 100vh;
        }

        .app-body {
          display: flex;
          flex: 1;
        }

        .app-main {
          flex: 1;
          overflow-x: auto;
        }

        .page-container {
          padding: 2rem;
        }

        .page-title {
          margin-bottom: 2rem;
          color: #f0f0f0;
        }

        .settings-container {
          background: #2a2d3a;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
          overflow: hidden;
        }

        .settings-tabs {
          display: flex;
          border-bottom: 1px solid #3a3d4a;
          background: #1a1d2a;
        }

        .tab {
          padding: 1rem 2rem;
          background: transparent;
          border: none;
          color: #9ca3af;
          cursor: pointer;
          transition: all 0.2s;
          font-size: 0.875rem;
          font-weight: 500;
        }

        .tab:hover {
          background: #2a2d3a;
          color: #f0f0f0;
        }

        .tab.active {
          background: #2a2d3a;
          color: #4f46e5;
          border-bottom: 2px solid #4f46e5;
        }

        .settings-content {
          padding: 2rem;
          min-height: 400px;
        }

        .settings-section h2 {
          margin-bottom: 1.5rem;
          color: #f0f0f0;
        }

        .setting-item {
          margin-bottom: 1.5rem;
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .setting-item label {
          color: #9ca3af;
          min-width: 200px;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .setting-item input[type="text"],
        .setting-item input[type="number"],
        .setting-item input[type="password"],
        .setting-item select {
          padding: 0.5rem 0.75rem;
          background: #1a1d2a;
          border: 1px solid #3a3d4a;
          color: #f0f0f0;
          border-radius: 0.25rem;
          min-width: 200px;
        }

        .setting-item input[type="checkbox"] {
          width: auto;
          margin: 0;
        }

        .api-status {
          margin-bottom: 2rem;
          padding: 1rem;
          background: #1a1d2a;
          border-radius: 0.25rem;
        }

        .status-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.75rem;
          color: #9ca3af;
        }

        .status-item:last-child {
          margin-bottom: 0;
        }

        .status {
          padding: 0.25rem 0.75rem;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          font-weight: 500;
        }

        .status.connected {
          background: #065f46;
          color: #34d399;
        }

        .status.disconnected {
          background: #7f1d1d;
          color: #fca5a5;
        }

        .warning {
          background: #78350f;
          color: #fbbf24;
          padding: 0.75rem 1rem;
          border-radius: 0.25rem;
          margin-bottom: 1rem;
          font-size: 0.875rem;
        }

        .api-keys-section h3 {
          margin-bottom: 1rem;
          color: #f0f0f0;
        }

        .key-input-group {
          display: flex;
          align-items: center;
          gap: 1rem;
          margin-bottom: 1rem;
        }

        .key-input-group label {
          min-width: 150px;
          color: #9ca3af;
        }

        .key-input-group input {
          flex: 1;
        }

        .update-btn {
          padding: 0.5rem 1rem;
          background: #4f46e5;
          color: white;
          border: none;
          border-radius: 0.25rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .update-btn:hover {
          background: #4338ca;
        }

        .settings-actions {
          padding: 1.5rem 2rem;
          border-top: 1px solid #3a3d4a;
          display: flex;
          gap: 1rem;
          justify-content: flex-end;
        }

        .save-btn {
          padding: 0.75rem 2rem;
          background: #4f46e5;
          color: white;
          border: none;
          border-radius: 0.25rem;
          cursor: pointer;
          transition: all 0.2s;
          font-weight: 500;
        }

        .save-btn:hover {
          background: #4338ca;
        }

        .cancel-btn {
          padding: 0.75rem 2rem;
          background: transparent;
          color: #9ca3af;
          border: 1px solid #3a3d4a;
          border-radius: 0.25rem;
          cursor: pointer;
          transition: all 0.2s;
          font-weight: 500;
        }

        .cancel-btn:hover {
          background: #3a3d4a;
          color: #f0f0f0;
        }
      `}</style>
    </div>
  )
}