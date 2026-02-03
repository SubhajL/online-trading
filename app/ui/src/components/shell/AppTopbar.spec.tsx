import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { AppTopbar } from './AppTopbar'

describe('AppTopbar', () => {
  it('renders topbar with app title', () => {
    render(<AppTopbar />)

    expect(screen.getByTestId('app-topbar')).toBeInTheDocument()
    expect(screen.getByText('Online Trader')).toBeInTheDocument()
  })

  it('shows connection status pill', () => {
    render(<AppTopbar connectionState="connected" />)

    expect(screen.getByRole('status', { name: 'Connection status: Connected' })).toBeInTheDocument()
  })

  it('shows offline status pill', () => {
    render(<AppTopbar connectionState="offline" />)

    expect(screen.getByRole('status', { name: 'Connection status: Offline' })).toBeInTheDocument()
  })

  it('shows reconnecting status with spinner', () => {
    render(<AppTopbar connectionState="reconnecting" />)

    expect(
      screen.getByRole('status', { name: 'Connection status: Reconnecting' }),
    ).toBeInTheDocument()
  })

  it('shows alerts bell with unread count', () => {
    render(<AppTopbar unreadAlerts={5} />)

    expect(screen.getByLabelText('5 unread alerts')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('caps unread count at 99+', () => {
    render(<AppTopbar unreadAlerts={150} />)

    expect(screen.getByText('99+')).toBeInTheDocument()
  })

  it('shows simple Alerts label when no unread', () => {
    render(<AppTopbar unreadAlerts={0} />)

    expect(screen.getByLabelText('Alerts')).toBeInTheDocument()
  })

  it('fires onAlertsClick when bell clicked', async () => {
    const user = userEvent.setup()
    const onAlertsClick = vi.fn()

    render(<AppTopbar onAlertsClick={onAlertsClick} />)

    await user.click(screen.getByLabelText('Alerts'))

    expect(onAlertsClick).toHaveBeenCalledOnce()
  })

  it('fires onHelpClick when help button clicked', async () => {
    const user = userEvent.setup()
    const onHelpClick = vi.fn()

    render(<AppTopbar onHelpClick={onHelpClick} />)

    await user.click(screen.getByLabelText('Help'))

    expect(onHelpClick).toHaveBeenCalledOnce()
  })

  it('fires onCommandPaletteClick when command button clicked', async () => {
    const user = userEvent.setup()
    const onCommandPaletteClick = vi.fn()

    render(<AppTopbar onCommandPaletteClick={onCommandPaletteClick} />)

    await user.click(screen.getByLabelText('Command palette (Ctrl+K)'))

    expect(onCommandPaletteClick).toHaveBeenCalledOnce()
  })

  it('shows menu button when showMenuButton is true', () => {
    render(<AppTopbar showMenuButton />)

    expect(screen.getByLabelText('Open menu')).toBeInTheDocument()
  })

  it('hides menu button by default', () => {
    render(<AppTopbar />)

    expect(screen.queryByLabelText('Open menu')).not.toBeInTheDocument()
  })

  it('shows user email in dropdown trigger', () => {
    render(<AppTopbar userEmail="trader@example.com" />)

    expect(screen.getByText('T')).toBeInTheDocument()
  })

  it('fires onLogout from user dropdown', async () => {
    const user = userEvent.setup()
    const onLogout = vi.fn()

    render(<AppTopbar userEmail="trader@example.com" onLogout={onLogout} />)

    await user.click(screen.getByText('T'))
    await user.click(screen.getByText('Sign out'))

    expect(onLogout).toHaveBeenCalledOnce()
  })
})
