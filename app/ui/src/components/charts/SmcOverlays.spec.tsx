import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SmcOverlays } from './SmcOverlays'
import type { SmcEvent } from '@/types'
import { getTokens } from '@/utils/getTokens'
import { DEFAULT_TOKENS } from '@/constants/defaultTokens'

vi.mock('@/utils/getTokens', () => ({ getTokens: vi.fn() }))

describe('SmcOverlays', () => {
  const mockSmcEvents: SmcEvent[] = [
    {
      id: 'event-1',
      symbol: 'BTCUSDT',
      type: 'CHOCH',
      direction: 'bullish',
      price: 45100,
      timeframe: '15m',
      timestamp: 1640995260,
    },
    {
      id: 'event-2',
      symbol: 'BTCUSDT',
      type: 'BOS',
      direction: 'bearish',
      price: 44900,
      timeframe: '15m',
      timestamp: 1640995320,
    },
    {
      id: 'event-3',
      symbol: 'BTCUSDT',
      type: 'ORDER_BLOCK',
      direction: 'bullish',
      price: 44800,
      timeframe: '15m',
      timestamp: 1640995380,
    },
    {
      id: 'event-4',
      symbol: 'BTCUSDT',
      type: 'FVG',
      direction: 'bearish',
      price: 45000,
      timeframe: '15m',
      timestamp: 1640995440,
    },
  ]

  const createMockChartRef = () => ({
    current: document.createElement('div'),
  })

  beforeEach(() => {
    vi.mocked(getTokens).mockReturnValue(DEFAULT_TOKENS)
  })

  describe('rendering', () => {
    it('should render overlay container', () => {
      const chartRef = createMockChartRef()
      render(<SmcOverlays events={[]} chartRef={chartRef} />)

      expect(screen.getByTestId('smc-overlays')).toBeInTheDocument()
    })

    it('should have correct styling for overlay container', () => {
      const chartRef = createMockChartRef()
      render(<SmcOverlays events={[]} chartRef={chartRef} />)

      const container = screen.getByTestId('smc-overlays') as HTMLElement
      expect(container.style.position).toBe('absolute')
      expect(container.style.top).toBe('0px')
      expect(container.style.left).toBe('0px')
      expect(container.style.pointerEvents).toBe('none')
    })

    it('should render empty container when no events', () => {
      const chartRef = createMockChartRef()
      render(<SmcOverlays events={[]} chartRef={chartRef} />)

      const container = screen.getByTestId('smc-overlays')
      expect(container.children).toHaveLength(0)
    })
  })

  describe('event overlays', () => {
    it('should create overlay for each event', () => {
      const chartRef = createMockChartRef()
      render(<SmcOverlays events={mockSmcEvents} chartRef={chartRef} />)

      const container = screen.getByTestId('smc-overlays')
      expect(container.children).toHaveLength(mockSmcEvents.length)
    })

    it('should create CHOCH overlay with correct label', () => {
      const chartRef = createMockChartRef()
      const chochEvent = mockSmcEvents.filter(e => e.type === 'CHOCH')
      render(<SmcOverlays events={chochEvent} chartRef={chartRef} />)

      const overlay = screen.getByTestId('smc-overlay-CHOCH')
      expect(overlay).toBeInTheDocument()
      expect(overlay).toHaveTextContent('↑ CHoCH')
    })

    it('should create BOS overlay with correct label', () => {
      const chartRef = createMockChartRef()
      const bosEvent = mockSmcEvents.filter(e => e.type === 'BOS')
      render(<SmcOverlays events={bosEvent} chartRef={chartRef} />)

      const overlay = screen.getByTestId('smc-overlay-BOS')
      expect(overlay).toBeInTheDocument()
      expect(overlay).toHaveTextContent('↓ BoS')
    })

    it('should create ORDER_BLOCK overlay with correct label', () => {
      const chartRef = createMockChartRef()
      const obEvent = mockSmcEvents.filter(e => e.type === 'ORDER_BLOCK')
      render(<SmcOverlays events={obEvent} chartRef={chartRef} />)

      const overlay = screen.getByTestId('smc-overlay-ORDER_BLOCK')
      expect(overlay).toBeInTheDocument()
      expect(overlay).toHaveTextContent('↑ OB')
    })

    it('should create FVG overlay with correct label', () => {
      const chartRef = createMockChartRef()
      const fvgEvent = mockSmcEvents.filter(e => e.type === 'FVG')
      render(<SmcOverlays events={fvgEvent} chartRef={chartRef} />)

      const overlay = screen.getByTestId('smc-overlay-FVG')
      expect(overlay).toBeInTheDocument()
      expect(overlay).toHaveTextContent('↓ FVG')
    })
  })

  describe('event styling', () => {
    it('should apply bullish CHOCH styling', () => {
      const chartRef = createMockChartRef()
      const event: SmcEvent[] = [
        {
          id: 'test-1',
          symbol: 'BTCUSDT',
          type: 'CHOCH',
          direction: 'bullish',
          price: 45000,
          timeframe: '15m',
          timestamp: Date.now(),
        },
      ]
      render(<SmcOverlays events={event} chartRef={chartRef} />)

      const label = screen.getByText('↑ CHoCH') as HTMLElement
      expect(label.style.backgroundColor).toBe(DEFAULT_TOKENS.colors.success[600])
      expect(label.style.color).toBe(DEFAULT_TOKENS.colors.text.inverse)
    })

    it('should apply bearish BOS styling', () => {
      const chartRef = createMockChartRef()
      const event: SmcEvent[] = [
        {
          id: 'test-2',
          symbol: 'BTCUSDT',
          type: 'BOS',
          direction: 'bearish',
          price: 45000,
          timeframe: '15m',
          timestamp: Date.now(),
        },
      ]
      render(<SmcOverlays events={event} chartRef={chartRef} />)

      const label = screen.getByText('↓ BoS') as HTMLElement
      expect(label.style.backgroundColor).toBe(DEFAULT_TOKENS.colors.error[600] || DEFAULT_TOKENS.colors.error[500])
      expect(label.style.color).toBe(DEFAULT_TOKENS.colors.text.inverse)
    })

    it('should apply bullish ORDER_BLOCK styling', () => {
      const chartRef = createMockChartRef()
      const event: SmcEvent[] = [
        {
          id: 'test-3',
          symbol: 'BTCUSDT',
          type: 'ORDER_BLOCK',
          direction: 'bullish',
          price: 45000,
          timeframe: '15m',
          timestamp: Date.now(),
        },
      ]
      render(<SmcOverlays events={event} chartRef={chartRef} />)

      const label = screen.getByText('↑ OB') as HTMLElement
      expect(label.style.backgroundColor).toBeTruthy()
      expect(label.style.color).toBeTruthy()
    })

    it('should apply bearish FVG styling', () => {
      const chartRef = createMockChartRef()
      const event: SmcEvent[] = [
        {
          id: 'test-4',
          symbol: 'BTCUSDT',
          type: 'FVG',
          direction: 'bearish',
          price: 45000,
          timeframe: '15m',
          timestamp: Date.now(),
        },
      ]
      render(<SmcOverlays events={event} chartRef={chartRef} />)

      const label = screen.getByText('↓ FVG') as HTMLElement
      expect(label.style.backgroundColor).toBeTruthy()
      expect(label.style.color).toBeTruthy()
    })
  })

  describe('data attributes', () => {
    it('should set data-event-id attribute', () => {
      const chartRef = createMockChartRef()
      const event: SmcEvent[] = [
        {
          id: 'unique-event-id',
          symbol: 'BTCUSDT',
          type: 'CHOCH',
          direction: 'bullish',
          price: 45000,
          timeframe: '15m',
          timestamp: Date.now(),
        },
      ]
      render(<SmcOverlays events={event} chartRef={chartRef} />)

      const overlay = screen.getByTestId('smc-overlay-CHOCH')
      expect(overlay).toHaveAttribute('data-event-id', 'unique-event-id')
    })
  })

  describe('updates', () => {
    it('should clear previous overlays when events change', () => {
      const chartRef = createMockChartRef()
      const { rerender } = render(<SmcOverlays events={mockSmcEvents} chartRef={chartRef} />)

      const container = screen.getByTestId('smc-overlays')
      expect(container.children).toHaveLength(4)

      const newEvents = mockSmcEvents.slice(0, 2)
      rerender(<SmcOverlays events={newEvents} chartRef={chartRef} />)

      expect(container.children).toHaveLength(2)
    })

    it('should handle empty chartRef', () => {
      const chartRef = { current: null }
      render(<SmcOverlays events={mockSmcEvents} chartRef={chartRef} />)

      const container = screen.getByTestId('smc-overlays')
      expect(container.children).toHaveLength(0)
    })
  })
})
