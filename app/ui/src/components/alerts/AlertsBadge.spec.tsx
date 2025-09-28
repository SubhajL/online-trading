import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AlertsBadge } from './AlertsBadge'

describe('AlertsBadge', () => {
  const mockOnClick = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render badge with count', () => {
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      expect(screen.getByTestId('alerts-badge')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('should show bell icon', () => {
      render(<AlertsBadge count={0} onClick={mockOnClick} />)

      expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
    })

    it('should not show count when zero', () => {
      render(<AlertsBadge count={0} onClick={mockOnClick} />)

      expect(screen.queryByTestId('alert-count')).not.toBeInTheDocument()
    })

    it('should show count when greater than zero', () => {
      render(<AlertsBadge count={3} onClick={mockOnClick} />)

      expect(screen.getByTestId('alert-count')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
    })
  })

  describe('count display', () => {
    it('should display single digit counts', () => {
      render(<AlertsBadge count={7} onClick={mockOnClick} />)

      expect(screen.getByText('7')).toBeInTheDocument()
    })

    it('should display double digit counts', () => {
      render(<AlertsBadge count={42} onClick={mockOnClick} />)

      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('should display 99+ for counts over 99', () => {
      render(<AlertsBadge count={100} onClick={mockOnClick} />)

      expect(screen.getByText('99+')).toBeInTheDocument()
    })

    it('should display 99+ for very large counts', () => {
      render(<AlertsBadge count={1000} onClick={mockOnClick} />)

      expect(screen.getByText('99+')).toBeInTheDocument()
    })
  })

  describe('interactions', () => {
    it('should call onClick when clicked', async () => {
      const user = userEvent.setup()
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      const badge = screen.getByTestId('alerts-badge')
      await user.click(badge)

      expect(mockOnClick).toHaveBeenCalledTimes(1)
    })

    it('should be clickable even with zero count', async () => {
      const user = userEvent.setup()
      render(<AlertsBadge count={0} onClick={mockOnClick} />)

      const badge = screen.getByTestId('alerts-badge')
      await user.click(badge)

      expect(mockOnClick).toHaveBeenCalledTimes(1)
    })
  })

  describe('styling', () => {
    it('should have hover effect', () => {
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      const badge = screen.getByTestId('alerts-badge')
      expect(badge).toHaveClass('hover:bg-gray-700')
    })

    it('should show count badge with red background', () => {
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      const countBadge = screen.getByTestId('alert-count')
      expect(countBadge).toHaveClass('bg-red-500')
    })

    it('should position count badge in top right', () => {
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      const countBadge = screen.getByTestId('alert-count')
      expect(countBadge).toHaveClass('absolute', '-top-1', '-right-1')
    })
  })

  describe('accessibility', () => {
    it('should have proper button role', () => {
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
    })

    it('should have accessible label', () => {
      render(<AlertsBadge count={5} onClick={mockOnClick} />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Alerts (5 unread)')
    })

    it('should update label with count', () => {
      const { rerender } = render(<AlertsBadge count={0} onClick={mockOnClick} />)

      let button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Alerts')

      rerender(<AlertsBadge count={10} onClick={mockOnClick} />)

      button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Alerts (10 unread)')
    })
  })

  describe('loading state', () => {
    it('should show loading spinner', () => {
      render(<AlertsBadge count={0} loading onClick={mockOnClick} />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })

    it('should hide bell icon when loading', () => {
      render(<AlertsBadge count={0} loading onClick={mockOnClick} />)

      expect(screen.queryByTestId('bell-icon')).not.toBeInTheDocument()
    })

    it('should still show count when loading', () => {
      render(<AlertsBadge count={5} loading onClick={mockOnClick} />)

      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('should disable clicks when loading', async () => {
      const user = userEvent.setup()
      render(<AlertsBadge count={5} loading onClick={mockOnClick} />)

      const badge = screen.getByTestId('alerts-badge')
      await user.click(badge)

      expect(mockOnClick).not.toHaveBeenCalled()
    })
  })

  describe('animation', () => {
    it('should have pulse animation for new alerts', () => {
      render(<AlertsBadge count={1} hasNew onClick={mockOnClick} />)

      const countBadge = screen.getByTestId('alert-count')
      expect(countBadge).toHaveClass('animate-pulse')
    })

    it('should not animate without new alerts', () => {
      render(<AlertsBadge count={1} hasNew={false} onClick={mockOnClick} />)

      const countBadge = screen.getByTestId('alert-count')
      expect(countBadge).not.toHaveClass('animate-pulse')
    })
  })
})
