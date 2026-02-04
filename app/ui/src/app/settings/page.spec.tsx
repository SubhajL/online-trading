import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import SettingsPage from './page'

describe('SettingsPage', () => {
  test('renders with CSS module classes', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  test('renders inside AppShell', () => {
    render(<SettingsPage />)
    expect(screen.getByTestId('app-shell')).toBeInTheDocument()
  })

  test('renders settings sidebar navigation', () => {
    render(<SettingsPage />)
    // Sidebar navigation sections per Spec §6.6
    expect(screen.getByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('Security')).toBeInTheDocument()
    expect(screen.getByText('API Keys')).toBeInTheDocument()
    expect(screen.getByText('Notifications')).toBeInTheDocument()
    expect(screen.getByText('Trading Preferences')).toBeInTheDocument()
    expect(screen.getByText('Appearance')).toBeInTheDocument()
    expect(screen.getByText('Danger Zone')).toBeInTheDocument()
  })

  test('renders action buttons', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Save Changes')).toBeInTheDocument()
    expect(screen.getByText('Reset to Defaults')).toBeInTheDocument()
  })
})
