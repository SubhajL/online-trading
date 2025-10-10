'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'
import styles from './settings.module.css'

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
    <div className={styles.appLayout}>
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className={styles.appBody}>
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className={styles.appMain} tabIndex={-1}>
          <div className={styles.pageContainer}>
            <h1 className={styles.pageTitle}>Settings</h1>

            <div className={styles.settingsContainer}>
              <div className={styles.settingsTabs}>
                <button
                  className={`${styles.tab} ${activeTab === 'general' ? styles.active : ''}`}
                  onClick={() => setActiveTab('general')}
                >
                  General
                </button>
                <button
                  className={`${styles.tab} ${activeTab === 'trading' ? styles.active : ''}`}
                  onClick={() => setActiveTab('trading')}
                >
                  Trading
                </button>
                <button
                  className={`${styles.tab} ${activeTab === 'notifications' ? styles.active : ''}`}
                  onClick={() => setActiveTab('notifications')}
                >
                  Notifications
                </button>
                <button
                  className={`${styles.tab} ${activeTab === 'api' ? styles.active : ''}`}
                  onClick={() => setActiveTab('api')}
                >
                  API Keys
                </button>
              </div>

              <div className={styles.settingsContent}>
                {activeTab === 'general' && (
                  <div className={styles.settingsSection}>
                    <h2>General Settings</h2>
                    <div className={styles.settingItem}>
                      <label>Theme</label>
                      <select
                        value={settings.general.theme}
                        onChange={e => handleSettingChange('general', 'theme', e.target.value)}
                      >
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                      </select>
                    </div>
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                  <div className={styles.settingsSection}>
                    <h2>Trading Settings</h2>
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                  <div className={styles.settingsSection}>
                    <h2>Notification Settings</h2>
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                    <div className={styles.settingItem}>
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
                  <div className={styles.settingsSection}>
                    <h2>API Configuration</h2>
                    <div className={styles.apiStatus}>
                      <div className={styles.statusItem}>
                        <span>Spot Trading</span>
                        <span
                          className={`${styles.status} ${settings.api.spotConnected ? styles.connected : styles.disconnected}`}
                        >
                          {settings.api.spotConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                      <div className={styles.statusItem}>
                        <span>Futures Trading</span>
                        <span
                          className={`${styles.status} ${settings.api.futuresConnected ? styles.connected : styles.disconnected}`}
                        >
                          {settings.api.futuresConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                    </div>
                    <div className={styles.settingItem}>
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
                    <div className={styles.apiKeysSection}>
                      <h3>API Keys</h3>
                      <p className={styles.warning}>⚠️ Never share your API keys with anyone</p>
                      <div className={styles.keyInputGroup}>
                        <label>Spot API Key</label>
                        <input type="password" placeholder="Enter your Spot API key" disabled />
                        <button
                          className={styles.updateBtn}
                          onClick={() => console.warn('TODO: Update Spot API key')}
                        >
                          Update
                        </button>
                      </div>
                      <div className={styles.keyInputGroup}>
                        <label>Spot Secret Key</label>
                        <input type="password" placeholder="Enter your Spot secret key" disabled />
                        <button
                          className={styles.updateBtn}
                          onClick={() => console.warn('TODO: Update Spot secret key')}
                        >
                          Update
                        </button>
                      </div>
                      <div className={styles.keyInputGroup}>
                        <label>Futures API Key</label>
                        <input type="password" placeholder="Enter your Futures API key" disabled />
                        <button
                          className={styles.updateBtn}
                          onClick={() => console.warn('TODO: Update Futures API key')}
                        >
                          Update
                        </button>
                      </div>
                      <div className={styles.keyInputGroup}>
                        <label>Futures Secret Key</label>
                        <input
                          type="password"
                          placeholder="Enter your Futures secret key"
                          disabled
                        />
                        <button
                          className={styles.updateBtn}
                          onClick={() => console.warn('TODO: Update Futures secret key')}
                        >
                          Update
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className={styles.settingsActions}>
                <button
                  className={styles.saveBtn}
                  onClick={() => console.warn('TODO: Save settings to BFF')}
                >
                  Save Changes
                </button>
                <button
                  className={styles.cancelBtn}
                  onClick={() => console.warn('TODO: Reset settings')}
                >
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
