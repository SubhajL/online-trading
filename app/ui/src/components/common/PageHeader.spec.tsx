import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  describe('rendering', () => {
    it('renders title with correct styling', () => {
      render(<PageHeader title="Dashboard" />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveTextContent('Dashboard')
      expect(heading).toHaveClass('text-2xl', 'font-semibold')
    })

    it('renders subtitle when provided', () => {
      render(<PageHeader title="Dashboard" subtitle="Overview of your trading activity" />)

      expect(screen.getByText('Overview of your trading activity')).toBeInTheDocument()
    })

    it('does not render subtitle element when not provided', () => {
      const { container } = render(<PageHeader title="Dashboard" />)

      expect(container.querySelector('p')).not.toBeInTheDocument()
    })

    it('renders actions slot when provided', () => {
      render(
        <PageHeader title="Dashboard" actions={<button data-testid="action-btn">Action</button>} />,
      )

      expect(screen.getByTestId('action-btn')).toBeInTheDocument()
    })

    it('does not render actions container when not provided', () => {
      const { container } = render(<PageHeader title="Dashboard" />)

      // Only header element should have direct children for title area
      const header = container.querySelector('header')
      expect(header?.children.length).toBe(1)
    })
  })

  describe('styling', () => {
    it('applies dark mode text classes', () => {
      render(<PageHeader title="Test" subtitle="Subtitle" />)

      const heading = screen.getByRole('heading')
      expect(heading).toHaveClass('dark:text-white')

      const subtitle = screen.getByText('Subtitle')
      expect(subtitle).toHaveClass('dark:text-slate-400')
    })

    it('applies custom className', () => {
      const { container } = render(<PageHeader title="Test" className="mb-6" />)

      expect(container.querySelector('header')).toHaveClass('mb-6')
    })

    it('uses responsive flex layout', () => {
      const { container } = render(<PageHeader title="Test" actions={<button>Action</button>} />)

      const header = container.querySelector('header')
      expect(header).toHaveClass('flex-col', 'sm:flex-row')
    })
  })

  describe('accessibility', () => {
    it('uses semantic header element', () => {
      const { container } = render(<PageHeader title="Test" />)

      expect(container.querySelector('header')).toBeInTheDocument()
    })

    it('uses h1 for main page title', () => {
      render(<PageHeader title="Page Title" />)

      expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    })
  })
})
