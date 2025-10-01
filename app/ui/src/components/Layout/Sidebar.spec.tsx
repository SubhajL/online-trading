import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { usePathname } from 'next/navigation'
import { Sidebar } from './Sidebar'

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(),
}))

describe('Sidebar', () => {
  test('renders all navigation items with icons', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Sidebar />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Portfolio')).toBeInTheDocument()
    expect(screen.getByText('Trades')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
    expect(screen.getByText('Analytics')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  test('applies active class to current page link', () => {
    vi.mocked(usePathname).mockReturnValue('/trades')
    render(<Sidebar />)

    const tradesLink = screen.getByText('Trades').closest('a')
    expect(tradesLink).toHaveClass('active')
  })

  test('applies active class to nested route', () => {
    vi.mocked(usePathname).mockReturnValue('/history/detail')
    render(<Sidebar />)

    const historyLink = screen.getByText('History').closest('a')
    expect(historyLink).toHaveClass('active')
  })

  test('sets aria-current page on active link', () => {
    vi.mocked(usePathname).mockReturnValue('/analytics')
    render(<Sidebar />)

    const analyticsLink = screen.getByText('Analytics').closest('a')
    expect(analyticsLink).toHaveAttribute('aria-current', 'page')
  })

  test('does not set aria-current on inactive links', () => {
    vi.mocked(usePathname).mockReturnValue('/analytics')
    render(<Sidebar />)

    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink).not.toHaveAttribute('aria-current')
  })

  test('shows tooltips on collapsed sidebar icons', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Sidebar isOpen={false} />)

    const dashboardLink = screen.getByLabelText('Dashboard')
    expect(dashboardLink).toHaveAttribute('title', 'Dashboard')
  })

  test('hides labels when sidebar collapsed', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const { container } = render(<Sidebar isOpen={false} />)

    const labels = container.querySelectorAll('.sidebar-label')
    labels.forEach(label => {
      expect(label).not.toBeVisible()
    })
  })

  test('shows labels when sidebar open', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Sidebar isOpen={true} />)

    expect(screen.getByText('Dashboard')).toBeVisible()
    expect(screen.getByText('Portfolio')).toBeVisible()
  })

  test('toggle button has correct aria-label when open', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const handleToggle = vi.fn()
    render(<Sidebar isOpen={true} onToggle={handleToggle} />)

    const toggleButton = screen.getByLabelText('Close sidebar')
    expect(toggleButton).toBeInTheDocument()
  })

  test('toggle button has correct aria-label when closed', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const handleToggle = vi.fn()
    render(<Sidebar isOpen={false} onToggle={handleToggle} />)

    const toggleButton = screen.getByLabelText('Open sidebar')
    expect(toggleButton).toBeInTheDocument()
  })

  test('calls onToggle when toggle button clicked', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const handleToggle = vi.fn()
    render(<Sidebar isOpen={true} onToggle={handleToggle} />)

    screen.getByLabelText('Close sidebar').click()
    expect(handleToggle).toHaveBeenCalledTimes(1)
  })

  test('shows connection status when sidebar open', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Sidebar isOpen={true} />)

    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(screen.getByText('v1.0.0')).toBeInTheDocument()
  })

  test('hides connection status when sidebar closed', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Sidebar isOpen={false} />)

    expect(screen.queryByText('Connected')).not.toBeInTheDocument()
    expect(screen.queryByText('v1.0.0')).not.toBeInTheDocument()
  })

  test('applies custom className when provided', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const { container } = render(<Sidebar className="custom-sidebar" />)

    const sidebar = container.querySelector('aside')
    expect(sidebar).toHaveClass('custom-sidebar')
  })
})
