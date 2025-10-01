'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'

export default function SettingsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeTab, setActiveTab] = useState<'general' | 'trading' | 'notifications' | 'api'>(
    'general',
  )

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

  const handleSettingChange = (category: string, key: string, value: string | number | boolean) => {
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

        <main id="main-content" className="app-main" tabIndex={-1}>
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
                        onChange={e => handleSettingChange('general', 'theme', e.target.value)}
                      >
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                      </select>
                    </div>
                    <div className="setting-item">
                      <label>Timezone</label>
                      <select
                        value={settings.general.timezone}
                        onChange={e => handleSettingChange('general', 'timezone', e.target.value)}
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
                        onChange={e => handleSettingChange('general', 'language', e.target.value)}
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
                        onChange={e =>
                          handleSettingChange('trading', 'defaultVenue', e.target.value)
                        }
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
                        onChange={e =>
                          handleSettingChange(
                            'trading',
                            'defaultLeverage',
                            parseInt(e.target.value),
                          )
                        }
                      />
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.trading.confirmOrders}
                          onChange={e =>
                            handleSettingChange('trading', 'confirmOrders', e.target.checked)
                          }
                        />
                        Confirm orders before submission
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>Max Position Size (USDT)</label>
                      <input
                        type="number"
                        value={settings.trading.maxPositionSize}
                        onChange={e =>
                          handleSettingChange(
                            'trading',
                            'maxPositionSize',
                            parseInt(e.target.value),
                          )
                        }
                      />
                    </div>
                    <div className="setting-item">
                      <label>Default Stop Loss (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={settings.trading.defaultStopLoss}
                        onChange={e =>
                          handleSettingChange(
                            'trading',
                            'defaultStopLoss',
                            parseFloat(e.target.value),
                          )
                        }
                      />
                    </div>
                    <div className="setting-item">
                      <label>Default Take Profit (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={settings.trading.defaultTakeProfit}
                        onChange={e =>
                          handleSettingChange(
                            'trading',
                            'defaultTakeProfit',
                            parseFloat(e.target.value),
                          )
                        }
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
                          onChange={e =>
                            handleSettingChange('notifications', 'emailAlerts', e.target.checked)
                          }
                        />
                        Email Alerts
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.pushNotifications}
                          onChange={e =>
                            handleSettingChange(
                              'notifications',
                              'pushNotifications',
                              e.target.checked,
                            )
                          }
                        />
                        Push Notifications
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.tradeExecutions}
                          onChange={e =>
                            handleSettingChange(
                              'notifications',
                              'tradeExecutions',
                              e.target.checked,
                            )
                          }
                        />
                        Trade Execution Alerts
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.priceAlerts}
                          onChange={e =>
                            handleSettingChange('notifications', 'priceAlerts', e.target.checked)
                          }
                        />
                        Price Alerts
                      </label>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.notifications.systemAlerts}
                          onChange={e =>
                            handleSettingChange('notifications', 'systemAlerts', e.target.checked)
                          }
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
                        <span
                          className={`status ${settings.api.spotConnected ? 'connected' : 'disconnected'}`}
                        >
                          {settings.api.spotConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                      <div className="status-item">
                        <span>Futures Trading</span>
                        <span
                          className={`status ${settings.api.futuresConnected ? 'connected' : 'disconnected'}`}
                        >
                          {settings.api.futuresConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                    </div>
                    <div className="setting-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={settings.api.testnetMode}
                          onChange={e =>
                            handleSettingChange('api', 'testnetMode', e.target.checked)
                          }
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
                        <button
                          className="update-btn"
                          onClick={() => console.warn('TODO: Update Spot API key')}
                        >
                          Update
                        </button>
                      </div>
                      <div className="key-input-group">
                        <label>Spot Secret Key</label>
                        <input type="password" placeholder="Enter your Spot secret key" disabled />
                        <button
                          className="update-btn"
                          onClick={() => console.warn('TODO: Update Spot secret key')}
                        >
                          Update
                        </button>
                      </div>
                      <div className="key-input-group">
                        <label>Futures API Key</label>
                        <input type="password" placeholder="Enter your Futures API key" disabled />
                        <button
                          className="update-btn"
                          onClick={() => console.warn('TODO: Update Futures API key')}
                        >
                          Update
                        </button>
                      </div>
                      <div className="key-input-group">
                        <label>Futures Secret Key</label>
                        <input
                          type="password"
                          placeholder="Enter your Futures secret key"
                          disabled
                        />
                        <button
                          className="update-btn"
                          onClick={() => console.warn('TODO: Update Futures secret key')}
                        >
                          Update
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="settings-actions">
                <button
                  className="save-btn"
                  onClick={() => console.warn('TODO: Save settings to BFF')}
                >
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
    </div>
  )
}
