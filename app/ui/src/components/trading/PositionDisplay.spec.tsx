import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PositionDisplay } from './PositionDisplay'
import type { Position } from '@/types'

describe('PositionDisplay', () => {
  const mockPosition: Position = {
    symbol: 'BTCUSDT' as any,
    side: 'BUY',
    quantity: 0.5,
    entryPrice: 45000,
    markPrice: 46000,
    pnl: 500,
    pnlPercent: 2.22,
    venue: 'SPOT',
  }

  const mockShortPosition: Position = {
    symbol: 'ETHUSDT' as any,
    side: 'SELL',
    quantity: 10,
    entryPrice: 3000,
    markPrice: 2900,
    pnl: 1000,
    pnlPercent: 3.33,
    venue: 'USD_M',
  }

  const mockLossPosition: Position = {
    symbol: 'BTCUSDT' as any,
    side: 'BUY',
    quantity: 0.1,
    entryPrice: 50000,
    markPrice: 48000,
    pnl: -200,
    pnlPercent: -4,
    venue: 'SPOT',
  }

  describe('rendering', () => {
    it('should render position display', () => {
      render(<PositionDisplay position={mockPosition} />)

      expect(screen.getByTestId('position-display')).toBeInTheDocument()
    })

    it('should display symbol and side', () => {
      render(<PositionDisplay position={mockPosition} />)

      expect(screen.getByText('BTCUSDT')).toBeInTheDocument()
      expect(screen.getByText('LONG')).toBeInTheDocument()
    })

    it('should display short position correctly', () => {
      render(<PositionDisplay position={mockShortPosition} />)

      expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
      expect(screen.getByText('SHORT')).toBeInTheDocument()
    })

    it('should show position details', () => {
      render(<PositionDisplay position={mockPosition} />)

      expect(screen.getByText(/Quantity:/)).toBeInTheDocument()
      expect(screen.getByText('0.5')).toBeInTheDocument()
      expect(screen.getByText(/Entry:/)).toBeInTheDocument()
      expect(screen.getByText('$45,000.00')).toBeInTheDocument()
      expect(screen.getByText(/Mark:/)).toBeInTheDocument()
      expect(screen.getByText('$46,000.00')).toBeInTheDocument()
    })

    it('should show venue badge', () => {
      render(<PositionDisplay position={mockPosition} />)

      expect(screen.getByText('SPOT')).toBeInTheDocument()
    })

    it('should show futures venue badge', () => {
      render(<PositionDisplay position={mockShortPosition} />)

      expect(screen.getByText('USD_M')).toBeInTheDocument()
    })
  })

  describe('profit and loss display', () => {
    it('should show profit in green', () => {
      render(<PositionDisplay position={mockPosition} />)

      const pnlElement = screen.getByText('+$500.00')
      expect(pnlElement).toHaveClass('text-green-500')

      const percentElement = screen.getByText('+2.22%')
      expect(percentElement).toHaveClass('text-green-500')
    })

    it('should show loss in red', () => {
      render(<PositionDisplay position={mockLossPosition} />)

      const pnlElement = screen.getByText('-$200.00')
      expect(pnlElement).toHaveClass('text-red-500')

      const percentElement = screen.getByText('-4.00%')
      expect(percentElement).toHaveClass('text-red-500')
    })

    it('should format large PnL values correctly', () => {
      const largePosition = {
        ...mockPosition,
        pnl: 12345.67,
        pnlPercent: 27.43,
      }
      render(<PositionDisplay position={largePosition} />)

      expect(screen.getByText('+$12,345.67')).toBeInTheDocument()
      expect(screen.getByText('+27.43%')).toBeInTheDocument()
    })
  })

  describe('position sizing', () => {
    it('should calculate position value', () => {
      render(<PositionDisplay position={mockPosition} />)

      // Position value = quantity * mark price = 0.5 * 46000 = 23000
      expect(screen.getByText(/Value:/)).toBeInTheDocument()
      expect(screen.getByText('$23,000.00')).toBeInTheDocument()
    })

    it('should handle large positions', () => {
      const largePosition = {
        ...mockPosition,
        quantity: 100,
        markPrice: 46000,
      }
      render(<PositionDisplay position={largePosition} />)

      // 100 * 46000 = 4,600,000
      expect(screen.getByText('$4,600,000.00')).toBeInTheDocument()
    })
  })

  describe('side styling', () => {
    it('should style long positions', () => {
      render(<PositionDisplay position={mockPosition} />)

      const sideElement = screen.getByText('LONG')
      expect(sideElement).toHaveClass('text-green-500', 'bg-green-500/10')
    })

    it('should style short positions', () => {
      render(<PositionDisplay position={mockShortPosition} />)

      const sideElement = screen.getByText('SHORT')
      expect(sideElement).toHaveClass('text-red-500', 'bg-red-500/10')
    })
  })

  describe('empty state', () => {
    it('should handle no position gracefully', () => {
      render(<PositionDisplay position={null} />)

      expect(screen.getByTestId('no-position')).toBeInTheDocument()
      expect(screen.getByText('No open position')).toBeInTheDocument()
    })
  })

  describe('formatting', () => {
    it('should format small quantities correctly', () => {
      const smallPosition = {
        ...mockPosition,
        quantity: 0.00012345,
      }
      render(<PositionDisplay position={smallPosition} />)

      expect(screen.getByText('0.00012345')).toBeInTheDocument()
    })

    it('should format prices with appropriate decimals', () => {
      const precisePosition = {
        ...mockPosition,
        entryPrice: 45123.45,
        markPrice: 46234.56,
      }
      render(<PositionDisplay position={precisePosition} />)

      expect(screen.getByText('$45,123.45')).toBeInTheDocument()
      expect(screen.getByText('$46,234.56')).toBeInTheDocument()
    })

    it('should handle zero PnL', () => {
      const breakEvenPosition = {
        ...mockPosition,
        pnl: 0,
        pnlPercent: 0,
      }
      render(<PositionDisplay position={breakEvenPosition} />)

      const pnlElement = screen.getByText('$0.00')
      expect(pnlElement).toHaveClass('text-gray-400')

      const percentElement = screen.getByText('0.00%')
      expect(percentElement).toHaveClass('text-gray-400')
    })
  })

  describe('compact mode', () => {
    it('should render in compact mode', () => {
      render(<PositionDisplay position={mockPosition} compact />)

      expect(screen.getByTestId('position-display')).toHaveClass('py-2')
      expect(screen.queryByText(/Value:/)).not.toBeInTheDocument()
    })

    it('should show essential info in compact mode', () => {
      render(<PositionDisplay position={mockPosition} compact />)

      expect(screen.getByText('BTCUSDT')).toBeInTheDocument()
      expect(screen.getByText('LONG')).toBeInTheDocument()
      expect(screen.getByText('+$500.00')).toBeInTheDocument()
      expect(screen.getByText('+2.22%')).toBeInTheDocument()
    })
  })

  describe('click handlers', () => {
    it('should call onClose when close button clicked', () => {
      const mockOnClose = vi.fn()
      render(<PositionDisplay position={mockPosition} onClose={mockOnClose} />)

      const closeButton = screen.getByTestId('close-position-button')
      closeButton.click()

      expect(mockOnClose).toHaveBeenCalledWith(mockPosition)
    })

    it('should not show close button without handler', () => {
      render(<PositionDisplay position={mockPosition} />)

      expect(screen.queryByTestId('close-position-button')).not.toBeInTheDocument()
    })
  })

  describe('realtime updates', () => {
    it('should update mark price', () => {
      const { rerender } = render(<PositionDisplay position={mockPosition} />)

      expect(screen.getByText('$46,000.00')).toBeInTheDocument()

      const updatedPosition = {
        ...mockPosition,
        markPrice: 47000,
        pnl: 1000,
        pnlPercent: 4.44,
      }

      rerender(<PositionDisplay position={updatedPosition} />)

      expect(screen.getByText('$47,000.00')).toBeInTheDocument()
      expect(screen.getByText('+$1,000.00')).toBeInTheDocument()
    })

    it('should transition from profit to loss', () => {
      const { rerender } = render(<PositionDisplay position={mockPosition} />)

      const pnlElement = screen.getByText('+$500.00')
      expect(pnlElement).toHaveClass('text-green-500')

      const lossPosition = {
        ...mockPosition,
        markPrice: 44000,
        pnl: -100,
        pnlPercent: -2,
      }

      rerender(<PositionDisplay position={lossPosition} />)

      const newPnlElement = screen.getByText('-$100.00')
      expect(newPnlElement).toHaveClass('text-red-500')
    })
  })
})