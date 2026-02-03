import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { AppShell } from './AppShell'

vi.mock('@/services/alerts.service', () => ({
  alertsService: {
    getAlerts: vi.fn().mockResolvedValue({ alerts: [], total: 0, page: 1, limit: 50 }),
    markAllAsRead: vi.fn().mockResolvedValue({ updated: 0 }),
  },
}))

// Mock next/navigation
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock next/link
vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode
    href: string
    [key: string]: unknown
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

describe('AppShell', () => {
  it('renders shell with topbar, sidebar, and content area', () => {
    render(
      <AppShell userEmail="test@example.com">
        <div data-testid="page-content">Hello</div>
      </AppShell>,
    )

    expect(screen.getByTestId('app-shell')).toBeInTheDocument()
    expect(screen.getByTestId('app-topbar')).toBeInTheDocument()
    expect(screen.getByTestId('app-sidebar')).toBeInTheDocument()
    expect(screen.getByTestId('page-content')).toBeInTheDocument()
  })

  it('renders children in main content area', () => {
    render(
      <AppShell>
        <p>Dashboard content</p>
      </AppShell>,
    )

    expect(screen.getByText('Dashboard content')).toBeInTheDocument()
  })

  it('shows offline banner when connectionState is offline', () => {
    render(
      <AppShell connectionState="offline">
        <div />
      </AppShell>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Connection lost.')).toBeInTheDocument()
  })

  it('shows reconnecting banner when connectionState is reconnecting', () => {
    render(
      <AppShell connectionState="reconnecting">
        <div />
      </AppShell>,
    )

    expect(screen.getByText('Reconnecting...')).toBeInTheDocument()
  })

  it('does not show banners when connected', () => {
    render(
      <AppShell connectionState="connected">
        <div />
      </AppShell>,
    )

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Reconnecting...')).not.toBeInTheDocument()
  })

  it('passes unread alerts count to topbar', () => {
    render(
      <AppShell unreadAlerts={5}>
        <div />
      </AppShell>,
    )

    expect(screen.getByLabelText('5 unread alerts')).toBeInTheDocument()
  })

  it('fires onLogout callback from user menu', async () => {
    const user = userEvent.setup()
    const onLogout = vi.fn()

    render(
      <AppShell userEmail="test@example.com" onLogout={onLogout}>
        <div />
      </AppShell>,
    )

    // Open user dropdown
    const userButton = screen.getByText('T')
    await user.click(userButton)

    // Click sign out
    const signOut = screen.getByText('Sign out')
    await user.click(signOut)

    expect(onLogout).toHaveBeenCalledOnce()
  })

  it('fires onCommandPaletteClick on Ctrl+K', async () => {
    const onCommandPaletteClick = vi.fn()

    render(
      <AppShell onCommandPaletteClick={onCommandPaletteClick}>
        <div />
      </AppShell>,
    )

    await userEvent.keyboard('{Control>}k{/Control}')

    expect(onCommandPaletteClick).toHaveBeenCalledOnce()
  })

  it('opens command palette on Ctrl+K by default', async () => {
    render(
      <AppShell>
        <div />
      </AppShell>,
    )

    await userEvent.keyboard('{Control>}k{/Control}')

    expect(screen.getByPlaceholderText('Type a command or search...')).toBeInTheDocument()
  })

  it('fires onAlertsClick when bell is clicked', async () => {
    const user = userEvent.setup()
    const onAlertsClick = vi.fn()

    render(
      <AppShell onAlertsClick={onAlertsClick}>
        <div />
      </AppShell>,
    )

    await user.click(screen.getByLabelText('Alerts'))

    expect(onAlertsClick).toHaveBeenCalledOnce()
  })

  it('opens alerts drawer by default', async () => {
    const user = userEvent.setup()

    render(
      <AppShell>
        <div />
      </AppShell>,
    )

    await user.click(screen.getByLabelText('Alerts'))

    expect(screen.getByTestId('alerts-empty-state')).toBeInTheDocument()
  })

  it('fires onHelpClick when help button is clicked', async () => {
    const user = userEvent.setup()
    const onHelpClick = vi.fn()

    render(
      <AppShell onHelpClick={onHelpClick}>
        <div />
      </AppShell>,
    )

    await user.click(screen.getByLabelText('Help'))

    expect(onHelpClick).toHaveBeenCalledOnce()
  })

  it('opens help drawer by default', async () => {
    const user = userEvent.setup()

    render(
      <AppShell>
        <div />
      </AppShell>,
    )

    await user.click(screen.getByLabelText('Help'))

    expect(
      screen.getByText('Keyboard shortcuts, glossary, and app information.'),
    ).toBeInTheDocument()
  })
})
