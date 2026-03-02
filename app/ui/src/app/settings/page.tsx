'use client'

import { useState } from 'react'
import { AppShell } from '@/components/shell'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { MaterialIcon } from '@/components/common/MaterialIcon'
import { PageHeader } from '@/components/common/PageHeader'
import { IntegrationPill } from '@/components/common/IntegrationPill'
import { cn } from '@/lib/utils'
import { isUiRevampEnabled } from '@/config/ui-flags'

const NAV_SECTIONS = [
  { id: 'profile', label: 'Profile', icon: 'person' },
  { id: 'security', label: 'Security', icon: 'shield' },
  { id: 'api', label: 'API Keys', icon: 'key' },
  { id: 'notifications', label: 'Notifications', icon: 'notifications' },
  { id: 'trading', label: 'Trading Preferences', icon: 'candlestick_chart' },
  { id: 'appearance', label: 'Appearance', icon: 'palette' },
  { id: 'danger', label: 'Danger Zone', icon: 'warning' },
] as const

type SectionId = (typeof NAV_SECTIONS)[number]['id']

export default function SettingsPage() {
  const revamp = isUiRevampEnabled()
  const [activeSection, setActiveSection] = useState<SectionId>(revamp ? 'api' : 'profile')
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
  const sectionCardClass = revamp
    ? 'bg-[#1A1A2E] border-[#232348] rounded-[18px] text-slate-100 shadow-[0_12px_30px_rgba(0,0,0,0.35)]'
    : 'bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-soft'

  return (
    <AppShell>
      <div className={revamp ? 'flex flex-col gap-6 text-slate-100' : 'flex flex-col gap-8'}>
        <PageHeader
          title="Settings"
          actions={<IntegrationPill transport="REST" endpoint="/settings/preferences" />}
        />

        {revamp && (
          <div className="flex flex-wrap items-center gap-2">
            <IntegrationPill transport="REST" endpoint="/settings/preferences" />
            <IntegrationPill transport="REST" endpoint="/settings/api-keys" />
            <IntegrationPill transport="REST" endpoint="/settings/notifications" />
          </div>
        )}

        {/* Spec §6.6: Sidebar + Content layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Sidebar (col-3) */}
          <nav className="lg:col-span-3" aria-label="Settings navigation">
            <div className="flex flex-col gap-1">
              {NAV_SECTIONS.map(section => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-xl text-left text-sm font-medium transition-colors',
                    activeSection === section.id
                      ? 'bg-primary/10 text-primary dark:bg-primary/20'
                      : revamp
                        ? 'text-slate-400 hover:bg-[#1A1A2E] hover:text-slate-100'
                        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800',
                    section.id === 'danger' &&
                      activeSection !== 'danger' &&
                      'text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30',
                    section.id === 'danger' &&
                      activeSection === 'danger' &&
                      'bg-red-500/10 text-red-500 dark:bg-red-500/20 dark:text-red-400',
                  )}
                >
                  <MaterialIcon
                    name={section.icon}
                    size="md"
                    className={cn(
                      section.id === 'danger' && activeSection !== 'danger' && 'text-red-500',
                    )}
                  />
                  {section.label}
                </button>
              ))}
            </div>
          </nav>

          {/* Content (col-9) */}
          <div className="lg:col-span-9">
            {/* Profile Section */}
            {activeSection === 'profile' && (
              <Card className={sectionCardClass}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
                    Profile Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="display-name">Display Name</Label>
                    <Input
                      id="display-name"
                      placeholder="Enter your display name"
                      className="w-full max-w-md"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="email">Email Address</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="your@email.com"
                      className="w-full max-w-md"
                    />
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Security Section */}
            {activeSection === 'security' && (
              <Card className={sectionCardClass}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
                    Security Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="current-password">Current Password</Label>
                    <Input
                      id="current-password"
                      type="password"
                      placeholder="Enter current password"
                      className="w-full max-w-md"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="new-password">New Password</Label>
                    <Input
                      id="new-password"
                      type="password"
                      placeholder="Enter new password"
                      className="w-full max-w-md"
                    />
                  </div>
                  <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-800 max-w-md">
                    <div>
                      <Label htmlFor="2fa">Two-Factor Authentication</Label>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Add an extra layer of security
                      </p>
                    </div>
                    <Switch id="2fa" />
                  </div>
                </CardContent>
              </Card>
            )}

            {/* API Keys Section */}
            {activeSection === 'api' && (
              <div className="flex flex-col gap-5">
                {/* Connection Status */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <Card className={sectionCardClass}>
                    <CardContent className="flex items-center justify-between p-5">
                      <div className="flex items-center gap-3">
                        <MaterialIcon name="shield" size="lg" className="text-slate-400" />
                        <div>
                          <p className="text-sm font-medium">Spot Trading</p>
                          <p className="text-xs text-slate-400">Last verified: 2 min ago</p>
                        </div>
                      </div>
                      <Badge
                        variant={settings.api.spotConnected ? 'default' : 'destructive'}
                        className={
                          settings.api.spotConnected
                            ? 'bg-success/15 text-success border-success/30'
                            : ''
                        }
                      >
                        {settings.api.spotConnected ? 'Connected' : 'Disconnected'}
                      </Badge>
                    </CardContent>
                  </Card>
                  <Card className={sectionCardClass}>
                    <CardContent className="flex items-center justify-between p-5">
                      <div className="flex items-center gap-3">
                        <MaterialIcon name="shield" size="lg" className="text-slate-400" />
                        <div>
                          <p className="text-sm font-medium">Futures Trading</p>
                          <p className="text-xs text-slate-400">Last verified: 2 min ago</p>
                        </div>
                      </div>
                      <Badge
                        variant={settings.api.futuresConnected ? 'default' : 'destructive'}
                        className={
                          settings.api.futuresConnected
                            ? 'bg-success/15 text-success border-success/30'
                            : ''
                        }
                      >
                        {settings.api.futuresConnected ? 'Connected' : 'Disconnected'}
                      </Badge>
                    </CardContent>
                  </Card>
                </div>

                {/* Testnet Toggle */}
                <Card className={sectionCardClass}>
                  <CardContent className="flex items-center justify-between p-5">
                    <div>
                      <Label htmlFor="testnet">Testnet Mode</Label>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Use testnet endpoints for paper trading
                      </p>
                    </div>
                    <Switch
                      id="testnet"
                      checked={settings.api.testnetMode}
                      onCheckedChange={v => handleSettingChange('api', 'testnetMode', v)}
                    />
                  </CardContent>
                </Card>

                {/* API Keys */}
                <Card className={sectionCardClass}>
                  <CardHeader>
                    <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                      <MaterialIcon name="key" size="md" />
                      API Keys
                    </CardTitle>
                    <p className="text-xs text-warning flex items-center gap-1 mt-1">
                      <MaterialIcon name="error" size="sm" /> Never share your API keys with anyone
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    {[
                      { label: 'Spot API Key', placeholder: 'Enter your Spot API key' },
                      { label: 'Spot Secret Key', placeholder: 'Enter your Spot secret key' },
                      { label: 'Futures API Key', placeholder: 'Enter your Futures API key' },
                      { label: 'Futures Secret Key', placeholder: 'Enter your Futures secret key' },
                    ].map(field => (
                      <div key={field.label} className="flex flex-col gap-1.5">
                        <Label>{field.label}</Label>
                        <div className="flex gap-2 max-w-lg">
                          <Input
                            type="password"
                            placeholder={field.placeholder}
                            disabled
                            className={cn(
                              'flex-1',
                              revamp && 'border-[#323267] bg-[#101022] text-slate-300',
                            )}
                          />
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => console.warn(`TODO: Update ${field.label}`)}
                          >
                            Update
                          </Button>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Notifications Section */}
            {activeSection === 'notifications' && (
              <Card className={sectionCardClass}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
                    Notification Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="divide-y divide-slate-100 dark:divide-slate-800">
                  {[
                    {
                      key: 'emailAlerts',
                      label: 'Email Alerts',
                      description: 'Receive email notifications for important events',
                    },
                    {
                      key: 'pushNotifications',
                      label: 'Push Notifications',
                      description: 'Browser push notifications',
                    },
                    {
                      key: 'tradeExecutions',
                      label: 'Trade Execution Alerts',
                      description: 'Get notified when orders are filled',
                    },
                    {
                      key: 'priceAlerts',
                      label: 'Price Alerts',
                      description: 'Notifications when price targets are hit',
                    },
                    {
                      key: 'systemAlerts',
                      label: 'System Alerts',
                      description: 'Engine status and connectivity alerts',
                    },
                  ].map(item => (
                    <div key={item.key} className="flex items-center justify-between py-4">
                      <div className="flex flex-col gap-0.5">
                        <Label htmlFor={item.key} className="text-sm">
                          {item.label}
                        </Label>
                        <span className="text-xs text-slate-400">{item.description}</span>
                      </div>
                      <Switch
                        id={item.key}
                        checked={
                          settings.notifications[item.key as keyof typeof settings.notifications]
                        }
                        onCheckedChange={v => handleSettingChange('notifications', item.key, v)}
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Trading Preferences Section */}
            {activeSection === 'trading' && (
              <Card className={sectionCardClass}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
                    Trading Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="venue">Default Venue</Label>
                    <Select
                      value={settings.trading.defaultVenue}
                      onValueChange={v => handleSettingChange('trading', 'defaultVenue', v)}
                    >
                      <SelectTrigger id="venue" className="w-full max-w-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="SPOT">Spot</SelectItem>
                        <SelectItem value="FUTURES">Futures</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="leverage">Default Leverage</Label>
                    <Input
                      id="leverage"
                      type="number"
                      min={1}
                      max={125}
                      value={settings.trading.defaultLeverage}
                      onChange={e =>
                        handleSettingChange(
                          'trading',
                          'defaultLeverage',
                          parseInt(e.target.value) || 1,
                        )
                      }
                      className="w-full max-w-xs"
                    />
                  </div>
                  <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-800 max-w-md">
                    <Label htmlFor="confirm-orders">Confirm orders before submission</Label>
                    <Switch
                      id="confirm-orders"
                      checked={settings.trading.confirmOrders}
                      onCheckedChange={v => handleSettingChange('trading', 'confirmOrders', v)}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="max-position">Max Position Size (USDT)</Label>
                    <Input
                      id="max-position"
                      type="number"
                      value={settings.trading.maxPositionSize}
                      onChange={e =>
                        handleSettingChange(
                          'trading',
                          'maxPositionSize',
                          parseInt(e.target.value) || 0,
                        )
                      }
                      className={`w-full max-w-xs ${settings.trading.maxPositionSize > 10000 ? 'border-warning' : ''}`}
                    />
                    {settings.trading.maxPositionSize > 10000 && (
                      <p className="text-xs text-warning flex items-center gap-1">
                        <MaterialIcon name="error" size="sm" /> High position size — ensure you
                        understand the risk.
                      </p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-5 max-w-xs">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="stop-loss">Default Stop Loss (%)</Label>
                      <Input
                        id="stop-loss"
                        type="number"
                        step={0.1}
                        value={settings.trading.defaultStopLoss}
                        onChange={e =>
                          handleSettingChange(
                            'trading',
                            'defaultStopLoss',
                            parseFloat(e.target.value) || 0,
                          )
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="take-profit">Default Take Profit (%)</Label>
                      <Input
                        id="take-profit"
                        type="number"
                        step={0.1}
                        value={settings.trading.defaultTakeProfit}
                        onChange={e =>
                          handleSettingChange(
                            'trading',
                            'defaultTakeProfit',
                            parseFloat(e.target.value) || 0,
                          )
                        }
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Appearance Section */}
            {activeSection === 'appearance' && (
              <Card className={sectionCardClass}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
                    Appearance Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="theme">Theme</Label>
                    <Select
                      value={settings.general.theme}
                      onValueChange={v => handleSettingChange('general', 'theme', v)}
                    >
                      <SelectTrigger id="theme" className="w-full max-w-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="dark">Dark</SelectItem>
                        <SelectItem value="light">Light</SelectItem>
                        <SelectItem value="system">System</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="timezone">Timezone</Label>
                    <Select
                      value={settings.general.timezone}
                      onValueChange={v => handleSettingChange('general', 'timezone', v)}
                    >
                      <SelectTrigger id="timezone" className="w-full max-w-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="UTC">UTC</SelectItem>
                        <SelectItem value="America/New_York">Eastern Time</SelectItem>
                        <SelectItem value="America/Chicago">Central Time</SelectItem>
                        <SelectItem value="America/Los_Angeles">Pacific Time</SelectItem>
                        <SelectItem value="Europe/London">London</SelectItem>
                        <SelectItem value="Asia/Tokyo">Tokyo</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="language">Language</Label>
                    <Select
                      value={settings.general.language}
                      onValueChange={v => handleSettingChange('general', 'language', v)}
                    >
                      <SelectTrigger id="language" className="w-full max-w-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="es">Spanish</SelectItem>
                        <SelectItem value="fr">French</SelectItem>
                        <SelectItem value="de">German</SelectItem>
                        <SelectItem value="zh">Chinese</SelectItem>
                        <SelectItem value="ja">Japanese</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Danger Zone Section */}
            {activeSection === 'danger' && (
              <Card
                className={cn(
                  revamp
                    ? 'rounded-[18px] border-2 border-red-500/40 bg-[#2a1015] text-slate-100 shadow-[0_12px_30px_rgba(0,0,0,0.35)]'
                    : 'bg-white dark:bg-slate-900 rounded-2xl border-2 border-red-200 dark:border-red-900 shadow-soft',
                )}
              >
                <CardHeader className="border-b border-red-200 dark:border-red-900">
                  <CardTitle className="text-sm font-medium text-red-500 uppercase tracking-wide flex items-center gap-2">
                    <MaterialIcon name="warning" size="md" />
                    Danger Zone
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6 pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Export All Data</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Download all your trading history and settings
                      </p>
                    </div>
                    <Button variant="outline" size="sm">
                      Export
                    </Button>
                  </div>
                  <div className="flex items-center justify-between border-t border-slate-100 dark:border-slate-800 pt-6">
                    <div>
                      <p className="text-sm font-medium">Revoke All API Keys</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Immediately disconnect all exchange connections
                      </p>
                    </div>
                    <Button variant="destructive" size="sm">
                      Revoke All
                    </Button>
                  </div>
                  <div className="flex items-center justify-between border-t border-slate-100 dark:border-slate-800 pt-6">
                    <div>
                      <p className="text-sm font-medium text-red-500">Delete Account</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Permanently delete your account and all data
                      </p>
                    </div>
                    <Button variant="destructive" size="sm">
                      Delete Account
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Save / Reset Actions */}
            <div className="flex justify-end gap-3 mt-6">
              <Button
                variant="secondary"
                className={cn(
                  revamp && 'border-[#323267] bg-[#15152a] text-slate-300 hover:bg-[#232348]',
                )}
                onClick={() => console.warn('TODO: Reset settings')}
              >
                Reset to Defaults
              </Button>
              <Button
                className={cn(revamp && 'bg-primary text-white hover:bg-primary/90')}
                onClick={() => console.warn('TODO: Save settings to BFF')}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
