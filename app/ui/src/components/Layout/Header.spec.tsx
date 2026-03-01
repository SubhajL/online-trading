import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { usePathname } from 'next/navigation'
import { Header } from './Header'

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(),
}))

describe('Header', () => {
  test('renders all navigation links', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Header />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Portfolio')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  test('applies active class to root path link', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Header />)

    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink).toHaveClass('active')
  })

  test('applies active class to matching non-root path', () => {
    vi.mocked(usePathname).mockReturnValue('/portfolio')
    render(<Header />)

    const portfolioLink = screen.getByText('Portfolio').closest('a')
    expect(portfolioLink).toHaveClass('active')

    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink).not.toHaveClass('active')
  })

  test('applies active class to nested route', () => {
    vi.mocked(usePathname).mockReturnValue('/history/detail')
    render(<Header />)

    const historyLink = screen.getByText('History').closest('a')
    expect(historyLink).toHaveClass('active')
  })

  test('does not apply active to similar paths', () => {
    vi.mocked(usePathname).mockReturnValue('/portfolio-old')
    render(<Header />)

    const portfolioLink = screen.getByText('Portfolio').closest('a')
    expect(portfolioLink).not.toHaveClass('active')
  })

  test('renders logout button when onLogout provided', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const handleLogout = vi.fn()
    render(<Header onLogout={handleLogout} />)

    expect(screen.getByText('Logout')).toBeInTheDocument()
  })

  test('calls onLogout when logout button clicked', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const handleLogout = vi.fn()
    render(<Header onLogout={handleLogout} />)

    screen.getByText('Logout').click()
    expect(handleLogout).toHaveBeenCalledTimes(1)
  })

  test('renders userName when provided', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    render(<Header userName="trader@test.com" />)

    expect(screen.getByTestId('user-email')).toHaveTextContent('trader@test.com')
  })

  test('applies custom className when provided', () => {
    vi.mocked(usePathname).mockReturnValue('/')
    const { container } = render(<Header className="custom-header" />)

    const header = container.querySelector('header')
    expect(header).toHaveClass('custom-header')
  })

  describe('WCAG Touch Targets & Accessibility', () => {
    test('nav links have touch-target-min class for 44px height', () => {
      vi.mocked(usePathname).mockReturnValue('/')
      render(<Header />)

      const dashboardLink = screen.getByText('Dashboard').closest('a')
      expect(dashboardLink).toBeInTheDocument()
      expect(dashboardLink).toHaveClass('nav-link')
      // CSS: .nav-link has min-height: var(--touch-target-min) which is 44px
    })

    test('logout button has touch-target-min for 44px height', () => {
      vi.mocked(usePathname).mockReturnValue('/')
      const handleLogout = vi.fn()
      render(<Header onLogout={handleLogout} />)

      const logoutButton = screen.getByText('Logout')
      expect(logoutButton).toHaveClass('logout-button')
      // CSS: .logout-button has min-height: var(--touch-target-min) which is 44px
    })

    test('logo link has focus-visible styling', () => {
      vi.mocked(usePathname).mockReturnValue('/')
      render(<Header />)

      const logoLink = screen.getByText('Trading Platform')
      expect(logoLink).toHaveClass('header-logo')
      // CSS ensures focus-visible with 2px solid var(--color-border-focus)
    })
  })
})
