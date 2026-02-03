import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { AppSidebar } from './AppSidebar'

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
}))

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

describe('AppSidebar', () => {
  const defaultProps = {
    isOpen: true,
    onToggle: vi.fn(),
  }

  it('renders all 6 navigation items when expanded', () => {
    render(<AppSidebar {...defaultProps} />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Trades')).toBeInTheDocument()
    expect(screen.getByText('Portfolio')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
    expect(screen.getByText('Analytics')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('hides labels when collapsed', () => {
    render(<AppSidebar {...defaultProps} isOpen={false} />)

    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
    expect(screen.queryByText('Trades')).not.toBeInTheDocument()
  })

  it('marks current route as active with aria-current', () => {
    render(<AppSidebar {...defaultProps} />)

    const dashboardLink = screen.getByRole('link', { current: 'page' })
    expect(dashboardLink).toHaveAttribute('href', '/')
  })

  it('fires onToggle when collapse button is clicked', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()

    render(<AppSidebar {...defaultProps} onToggle={onToggle} />)

    await user.click(screen.getByLabelText('Collapse sidebar'))

    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('shows expand label when collapsed', () => {
    render(<AppSidebar {...defaultProps} isOpen={false} />)

    expect(screen.getByLabelText('Expand sidebar')).toBeInTheDocument()
  })

  it('shows connection status indicator', () => {
    render(<AppSidebar {...defaultProps} connectionState="connected" />)

    expect(screen.getByRole('status', { name: 'Connected' })).toBeInTheDocument()
  })

  it('shows offline connection status', () => {
    render(<AppSidebar {...defaultProps} connectionState="offline" />)

    expect(screen.getByRole('status', { name: 'Offline' })).toBeInTheDocument()
  })

  it('shows reconnecting connection status', () => {
    render(<AppSidebar {...defaultProps} connectionState="reconnecting" />)

    expect(screen.getByRole('status', { name: 'Reconnecting' })).toBeInTheDocument()
  })

  it('shows version number when expanded', () => {
    render(<AppSidebar {...defaultProps} />)

    expect(screen.getByText('v1.0.0')).toBeInTheDocument()
  })

  it('hides version number when collapsed', () => {
    render(<AppSidebar {...defaultProps} isOpen={false} />)

    expect(screen.queryByText('v1.0.0')).not.toBeInTheDocument()
  })

  it('has accessible main navigation landmark', () => {
    render(<AppSidebar {...defaultProps} />)

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
  })
})
