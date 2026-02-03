import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { AlertsDrawer } from './AlertsDrawer'
import type { Alert } from '@/types/alerts'

const baseAlert = (overrides: Partial<Alert> = {}): Alert => ({
  id: 'alert-1' as any,
  type: 'info',
  priority: 'low',
  title: 'Test Alert',
  message: 'Test message',
  read: false,
  createdAt: new Date(Date.now() - 2 * 60 * 1000).toISOString(), // 2 minutes ago
  ...overrides,
})

describe('AlertsDrawer', () => {
  it('renders alerts list when open with alerts', () => {
    const alerts = [
      baseAlert({ id: 'alert-1' as any, type: 'info', title: 'Info Alert', priority: 'low' }),
      baseAlert({
        id: 'alert-2' as any,
        type: 'error',
        title: 'Error Alert',
        priority: 'critical',
      }),
    ]

    render(<AlertsDrawer open={true} onOpenChange={vi.fn()} alerts={alerts} />)

    expect(screen.getByText('Info Alert')).toBeInTheDocument()
    expect(screen.getByText('Error Alert')).toBeInTheDocument()
  })

  it('shows empty state when no alerts', () => {
    render(<AlertsDrawer open={true} onOpenChange={vi.fn()} alerts={[]} />)

    expect(screen.getByTestId('alerts-empty-state')).toBeInTheDocument()
    expect(screen.getByText('No alerts')).toBeInTheDocument()
  })

  it('shows unread badge count in header', () => {
    const alerts = [
      baseAlert({ id: 'alert-1' as any, read: false }),
      baseAlert({ id: 'alert-2' as any, read: true }),
      baseAlert({ id: 'alert-3' as any, read: false }),
    ]

    render(<AlertsDrawer open={true} onOpenChange={vi.fn()} alerts={alerts} />)

    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('calls onMarkAllRead when mark all as read is clicked', async () => {
    const user = userEvent.setup()
    const onMarkAllRead = vi.fn()
    const alerts = [baseAlert({ id: 'alert-1' as any, read: false })]

    render(
      <AlertsDrawer
        open={true}
        onOpenChange={vi.fn()}
        alerts={alerts}
        onMarkAllRead={onMarkAllRead}
      />,
    )

    await user.click(screen.getByText('Mark all as read'))
    expect(onMarkAllRead).toHaveBeenCalledOnce()
  })

  it('hides mark all as read when all alerts are read', () => {
    const alerts = [baseAlert({ id: 'alert-1' as any, read: true })]

    render(<AlertsDrawer open={true} onOpenChange={vi.fn()} alerts={alerts} />)

    expect(screen.queryByText('Mark all as read')).not.toBeInTheDocument()
  })

  it('displays relative time for alerts', () => {
    const alerts = [
      baseAlert({
        id: 'alert-1' as any,
        createdAt: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
      }),
    ]

    render(<AlertsDrawer open={true} onOpenChange={vi.fn()} alerts={alerts} />)

    expect(screen.getByText('2m ago')).toBeInTheDocument()
  })

  it('renders priority and type chips', () => {
    const alerts = [
      baseAlert({
        id: 'alert-1' as any,
        type: 'order',
        title: 'Order Alert',
        priority: 'medium',
      }),
      baseAlert({
        id: 'alert-2' as any,
        type: 'smc',
        title: 'SMC Alert',
        priority: 'high',
      }),
    ]

    render(<AlertsDrawer open={true} onOpenChange={vi.fn()} alerts={alerts} />)

    expect(screen.getByText('Order Alert')).toBeInTheDocument()
    expect(screen.getByText('SMC Alert')).toBeInTheDocument()
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    expect(screen.getByText('Order')).toBeInTheDocument()
    expect(screen.getByText('SMC')).toBeInTheDocument()
  })

  it('does not render content when closed', () => {
    render(<AlertsDrawer open={false} onOpenChange={vi.fn()} alerts={[baseAlert()]} />)

    expect(screen.queryByText('Test Alert')).not.toBeInTheDocument()
  })
})
