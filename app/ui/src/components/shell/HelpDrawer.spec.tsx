import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { HelpDrawer } from './HelpDrawer'

describe('HelpDrawer', () => {
  it('renders when open is true', () => {
    render(<HelpDrawer open={true} onOpenChange={vi.fn()} />)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(
      screen.getByText('Keyboard shortcuts, glossary, and app information.'),
    ).toBeInTheDocument()
  })

  it('does not render content when open is false', () => {
    render(<HelpDrawer open={false} onOpenChange={vi.fn()} />)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows shortcuts tab by default', () => {
    render(<HelpDrawer open={true} onOpenChange={vi.fn()} />)

    expect(screen.getByText('Command Palette')).toBeInTheDocument()
    expect(screen.getByText('Toggle Sidebar')).toBeInTheDocument()
    expect(screen.getByText('Close overlay')).toBeInTheDocument()
  })

  it('shows keyboard shortcut items with kbd styling', () => {
    render(<HelpDrawer open={true} onOpenChange={vi.fn()} />)

    const kbdElements = screen.getAllByText((_, el) => el?.tagName === 'KBD')
    expect(kbdElements.length).toBeGreaterThanOrEqual(5)
    expect(screen.getByText('Escape', { selector: 'kbd' })).toBeInTheDocument()
    expect(screen.getByText('K', { selector: 'kbd' })).toBeInTheDocument()
  })

  it('can switch to glossary tab', async () => {
    const user = userEvent.setup()
    render(<HelpDrawer open={true} onOpenChange={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: 'Glossary' }))

    expect(screen.getByText('CHOCH')).toBeInTheDocument()
    expect(screen.getByText('BOS')).toBeInTheDocument()
    expect(screen.getByText('Order Block')).toBeInTheDocument()
    expect(screen.getByText('FVG')).toBeInTheDocument()
  })

  it('shows all glossary terms', async () => {
    const user = userEvent.setup()
    render(<HelpDrawer open={true} onOpenChange={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: 'Glossary' }))

    const expectedTerms = [
      'CHOCH',
      'BOS',
      'Order Block',
      'FVG',
      'EMA',
      'RSI',
      'MACD',
      'ATR',
      'Bollinger Bands',
    ]
    for (const term of expectedTerms) {
      expect(screen.getByText(term)).toBeInTheDocument()
    }
  })

  it('can switch to about tab', async () => {
    const user = userEvent.setup()
    render(<HelpDrawer open={true} onOpenChange={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: 'About' }))

    expect(screen.getByText('Version')).toBeInTheDocument()
    expect(screen.getByText('0.1.0-dev')).toBeInTheDocument()
    expect(screen.getByText('Links')).toBeInTheDocument()
  })
})
