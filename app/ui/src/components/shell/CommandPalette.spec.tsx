import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CommandPalette } from './CommandPalette'

const mockPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

describe('CommandPalette', () => {
  const onOpenChange = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders when open=true', () => {
    render(<CommandPalette open={true} onOpenChange={onOpenChange} />)
    expect(screen.getByPlaceholderText('Type a command or search...')).toBeInTheDocument()
  })

  it('is hidden when open=false', () => {
    render(<CommandPalette open={false} onOpenChange={onOpenChange} />)
    expect(screen.queryByPlaceholderText('Type a command or search...')).not.toBeInTheDocument()
  })

  it('shows all navigation items', () => {
    render(<CommandPalette open={true} onOpenChange={onOpenChange} />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Portfolio')).toBeInTheDocument()
    expect(screen.getByText('Trading')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
    expect(screen.getByText('Analytics')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('shows action items', () => {
    render(<CommandPalette open={true} onOpenChange={onOpenChange} />)
    expect(screen.getByText('New Order')).toBeInTheDocument()
    expect(screen.getByText('Refresh Data')).toBeInTheDocument()
    expect(screen.getByText('Toggle Dark Mode')).toBeInTheDocument()
  })

  it('filters items based on search input', async () => {
    const user = userEvent.setup()
    render(<CommandPalette open={true} onOpenChange={onOpenChange} />)

    const input = screen.getByPlaceholderText('Type a command or search...')
    await user.type(input, 'Dashboard')

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.queryByText('Portfolio')).not.toBeInTheDocument()
    expect(screen.queryByText('New Order')).not.toBeInTheDocument()
  })

  it('calls onOpenChange(false) when navigation item selected', async () => {
    const user = userEvent.setup()
    render(<CommandPalette open={true} onOpenChange={onOpenChange} />)

    await user.click(screen.getByText('Dashboard'))

    expect(mockPush).toHaveBeenCalledWith('/')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows empty state for no matches', async () => {
    const user = userEvent.setup()
    render(<CommandPalette open={true} onOpenChange={onOpenChange} />)

    const input = screen.getByPlaceholderText('Type a command or search...')
    await user.type(input, 'xyznonexistent')

    expect(screen.getByText('No results found.')).toBeInTheDocument()
  })
})
