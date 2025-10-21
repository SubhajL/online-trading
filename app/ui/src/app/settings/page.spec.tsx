import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import SettingsPage from './page'

describe('SettingsPage', () => {
  test('renders with CSS module classes', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  test('applies pageShell CSS module class to root div', () => {
    const { container } = render(<SettingsPage />)
    const rootDiv = container.firstChild as HTMLElement
    expect(rootDiv.className).toContain('pageShell')
  })

  test('renders settings tabs', () => {
    render(<SettingsPage />)
    expect(screen.getByText('General')).toBeInTheDocument()
    expect(screen.getByText('Trading')).toBeInTheDocument()
    expect(screen.getByText('Notifications')).toBeInTheDocument()
    expect(screen.getByText('API Keys')).toBeInTheDocument()
  })

  test('renders action buttons', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Save Changes')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })
})
