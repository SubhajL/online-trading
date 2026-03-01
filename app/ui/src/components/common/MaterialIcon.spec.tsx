import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MaterialIcon } from './MaterialIcon'

describe('MaterialIcon', () => {
  describe('rendering', () => {
    it('renders material-symbols-outlined glyph with icon name', () => {
      render(<MaterialIcon name="notifications" ariaLabel="Notifications" />)

      const icon = screen.getByLabelText('Notifications')
      expect(icon).toBeInTheDocument()
      expect(icon).toHaveClass('material-symbols-outlined')
      expect(icon).toHaveTextContent('notifications')
    })

    it('renders decorative icon with aria-hidden when no ariaLabel provided', () => {
      render(<MaterialIcon name="search" />)

      const icon = screen.getByText('search')
      expect(icon).toHaveAttribute('aria-hidden', 'true')
    })

    it('applies data-testid for test selection', () => {
      render(<MaterialIcon name="settings" ariaLabel="Settings" />)

      expect(screen.getByTestId('icon-settings')).toBeInTheDocument()
    })
  })

  describe('sizing', () => {
    it('applies sm size (16px)', () => {
      render(<MaterialIcon name="check" size="sm" />)

      const icon = screen.getByText('check')
      expect(icon).toHaveClass('text-[16px]')
    })

    it('applies md size (20px)', () => {
      render(<MaterialIcon name="check" size="md" />)

      const icon = screen.getByText('check')
      expect(icon).toHaveClass('text-[20px]')
    })

    it('applies lg size (24px) by default', () => {
      render(<MaterialIcon name="check" />)

      const icon = screen.getByText('check')
      expect(icon).toHaveClass('text-[24px]')
    })

    it('applies xl size (32px)', () => {
      render(<MaterialIcon name="check" size="xl" />)

      const icon = screen.getByText('check')
      expect(icon).toHaveClass('text-[32px]')
    })
  })

  describe('styling', () => {
    it('applies custom className', () => {
      render(<MaterialIcon name="star" className="text-primary" />)

      const icon = screen.getByText('star')
      expect(icon).toHaveClass('text-primary')
    })

    it('merges base classes with custom className', () => {
      render(<MaterialIcon name="star" className="text-red-500" />)

      const icon = screen.getByText('star')
      expect(icon).toHaveClass('material-symbols-outlined')
      expect(icon).toHaveClass('text-red-500')
    })
  })

  describe('accessibility', () => {
    it('uses role="img" when ariaLabel is provided', () => {
      render(<MaterialIcon name="warning" ariaLabel="Warning" />)

      const icon = screen.getByRole('img', { name: 'Warning' })
      expect(icon).toBeInTheDocument()
    })

    it('does not have role="img" for decorative icons', () => {
      render(<MaterialIcon name="decorative" />)

      expect(screen.queryByRole('img')).not.toBeInTheDocument()
    })
  })
})
